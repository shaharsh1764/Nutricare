# V2 dataset preparation report

Generated 2026-11-08T11:07:07Z. Seed 42.

## The six counts

These are different numbers and must never be collapsed. Only the last column is a training-image count.

| Class | 1 discovered | 2 metadata | 3 rights | 4 reviewed | 5 approved | 6 usable |
|---|---|---|---|---|---|---|
| roti | 14 | 14 | 2 | 14 | 7 | 0 |
| idli | 14 | 14 | 1 | 14 | 7 | 0 |

Classes prepared: **2**. Classes ready for training: **0**. Usable images: **0**.

Leak-free: **False**.

## Why counts are zero

- training_usable requires local image bytes, a passing decode check and a human approval; without --images every count 6 is zero by design
- exact duplicates are detected from page id, SHA1 and normalised title; near duplicates additionally need decoded pixels
- cross-class duplicates are a label conflict for a human to resolve, not something this tool resolves silently
- no rights conclusion is drawn: tiers reflect the declared licence only
