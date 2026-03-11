"""Monitor blueprint package."""

from flask import Blueprint

monitor_bp = Blueprint("monitor", __name__)

from . import routes  # noqa: E402,F401 keeps blueprint routes registered
