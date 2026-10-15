"""Flask web app: a JSON API and a dashboard over the pipeline's output.

    flask --app fx_etl.web run                       # development
    gunicorn "fx_etl.web:create_app()"               # production
"""

from __future__ import annotations

from flask import Flask, render_template

from .. import __version__, load
from ..config import Settings, get_settings
from ..logging_config import configure_logging


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config["FX_SETTINGS"] = settings
    app.json.sort_keys = False

    engine = load.get_engine(settings.database_url)
    load.init_db(engine)
    app.extensions["fx_engine"] = engine

    from .api import bp as api_bp

    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return render_template("index.html", version=__version__, settings=settings)

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app
