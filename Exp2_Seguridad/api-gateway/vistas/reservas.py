from flask import request
from flask_restful import Resource
import requests


class VistaReservas(Resource):
    def post(self):
        token = request.headers.get("X-Auth-Token")
        forward_headers = {}
        for header_name in [
            "X-Simulation-UUID",
            "X-Geo",
            "X-Device-Id",
            "X-Client-IP",
            "X-Forwarded-For",
        ]:
            value = request.headers.get(header_name)
            if value:
                forward_headers[header_name] = value
        auth_response = requests.post(
            "http://auth:8080/validate",
            timeout=5,
            json={"X-Auth-Token": token},
            headers=forward_headers,
        )

        if not str(auth_response.status_code).startswith("2"):
            return auth_response.json(), auth_response.status_code

        reserva_headers = {"X-Auth-Token": token, **forward_headers}

        reserva_response = requests.post(
            "http://reservas:8080/reservas",
            timeout=5,
            headers=reserva_headers,
            json=request.get_json(silent=True) or {},
        )

        return reserva_response.json(), reserva_response.status_code
