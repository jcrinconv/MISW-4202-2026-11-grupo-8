from flask import Flask
from flask_cors import CORS
from flask_restful import Api
from vistas.login import VistaLogin
from vistas.reservas import VistaReservas

app = None


def create_flask_app():
    app = Flask(__name__)

    app_context = app.app_context()
    app_context.push()
    add_urls(app)
    CORS(
        app,
        origins="*",
    )

    return app


def add_urls(app):
    api = Api(app)
    api.add_resource(VistaLogin, "/login")
    api.add_resource(VistaReservas, "/reservas")


app = create_flask_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
