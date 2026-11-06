#!/usr/bin/env python3
"""Obtain real ImageNet-pretrained MobileNetV3 weights when download.pytorch.org
is unreachable, by converting a GitHub-hosted checkpoint into torchvision's
key layout.

Why this exists
---------------
`torchvision.models.mobilenet_v3_small(weights=DEFAULT)` downloads from
download.pytorch.org, which may be blocked. Some research repositories commit
their ImageNet weights directly to GitHub, but with their own key names and
with 1x1 convolutions stored as `nn.Linear`.

This module bridges that gap deterministically:
  * keys are matched **by position** against torchvision's state_dict (the two
    architectures have the same 244 tensors in the same order — verified), and
  * the 18 `nn.Linear`-stored 1x1 convolutions are reshaped (out,in) -> (out,in,1,1).

It performs no guessing: every tensor is shape-checked after mapping, and the
function refuses to return a partial model. If the mapping does not line up
exactly, it raises instead of silently producing random weights.

Usage
-----
    python training/load_imagenet_backbone.py \
        --checkpoint mobilenetv3-small-55df8e1f.pth \
        --architecture mobilenet_v3_small \
        --out models/backbone_mobilenetv3_small.pth

The output file is a plain torchvision-format state_dict, usable as:
    model.load_state_dict(torch.load(out))
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def convert(external_state: dict, architecture: str) -> dict:
    """Map an external MobileNetV3 checkpoint onto torchvision's key layout."""
    import torchvision.models as models

    builders = {
        "mobilenet_v3_small": models.mobilenet_v3_small,
        "mobilenet_v3_large": models.mobilenet_v3_large,
    }
    if architecture not in builders:
        raise ValueError(f"unsupported architecture {architecture!r}")
    reference = builders[architecture](weights=None).state_dict()

    state = external_state.get("state_dict", external_state)
    state = {k.replace("module.", "", 1): v for k, v in state.items()}

    ref_keys, ext_keys = list(reference), list(state)
    if len(ref_keys) != len(ext_keys):
        raise ValueError(
            f"tensor count mismatch: torchvision has {len(ref_keys)}, "
            f"checkpoint has {len(ext_keys)} — refusing to guess a mapping")

    converted, reshaped = {}, 0
    for ref_key, ext_key in zip(ref_keys, ext_keys):
        tensor = state[ext_key]
        target_shape = reference[ref_key].shape
        if tuple(tensor.shape) != tuple(target_shape):
            if len(target_shape) == 4 and len(tensor.shape) == 2:
                out_c, in_c = tensor.shape
                if (out_c, in_c, 1, 1) != tuple(target_shape):
                    raise ValueError(f"{ext_key}: cannot reshape {tuple(tensor.shape)} "
                                     f"to {tuple(target_shape)}")
                tensor = tensor.reshape(out_c, in_c, 1, 1)
                reshaped += 1
            else:
                raise ValueError(f"{ext_key}: shape {tuple(tensor.shape)} does not "
                                 f"match torchvision {tuple(target_shape)}")
        converted[ref_key] = tensor

    # Final proof: load it into a real model. Anything less is wishful thinking.
    model = builders[architecture](weights=None)
    model.load_state_dict(converted, strict=True)
    print(f"  mapped {len(converted)} tensors "
          f"({reshaped} 1x1 convs reshaped from Linear) — strict load OK")
    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--architecture", default="mobilenet_v3_small",
                        choices=["mobilenet_v3_small", "mobilenet_v3_large"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    import torch
    src = Path(args.checkpoint)
    if not src.is_file():
        print(f"checkpoint not found: {src}")
        return 2
    print(f"Loading {src} ({src.stat().st_size / 1e6:.1f} MB) …")
    raw = torch.load(src, map_location="cpu", weights_only=False)
    converted = convert(raw, args.architecture)

    out = Path(args.out or PROJECT / "models" / f"backbone_{args.architecture}.pth")
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(converted, out)
    print(f"Saved torchvision-format backbone: {out} "
          f"({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
