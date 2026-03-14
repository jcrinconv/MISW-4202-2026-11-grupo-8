from flask import request
from flask_restful import Resource
import requests


class VistaReservas(Resource):
    def post(self):
        token = request.headers.get("X-Auth-Token")
        auth_response = requests.post(
            "http://auth:8080/validate",
            timeout=5,
            json={"X-Auth-Token": token},
        )

        if not str(auth_response.status_code).startswith("2"):
            return auth_response.json(), auth_response.status_code

        reserva_response = requests.post(
            "http://reservas:8080/reservas",
            timeout=5,
            headers={"X-Auth-Token": token},
            json=request.get_json(silent=True) or {},
        )

        return reserva_response.json(), reserva_response.status_code
