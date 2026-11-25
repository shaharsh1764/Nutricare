# Testing a pull request locally

A copy‑paste walkthrough for running this branch on your own machine and
checking the Food Scanner's refusal behaviour by hand.

The current PR for the scanner work is **#21**:
[shaharsh1764/Nutricare#21](https://github.com/shaharsh1764/Nutricare/pull/21)

> **Do not use `pull/20`.** PR #20 was closed without merging and contains only
> the earlier catalogue and interface work — it does **not** include the scanner
> changes. Its tip is `cb8bec4`; the scanner work is `e8b0088`.

---

## 1. Go to your existing clone

```powershell
cd path\to\Nutricare
```

Use PowerShell, Git Bash, or any terminal — the commands are the same
everywhere.

## 2. Fetch PR #21

```powershell
git fetch origin pull/21/head:pr-21-scanner
```

This downloads the PR into a local branch you own. It does not touch `main` or
any branch you already have.

## 3. Switch to the PR branch

```powershell
git switch pr-21-scanner
```

## 4. Verify you are on the right code

```powershell
git log --oneline -1
```

You should see exactly:

```text
e8b0088 Scanner: refuse unusable images and raise the confidence gate to 40%
```

If the hash is different, you are on the wrong ref — check step 2.

## 5. Install dependencies

The scanner needs machine‑learning libraries that the basic requirements file
deliberately leaves out. **Without them the scanner is disabled and you cannot
test this PR.**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then install the scanner dependencies. **The `--no-cache-dir` flag matters** —
without it pip downloads several gigabytes of NVIDIA CUDA libraries you will
never use:

```powershell
pip install --no-cache-dir "torch>=2.0,<3" "torchvision>=0.15,<1" "Pillow>=10,<14"
```

On macOS or Linux the activation line is `source .venv/bin/activate`.

Optional, much smaller, CPU‑only build (good if you have no NVIDIA GPU):

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

## 6. Run the tests

```powershell
pytest -q
```

You should see:

```text
1209 passed
```

If you instead see a large number of failures mentioning `torch` or
`ModuleNotFoundError`, step 5 did not complete — the scanner tests are skipped or
erroring because the ML extras are missing.

## 7. Start the app

```powershell
python app.py
```

Open <http://127.0.0.1:5055>, create a local profile on the welcome screen, then
open **Food Scanner** in the sidebar.

## 8. Check the behaviour by hand

Upload these and confirm what the scanner says:

| Upload | Expected result |
| --- | --- |
| A blank image (solid white or grey) | “This image doesn’t look like a photo of food.” |
| A smooth gradient or a wall | Same refusal as above |
| A realistic photo of a single dish | A suggestion, or an honest “couldn’t recognize” |

The old behaviour — before this branch — was to answer a **blank white image
with “Lassi, 89.9% confident”**. If you see a food name for a blank image, the
new code is not running.

When you are done, get back to your normal branch:

```powershell
git switch main
```

---

## Cheat sheet

| Goal | Command |
| --- | --- |
| Fetch PR #21 | `git fetch origin pull/21/head:pr-21-scanner` |
| Switch to it | `git switch pr-21-scanner` |
| Confirm the commit | `git log --oneline -1` → `e8b0088` |
| Run tests | `pytest -q` → `1209 passed` |
| Run the app | `python app.py` → <http://127.0.0.1:5055> |
| Return to main | `git switch main` |
| Delete the test branch | `git branch -D pr-21-scanner` |

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `error: could not find remote ref pull/21/head` | Wrong PR number, or the PR was closed and deleted. Use `gh pr list` or check the PR page. |
| Scanner says recognition is switched off | The ML extras from step 5 are missing. |
| `No space left on device` during pip install | Re‑run step 5 with `--no-cache-dir`; on Windows also clear `%LOCALAPPDATA%\pip\Cache`. |
| Tests pass but the UI looks green and old | You are on `main`, not `pr-21-scanner`. Check step 4. |
| `1209 passed` but fewer than 1200 collected | Some tests are skipped because the model files or ML extras are absent. |

## Why not simply clone the branch?

`git clone --branch arena/872f2a84-nutricare` works too, and is the simplest
route for a first look. The `git fetch pull/21/head` flow above is better when
you already have a clone, because it adds the PR as a normal local branch you
can switch to and delete without disturbing anything else.
