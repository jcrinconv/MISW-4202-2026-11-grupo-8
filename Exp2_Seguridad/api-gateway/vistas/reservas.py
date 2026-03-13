from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
import requests


class VistaReservas(Resource):
    def post(self):
        token = request.headers.get("X-Auth-Token")
        response = requests.post(
            "http://auth:8080/validate",
            timeout=5,
            json={"X-Auth-Token": token},
        )
        print(response.status_code)
        if str(response.status_code).startswith("2"):
            return response.json(), response.status_code
        else:
            response = requests.post(
                "http://reservas:8080/reservas",
                timeout=5,
                json={"X-Auth-Token": token},
            )

            return response.json(), response.status_code
