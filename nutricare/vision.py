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
  * Low-confidence output is surfaced as ``low_confidence: True`` so callers
    must ask the user to pick a food manually.

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

# Which checkpoint is installed by default.
#
# The default is `food_classifier_cc0.pt`, trained only on a dataset whose
# publisher declares CC0 1.0. That declaration is documented; the publisher's
# authority over every underlying photograph is NOT independently verified. See
# docs/MODEL.md §10.6 before treating these weights as safe to redistribute. The older 20-class `food_classifier.pt` is more
# capable but its training images carry no licence at all, so it must not be the
# one that ships (see docs/LICENSING_AUDIT.md and docs/COVERAGE.md).
#
# The 20-class checkpoint is deliberately NOT in this repository: its training
# data has no licence, so it cannot be distributed. See docs/LICENSING_AUDIT.md.
# To use it locally you must obtain it yourself and point NUTRICARE_MODEL at it.
DEFAULT_MODEL_PATH = PROJECT_DIR / "models" / "food_classifier_cc0.pt"

# The first CC0 run (7 classes), kept for comparison. Not the default.
PREVIOUS_CC0_MODEL_PATH = PROJECT_DIR / "models" / "food_classifier_cc0_7class.pt"

# Experimental 80-class Indian-food model (224x224 input resolution).
# The checkpoint lives INSIDE the repository so a fresh clone works anywhere
# (including Windows); NUTRICARE_EXPERIMENTAL_MODEL overrides the location.
# Measured performance (leakage-cleaned held-out test, 631 same-dataset
# photographs; evaluation/stage_a_clean_baseline.json): Top-1 56.9%,
# macro-F1 0.549 — EXPERIMENTAL ONLY, not production-ready, and NOT a claim
# about real-world photographs. Its training images have no verified licence
# (see Stage B licensing assessment in evaluation/stage_b/STAGE_B_PREPARATION.md).
# Must NOT replace the 12-class CC0 default model.
EXPERIMENTAL_MODEL_PATH = Path(
    os.environ.get(
        "NUTRICARE_EXPERIMENTAL_MODEL",
        str(PROJECT_DIR / "models" / "v2" / "food_classifier_indian_80_224.pt"),
    )
)

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

