"""AI Food Scanner: image validation and food-image classification inference.

Two clearly separated responsibilities:

  1. ``validate_image`` — pure-Python structural validation of an uploaded
     image (magic bytes + header parsing for dimensions). This deliberately
     does NOT need Pillow, so the web app keeps its tiny dependency set and
     rejects junk uploads even when the ML stack is not installed.

  2. ``Predictor`` — loads a trained checkpoint ONCE per process and turns
     image bytes into ranked food-class predictions.

Honesty rules enforced here:
  * If no checkpoint exists (or torch is missing) the predictor reports
    ``available: False`` and ``predict`` raises ``ModelUnavailable``.
    It NEVER invents a prediction. There is no random-guess fallback, no
    "demo mode", and no hardcoded answer table.
  * The returned ``confidence`` is the model's own softmax probability. It is
    not fudged, clamped or re-interpreted as certainty.
  * Low-confidence output is surfaced as ``low_confidence: True`` as an
    uncalibrated uncertainty signal. It never selects another model or causes a
    technical fallback; every prediction remains unconfirmed.

The model is a single-label classifier: it reports the one dominant dish in a
photograph. It does not segment a plate into separate dishes, and the API says
so explicitly (see ``SINGLE_LABEL_NOTE``).
"""

from __future__ import annotations

import io
import json
import os
import struct
import threading
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

CLASSES_PATH = PROJECT_DIR / "data" / "food_classes.json"

# The shipped CC0-declared 12-class checkpoint. It remains available only as a
# technical fallback for the scanner's 80-class primary model. Its publisher's
# authority over every underlying photograph is not independently verified; see
# docs/MODEL.md before treating the weight as redistribution-cleared.
DEFAULT_MODEL_PATH = PROJECT_DIR / "models" / "food_classifier_cc0.pt"

# The first CC0 run (7 classes), retained for comparison only. It is not in the
# recognition policy and is never selected by a scan.
PREVIOUS_CC0_MODEL_PATH = PROJECT_DIR / "models" / "food_classifier_cc0_7class.pt"

# Primary scanner checkpoint: the 80-class Indian-food model (224px input).
# NUTRICARE_PRIMARY_MODEL is the preferred deployment override. The older
# NUTRICARE_EXPERIMENTAL_MODEL name remains accepted for deployment compatibility.
# Training-image rights are unresolved: internal experimental use only; do not
# redistribute. See docs/MODEL.md and the model metrics sidecar.
PRIMARY_MODEL_PATH = Path(
    os.environ.get(
        "NUTRICARE_PRIMARY_MODEL",
        os.environ.get(
            "NUTRICARE_EXPERIMENTAL_MODEL",
            str(PROJECT_DIR / "models" / "v2" / "food_classifier_indian_80_224.pt"),
        ),
    )
)
# Compatibility alias for code that only needs the artifact location. It does
# not mean this model is user-selectable in the scan API.
EXPERIMENTAL_MODEL_PATH = PRIMARY_MODEL_PATH

# The legacy 20-class checkpoint is NOT shipped. Its training images have no
# licence anywhere in the chain (see docs/LICENSING_AUDIT.md), so it was removed
# from this repository and from its git history rather than merely being made
# opt-in. This path is retained only so old local deployments fail loudly and
# explain themselves instead of silently loading a file that is no longer here.
REMOVED_UNLICENSED_MODEL_PATH = PROJECT_DIR / "models" / "food_classifier.pt"

# Uploads: generous enough for a phone photo, small enough to stay safe.
MAX_UPLOAD_BYTES = int(os.environ.get("NUTRICARE_MAX_UPLOAD_BYTES", 8 * 1024 * 1024))
MAX_DIMENSION = 8000          # reject absurd pixel counts before decoding
MIN_DIMENSION = 16            # reject 1-px noise images

# Retained as an uncertainty signal for existing clients. It has no documented
# calibration or rejection evaluation and must never choose a model or trigger
# the 12-class technical fallback. Every scanner prediction is unconfirmed.
LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("NUTRICARE_LOW_CONFIDENCE", 0.40))

CONFIDENCE_NOTE = (
    "Confidence is the selected model's raw softmax output. It is not calibrated "
    "as a probability of correctness and every food prediction remains unconfirmed."
)

