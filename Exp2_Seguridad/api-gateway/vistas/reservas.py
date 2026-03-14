from flask import request
from flask_restful import Resource
import requests


class VistaReservas(Resource):
    def post(self):
        token = request.headers.get("X-Auth-Token")
        simulation_uuid = request.headers.get("X-Simulation-UUID")
        auth_response = requests.post(
            "http://auth:8080/validate",
            timeout=5,
            json={"X-Auth-Token": token},
            headers={"X-Simulation-UUID": simulation_uuid} if simulation_uuid else {},
        )

        if not str(auth_response.status_code).startswith("2"):
            return auth_response.json(), auth_response.status_code

        reserva_headers = {"X-Auth-Token": token}
        if simulation_uuid:
            reserva_headers["X-Simulation-UUID"] = simulation_uuid

        reserva_response = requests.post(
            "http://reservas:8080/reservas",
            timeout=5,
            headers=reserva_headers,
            json=request.get_json(silent=True) or {},
        )

        return reserva_response.json(), reserva_response.status_code
