from flask import request
from flask_restful import Resource
import requests


class VistaLogin(Resource):
    def post(self):
        body = request.get_json()
        response = requests.post("http://auth:8080/login", json=body, timeout=5)
        return response.json(), response.status_code