SINGLE_LABEL_NOTE = (
    "The recognition model is a single-label classifier: it identifies the one "
    "dominant dish in a photograph. It cannot separate several dishes on the "
    "same plate — log those one at a time."
)

ESTIMATE_NOTE = (
    "Values are estimates, not laboratory measurements. A photograph cannot "
    "reveal cooking oil, recipe or exact weight, so intake can differ "
    "substantially from these numbers."
)

PORTION_NOTE = (
    "Weight cannot be measured from a photograph. The default serving is the "
    "dataset's reference serving; adjust the grams to match what you actually ate."
)


class ImageError(ValueError):
    """Uploaded bytes are not an acceptable image."""


class ModelUnavailable(RuntimeError):
    """No usable trained checkpoint / ML runtime is present."""


# --------------------------------------------------------------- taxonomy
def load_classes() -> dict:
    """Canonical class taxonomy, keyed by slug. Cached per process."""
    return json.loads(CLASSES_PATH.read_text(encoding="utf-8"))


def class_list() -> list[dict]:
    return load_classes()["classes"]


def class_by_slug() -> dict[str, dict]:
    return {c["slug"]: c for c in class_list()}


# --------------------------------------------------------------- validation
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)

ALLOWED_FORMATS = ("jpeg", "png", "webp")


