"""Flask application factory for the monitor service."""

from flask import Flask

from config import config_by_name
from monitor.modelos.modelos import db
from monitor.monitor import monitor_bp


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    config_class = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_class)

    db.init_app(app)

    if app.config.get("CREATE_SCHEMA_ON_STARTUP"):
        with app.app_context():
            db.create_all()

    app.register_blueprint(monitor_bp, url_prefix="/api/monitor")

    return app
