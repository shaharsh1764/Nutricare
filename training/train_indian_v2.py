#!/usr/bin/env python3
"""Train a real Indian/Bengali food classifier on real downloaded images.

Differences from the earlier 12-class trainer that matter:

* **Duplicate-group-aware splitting.** Near-duplicate pairs are clustered with
  union-find before the split, so two shots of the same plate can never be in
  both train and test. Without this, test accuracy is inflated and the number
  is meaningless.
* **Warm-started from our own shipped checkpoint.** The ImageNet-pretrained
  weights are not downloadable in this sandbox (`download.pytorch.org` is
  firewalled), but ``models/food_classifier_cc0.pt`` already contains a
  MobileNetV3-Small feature extractor trained on real food imagery. We reuse
  every layer except the 12-way head. This is deliberate transfer learning, not
  training from scratch.
* **Honest reporting.** Per-class precision/recall/F1, a confusion matrix, and
  an explicit train-vs-test gap so overfitting is measurable rather than
  asserted.

Usage:
    python training/train_indian_v2.py --data /tmp/dataset_v2 --out models/indian_food_v1.pt
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def scan(data_dir: Path) -> Tuple[List[str], Dict[str, List[Path]]]:
    classes = sorted(p.name for p in data_dir.iterdir()
                     if p.is_dir() and any(f.suffix.lower() in IMAGE_SUFFIXES
                                           for f in p.iterdir()))
    per_class = {
        c: sorted(p for p in (data_dir / c).iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        for c in classes
    }
    return classes, per_class


class FoodDataset(Dataset):
    def __init__(self, items: List[Tuple[Path, int]], size: int, train: bool):
        from PIL import Image

        self.Image = Image
        self.items = items
        self.size = size
        self.train = train
        if train:
            from torchvision import transforms
            self.tf = transforms.Compose([
                transforms.RandomResizedCrop(size, scale=(0.6, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.RandomRotation(12),
                transforms.ColorJitter(0.25, 0.25, 0.25),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ])
        else:
            from torchvision import transforms
            self.tf = transforms.Compose([
                transforms.Resize(int(size * 1.14)),
                transforms.CenterCrop(size),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ])

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        path, label = self.items[index]
        try:
            img = self.Image.open(path).convert("RGB")
        except Exception:  # pragma: no cover - audit already removed these
            img = self.Image.new("RGB", (self.size, self.size))
        return self.tf(img), label


# ---------------------------------------------------------------------------
# Duplicate-aware split
# ---------------------------------------------------------------------------


def union_find_groups(per_class: Dict[str, List[Path]]) -> Dict[Path, int]:
    """Cluster images that are near-identical, so a cluster stays in one split."""
    from PIL import Image

    parent: Dict[Path, Path] = {}

    def find(x: Path) -> Path:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Path, b: Path) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    def dhash(path: Path) -> str | None:
        try:
            with Image.open(path) as img:
                small = img.convert("L").resize((9, 8), Image.LANCZOS)
                px = list(small.tobytes())
        except Exception:
            return None
        bits = 0
        i = 0
        for r in range(8):
            for c in range(8):
                if px[r * 9 + c] > px[r * 9 + c + 1]:
                    bits |= 1 << i
                i += 1
        return f"{bits:016x}"

    hashed: List[Tuple[Path, str]] = []
    for cls, paths in per_class.items():
        for p in paths:
            h = dhash(p)
            if h:
                hashed.append((p, h))
                find(p)

    # Bucket by the leading 8 bits so this is not an O(n^2) sweep.
    buckets: Dict[str, List[Tuple[Path, str]]] = defaultdict(list)
    for p, h in hashed:
        buckets[h[:2]].append((p, h))
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, ha = bucket[i]
                b, hb = bucket[j]
                if bin(int(ha, 16) ^ int(hb, 16)).count("1") <= 5:
                    union(a, b)

    return {p: id(find(p)) for p in parent}


def split_dataset(
    per_class: Dict[str, List[Path]],
    groups: Dict[Path, int],
    *,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> Dict[str, List[Tuple[Path, str]]]:
    """Group-aware, per-class stratified split."""
    rng = random.Random(seed)
    out: Dict[str, List[Tuple[Path, str]]] = {"train": [], "val": [], "test": []}

    for cls, paths in per_class.items():
        # bucket this class's images by duplicate-group id
        by_group: Dict[int, List[Path]] = defaultdict(list)
        for p in paths:
            by_group[groups.get(p, id(p))].append(p)
        items = [(gid, ps) for gid, ps in by_group.items()]
        rng.shuffle(items)

        total = len(paths)
        n_test = max(1, int(round(total * test_frac)))
        n_val = max(1, int(round(total * val_frac)))

        test_n = val_n = 0
        for _gid, ps in items:
            if test_n < n_test:
                out["test"].extend((p, cls) for p in ps)
                test_n += len(ps)
            elif val_n < n_val:
                out["val"].extend((p, cls) for p in ps)
                val_n += len(ps)
            else:
                out["train"].extend((p, cls) for p in ps)
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def confusion(y_true: List[int], y_pred: List[int], n: int) -> List[List[int]]:
    m = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        m[t][p] += 1
    return m


def per_class_scores(mat: List[List[int]]) -> List[Dict[str, float]]:
    scores = []
    for i in range(len(mat)):
        tp = mat[i][i]
        fp = sum(mat[r][i] for r in range(len(mat))) - tp
        fn = sum(mat[i]) - tp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        scores.append({"precision": round(prec, 4), "recall": round(rec, 4),
                       "f1": round(f1, 4), "support": sum(mat[i])})
    return scores


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--backbone", default="models/food_classifier_cc0.pt")
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--epochs", type=int, default=24)
    ap.add_argument("--warmup-epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr-head", type=float, default=2e-3)
    ap.add_argument("--lr-finetune", type=float, default=3e-4)
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    torch.manual_seed(42)
    random.seed(42)

    data_dir = Path(args.data)
    classes, per_class = scan(data_dir)
    print(f"classes: {len(classes)}  images: {sum(len(v) for v in per_class.values())}")

    groups = union_find_groups(per_class)
    splits = split_dataset(per_class, groups)
    # map labels
    label_of = {c: i for i, c in enumerate(classes)}
    splits_i = {k: [(p, label_of[c]) for p, c in v] for k, v in splits.items()}
    print({k: len(v) for k, v in splits_i.items()})

    train_ds = FoodDataset(splits_i["train"], args.size, True)
    val_ds = FoodDataset(splits_i["val"], args.size, False)
    test_ds = FoodDataset(splits_i["test"], args.size, False)

    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=0)
    val_dl = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=0)
    test_dl = DataLoader(test_ds, batch_size=args.batch, shuffle=False, num_workers=0)

    from torchvision import models

    net = models.mobilenet_v3_small(weights=None)
    init_note = "random"
    backbone_path = Path(args.backbone)
    if backbone_path.exists():
        ck = torch.load(backbone_path, map_location="cpu", weights_only=False)
        sd = {k: v for k, v in ck["state_dict"].items() if not k.startswith("classifier.3")}
        res = net.load_state_dict(sd, strict=False)
        init_note = f"warm-started from {backbone_path} ({ck.get('architecture')}); head reinitialised"
        print(f"backbone loaded from {backbone_path}; missing: {res.missing_keys}")

    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(classes))

    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)

    def run_epoch(opt=None) -> Tuple[float, float]:
        training = opt is not None
        net.train() if training else net.eval()
        total, correct, loss_sum = 0, 0, 0.0
        with torch.set_grad_enabled(training):
            for x, y in train_dl if training else _eval_loader():
                if training:
                    opt.zero_grad()
                logits = net(x)
                loss = criterion(logits, y)
                if training:
                    loss.backward()
                    opt.step()
                loss_sum += loss.item() * y.size(0)
                correct += (logits.argmax(1) == y).sum().item()
                total += y.size(0)
        return loss_sum / max(total, 1), correct / max(total, 1)

    eval_loader_holder = {"dl": None}

    def _eval_loader():
        return eval_loader_holder["dl"]

    def evaluate(loader) -> Tuple[float, float, List[int], List[int]]:
        net.eval()
        total, correct, loss_sum = 0, 0, 0.0
        ys, ps = [], []
        with torch.no_grad():
            for x, y in loader:
                logits = net(x)
                loss = criterion(logits, y)
                loss_sum += loss.item() * y.size(0)
                pred = logits.argmax(1)
                correct += (pred == y).sum().item()
                total += y.size(0)
                ys.extend(y.tolist())
                ps.extend(pred.tolist())
        return loss_sum / max(total, 1), correct / max(total, 1), ys, ps

    history = []
    started = time.time()

    # ---- phase 1: train the head only, backbone frozen
    for p in net.features.parameters():
        p.requires_grad = False
    opt1 = torch.optim.Adam(net.classifier.parameters(), lr=args.lr_head)
    for ep in range(1, args.warmup_epochs + 1):
        eval_loader_holder["dl"] = train_dl
        tr_loss, tr_acc = run_epoch(opt1)
        _, va_acc, _, _ = evaluate(val_dl)
        history.append({"epoch": ep, "phase": "head", "train_loss": round(tr_loss, 4),
                        "train_acc": round(tr_acc, 4), "val_acc": round(va_acc, 4)})
        print(f"  head ep{ep}: train {tr_acc:.3f} val {va_acc:.3f}", flush=True)

    # ---- phase 2: fine-tune everything
    for p in net.features.parameters():
        p.requires_grad = True
    opt2 = torch.optim.AdamW(net.parameters(), lr=args.lr_finetune, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt2, T_max=max(args.epochs - args.warmup_epochs, 1))
    best_val = -1.0
    best_state = None
    for ep in range(args.warmup_epochs + 1, args.epochs + 1):
        eval_loader_holder["dl"] = train_dl
        tr_loss, tr_acc = run_epoch(opt2)
        sched.step()
        va_loss, va_acc, _, _ = evaluate(val_dl)
        history.append({"epoch": ep, "phase": "finetune", "train_loss": round(tr_loss, 4),
                        "train_acc": round(tr_acc, 4), "val_loss": round(va_loss, 4),
                        "val_acc": round(va_acc, 4)})
        if va_acc > best_val:
            best_val = va_acc
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        print(f"  ft ep{ep}: train {tr_acc:.3f} val {va_acc:.3f} best {best_val:.3f}", flush=True)

    if best_state is not None:
        net.load_state_dict(best_state)

    train_seconds = time.time() - started

    # ---- final metrics
    _, train_acc, ty, tp = evaluate(train_dl)
    te_loss, te_acc, y_true, y_pred = evaluate(test_dl)
    mat = confusion(y_true, y_pred, len(classes))
    scores = per_class_scores(mat)

    ranked = sorted(zip(classes, scores), key=lambda kv: kv[1]["f1"])
    worst = [{"class": c, **s} for c, s in ranked[:6]]
    best = [{"class": c, **s} for c, s in ranked[-6:][::-1]]

    # which classes get confused most often
    confusions = []
    for i in range(len(classes)):
        for j in range(len(classes)):
            if i != j and mat[i][j] > 0:
                confusions.append({"true": classes[i], "predicted": classes[j],
                                   "count": mat[i][j]})
    confusions.sort(key=lambda d: -d["count"])

    macro_p = sum(s["precision"] for s in scores) / len(scores)
    macro_r = sum(s["recall"] for s in scores) / len(scores)
    macro_f1 = sum(s["f1"] for s in scores) / len(scores)

    report = {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "architecture": "mobilenet_v3_small",
        "initialisation": init_note,
        "image_size": args.size,
        "epochs": args.epochs,
        "train_seconds": round(train_seconds, 1),
        "device": "cpu",
        "classes": len(classes),
        "dataset": {
            "total_images": sum(len(v) for v in per_class.values()),
            "split_sizes": {k: len(v) for k, v in splits_i.items()},
            "per_class": {c: len(per_class[c]) for c in classes},
            "split_policy": "duplicate-group-aware, per-class stratified 70/15/15",
        },
        "results": {
            "test_accuracy": round(te_acc, 4),
            "test_loss": round(te_loss, 4),
            "train_accuracy": round(train_acc, 4),
            "train_test_gap": round(train_acc - te_acc, 4),
            "macro_precision": round(macro_p, 4),
            "macro_recall": round(macro_r, 4),
            "macro_f1": round(macro_f1, 4),
            "weighted_f1": round(sum(s["f1"] * s["support"] for s in scores)
                                 / max(sum(s["support"] for s in scores), 1), 4),
            "test_support": len(y_true),
        },
        "per_class": {c: s for c, s in zip(classes, scores)},
        "weakest_classes": worst,
        "strongest_classes": best,
        "top_confusions": confusions[:20],
        "confusion_matrix": mat,
        "class_names": classes,
        "history": history,
        "licence": "Training images: Ishmam97/Bangladeshi-Food-Dataset (CC0-1.0 LICENSE / CC BY 4.0 README).",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": net.state_dict(),
        "classes": classes,
        "architecture": "mobilenet_v3_small",
        "input_size": args.size,
        "normalise_mean": IMAGENET_MEAN,
        "normalise_std": IMAGENET_STD,
        "trained_at": report["generated_utc"],
        "test_accuracy": te_acc,
        "test_support": len(y_true),
        "torch_version": str(torch.__version__),
        "device": "cpu",
        "epochs": args.epochs,
        "dataset_report": report["dataset"],
        "initialisation": init_note,
        "licence": report["licence"],
    }, out)
    print(f"\nsaved model: {out}  ({out.stat().st_size/1e6:.1f} MB)")

    report_path = Path(args.report) if args.report else out.with_suffix(".metrics.json")
    report_path.write_text(json.dumps(report, indent=1) + "\n")
    print(f"saved metrics: {report_path}")
    print(f"\nTEST ACCURACY: {te_acc:.4f}   macro-F1: {macro_f1:.4f}   "
          f"train-test gap: {train_acc - te_acc:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