def sniff_format(data: bytes) -> str | None:
    """Identify the container from its magic bytes (never from the filename)."""
    for signature, name in _SIGNATURES:
        if data.startswith(signature):
            return name
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _jpeg_size(data: bytes) -> tuple[int, int]:
    """Walk JPEG segments to the first Start-Of-Frame marker."""
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if i + 2 > n:
            break
        length = struct.unpack(">H", data[i:i + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 7 > n:
                break
            height, width = struct.unpack(">HH", data[i + 3:i + 7])
            return width, height
        i += length
    raise ImageError("This JPEG is corrupted or has no readable dimensions.")


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ImageError("This PNG is corrupted (missing IHDR header).")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _webp_size(data: bytes) -> tuple[int, int]:
    if len(data) < 30:
        raise ImageError("This WebP file is truncated.")
    kind = data[12:16]
    if kind == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if kind == b"VP8L":
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    if kind == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    raise ImageError("Unrecognised WebP variant.")


_DIMENSION_READERS = {"jpeg": _jpeg_size, "png": _png_size, "webp": _webp_size}


def validate_image(data: bytes | None) -> dict:
    """Validate raw upload bytes. Returns metadata or raises ``ImageError``.

    Checks performed: non-empty, size ceiling, real image container (magic
    bytes, so a renamed .exe is rejected), parseable header, sane dimensions.
    """
    if not data:
        raise ImageError("No image data received.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError(
            f"Image is too large ({len(data) // 1024} KB). "
            f"Maximum is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    fmt = sniff_format(data)
    if fmt is None:
        raise ImageError("Unsupported file type. Please upload a JPG, PNG or WebP image.")
    if fmt not in ALLOWED_FORMATS:
        raise ImageError(f"{fmt.upper()} images are not supported. Use JPG, PNG or WebP.")
    try:
        width, height = _DIMENSION_READERS[fmt](data)
    except ImageError:
        raise
    except Exception:  # malformed header of any kind
        raise ImageError("This image is corrupted and could not be read.")
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageError("Image is too small to analyse (minimum 16×16 pixels).")
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ImageError(f"Image dimensions are too large (maximum {MAX_DIMENSION}px).")
    return {"format": fmt, "width": width, "height": height, "bytes": len(data)}


def safe_filename(name: str | None) -> str:
    """Basename only, safe charset, always ends up inside our own temp dir."""
    base = os.path.basename(str(name or "upload"))
    cleaned = "".join(c for c in base if c.isalnum() or c in "._-")[:64]
    return cleaned or "upload"


# --------------------------------------------------------------- prediction
class Predictor:
    """Wraps a trained torch checkpoint. One instance per process.

    The model is loaded lazily on first prediction (so ``import`` is cheap and
    the app starts even without ML dependencies installed) and then cached.
    """

    def __init__(self, model_path: str | Path | None = None):
        self.model_path = Path(
            model_path or os.environ.get("NUTRICARE_MODEL") or DEFAULT_MODEL_PATH)
        self._lock = threading.Lock()
        self._model = None
        self._classes: list[dict] = []
        self._transform = None
        self._meta: dict = {}
        self._load_error: str | None = None
        self._attempted = False
        self._output_count: int | None = None

    # -- status ---------------------------------------------------------
    @property
    def available_path(self) -> bool:
        return self.model_path.is_file()

    def _output_class_count(self) -> int | None:
        """Number of output classes of THIS checkpoint (never the taxonomy size).

        Resolution order: already-loaded classes; the metrics sidecar written
        beside the checkpoint; finally the checkpoint file itself (metadata
        read, model not built). Returns None when the count cannot be
        established without loading — status then reports None rather than
        inventing a number.
        """
        if self._classes:
            return len(self._classes)
        if self._output_count is not None:
            return self._output_count
        count = None
        sidecar = self.model_path.with_suffix(".metrics.json")
        if sidecar.is_file():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                for key in ("classes", "class_names", "num_classes"):
                    value = meta.get(key)
                    if isinstance(value, int):
                        count = value
                        break
                    if isinstance(value, list):
                        count = len(value)
                        break
            except Exception:
                count = None
        if count is None and self.available_path:
            try:
                import torch  # noqa: PLC0415  (optional dependency)

                checkpoint = torch.load(self.model_path, map_location="cpu",
                                        weights_only=False)
                classes = checkpoint.get("classes") or checkpoint.get("class_names")
                if classes is not None:
                    count = len(classes)
            except Exception:
                count = None
        self._output_count = count
        return count

    def _read_sidecar(self) -> dict:
        """Training metadata next to the checkpoint, without importing torch.

        The trainer writes <name>.metrics.json beside <name>.pt, so the UI can
        report the model's REAL measured accuracy before the first prediction
        (and even on a machine with no ML stack installed).
        """
        sidecar = self.model_path.with_suffix(".metrics.json")
        if not sidecar.is_file():
            return {}
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            return {}
        # The CC0 sidecars use ``test_metrics`` while the 80-class training
        # sidecar uses ``results``. Both are artifact metadata, not a claim
        # that raw confidence is calibrated or that the score generalises.
        test = meta.get("test_metrics") or meta.get("results") or {}
        return {
            "architecture": meta.get("architecture"),
            "input_size": meta.get("image_size"),
            "trained_at": meta.get("generated_at") or meta.get("generated_utc"),
            "test_accuracy": test.get("accuracy", test.get("test_accuracy")),
            "test_macro_f1": test.get("macro_f1"),
            "test_support": test.get("support", test.get("test_support")),
            "classes": meta.get("classes"),
            "trained_on": (meta.get("dataset") or {}).get("sources"),
        }

    def status(self) -> dict:
        """Non-throwing description used by /api/vision/status and the UI."""
        info = {
            "model_path": str(self.model_path),
            "model_present": self.available_path,
            "loaded": self._model is not None,
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "classes": self._output_class_count(),
            "single_label": True,
            "note": SINGLE_LABEL_NOTE,
        }
        meta = dict(self._read_sidecar())
        if self._meta:
            meta.update({k: v for k, v in self._meta.items() if v is not None})
        if meta:
            info.update({k: v for k, v in meta.items() if v is not None})
        # The checkpoint's own output count wins over anything the sidecar
        # or taxonomy might suggest; never report the taxonomy size (137)
        # as the model's output size.
        count = self._output_class_count()
        if count is not None:
            info["classes"] = count
        elif not isinstance(info.get("classes"), int):
            info["classes"] = None
        if self.available_path and not self._model and not self._attempted:
            info["detail"] = "Checkpoint found but not loaded yet; it loads on first use."
        if self._load_error:
            info["detail"] = self._load_error
        if not self.available_path:
            info["detail"] = (
                "No trained checkpoint is installed, so photo recognition is "
                "switched off. The app will not guess — see docs/MODEL.md for "
                "how to train and install one. Manual logging still works.")
        return info

    # -- loading --------------------------------------------------------
    def _load(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            self._attempted = True
            if not self.available_path:
                self._load_error = (f"No model checkpoint at {self.model_path}.")
                raise ModelUnavailable(self._load_error)
            try:
                import torch  # noqa: PLC0415  (optional dependency)
                from torchvision import transforms  # noqa: PLC0415
            except Exception as exc:  # pragma: no cover - env dependent
                self._load_error = (
                    "The ML runtime (torch/torchvision) is not installed in this "
                    f"environment, so the trained model cannot run ({exc}).")
                raise ModelUnavailable(self._load_error) from exc
            try:
                checkpoint = torch.load(self.model_path, map_location="cpu",
                                        weights_only=False)
            except Exception as exc:
                self._load_error = f"Checkpoint could not be read: {exc}"
                raise ModelUnavailable(self._load_error) from exc

            architecture = checkpoint.get("architecture", "mobilenet_v3_small")
            num_classes = len(checkpoint["classes"])
            model = build_model(architecture, num_classes, pretrained=False)
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()

            self._model = model
            self._meta = {k: checkpoint.get(k) for k in
                          ("architecture", "trained_at", "input_size", "test_accuracy")}
            input_size = int(checkpoint.get("input_size", 224))
            mean = checkpoint.get("normalise_mean", [0.485, 0.456, 0.406])
            std = checkpoint.get("normalise_std", [0.229, 0.224, 0.225])
            self._transform = transforms.Compose([
                transforms.Resize(int(input_size * 256 / 224)),
                transforms.CenterCrop(input_size),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean, std=std),
            ])
            index = {c["slug"]: c for c in class_list()}
            self._classes = [index.get(slug, {"slug": slug, "label": slug,
                                              "group": "unknown"})
                             for slug in checkpoint["classes"]]

    # -- inference ------------------------------------------------------
    def predict(self, image_bytes: bytes, top_k: int = 3) -> dict:
        """Ranked predictions for one photograph.

        Raises ``ImageError`` for bad input and ``ModelUnavailable`` when no
        model is installed. Both are handled by the API layer as explicit,
        non-fabricated failures.
        """
        meta = validate_image(image_bytes)
        self._load()

        import torch  # noqa: PLC0415
        from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except UnidentifiedImageError as exc:
            raise ImageError("This file could not be decoded as an image.") from exc
        except Exception as exc:
            raise ImageError(f"This image could not be decoded ({exc}).") from exc

        if image.mode != "RGB":
            image = image.convert("RGB")
        tensor = self._transform(image).unsqueeze(0)

        with torch.no_grad():
            logits = self._model(tensor)[0]
            probabilities = torch.softmax(logits, dim=0).tolist()

        ranked = sorted(zip(self._classes, probabilities),
                        key=lambda pair: -pair[1])[:max(1, min(top_k, 5))]
        predictions = [{
            "slug": cls["slug"],
            "label": cls.get("label", cls["slug"]),
            "group": cls.get("group", "unknown"),
            "confidence": round(float(prob), 4),
            "confidence_pct": round(float(prob) * 100, 1),
        } for cls, prob in ranked]

        top = predictions[0]
        return {
            "predictions": predictions,
            "top": top,
            "low_confidence": top["confidence"] < LOW_CONFIDENCE_THRESHOLD,
            "threshold": LOW_CONFIDENCE_THRESHOLD,
            "image": {k: meta[k] for k in ("format", "width", "height")},
            "single_label": True,
            "note": SINGLE_LABEL_NOTE,
        }


def build_model(architecture: str, num_classes: int, pretrained: bool = False):
    """Construct the classifier. Shared by training and inference so the two
    can never drift apart."""
    import torch.nn as nn  # noqa: PLC0415
    import torchvision.models as models  # noqa: PLC0415

    if architecture == "mobilenet_v3_small":
        weights = models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        model = models.mobilenet_v3_small(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
    elif architecture == "mobilenet_v3_large":
        weights = models.MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
        model = models.mobilenet_v3_large(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
    elif architecture == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
    elif architecture == "resnet18":
        weights = models.ResNet18_Weights.DEFAULT if pretrained else None
        model = models.resnet18(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:
        raise ValueError(f"Unknown architecture {architecture!r}")
    return model



# -------------------------------------------------- primary/fallback policy
#
# The active scan path is deliberately one-way: it runs the 80-class model and
# returns that model's ranking. It invokes the 12-class model only after a
# genuine *technical* primary failure. It never compares softmax outputs, asks
# the two checkpoints to agree, or changes model because confidence is low.

PRIMARY_MODEL_NAME = "primary_80_class"
FALLBACK_MODEL_NAME = "technical_fallback_12_class"

TECHNICAL_FALLBACK_CONDITIONS = (
    "the 80-class primary checkpoint is missing",
    "the 80-class primary checkpoint cannot be read",
    "the 80-class primary model cannot initialise",
    "the 80-class primary model raises an inference exception",
)


def configured_primary_model_path() -> Path:
    """Resolve the primary path after environment loading.

    This permits ``.env`` loading before app creation as well as ordinary process
    environment configuration. Without an override, a test/deployment may still
    explicitly replace ``PRIMARY_MODEL_PATH`` before resetting the predictor.
    """
    override = os.environ.get("NUTRICARE_PRIMARY_MODEL") or \
        os.environ.get("NUTRICARE_EXPERIMENTAL_MODEL")
    return Path(override) if override else PRIMARY_MODEL_PATH


def configured_fallback_model_path() -> Path:
    """Resolve the 12-class fallback path without changing legacy deployment.

    ``NUTRICARE_FALLBACK_MODEL`` is the explicit policy setting. The old
    ``NUTRICARE_MODEL`` setting remains a compatible override for the 12-class
    fallback only; it cannot select the normal scanner model.
    """
    override = os.environ.get("NUTRICARE_FALLBACK_MODEL") or \
        os.environ.get("NUTRICARE_MODEL")
    return Path(override) if override else DEFAULT_MODEL_PATH


# --------------------------------------------------------------- singletons
_PREDICTORS: dict[str, Predictor] = {}
_PREDICTOR_LOCK = threading.Lock()


def _predictor_name(model_name: str) -> str:
    """Resolve internal compatibility aliases, never a scan-time selection."""
    aliases = {
        "primary": PRIMARY_MODEL_NAME,
        "experimental": PRIMARY_MODEL_NAME,
        PRIMARY_MODEL_NAME: PRIMARY_MODEL_NAME,
        # The historical no-argument/default helper is retained for non-scan
        # callers (including the pre-existing manual picker), where it reports
        # the 12-class checkpoint. /predict never uses this alias.
        "default": FALLBACK_MODEL_NAME,
        "fallback": FALLBACK_MODEL_NAME,
        FALLBACK_MODEL_NAME: FALLBACK_MODEL_NAME,
    }
    try:
        return aliases[model_name]
    except KeyError as exc:
        raise ValueError(f"Unknown model name: {model_name!r}") from exc


def get_predictor(model_name: str = "default") -> Predictor:
    """Return a lazily created checkpoint predictor.

    This helper accepts historical aliases to avoid breaking non-scan callers.
    It is not a model-selection interface: normal scanner inference always uses
    :func:`recognize`, which explicitly calls the 80-class primary first.
    """
    name = _predictor_name(model_name)
    if name not in _PREDICTORS:
        with _PREDICTOR_LOCK:
            if name not in _PREDICTORS:
                path = configured_primary_model_path() if name == PRIMARY_MODEL_NAME \
                    else configured_fallback_model_path()
                _PREDICTORS[name] = Predictor(path)
    return _PREDICTORS[name]


def get_primary_predictor() -> Predictor:
    """The 80-class model used for every normal scan."""
    return get_predictor(PRIMARY_MODEL_NAME)


def get_fallback_predictor() -> Predictor:
    """The 12-class checkpoint reserved for technical fallback."""
    return get_predictor(FALLBACK_MODEL_NAME)


def reset_predictor(model_name: str | None = None) -> None:
    """Drop cached predictor(s), primarily for tests and maintenance."""
    global _PREDICTORS
    with _PREDICTOR_LOCK:
        if model_name is None:
            _PREDICTORS.clear()
        else:
            _PREDICTORS.pop(_predictor_name(model_name), None)


def model_status(model_name: str = "default") -> dict:
    """Non-throwing status for one checkpoint (including compatibility aliases)."""
    return get_predictor(model_name).status()


def get_available_models() -> list[dict]:
    """Describe the fixed scanner policy without offering a model selector."""
    fallback_path = configured_fallback_model_path()
    return [
        {
            "name": PRIMARY_MODEL_NAME,
            "role": "primary",
            "description": "80-class Indian-food recognition model (224px input)",
            "path": str(configured_primary_model_path()),
            "present": configured_primary_model_path().is_file(),
            "classes": 80,
            "selection_allowed": False,
            "licence": "UNRESOLVED — internal experimental use only; do not redistribute.",
            "note": (
                "Normal scans run this model only. Its training-image rights are "
                "unresolved and its held-out metrics do not establish real-world accuracy."
            ),
        },
        {
            "name": FALLBACK_MODEL_NAME,
            "role": "technical_fallback",
            "description": "12-class CC0-declared checkpoint",
            "path": str(fallback_path),
            "present": fallback_path.is_file(),
            "classes": 12,
            "selection_allowed": False,
            "note": (
                "Used only after a technical failure of the 80-class primary model; "
                "never used for low confidence."
            ),
        },
    ]


def recognition_status() -> dict:
    """Status and policy metadata for the scanner; loading remains lazy."""
    primary = model_status(PRIMARY_MODEL_NAME)
    fallback = model_status(FALLBACK_MODEL_NAME)
    return {
        "primary": primary,
        "fallback": fallback,
        "policy": {
            "primary_model": PRIMARY_MODEL_NAME,
            "technical_fallback_model": FALLBACK_MODEL_NAME,
            "fallback_conditions": list(TECHNICAL_FALLBACK_CONDITIONS),
            "low_confidence_triggers_fallback": False,
            "prediction_unconfirmed": True,
            "confidence_calibrated": False,
        },
    }


def _technical_failure_kind(error: Exception) -> str:
    """Stable, non-sensitive reason code for a fallback response."""
    return "primary_unavailable" if isinstance(error, ModelUnavailable) \
        else "primary_inference_error"


def _annotate_recognition(result: dict, *, served_by: str,
                          primary_error: Exception | None = None) -> dict:
    """Add policy metadata without changing the Predictor ranking contract."""
    annotated = dict(result)
    fallback_used = served_by == FALLBACK_MODEL_NAME
    annotated["model"] = served_by
    annotated["recognition"] = {
        "served_by": served_by,
        "primary_model": PRIMARY_MODEL_NAME,
        "fallback_used": fallback_used,
        "fallback_reason": (
            _technical_failure_kind(primary_error) if primary_error else None
        ),
        "prediction_unconfirmed": True,
        "confidence_calibrated": False,
        "confidence_note": CONFIDENCE_NOTE,
        "low_confidence_triggers_fallback": False,
    }
    return annotated


def recognize(image_bytes: bytes, top_k: int = 3) -> dict:
    """Run the fixed 80-class-primary, 12-class-technical-fallback policy.

    Fallback is intentionally limited to primary checkpoint absence/read errors,
    primary initialisation errors, and primary inference exceptions. An
    :class:`ImageError` is an upload problem, not a model failure, so it is
    returned directly and never causes a second inference. Likewise, an ordinary
    low-confidence primary prediction is returned unchanged and never invokes
    the fallback.

    If both checkpoints fail technically, this raises :class:`ModelUnavailable`
    so the API can return its existing explicit 503 recognition-unavailable
    response. No prediction is fabricated or combined.
    """
    try:
        primary_result = get_primary_predictor().predict(image_bytes, top_k=top_k)
    except ImageError:
        raise
    except Exception as primary_error:
        try:
            fallback_result = get_fallback_predictor().predict(
                image_bytes, top_k=top_k)
        except ImageError:
            raise
        except Exception as fallback_error:
            raise ModelUnavailable(
                "Photo recognition is unavailable because the 80-class primary "
                "model and the 12-class technical fallback both failed."
            ) from fallback_error
        return _annotate_recognition(
            fallback_result,
            served_by=FALLBACK_MODEL_NAME,
            primary_error=primary_error,
        )
    return _annotate_recognition(primary_result, served_by=PRIMARY_MODEL_NAME)
