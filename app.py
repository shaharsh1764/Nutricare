"""NutriCare entry point.

Run with:  python app.py
Then open: http://localhost:5000
"""

import os
from pathlib import Path

from nutricare import create_app


def load_dotenv(path: Path | None = None):
    """Tiny .env loader (no extra dependency). Existing env vars win."""
    path = path or Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
