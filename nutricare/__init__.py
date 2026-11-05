"""NutriCare app factory."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, render_template

from . import db
from .api import api
from .vision_api import vision_api


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__,
                template_folder=str(Path(__file__).parent.parent / "templates"),
                static_folder=str(Path(__file__).parent.parent / "static"))
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    app.config["JSON_SORT_KEYS"] = False
    # Lax keeps the local-profile session across refreshes and same-site
    # navigation (the default None is rejected by browsers without Secure).
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    if test_config:
        app.config.update(test_config)

    app.register_blueprint(api)
    # AI Food Scanner endpoints live in their own blueprint (/api/vision) so the
    # existing /api surface is untouched. The recognition model itself is lazily
    # loaded on the first prediction, so startup never depends on the ML stack.
    app.register_blueprint(vision_api)
    # 8 MB image uploads by default; nginx/proxy limits should match.
    app.config.setdefault("MAX_CONTENT_LENGTH", 12 * 1024 * 1024)
    app.teardown_appcontext(db.close_db)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # Schema setup + legacy migration + shared (non-personal) food dataset.
    # NO demo data and NO user is created here: first run shows onboarding and
    # every new account starts genuinely empty. Fictional sample data exists
    # only behind the explicitly labelled demo mode (/api/demo/load).
    with app.app_context():
        conn = db.connect()
        try:
            db.migrate_legacy(conn)  # no-op unless a v1 database is present
            db.init_db(conn)
            db.seed_foods(conn)
        finally:
            conn.close()
    return app
