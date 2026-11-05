#!/usr/bin/env python3
"""NutriCare AI Food Scanner — reproducible training script.

Fine-tunes a lightweight ImageNet-pretrained CNN on a food image dataset laid
out in ``data/raw/<dataset>/<class_name>/`` folders (standard imagefolder), maps
those folders onto NutriCare's canonical class taxonomy, and writes:

    models/food_classifier.pt          checkpoint consumed by nutricare/vision.py
    models/food_classifier.metrics.json accuracy / precision / recall / F1,
                                       per-class report and confusion matrix
    models/food_classifier.report.txt   human-readable summary

The output contract is fixed: ``vision.Predictor`` reads exactly these keys, so
a model trained by this script drops straight into the running app.

Nothing here reports a number it did not measure. If the dataset is missing, the
script stops and says so; it never falls back to a stub "model".

Quick check that the whole pipeline works, without any dataset:

    python training/train_food_classifier.py --self-test

Real training (expect hours on CPU; use a GPU for the full class list):

    python training/download_datasets.py --out data/raw
    python training/train_food_classifier.py \
        --data data/raw --epochs 12 --architecture mobilenet_v3_small
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

CLASSES_PATH = PROJECT / "data" / "food_classes.json"
RAW_DIR = PROJECT / "data" / "raw"
MODEL_DIR = PROJECT / "models"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Folder-name aliases -> NutriCare class slug. Matching is case/punctuation
# insensitive, so "Masala_Dosa", "masala dosa" and "MasalaDosa" all land together.
EXTRA_ALIASES = {
    "chapati": "roti", "chapatti": "roti", "phulka": "roti", "roti": "roti",
    "paratha": "paratha_plain", "parantha": "paratha_plain",
    "aloo paratha": "aloo_paratha", "naan": "naan", "nan": "naan",
    "poori": "puri", "puri": "puri", "bhature": "bhatura", "bhatura": "bhatura",
    "rice": "rice_white", "white rice": "rice_white", "chawal": "rice_white",
    "brown rice": "rice_brown", "pulao": "pulao", "pilaf": "pulao",
    "jeera rice": "pulao", "khichdi": "khichdi", "khichri": "khichdi",
    "idli": "idli", "idly": "idli", "dosa": "dosa_plain", "plain dosa": "dosa_plain",
    "masala dosa": "masala_dosa", "uttapam": "uttapam", "uthappam": "uttapam",
    "poha": "poha", "upma": "upma", "vada": "vada", "medu vada": "vada",
    "chole bhature": "chole_bhature", "dal": "dal_plain", "daal": "dal_plain",
    "toor dal": "dal_plain", "dal tadka": "dal_tadka", "dal fry": "dal_tadka",
    "rajma": "rajma", "chole": "chole", "chana masala": "chole",
    "palak paneer": "palak_paneer", "matar paneer": "mattar_paneer",
    "mattar paneer": "mattar_paneer", "aloo gobi": "aloo_gobi",
    "mixed vegetable": "mixed_veg_sabzi", "sabzi": "mixed_veg_sabzi",
    "vegetable curry": "mixed_veg_sabzi", "sambar": "sambar", "rasam": "rasam",
    "kadhi": "kadhi", "paneer butter masala": "paneer_butter_masala",
    "bhindi": "bhindi_masala", "okra": "bhindi_masala", "curd": "curd_dahi",
    "dahi": "curd_dahi", "yogurt": "curd_dahi",
    "veg biryani": "veg_biryani", "vegetable biryani": "veg_biryani",
    "chicken biryani": "chicken_biryani", "biryani": "chicken_biryani",
    "curd rice": "curd_rice", "lemon rice": "lemon_rice",
    "tomato rice": "tomato_rice", "fried rice": "fried_rice",
    "samosa": "samosa", "pav bhaji": "pav_bhaji", "pakora": "pakora",
    "bhajji": "pakora", "dhokla": "dhokla", "kachori": "kachori",
    "vada pav": "vada_pav", "pani puri": "pani_puri", "golgappa": "pani_puri",
    "bhel puri": "bhel_puri", "bhel": "bhel_puri",
    "pizza": "pizza", "burger": "burger", "hamburger": "burger",
    "sandwich": "sandwich", "pasta": "pasta", "noodles": "noodles",
    "chow mein": "noodles", "french fries": "french_fries", "fries": "french_fries",
    "fried chicken": "fried_chicken", "momos": "momos", "momo": "momos",
    "spring rolls": "spring_rolls", "spring roll": "spring_rolls",
    "pancakes": "pancakes", "pancake": "pancakes", "salad": "salad",
    "thepla": "thepla",
}


def norm(text: str) -> str:
    keep = [c.lower() if c.isalnum() or c.isspace() else " " for c in str(text)]
    return " ".join("".join(keep).split())


def load_taxonomy() -> list[dict]:
    return json.loads(CLASSES_PATH.read_text(encoding="utf-8"))["classes"]


def build_alias_map(taxonomy: list[dict]) -> dict[str, str]:
    """alias -> slug, from the taxonomy itself plus known dataset folder names."""
    mapping = {}
    for entry in taxonomy:
        for alias in [entry["slug"].replace("_", " "), entry["label"], *entry["aliases"]]:
            mapping[norm(alias)] = entry["slug"]
    for alias, slug in EXTRA_ALIASES.items():
        mapping[norm(alias)] = slug
    return mapping


# ---------------------------------------------------------------------------
def discover(data_dirs: list[Path], taxonomy: list[dict], min_images: int) -> dict:
    """Group image folders into classes. Returns {slug: [paths]} + a report."""
    aliases = build_alias_map(taxonomy)
    valid_slugs = {entry["slug"] for entry in taxonomy}
    found: dict[str, list[Path]] = {}
    unmapped: dict[str, int] = Counter()
    per_class_filesize: dict[str, list[int]] = {}

    for root in data_dirs:
        if not root.is_dir():
            print(f"  ! missing dataset directory: {root}")
            continue
        for folder in sorted(p for p in root.rglob("*") if p.is_dir()):
            files = [f for f in folder.iterdir()
                     if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES]
            if not files:
                continue
            key = norm(folder.name)
            slug = aliases.get(key)
            if slug is None or slug not in valid_slugs:
                unmapped[folder.name] += len(files)
                continue
            found.setdefault(slug, []).extend(files)

    report = {"mapped_classes": len(found), "unmapped_folders": dict(unmapped),
              "classes": {}}
    for slug, files in sorted(found.items()):
        if len(files) < min_images:
            report["classes"][slug] = {"images": len(files), "kept": False}
            continue
        report["classes"][slug] = {"images": len(files), "kept": True}
        per_class_filesize[slug] = [f.stat().st_size for f in files]
    kept = {slug: files for slug, files in found.items()
            if report["classes"][slug]["kept"]}
    report["kept_classes"] = len(kept)
    report["total_images"] = sum(len(v) for v in kept.values())
    return {"classes": kept, "report": report}


def split_dataset(classes: dict[str, list[Path]], val_pct: float, test_pct: float,
                  seed: int) -> dict:
    """Stratified per-class split. The test split is never used for training."""
    rng = random.Random(seed)
    out = {"train": [], "val": [], "test": []}
    for slug in sorted(classes):
        # De-duplicate identical byte sizes+names first: cheap leakage guard for
        # datasets that ship the same photo twice under different names.
        seen, unique = set(), []
        for path in classes[slug]:
            signature = (path.name.split(".")[0], path.stat().st_size)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(path)
        rng.shuffle(unique)
        count = len(unique)
        n_test = max(1, round(count * test_pct)) if count >= 5 else 0
        n_val = max(1, round(count * val_pct)) if count >= 5 else 0
        if count - n_test - n_val < 1:      # never leave training empty
            n_test = n_val = 0
        test = unique[:n_test]
        val = unique[n_test:n_test + n_val]
        train = unique[n_test + n_val:]
        out["train"] += [(p, slug) for p in train]
        out["val"] += [(p, slug) for p in val]
        out["test"] += [(p, slug) for p in test]
    return out


# ---------------------------------------------------------------------------
def metrics_from_confusion(matrix: list[list[int]], labels: list[str]) -> dict:
    """Accuracy, macro/weighted precision-recall-F1 and a per-class table."""
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[i][i] for i in range(len(labels)))
    per_class, f1_scores, supports = {}, [], []
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(labels))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        support = sum(matrix[i])
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4),
                            "f1": round(f1, 4), "support": support}
        f1_scores.append(f1)
        supports.append(support)
    macro = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    weighted = (sum(f * s for f, s in zip(f1_scores, supports)) / sum(supports)
                if sum(supports) else 0.0)
    return {
        "accuracy": round(correct / total, 4) if total else 0.0,
        "macro_f1": round(macro, 4),
        "weighted_f1": round(weighted, 4),
        "support": total,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "labels": labels,
    }


def hardest_pairs(matrix: list[list[int]], labels: list[str], limit: int = 8) -> list:
    """Most confused class pairs — the honest 'what still fails' list."""
    pairs = []
    for i, actual in enumerate(labels):
        for j, predicted in enumerate(labels):
            if i != j and matrix[i][j]:
                pairs.append((matrix[i][j], actual, predicted))
    pairs.sort(reverse=True)
    return [{"count": c, "actual": a, "predicted_as": p} for c, a, p in pairs[:limit]]


# ---------------------------------------------------------------------------
def self_test() -> int:
    """Prove the pipeline end-to-end on synthetic images, in seconds.

    This trains a real model on random noise. It therefore reports a genuinely
    measured accuracy — on noise — and explicitly labels it as meaningless for
    real food photographs. It is a pipeline check, not a product claim.
    """
    import torch
    from PIL import Image

    torch.manual_seed(0)
    random.seed(0)
    taxonomy = load_taxonomy()[:3]
    slugs = [entry["slug"] for entry in taxonomy]
    work = PROJECT / "data" / "selftest"
    if work.exists():
        import shutil
        shutil.rmtree(work)
    for slug in slugs:
        folder = work / "synthetic" / slug
        folder.mkdir(parents=True)
        for i in range(8):
            pixels = torch.randint(0, 256, (48, 48, 3), dtype=torch.uint8).numpy()
            Image.fromarray(pixels).save(folder / f"{i}.jpg")

    code = run(data_dirs=[work / "synthetic"], epochs=2, batch_size=4, lr=0.01,
               architecture="mobilenet_v3_small", image_size=128, workers=0,
               output=MODEL_DIR / "selftest.pt", seed=0, min_images=1,
               val_pct=0.25, test_pct=0.25, freeze_epochs=0, allow_tiny=True,
               pretrained=False)
    checkpoint = MODEL_DIR / "selftest.pt"
    print("\n" + "=" * 78)
    if code == 0 and checkpoint.exists():
        size_kb = checkpoint.stat().st_size / 1024
        print(f"SELF-TEST PASSED — pipeline produced {checkpoint} ({size_kb:.0f} KB)")
        print("The accuracy above was measured on random noise and is NOT a "
              "statement about real food photographs.")
        print("Load it in the app with:  NUTRICARE_MODEL=models/selftest.pt python app.py")
        return 0
    print("SELF-TEST FAILED — see the error above.")
    return 1


def run(data_dirs: list[Path], epochs: int, batch_size: int, lr: float,
        architecture: str, image_size: int, workers: int, output: Path,
        seed: int, min_images: int, val_pct: float, test_pct: float,
        freeze_epochs: int, allow_tiny: bool, pretrained: bool = True) -> int:
    try:
        import numpy as np
        import torch
        import torch.nn as nn
        from PIL import Image
        from torch.utils.data import DataLoader, Dataset
        from torchvision import transforms
    except Exception as exc:  # noqa: BLE001
        print(f"Missing ML dependency: {exc}")
        print("Install with:  pip install -r requirements-ml.txt")
        return 2

    sys.path.insert(0, str(PROJECT))
    from nutricare import vision  # noqa: PLC0415

    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}  |  architecture: {architecture}  "
          f"|  torch {torch.__version__}")

    taxonomy = load_taxonomy()
    print("\nScanning datasets …")
    discovered = discover(data_dirs, taxonomy, min_images)
    report = discovered["report"]
    print(f"  mapped classes : {report['mapped_classes']}")
    print(f"  kept classes   : {report['kept_classes']} "
          f"(>= {min_images} usable images)")
    print(f"  total images   : {report['total_images']}")
    if report["unmapped_folders"]:
        print(f"  unmapped folders: {len(report['unmapped_folders'])} "
              f"(see metrics json; add aliases to EXTRA_ALIASES)")

    if not discovered["classes"]:
        print("\nNo usable images found. Nothing was trained and no model was written.")
        print("Run training/download_datasets.py first, or point --data at a folder "
              "laid out as <class>/<images>.")
        return 3
    if report["kept_classes"] < 2 and not allow_tiny:
        print("\nFewer than 2 classes with enough images — training would be "
              "meaningless. Pass --allow-tiny to override.")
        return 3

    splits = split_dataset(discovered["classes"], val_pct, test_pct, seed)
    print(f"  split          : train {len(splits['train'])} · "
          f"val {len(splits['val'])} · test {len(splits['test'])}")
    if not splits["train"] or not splits["test"]:
        print("\nSplit unusable (need at least one train and one test image). "
              "Nothing was trained.")
        return 3

    classes = sorted(discovered["classes"])
    index_of = {slug: i for i, slug in enumerate(classes)}
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.25, 0.25, 0.2),
        transforms.RandomRotation(12),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(int(image_size * 256 / 224)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])

    class FoodData(Dataset):
        def __init__(self, rows, transform):
            self.rows = rows
            self.transform = transform

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            path, slug = self.rows[i]
            try:
                image = Image.open(path).convert("RGB")
            except Exception:  # unreadable/corrupt file -> neutral image
                image = Image.new("RGB", (image_size, image_size))
            return self.transform(image), index_of[slug]

    loaders = {
        "train": DataLoader(FoodData(splits["train"], train_tf), batch_size=batch_size,
                            shuffle=True, num_workers=workers),
        "val": DataLoader(FoodData(splits["val"], eval_tf), batch_size=batch_size,
                          num_workers=workers),
        "test": DataLoader(FoodData(splits["test"], eval_tf), batch_size=batch_size,
                           num_workers=workers),
    }

    # Pretrained ImageNet weights: required for transfer learning. If they cannot
    # be fetched we stop rather than silently training from scratch, which would
    # produce a model too weak to be honest about.
    if not pretrained:
        # Only the --self-test path sets this. Random init on noise still proves
        # checkpoint/state_dict/metrics plumbing, and the output says so.
        print("\nNOTE: pretrained=False — this model is randomly initialised and "
              "carries NO transfer-learned knowledge.")
        model = vision.build_model(architecture, len(classes), pretrained=False)
    try:
        model = (model if not pretrained
                 else vision.build_model(architecture, len(classes), pretrained=True))
    except Exception as exc:  # noqa: BLE001
        print(f"\nCould not load ImageNet-pretrained weights: {exc}")
        print("Transfer learning needs download.pytorch.org to be reachable.")
        print("Re-run where that host is allowed, or pre-populate "
              "~/.cache/torch/hub/checkpoints with the weights file.")
        return 4

    if freeze_epochs > 0:
        for parameter in model.parameters():
            parameter.requires_grad = False
        head = (model.classifier[-1] if hasattr(model, "classifier")
                else model.fc)
        for parameter in head.parameters():
            parameter.requires_grad = True
    model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, epochs))

    def evaluate(loader):
        model.eval()
        matrix = [[0] * len(classes) for _ in classes]
        loss_sum, seen = 0.0, 0
        with torch.no_grad():
            for images, targets in loader:
                images, targets = images.to(device), targets.to(device)
                logits = model(images)
                loss_sum += criterion(logits, targets).item() * targets.size(0)
                seen += targets.size(0)
                for actual, predicted in zip(targets.tolist(), logits.argmax(1).tolist()):
                    matrix[actual][predicted] += 1
        return (loss_sum / seen if seen else 0.0), matrix

    history, best_accuracy, best_state = [], -1.0, None
    started = time.time()
    for epoch in range(1, epochs + 1):
        if freeze_epochs and epoch == freeze_epochs + 1:
            for parameter in model.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=lr * 0.2,
                                          weight_decay=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=max(1, epochs - freeze_epochs))
            print("  (unfroze backbone for fine-tuning)")
        model.train()
        running, seen = 0.0, 0
        for images, targets in loaders["train"]:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), targets)
            loss.backward()
            optimizer.step()
            running += loss.item() * targets.size(0)
            seen += targets.size(0)
        scheduler.step()
        train_loss = running / seen if seen else 0.0
        val_loss, val_matrix = evaluate(loaders["val"] or loaders["test"])
        val_total = sum(sum(row) for row in val_matrix)
        val_accuracy = (sum(val_matrix[i][i] for i in range(len(classes))) / val_total
                        if val_total else 0.0)
        history.append({"epoch": epoch, "train_loss": round(train_loss, 4),
                        "val_loss": round(val_loss, 4),
                        "val_accuracy": round(val_accuracy, 4)})
        print(f"  epoch {epoch:>2}/{epochs}  train_loss {train_loss:.4f}  "
              f"val_loss {val_loss:.4f}  val_acc {val_accuracy:.3f}")
        if val_accuracy >= best_accuracy:
            best_accuracy = val_accuracy
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    print("\nEvaluating on the held-out TEST split (never used for training) …")
    test_loss, matrix = evaluate(loaders["test"])
    payload = metrics_from_confusion(matrix, classes)

    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "classes": classes,
        "architecture": architecture,
        "input_size": image_size,
        "normalise_mean": mean,
        "normalise_std": std,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_accuracy": payload["accuracy"],
        "test_support": payload["support"],
        "torch_version": torch.__version__,
        "device": str(device),
        "epochs": epochs,
        "dataset_report": report,
    }, output)

    metrics_path = output.with_suffix(".metrics.json")
    metrics_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "architecture": architecture,
        "image_size": image_size,
        "epochs": epochs,
        "device": str(device),
        "train_seconds": round(time.time() - started, 1),
        "classes": len(classes),
        "dataset": report,
        "split": {k: len(v) for k, v in splits.items()},
        "history": history,
        "test_loss": round(test_loss, 4),
        "test_metrics": payload,
        "hardest_confusions": hardest_pairs(matrix, classes),
        "worst_classes": sorted(payload["per_class"].items(),
                                key=lambda kv: kv[1]["f1"])[:10],
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    report_path = output.with_suffix(".report.txt")
    lines = [
        "NutriCare food classifier — evaluation report",
        f"generated : {metrics_payload['generated_at']}",
        f"model     : {output} ({output.stat().st_size / 1024 / 1024:.1f} MB)",
        f"architecture: {architecture} @ {image_size}px on {device}",
        f"classes   : {len(classes)}",
        f"split     : train {len(splits['train'])} / val {len(splits['val'])} "
        f"/ test {len(splits['test'])}",
        "",
        f"TEST accuracy    : {payload['accuracy']:.4f}  (n={payload['support']})",
        f"TEST macro F1    : {payload['macro_f1']:.4f}",
        f"TEST weighted F1 : {payload['weighted_f1']:.4f}",
        "",
        "Per-class (sorted by F1, worst first — poor classes are NOT hidden):",
    ]
    for label, stats in sorted(payload["per_class"].items(), key=lambda kv: kv[1]["f1"]):
        lines.append(f"  {label:<28} F1 {stats['f1']:.3f}  P {stats['precision']:.3f}  "
                     f"R {stats['recall']:.3f}  n={stats['support']}")
    lines += ["", "Most confused pairs (actual -> predicted):"]
    for pair in metrics_payload["hardest_confusions"]:
        lines.append(f"  {pair['actual']} -> {pair['predicted_as']}: {pair['count']}")
    lines += ["", "Confusion matrix (rows = actual, cols = predicted):",
              "  labels: " + ", ".join(classes)]
    for i, label in enumerate(classes):
        lines.append(f"  {label:<28} " + " ".join(f"{v:>5}" for v in matrix[i]))
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nTEST accuracy : {payload['accuracy']:.4f}  (n={payload['support']})")
    print(f"TEST macro F1 : {payload['macro_f1']:.4f}")
    worst = ", ".join("{} ({:.2f})".format(k, v["f1"])
                      for k, v in metrics_payload["worst_classes"][:5])
    print(f"worst classes : {worst}")
    print(f"\nSaved:\n  {output}\n  {metrics_path}\n  {report_path}")
    print("\nInstall into the app:  the path models/food_classifier.pt is the default, "
          "so just restart the server.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train the NutriCare food classifier.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", action="append", default=None,
                        help="dataset root(s) containing <class>/<images> folders")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--architecture", default="mobilenet_v3_small",
                        choices=["mobilenet_v3_small", "mobilenet_v3_large",
                                 "efficientnet_b0", "resnet18"])
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", default=str(MODEL_DIR / "food_classifier.pt"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-images", type=int, default=20,
                        help="drop classes with fewer usable images than this")
    parser.add_argument("--val-pct", type=float, default=0.15)
    parser.add_argument("--test-pct", type=float, default=0.15)
    parser.add_argument("--freeze-epochs", type=int, default=1,
                        help="epochs to train the head only before fine-tuning")
    parser.add_argument("--allow-tiny", action="store_true",
                        help="permit <2 classes (pipeline checks only)")
    parser.add_argument("--self-test", action="store_true",
                        help="synthetic end-to-end pipeline check (no dataset needed)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    data_dirs = [Path(p) for p in (args.data or [str(RAW_DIR)])]
    return run(data_dirs=data_dirs, epochs=args.epochs, batch_size=args.batch_size,
               lr=args.lr, architecture=args.architecture,
               image_size=args.image_size, workers=args.workers,
               output=Path(args.output), seed=args.seed, min_images=args.min_images,
               val_pct=args.val_pct, test_pct=args.test_pct,
               freeze_epochs=args.freeze_epochs, allow_tiny=args.allow_tiny)


if __name__ == "__main__":
    sys.exit(main())
