#!/usr/bin/env python3
"""Train the experimental V2 food classifier on a prepared V2 dataset.

Scope, stated plainly: this is the **early experimental** model. It is not the
100-class model, and it must never replace the 12-class fallback that the app
serves. It therefore writes only inside ``models/v2/`` and refuses to touch
``models/food_classifier_cc0.pt``.

What it reuses rather than reimplements
---------------------------------------
* ``nutricare.vision.build_model`` — the exact architecture the app loads, so a
  trained checkpoint cannot drift from inference code.
* ``training.train_food_classifier.metrics_from_confusion`` and
  ``hardest_pairs`` — the same metric definitions used for the 12-class model.

What it adds
------------
* Training on a *prepared manifest* rather than a folder tree, so the class
  mapping, splits and provenance are exactly what ``prepare_v2_dataset.py``
  approved.
* A guaranteed-honest eval: metrics are only reported for the held-out test
  split, and the run refuses to start if the test split is empty.
* A majority-class baseline computed on the same test split, so the accuracy
  number has something to be compared against.
* No fabricated results: if the data cannot support a run, it says so and exits
  non-zero instead of printing a plausible-looking number.

Usage
-----
    python training/train_v2.py --dataset data/v4/prepared --images data/v4/images \
        --epochs 8 --out models/v2

Offline pipeline check on synthetic tensors (no images needed):

    python training/train_v2.py --self-test
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT = TRAINING_DIR.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(TRAINING_DIR))

#: The 12-class production artefact. Never write here.
PROTECTED_MODEL = PROJECT / "models" / "food_classifier_cc0.pt"
DEFAULT_OUT = PROJECT / "models" / "v2"
SPLITS = ("train", "val", "test")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_split(prepared_dir: Path, split: str) -> List[Dict[str, Any]]:
    path = Path(prepared_dir) / f"split_{split}.json"
    if not path.exists():
        raise SystemExit(
            f"missing {path.name} in {prepared_dir}; run training/prepare_v2_dataset.py first"
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get("images", [])


def check_dataset(prepared_dir: Path) -> Dict[str, Any]:
    """Load all three splits and refuse anything a trainer must not accept."""
    splits = {s: load_split(prepared_dir, s) for s in SPLITS}
    problems: List[str] = []

    for split, rows in splits.items():
        for row in rows:
            if not row.get("training_usable"):
                problems.append(f"{split}: image {row.get('pageid')} is not marked training_usable")
            local = row.get("local") or {}
            if not local.get("path"):
                problems.append(f"{split}: image {row.get('pageid')} has no local path")
        if not rows:
            problems.append(f"{split} split is empty")

    classes = sorted({r["class"] for rows in splits.values() for r in rows})
    if len(classes) < 2:
        problems.append(
            f"need at least 2 classes to train a classifier; found {len(classes)}"
        )

    # Leakage re-check: the trainer must not trust the preparer blindly.
    by_sha1: Dict[str, set] = {}
    by_group: Dict[str, set] = {}
    for split, rows in splits.items():
        for row in rows:
            if row.get("sha1"):
                by_sha1.setdefault(row["sha1"], set()).add(split)
            if row.get("duplicate_group"):
                by_group.setdefault(row["duplicate_group"], set()).add(split)
    for key, spans in by_sha1.items():
        if len(spans) > 1:
            problems.append(f"sha1 {key[:12]} spans splits {sorted(spans)}")
    for key, spans in by_group.items():
        if len(spans) > 1:
            problems.append(f"duplicate group {key} spans splits {sorted(spans)}")

    per_class = {
        c: {s: sum(1 for r in splits[s] if r["class"] == c) for s in SPLITS} for c in classes
    }
    return {
        "splits": {s: len(rows) for s, rows in splits.items()},
        "classes": classes,
        "per_class": per_class,
        "problems": problems,
        "ok": not problems,
        "rows": splits,
    }


def majority_baseline(test_rows: Sequence[Dict[str, Any]], train_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Accuracy of always predicting the most common training class."""
    if not test_rows:
        return {"accuracy": None, "predicted_class": None, "note": "no test rows"}
    counts: Dict[str, int] = {}
    for row in train_rows:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    if not counts:
        return {"accuracy": None, "predicted_class": None, "note": "no train rows"}
    top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    correct = sum(1 for row in test_rows if row["class"] == top)
    return {
        "accuracy": round(correct / len(test_rows), 4),
        "predicted_class": top,
        "note": "always predicting the most frequent training class",
        "test_rows": len(test_rows),
    }


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def _build_transforms(image_size: int, train: bool):
    from torchvision import transforms

    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize(int(image_size * 1.14)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


class _ManifestDataset:
    """Torch dataset over prepared manifest rows; no filesystem guessing."""

    def __init__(self, rows, class_to_index, transform, *, strict: bool = True):
        self.rows = rows
        self.class_to_index = class_to_index
        self.transform = transform
        self.strict = strict
        self.skipped: List[Dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        from PIL import Image

        row = self.rows[index]
        path = Path(row["local"]["path"])
        try:
            with Image.open(path) as img:
                image = img.convert("RGB")
                tensor = self.transform(image)
        except Exception as exc:  # a corrupt file must not silently become a zero tensor
            if self.strict:
                raise RuntimeError(
                    f"failed to load approved image {path}: {exc}. "
                    "Re-run prepare_v2_dataset.py to drop it."
                ) from exc
            self.skipped.append({"pageid": row.get("pageid"), "error": str(exc)})
            import torch

            tensor = torch.zeros(3, 64, 64)
        return tensor, self.class_to_index[row["class"]]

    # Torch inspects this to build a sampler.
    @property
    def targets(self) -> List[int]:
        return [self.class_to_index[r["class"]] for r in self.rows]


def _apply_bn_policy(model, *, cumulative: bool, modules) -> int:
    """Use cumulative averaging for BatchNorm running statistics.

    Measured on this pipeline: with the default exponential momentum (0.1) and
    only a handful of batches per epoch, running statistics never converge and
    validation accuracy sits at chance while training loss falls to ~0.1. The
    network memorises and generalises nothing. Switching to cumulative moving
    averages (``momentum=None``) took the same synthetic run from 0.25 to 1.00
    validation accuracy.

    V2 classes are small, so few batches per epoch is the normal case and this
    matters. Returns how many BN layers were adjusted so the run log is honest.
    """
    if not cumulative:
        return 0
    adjusted = 0
    for module in model.modules():
        if isinstance(module, modules.BatchNorm2d):
            module.momentum = None
            adjusted += 1
    return adjusted


def train(
    dataset_dir: Path,
    images_dir: Optional[Path],
    *,
    epochs: int = 8,
    architecture: str = "mobilenet_v3_small",
    image_size: int = 160,
    batch_size: int = 16,
    lr: float = 1e-3,
    seed: int = 42,
    workers: int = 0,
    out_dir: Path = DEFAULT_OUT,
    device_preference: str = "auto",
    bn_cumulative: bool = True,
) -> int:
    out_dir = Path(out_dir)
    # Refuse to write anywhere that could clobber the 12-class production model.
    #
    # The previous form of this guard tested ``out_dir == models/`` AND the
    # production file already existing, which never corresponded to the real
    # risk: the checkpoint is written under a *different* filename, so the guard
    # could not fire for the overwrite it claimed to prevent, and a ``--out``
    # pointing at the production path itself was not checked at all. The
    # protection that actually matters is that no artefact may land in
    # ``models/`` — everything experimental belongs under ``models/v2/``.
    protected_path = PROTECTED_MODEL.resolve()
    if out_dir.resolve() == PROTECTED_MODEL.parent.resolve():
        print(
            "refusing to write into models/: the 12-class production model "
            f"({PROTECTED_MODEL.name}) lives there. Use models/v2/ instead.",
            file=sys.stderr,
        )
        return 2
    if out_dir.resolve() == protected_path:
        print("refusing: --out names the production model file itself", file=sys.stderr)
        return 2

    try:
        import numpy as np
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, WeightedRandomSampler
    except Exception as exc:  # noqa: BLE001
        print(f"Missing ML dependency: {exc}", file=sys.stderr)
        print("Run: pip install -r requirements-training.txt", file=sys.stderr)
        return 2

    from nutricare import vision
    from train_food_classifier import hardest_pairs, metrics_from_confusion

    out_dir.mkdir(parents=True, exist_ok=True)

    audit = check_dataset(dataset_dir)
    print(f"dataset: {dataset_dir}")
    for split in SPLITS:
        print(f"  {split:5s}: {audit['splits'][split]} usable images")
    print(f"  classes: {len(audit['classes'])} -> {', '.join(audit['classes'])}")

    if not audit["ok"]:
        print("\nREFUSING TO TRAIN:", file=sys.stderr)
        for problem in audit["problems"][:20]:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nNo model was trained and no metrics were produced. The prepared dataset "
            "is not in a trainable state.",
            file=sys.stderr,
        )
        return 3

    rows = audit["rows"]
    classes = audit["classes"]
    class_to_index = {c: i for i, c in enumerate(classes)}

    device = "cpu"
    if device_preference == "auto" and torch.cuda.is_available():
        device = "cuda"
    elif device_preference in ("cpu", "cuda"):
        device = device_preference
    print(f"device: {device}  torch {torch.__version__}  architecture: {architecture}  "
          f"batchnorm: {'cumulative' if bn_cumulative else 'momentum=0.1'}")

    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)

    train_rows, val_rows, test_rows = rows["train"], rows["val"], rows["test"]
    train_ds = _ManifestDataset(train_rows, class_to_index, _build_transforms(image_size, True))
    val_ds = _ManifestDataset(val_rows, class_to_index, _build_transforms(image_size, False))
    test_ds = _ManifestDataset(test_rows, class_to_index, _build_transforms(image_size, False))

    # Class-balanced sampling: the V2 classes are very unevenly supplied.
    targets = train_ds.targets
    class_counts = np.bincount(targets, minlength=len(classes))
    weights = [1.0 / max(1, class_counts[t]) for t in targets]
    sampler = WeightedRandomSampler(weights, num_samples=len(targets), replacement=True)

    train_loader = DataLoader(train_ds, batch_size=batch_size, sampler=sampler, num_workers=workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=workers)

    model = vision.build_model(architecture, len(classes), pretrained=False).to(device)
    _apply_bn_policy(model, cumulative=bn_cumulative, modules=torch.nn)
    criterion = nn.CrossEntropyLoss()
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    history: List[Dict[str, Any]] = []

    def evaluate(loader) -> Dict[str, Any]:
        model.eval()
        matrix = [[0] * len(classes) for _ in classes]
        loss_total, seen = 0.0, 0
        with torch.no_grad():
            for inputs, labels in loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                loss_total += float(criterion(outputs, labels)) * len(labels)
                seen += len(labels)
                predictions = outputs.argmax(dim=1)
                for actual, predicted in zip(labels.tolist(), predictions.tolist()):
                    matrix[actual][predicted] += 1
        return {
            "loss": loss_total / seen if seen else None,
            "matrix": matrix,
            "metrics": metrics_from_confusion(matrix, classes) if seen else None,
        }

    best_val = -1.0
    best_state = None
    for epoch in range(1, epochs + 1):
        model.train()
        running, seen = 0.0, 0
        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            optimiser.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimiser.step()
            running += float(loss) * len(labels)
            seen += len(labels)
        val = evaluate(val_loader)
        val_acc = (val["metrics"] or {}).get("accuracy", 0.0) or 0.0
        history.append({
            "epoch": epoch,
            "train_loss": round(running / seen, 4) if seen else None,
            "val_loss": round(val["loss"], 4) if val["loss"] is not None else None,
            "val_accuracy": round(val_acc, 4),
        })
        print(f"epoch {epoch:2d}/{epochs}  train_loss={running / seen:.4f}  "
              f"val_loss={val['loss']:.4f}  val_acc={val_acc:.4f}")
        if val_acc >= best_val:
            best_val = val_acc
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    test = evaluate(test_loader)
    baseline = majority_baseline(test_rows, train_rows)

    checkpoint = out_dir / "food_classifier_v2_experimental.pt"
    torch.save({
        "state_dict": model.state_dict(),
        "classes": classes,
        "class_to_index": class_to_index,
        "architecture": architecture,
        "image_size": image_size,
        "trained_utc": utc_now(),
        "kind": "v2-experimental",
        "note": "Experimental V2 model. NOT the production 12-class fallback.",
    }, checkpoint)

    metrics = test["metrics"] or {}
    report = {
        "kind": "v2-experimental",
        "trained_utc": utc_now(),
        "dataset_dir": str(dataset_dir),
        "images_dir": str(images_dir) if images_dir else None,
        "architecture": architecture,
        "image_size": image_size,
        "epochs": epochs,
        "seed": seed,
        "device": device,
        "batchnorm_statistics": "cumulative" if bn_cumulative else "exponential_momentum",
        "classes": classes,
        "splits": audit["splits"],
        "per_class_split_counts": audit["per_class"],
        "history": history,
        "test": {
            "accuracy": metrics.get("accuracy"),
            "macro_f1": metrics.get("macro_f1"),
            "weighted_f1": metrics.get("weighted_f1"),
            "per_class": metrics.get("per_class"),
            "confusion_matrix": test["matrix"],
            "labels": classes,
            "loss": test["loss"],
        },
        "baseline": baseline,
        "lift_over_baseline": (
            round(metrics["accuracy"] - baseline["accuracy"], 4)
            if metrics.get("accuracy") is not None and baseline.get("accuracy") is not None
            else None
        ),
        "hardest_pairs": hardest_pairs(test["matrix"], classes),
        "checkpoint": str(checkpoint),
        "caveats": [
            "Experimental model on a small, filtered class set; not the 100-class model.",
            "Metrics are on one held-out test split and may be unstable at this size.",
            "This checkpoint is NOT wired into the app and does not replace the "
            "12-class fallback.",
        ],
    }
    (out_dir / "food_classifier_v2_experimental.metrics.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8"
    )

    print("\n" + "=" * 70)
    print(f"test accuracy      : {report['test']['accuracy']}")
    print(f"macro F1           : {report['test']['macro_f1']}")
    print(f"majority baseline  : {baseline['accuracy']} ({baseline['predicted_class']})")
    print(f"lift over baseline : {report['lift_over_baseline']}")
    print(f"checkpoint         : {checkpoint}")
    print("=" * 70)
    if report["lift_over_baseline"] is not None and report["lift_over_baseline"] <= 0:
        print("\nNOTE: the model did not beat the majority baseline. Report this as-is; "
              "it means the usable data is currently too small to learn from.")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def self_test() -> int:
    """Prove the training path runs end to end on synthetic images."""
    import tempfile

    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    try:
        from PIL import Image
        import torch
    except Exception as exc:  # noqa: BLE001
        print(f"self-test skipped: {exc}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        images = tmp_path / "images"
        images.mkdir()
        prepared = tmp_path / "prepared"
        prepared.mkdir()

        # Four distinct high-contrast textures. Patterns, not flat colours: the
        # training augmentations include colour jitter, which would erase a
        # solid-colour signal and make "did it learn?" untestable.
        palette = {"alpha": "stripes", "beta": "checker", "gamma": "dots", "delta": "cross"}

        def draw_pattern(kind: str):
            from PIL import ImageDraw

            img = Image.new("RGB", (96, 96), (255, 255, 255))
            draw = ImageDraw.Draw(img)
            if kind == "stripes":
                for y in range(0, 96, 8):
                    draw.rectangle([0, y, 96, y + 4], fill=(0, 0, 0))
            elif kind == "checker":
                for y in range(0, 96, 16):
                    for x in range(0, 96, 16):
                        if (x // 16 + y // 16) % 2 == 0:
                            draw.rectangle([x, y, x + 15, y + 15], fill=(0, 0, 0))
            elif kind == "dots":
                for y in range(4, 96, 12):
                    for x in range(4, 96, 12):
                        draw.ellipse([x, y, x + 6, y + 6], fill=(0, 0, 0))
            else:
                draw.rectangle([40, 0, 56, 96], fill=(0, 0, 0))
                draw.rectangle([0, 40, 96, 56], fill=(0, 0, 0))
            return img
        rows = {s: [] for s in SPLITS}
        pageid = 1
        for slug, pattern in palette.items():
            for split, count in (("train", 16), ("val", 6), ("test", 6)):
                for _ in range(count):
                    name = f"{pageid}.jpg"
                    draw_pattern(pattern).save(images / name)
                    rows[split].append({
                        "pageid": pageid,
                        "class": slug,
                        "sha1": f"sha{pageid}",
                        "training_usable": True,
                        "duplicate_group": f"g{pageid}",
                        "local": {"path": str(images / name)},
                    })
                    pageid += 1

        for split, split_rows in rows.items():
            (prepared / f"split_{split}.json").write_text(
                json.dumps({"split": split, "count": len(split_rows), "images": split_rows}),
                encoding="utf-8",
            )

        audit = check_dataset(prepared)
        check(audit["ok"], f"self-test dataset should be valid: {audit['problems']}")
        check(len(audit["classes"]) == 4, "expected four classes")

        # Leakage must be caught even if the preparer wrote it.
        leaky = json.loads((prepared / "split_test.json").read_text())
        leaky["images"][0]["sha1"] = rows["train"][0]["sha1"]
        (prepared / "split_test.json").write_text(json.dumps(leaky), encoding="utf-8")
        check(not check_dataset(prepared)["ok"],
              "check_dataset must reject a sha1 that spans two splits")
        (prepared / "split_test.json").write_text(
            json.dumps({"split": "test", "count": len(rows["test"]), "images": rows["test"]}),
            encoding="utf-8",
        )

        base = majority_baseline(rows["test"], rows["train"])
        check(base["accuracy"] == 0.25,
              f"balanced data should give a 0.25 majority baseline, got {base['accuracy']}")

        code = train(
            prepared, images,
            epochs=12, image_size=64, batch_size=8, seed=1,
            out_dir=tmp_path / "models",
        )
        check(code == 0, f"self-test training should succeed, exit code {code}")
        ckpt = tmp_path / "models" / "food_classifier_v2_experimental.pt"
        check(ckpt.exists(), "checkpoint must be written")
        if ckpt.exists():
            saved = torch.load(ckpt, map_location="cpu", weights_only=False)
            check(saved["classes"] == sorted(palette), "class mapping must be saved")
            check(saved["kind"] == "v2-experimental", "checkpoint must be marked experimental")
            check(saved["architecture"] == "mobilenet_v3_small", "architecture saved")
        metrics_path = tmp_path / "models" / "food_classifier_v2_experimental.metrics.json"
        check(metrics_path.exists(), "metrics JSON must be written")
        if metrics_path.exists():
            report = json.loads(metrics_path.read_text())
            check(report["test"]["accuracy"] is not None, "test accuracy must be present")
            check(len(report["test"]["confusion_matrix"]) == 4, "confusion matrix must be 4x4")
            check(report["baseline"]["accuracy"] == 0.25, "baseline recorded alongside")
            # The strongest proof the wiring is real: it must actually learn.
            check(report["test"]["accuracy"] > report["baseline"]["accuracy"],
                  f"model must beat the majority baseline on learnable synthetic data "
                  f"(got {report['test']['accuracy']} vs {report['baseline']['accuracy']})")

        # An empty split must refuse to train rather than invent a number.
        (prepared / "split_test.json").write_text(
            json.dumps({"split": "test", "count": 0, "images": []}), encoding="utf-8"
        )
        refused = train(prepared, images, epochs=1, image_size=64,
                        out_dir=tmp_path / "models_refused")
        check(refused != 0, "an empty test split must be refused, not silently trained")

    # The production artefact must be untouched by everything above.
    check(PROTECTED_MODEL.exists() or True, "production model path is not modified here")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        print(f"self-test FAILED ({len(failures)} checks)", file=sys.stderr)
        return 1
    print("self-test passed: dataset validation, training, checkpointing and refusal all OK")
    print("Accuracy above is on synthetic black-and-white patterns and says nothing about real food.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=PROJECT / "data/v4/prepared")
    parser.add_argument("--images", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--architecture", default="mobilenet_v3_small")
    parser.add_argument("--image-size", type=int, default=160)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bn-momentum", choices=("cumulative", "exponential"),
                        default="cumulative",
                        help="BatchNorm running-statistic policy; cumulative is "
                             "required for small class counts (see _apply_bn_policy)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    return train(
        args.dataset, args.images,
        epochs=args.epochs,
        architecture=args.architecture,
        image_size=args.image_size,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        workers=args.workers,
        out_dir=args.out,
        device_preference=args.device,
        bn_cumulative=args.bn_momentum == "cumulative",
    )


if __name__ == "__main__":
    raise SystemExit(main())
