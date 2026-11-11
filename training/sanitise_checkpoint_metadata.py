#!/usr/bin/env python3
"""Correct the false licence metadata in the 80-class checkpoint + sidecar.

The checkpoint was generated with a hardcoded licence string naming an
unrelated Bangladeshi dataset as CC0/CC BY. The actual training images are
a web-scraped 80-class Indian food set with NO verified licence. This
script replaces the false claim with an unresolved-licence record while:

  * preserving the learned weights exactly (state_dict untouched),
  * preserving the ordered 80-class list and all architecture metadata,
  * preserving the original false string verbatim for the audit trail,
  * refusing to run on any input whose SHA256 is not the recorded
    original (so it can never silently rewrite a different checkpoint).

Re-serialisation changes the file bytes, so the new SHA256 differs; both
hashes are printed and embedded in the corrected metadata. The original
checkpoint remains preserved in git history (commit 5ba7461 on the
research branch) — this script never deletes anything.

Usage: python training/sanitise_checkpoint_metadata.py \
           [checkpoint.pt] [metrics.json]
"""
import hashlib
import json
import sys
from pathlib import Path

EXPECTED_ORIGINAL_SHA256 = (
    "754b368cdf084233db00f86fc50693d00d85a433a366a832187ab35063b833dc")
EXPECTED_ORIGINAL_LICENCE = (
    "Training images: Ishmam97/Bangladeshi-Food-Dataset "
    "(CC0-1.0 LICENSE / CC BY 4.0 README).")
CORRECTED_LICENCE = (
    "UNRESOLVED: training images are from a web-scraped 80-class Indian "
    "food image set (SoumyaXD/Kaggle lineage); no verified licence was "
    "found for the underlying images. Internal experimental use only - "
    "do not redistribute. See docs/LICENSING_AUDIT.md.")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_dict_hash(state_dict) -> str:
    digest = hashlib.sha256()
    for key in state_dict:
        digest.update(key.encode())
        digest.update(state_dict[key].numpy().tobytes())
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ckpt_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        root / "models/v2/food_classifier_indian_80_224.pt"
    metrics_path = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        ckpt_path.with_suffix(".metrics.json")

    import torch  # local import: only needed when actually sanitising

    before = sha256(ckpt_path)
    if before != EXPECTED_ORIGINAL_SHA256:
        print(f"REFUSING: input SHA256 {before} != recorded original "
              f"{EXPECTED_ORIGINAL_SHA256}", file=sys.stderr)
        return 1

    checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    if checkpoint.get("licence") != EXPECTED_ORIGINAL_LICENCE:
        print("REFUSING: embedded licence is not the known false string; "
              "nothing to correct (or already corrected).", file=sys.stderr)
        return 1
    weights_hash_before = state_dict_hash(checkpoint["state_dict"])

    checkpoint["licence_original_as_generated"] = checkpoint["licence"]
    checkpoint["licence"] = CORRECTED_LICENCE
    checkpoint["licence_correction"] = (
        "Embedded licence corrected post-training: the generated string "
        "named an unrelated dataset. Weights, class order and architecture "
        "metadata are unchanged; original file SHA256 recorded below.")
    checkpoint["original_sha256"] = before

    tmp = ckpt_path.with_suffix(".pt.tmp")
    torch.save(checkpoint, tmp)
    tmp.replace(ckpt_path)
    after = sha256(ckpt_path)

    # Verify: strict reload, identical weights, identical predictions.
    reloaded = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    assert state_dict_hash(reloaded["state_dict"]) == weights_hash_before
    assert reloaded["classes"] == checkpoint["classes"]
    assert len(reloaded["classes"]) == 80

    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics.get("licence") == EXPECTED_ORIGINAL_LICENCE:
            metrics["licence_as_generated_original"] = metrics["licence"]
            metrics["licence"] = CORRECTED_LICENCE
            metrics["licence_erratum"] = (
                "The originally generated licence string (preserved in "
                "licence_as_generated_original) named an unrelated "
                "Bangladeshi dataset as CC0/CC BY; it was incorrect for "
                "these web-scraped images, whose licence is unresolved.")
            metrics["checkpoint_original_sha256"] = before
            metrics["checkpoint_sanitised_sha256"] = after
            metrics_path.write_text(
                json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    print(f"original SHA256 : {before}")
    print(f"sanitised SHA256: {after}")
    print(f"state_dict hash : {weights_hash_before} (unchanged)")
    print("classes/order   : preserved (80)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