# Below this probability the UI must not present the answer as a definite food.
LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("NUTRICARE_LOW_CONFIDENCE", 0.40))

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
        test = meta.get("test_metrics") or {}
        return {
            "architecture": meta.get("architecture"),
            "input_size": meta.get("image_size"),
            "trained_at": meta.get("generated_at"),
            "test_accuracy": test.get("accuracy"),
            "test_macro_f1": test.get("macro_f1"),
            "test_support": test.get("support"),
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



# --------------------------------------------------------------- fallback

# The 35-class Indian-food model trained on a curated dataset
# (35 classes, 6,975 images, test accuracy 83.7%).
# Kept beside the 12-class CC0 model so the old model remains a fallback.
# NOTE: the training dataset's licensing conflict (CC0 vs CC BY, unverified
# provenance) remains unresolved — this model is experimental only and must
# NOT become the production default.
INDIAN_MODEL_PATH = PROJECT_DIR / "models" / "indian_food_v1.pt"
INDIAN_MODEL_METRICS = PROJECT_DIR / "models" / "indian_food_v1.metrics.json"


class FallbackPredictor:
    """Tries the primary (Indian-food) checkpoint, falls back to the 12-class CC0 model.

    Never fabricates a prediction: if neither checkpoint is available, every
    predict() call raises ModelUnavailable. The status() method reports which
    model is actually serving so the UI can be honest about coverage.
    """

    def __init__(self, primary_path: Path, fallback_path: Path):
        self.primary_path = primary_path
        self.fallback_path = fallback_path
        self._primary: Predictor | None = None
        self._fallback: Predictor | None = None
        self._serving: str | None = None
        self._lock = threading.Lock()

    def _resolve(self) -> Predictor:
        with self._lock:
            if self._serving is not None:
                return self._primary if self._serving == "primary" else self._fallback  # type: ignore[return-value]
            if self.primary_path.is_file():
                try:
                    self._primary = Predictor(self.primary_path)
                    self._primary._load()
                    self._serving = "primary"
                    return self._primary
                except Exception:
                    self._primary = None
            if self.fallback_path.is_file():
                try:
                    self._fallback = Predictor(self.fallback_path)
                    self._fallback._load()
                    self._serving = "fallback"
                    return self._fallback
                except Exception:
                    self._fallback = None
            raise ModelUnavailable(
                f"No usable checkpoint at {self.primary_path} or {self.fallback_path}."
            )

    @property
    def serving(self) -> str | None:
        return self._serving

    @property
    def primary_present(self) -> bool:
        return self.primary_path.is_file()

    @property
    def fallback_present(self) -> bool:
        return self.fallback_path.is_file()

    def status(self) -> dict:
        """Report model status without loading any checkpoint.

        Deliberately does *not* call ``_resolve()``: status must be a cheap,
        side-effect-free probe. Loading the model happens lazily on first
        ``predict()``. We report which model *would* serve based on file
        existence, plus any metrics sidecar that is already on disk.
        """
        serving = None
        if self.primary_path.is_file():
            serving = "primary"
        elif self.fallback_path.is_file():
            serving = "fallback"
        info = {
            "model_path": str(
                self.primary_path if serving == "primary" else self.fallback_path
            ),
            "serving": serving,
            "primary_present": self.primary_present,
            "fallback_present": self.fallback_present,
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "single_label": True,
            "note": SINGLE_LABEL_NOTE,
        }
        # Attach metrics from the sidecar JSON if present (no torch needed).
        sidecar = (
            INDIAN_MODEL_METRICS
            if serving == "primary"
            else DEFAULT_MODEL_PATH.with_suffix(".metrics.json")
        )
        if sidecar.is_file():
            try:
                side = json.loads(sidecar.read_text(encoding="utf-8"))
                test = side.get("test_metrics") or {}
                info["test_accuracy"] = test.get("accuracy")
                info["test_macro_f1"] = test.get("macro_f1")
                info["test_support"] = test.get("support")
                info["classes"] = side.get("classes")
                info["dataset"] = side.get("dataset")
            except Exception:
                pass
        return info

    def predict(self, image_bytes: bytes, top_k: int = 3) -> dict:
        model = self._resolve()
        return model.predict(image_bytes, top_k=top_k)


# --------------------------------------------------------------- singleton
_PREDICTORS: dict[str, Predictor | FallbackPredictor] = {}
_PREDICTOR_LOCK = threading.Lock()


def _create_default_predictor() -> Predictor | FallbackPredictor:
    """Build the default production predictor (Indian model -> 12-class CC0 fallback).

    Respects the NUTRICARE_MODEL environment variable so tests can point the
    default model at an absent checkpoint.
    """
    if INDIAN_MODEL_PATH.is_file():
        return FallbackPredictor(INDIAN_MODEL_PATH, DEFAULT_MODEL_PATH)
    return Predictor()  # no args -> uses NUTRICARE_MODEL env or DEFAULT_MODEL_PATH


def _create_experimental_predictor() -> Predictor:
    """Build the experimental 80-class predictor (224x224 input).

    Loaded only when explicitly requested. Never becomes the default.
    Construction never raises: a missing/invalid checkpoint is reported
    gracefully by ``status()`` and surfaces as ``ModelUnavailable`` (503)
    only when a prediction is actually attempted.
    """
    return Predictor(EXPERIMENTAL_MODEL_PATH)


def get_predictor(model_name: str = "default") -> Predictor | FallbackPredictor:
    """Return the named predictor, loading it lazily on first use.

    ``model_name`` is one of:
      * ``"default"`` — the production default (12-class CC0 or Indian fallback)
      * ``"experimental"`` — the 80-class Indian-food model (224x224)

    Unknown names raise ``ValueError``. The caller is responsible for handling
    ``ModelUnavailable`` when a checkpoint is missing.
    """
    if model_name not in ("default", "experimental"):
        raise ValueError(f"Unknown model name: {model_name!r}")

    global _PREDICTORS
    if model_name not in _PREDICTORS:
        with _PREDICTOR_LOCK:
            if model_name not in _PREDICTORS:
                if model_name == "default":
                    _PREDICTORS[model_name] = _create_default_predictor()
                else:
                    _PREDICTORS[model_name] = _create_experimental_predictor()
    return _PREDICTORS[model_name]


def get_available_models() -> list[dict]:
    """Report status of all available models without loading any checkpoint.

    Each entry describes whether the checkpoint file is present and whether
    the model is experimental. Used by the UI to show an honest model selector.
    """
    default_path = INDIAN_MODEL_PATH if INDIAN_MODEL_PATH.is_file() else DEFAULT_MODEL_PATH
    default_desc = ("Default production model (Indian-food model, 12-class CC0 fallback)"
                    if INDIAN_MODEL_PATH.is_file() else
                    "Default production model (12-class CC0)")
    models = [
        {
            "name": "default",
            "description": default_desc,
            "path": str(default_path),
            "present": default_path.is_file(),
            "experimental": False,
            "note": "Production default. Never replaced by the experimental model.",
        },
        {
            "name": "experimental",
            "description": "Experimental 80-class Indian-food model (224x224 input)",
            "path": str(EXPERIMENTAL_MODEL_PATH),
            "present": EXPERIMENTAL_MODEL_PATH.is_file(),
            "experimental": True,
            "note": "Experimental only — not production-validated. Measured Top-1 56.9% / "
                    "macro-F1 0.549 on a leakage-cleaned held-out split of the SAME dataset "
                    "(631 photographs; evaluation/stage_a_clean_baseline.json), not on "
                    "real-world photographs. Training-image licence unresolved; internal use only.",
        },
    ]
    return models


def reset_predictor(model_name: str | None = None) -> None:
    """Drop cached predictor(s).

    When ``model_name`` is None, all cached predictors are dropped.
    Used by tests and after installing a checkpoint.
    """
    global _PREDICTORS
    with _PREDICTOR_LOCK:
        if model_name is None:
            _PREDICTORS.clear()
        else:
            _PREDICTORS.pop(model_name, None)


def model_status(model_name: str = "default") -> dict:
    """Non-throwing status for the named model."""
    return get_predictor(model_name).status()


# --------------------------------------------------------------- dual-model scan
#
# Every Scan a Meal analysis runs BOTH installed models on the same image
# (the 12-class production model and the 80-class experimental model) and
# combines their answers conservatively. The user never selects a model.
#
# Why the combination is NOT "pick the higher confidence": the two models'
# softmax outputs are uncalibrated and come from different training runs, so
# a 0.9 from one is not evidence against a 0.6 from the other. Raw scores are
# therefore never compared across models. Each model is judged only against
# its own low-confidence threshold, and cross-model evidence is structural:
#
#   1. agreement               both top-1 predictions are the same canonical
#                              food (see canonical_food_key) -> accept it.
#   2. cross_model_support     one model's top-1 appears in the other model's
#                              ranked list -> accept the supported top-1.
#                              (If EACH top-1 appears in the other's list the
#                              support is mutual and symmetric — that is rule
#                              4, unresolved, not a win for either model.)
#   3. single_model_confident  exactly one model's top-1 clears its own
#                              threshold -> accept that one.
#   4. disagreement_unresolved anything else -> do not invent certainty:
#                              flag uncertain / needs user confirmation, with
#                              a provisional top-1 (the production model's,
#                              unless only the other prediction resolves to a
#                              documented nutrition entry — coverage is a
#                              tie-break only, never visual evidence).
#
# If exactly one model is unavailable/failing, the other's prediction is used
# (rule "single_model_fallback") with its own low-confidence flag preserved.
# If both fail, ModelUnavailable is raised and the API keeps its existing
# 503 "recognition switched off" behaviour — never a fabricated food.

DUAL_MODEL_STRATEGY = (
    "Both models see the same image. Raw confidence scores are never "
    "compared across models (uncalibrated softmax). Selection rules, in "
    "order: canonical agreement; cross-model top-k support; single model "
    "clearing its own low-confidence threshold; otherwise unresolved "
    "disagreement flagged for user confirmation."
)


# Alias pairs that must NOT be treated as the same dish even though the
# taxonomy cross-lists them: ``biryani`` is the generic dish (vegetable,
# mutton, egg, chicken, …) while ``chicken_biryani`` is one specific kind.
# The taxonomy's biryani entry itself only maps nutrition to Chicken
# biryani as a recipe-derived approximation, so calling the pair
# "agreement" would overstate the evidence. They stay distinct canonical
# foods and can only support each other through the weaker cross-model
# top-k rule, never as identical labels.
_NON_EQUIVALENT_ALIAS_PAIRS = {
    frozenset({"biryani", "chicken_biryani"}),
}


def canonical_food_key(slug: str) -> str:
    """Canonical food key for comparing predictions across models.

    The two checkpoints use different class names for a few identical dishes
    (12-class ``chole`` vs 80-class ``chana_masala``). The taxonomy records
    this through alias lists: an entry naming another entry's slug as an
    alias marks the pair as the same dish. Union-find over those alias edges
    yields the equivalence classes (currently {cham_cham, chomchom},
    {chana_masala, chole}, {chapati, roti} — each verified as genuinely
    interchangeable labels for one dish); the key is the alphabetically
    first slug of the class. Pairs in ``_NON_EQUIVALENT_ALIAS_PAIRS``
    (biryani / chicken_biryani: generic vs specific) are deliberately kept
    separate. Dishes that merely share a dataset nutrition entry through
    approximation (e.g. kheer / phirni) have no alias edge and also stay
    distinct — nutrition must never relabel a dish. Unknown slugs are
    their own key.
    """
    entries = class_list()
    slugs = {c["slug"] for c in entries}
    if slug not in slugs:
        return slug
    parent = {s: s for s in slugs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def norm(alias: str) -> str:
        return alias.lower().replace(" ", "_").replace("-", "_")

    for entry in entries:
        for alias in entry.get("aliases", []):
            other = norm(alias)
            if other in slugs and other != entry["slug"]:
                if frozenset({entry["slug"], other}) in \
                        _NON_EQUIVALENT_ALIAS_PAIRS:
                    continue  # related dishes, not interchangeable labels
                ra, rb = find(entry["slug"]), find(other)
                if ra != rb:
                    parent[rb] = ra
    members = [s for s in slugs if find(s) == find(slug)]
    return min(members)


def _provisional_model(d_raw: dict, e_raw: dict) -> str:
    """Provisional top-1 source for an unresolved disagreement.

    Production model by default; nutrition resolvability breaks the tie
    only when exactly one side can be priced from the documented dataset.
    The result is always flagged uncertain — this never decides the food.
    """
    if _nutrition_resolvable(d_raw["slug"]) or \
            not _nutrition_resolvable(e_raw["slug"]):
        return "default"
    return "experimental"


def _model_confident(result: dict) -> bool:
    """Whether a model's OWN top-1 clears its OWN threshold (never compared
    against the other model's score)."""
    if not result or not result.get("predictions"):
        return False
    if "low_confidence" in result:
        return not result["low_confidence"]
    threshold = result.get("threshold", LOW_CONFIDENCE_THRESHOLD)
    return result["predictions"][0]["confidence"] >= threshold


def _nutrition_resolvable(slug: str) -> bool:
    """Whether the taxonomy maps this slug to a documented dataset food.

    Used only as a tie-break between otherwise equally (un)supported
    disagreeing predictions — database coverage is not visual evidence.
    """
    entry = class_by_slug().get(slug) or {}
    return bool(entry.get("food"))


def combine_model_predictions(default_result: dict | None,
                              experimental_result: dict | None,
                              default_error: str | None = None,
                              experimental_error: str | None = None) -> dict:
    """Combine the two models' results for one image into a single answer.

    Either result may be None when that model was unavailable (the matching
    error string is recorded for debugging). Raises ModelUnavailable when
    both models failed. See the dual-model comment above for the rules.
    """
    if default_result is None and experimental_result is None:
        raise ModelUnavailable(
            "Both recognition models are unavailable "
            f"(default: {default_error or 'unknown error'}; "
            f"experimental: {experimental_error or 'unknown error'}).")

    available = {}
    if default_result is not None:
        available["default"] = default_result
    if experimental_result is not None:
        available["experimental"] = experimental_result

    # Merge ranked candidates, deduplicated by canonical food. Order: the
    # production model's list first, then experimental-only foods. A merged
    # candidate keeps its first-seen (source) model's own confidence — scores
    # are never averaged or compared across models.
    merged: list[dict] = []
    by_key: dict[str, dict] = {}
    for name in ("default", "experimental"):
        result = available.get(name)
        if result is None:
            continue
        for pred in result.get("predictions", []):
            key = canonical_food_key(pred["slug"])
            if key in by_key:
                if name not in by_key[key]["source_models"]:
                    by_key[key]["source_models"].append(name)
                continue
            candidate = dict(pred)
            candidate["canonical_key"] = key
            candidate["source_models"] = [name]
            by_key[key] = candidate
            merged.append(candidate)

    def raw_top(name: str) -> dict | None:
        result = available.get(name)
        if not result or not result.get("predictions"):
            return None
        return result["predictions"][0]

    def keys_of(name: str) -> set[str]:
        result = available.get(name)
        if not result:
            return set()
        return {canonical_food_key(p["slug"])
                for p in result.get("predictions", [])}

    d_raw, e_raw = raw_top("default"), raw_top("experimental")
    d_key = canonical_food_key(d_raw["slug"]) if d_raw else None
    e_key = canonical_food_key(e_raw["slug"]) if e_raw else None
    agreed = bool(d_key is not None and d_key == e_key)
    uncertain = False
    selected_model: str

    if d_raw is not None and e_raw is not None:
        d_conf = _model_confident(default_result)
        e_conf = _model_confident(experimental_result)
        if agreed:
            rule = "agreement"
            # Present the within-model-confident prediction when exactly one
            # is; both slugs resolve to the same canonical food either way.
            selected_model = "experimental" if (e_conf and not d_conf) else "default"
            uncertain = not (d_conf or e_conf)
            if uncertain:
                rule = "agreement_low_confidence"
        elif e_key in keys_of("default") and d_key in keys_of("experimental"):
            # Mutual support: each top-1 appears in the other model's list.
            # The evidence is symmetric, so neither model can be preferred
            # without comparing raw scores — treat as unresolved and ask
            # the user, with the production top-1 as provisional.
            rule = "disagreement_unresolved"
            uncertain = True
            selected_model = _provisional_model(d_raw, e_raw)
        elif e_key in keys_of("default"):
            selected_model, rule = "experimental", "cross_model_support"
            uncertain = not e_conf
        elif d_key in keys_of("experimental"):
            selected_model, rule = "default", "cross_model_support"
            uncertain = not d_conf
        elif d_conf != e_conf:
            selected_model = "default" if d_conf else "experimental"
            rule = "single_model_confident"
        else:
            rule = "disagreement_unresolved"
            uncertain = True
            selected_model = _provisional_model(d_raw, e_raw)
    else:
        selected_model = "default" if d_raw is not None else "experimental"
        rule = "single_model_fallback"
        uncertain = not _model_confident(available[selected_model])

    # The selected candidate is the selecting model's OWN top-1 entry (its
    # own label/confidence), annotated — never a merged or averaged score.
    selected = dict(raw_top(selected_model))
    selected_key = canonical_food_key(selected["slug"])
    selected["canonical_key"] = selected_key
    selected["source_models"] = [
        name for name in ("default", "experimental")
        if selected_key in keys_of(name)]
    # Selected first; the OTHER model's top-1 second (it is the alternative
    # the user is asked to confirm against); then the remaining candidates
    # in merged order.
    other_name = "experimental" if selected_model == "default" else "default"
    other_raw = raw_top(other_name) if other_name in available else None
    ordered = [selected]
    if other_raw is not None:
        other_candidate = by_key[canonical_food_key(other_raw["slug"])]
        if other_candidate["canonical_key"] != selected_key:
            ordered.append(other_candidate)
    predictions = ordered + [c for c in merged
                             if c not in ordered
                             and c["canonical_key"] != selected_key]
    low_confidence = uncertain or not _model_confident(available[selected_model])

    def model_debug(name: str, result: dict | None, error: str | None) -> dict:
        if result is None:
            return {"available": False, "error": error}
        top = result["predictions"][0] if result.get("predictions") else None
        return {
            "available": True,
            "top": ({"slug": top["slug"], "label": top.get("label"),
                     "confidence": top.get("confidence")} if top else None),
            "low_confidence": not _model_confident(result),
        }

    base = default_result if default_result is not None else experimental_result
    return {
        "predictions": predictions,
        "top": selected,
        "low_confidence": low_confidence,
        "threshold": LOW_CONFIDENCE_THRESHOLD,
        "image": base.get("image"),
        "single_label": True,
        "note": SINGLE_LABEL_NOTE,
        "model": "dual",
        "ensemble": {
            "strategy": DUAL_MODEL_STRATEGY,
            "confidence_scores_comparable": False,
            "agreement": agreed,
            "rule": rule,
            "selected_slug": selected["slug"],
            "selected_model": selected_model,
            "uncertain": uncertain,
            "needs_user_confirmation": uncertain,
            "unavailable_models": [
                name for name in ("default", "experimental")
                if name not in available],
            "models": {
                "default": model_debug("default", default_result, default_error),
                "experimental": model_debug(
                    "experimental", experimental_result, experimental_error),
            },
        },
    }


def predict_both_models(image_bytes: bytes, top_k: int = 3) -> dict:
    """Run BOTH models on the same image bytes and combine their answers.

    Each predictor applies its own checkpoint's preprocessing to the same
    validated bytes. A model that is missing, corrupt or otherwise failing
    is recorded in the ensemble debug block and the other model's answer is
    used; ImageError (undecodable image) is re-raised when neither model
    could process the image; ModelUnavailable is raised when both fail.
    """
    results: dict[str, dict | None] = {}
    errors: dict[str, str | None] = {}
    image_errors: dict[str, str] = {}
    for name in ("default", "experimental"):
        try:
            results[name] = get_predictor(name).predict(image_bytes, top_k=top_k)
            errors[name] = None
        except ImageError as exc:
            results[name] = None
            errors[name] = str(exc)
            image_errors[name] = str(exc)
        except Exception as exc:  # ModelUnavailable or runtime failure
            results[name] = None
            errors[name] = str(exc)
    if len(image_errors) == 2:
        raise ImageError(image_errors["default"])
    return combine_model_predictions(
        results["default"], results["experimental"],
        default_error=errors["default"],
        experimental_error=errors["experimental"])
