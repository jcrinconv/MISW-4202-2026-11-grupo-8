# AuthAnomaly

Componente responsable de detectar comportamientos anómalos en el flujo de autenticación.

## Objetivo

- Recibir eventos `POST /auth-event` provenientes de la cola o gateway.
- Evaluar reglas en menos de **2 segundos** para cada usuario.
- Cuando detecta una anomalía, invoca `POST /block-user` del componente `Auth` con el detalle.
- Manejar múltiples autenticaciones concurrentes manteniendo el contexto por usuario.

## Arquitectura

```
Queue/API → AuthAnomaly (/auth-event) → Auth (/block-user)
                     │
                     ├─ Reglas en memoria (fallos consecutivos, multi IP, token replay)
                     └─ Métricas SLA + notificación HTTP
```

## Endpoints

| Método | Ruta | Descripción |
| ------ | ---- | ----------- |
| `GET` | `/health` | Estado general y configuración relevante |
| `GET` | `/rules` | Reglas activas y ventanas |
| `POST` | `/auth-event` | Ingresa un evento y espera la evaluación (202 Accepted) |

### Payload `/auth-event`

```json
{
  "user": "string",
  "activity": "login|validate|reservas",
  "status": "SUCCESS|FAILED|DENIED|...",
  "detail": "texto o JSON",
  "metadata": {"ip": "1.1.1.1", "device_id": "abc", "geo": "BOG"},
  "auth_token": "<JWT opcional>",
  "auth_id": "uuid opcional",
  "simulation_uuid": "uuid opcional de la simulación",
  "occurred_at": "2026-03-11T15:00:00Z"
}
```

Cada regla se evalúa sobre el conjunto `user + simulation_uuid`.
Esto evita que eventos históricos de simulaciones anteriores disparen bloqueos sobre una simulación nueva del mismo usuario.

## Configuración (variables de entorno)

| Variable | Descripción | Default |
| -------- | ----------- | ------- |
| `AUTH_SERVICE_BASE_URL` | URL base del componente Auth | `http://auth:5000` |
| `AUTH_BLOCK_ENDPOINT` | Ruta relativa para bloquear usuarios | `/block-user` |
| `AUTH_NOTIFY_ENABLED` | Habilita/inhabilita notificación real | `true` |
| `AUTH_DB_HOST` | Host de MySQL | `mysql` |
| `AUTH_DB_PORT` | Puerto de MySQL | `3306` |
| `AUTH_DB_NAME` | Base de datos | `security_audit` |
| `AUTH_DB_USER` | Usuario de MySQL | `audit_user` |
| `AUTH_DB_PASSWORD` | Password de MySQL | `secure_audit_pass_2024` |
| `AUTH_EVENTS_DB_URL` | URL SQLAlchemy para la BD de eventos | `mysql+pymysql://audit_user:***@mysql:3306/security_audit` |
| `AUTH_ANOMALIES_DB_URL` | URL SQLAlchemy para la BD de anomalías | `mysql+pymysql://audit_user:***@mysql:3306/security_audit` |
| `AUTH_CREATE_SCHEMA_ON_STARTUP` | Crear tablas automáticamente al iniciar | `true` |
| `AUTH_FAILURE_THRESHOLD` | Fallos consecutivos para disparar alerta | `3` |
| `AUTH_FAILURE_WINDOW_SECONDS` | Ventana para la regla de fallos | `60` |
| `AUTH_MULTI_IP_THRESHOLD` | Cantidad de requests consecutivos desde países distintos para alertar | `2` |
| `AUTH_MULTI_IP_WINDOW_SECONDS` | Ventana para la regla geo/multi país | `60` |
| `AUTH_TOKEN_REPLAY_TTL_SECONDS` | TTL para detectar reutilización de token | `180` |
| `AUTH_DETECTION_SLA_MS` | SLA máximo aceptado | `2000` |
| `AUTH_RATELIMIT_THRESHOLD` | Cantidad máxima de requests permitidos en la ventana | `30` |
| `AUTH_RATELIMIT_WINDOW_SECONDS` | Ventana temporal para RateLimitRule | `60` |
| `AUTH_RATELIMIT_ACTIVITIES` | Lista separada por comas de actividades a vigilar | `validate` |
| `AUTH_RATELIMIT_STATUSES` | Estados que cuentan para RateLimitRule | `success` |

## Ejecución local

```bash
cd auth_anomaly
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn auth_anomaly.app:app --reload --port 6005
```

## Pruebas

```bash
cd auth_anomaly
pytest
```

## Persistencia y validación del experimento

AuthAnomaly persiste automáticamente:

- **Eventos recibidos** en la tabla `auth_events` (BD `AUTH_EVENTS_DB_URL`) incluyendo `received_at`, `processed_at` y `processing_time_ms`.
- **Anomalías notificadas** en `auth_anomalies` (BD `AUTH_ANOMALIES_DB_URL`) junto con el resultado del intento de notificación (`notification_success` y `notification_detail`).

Estas tablas permiten auditar el SLA de 2 segundos. Ejemplo usando MySQL:

```bash
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT COUNT(*), AVG(processing_time_ms) FROM auth_events WHERE anomaly_count > 0;"
```

O para revisar las anomalías detectadas:

```bash
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT user, rule, latency_ms, notification_success FROM auth_anomalies ORDER BY detected_at DESC LIMIT 10;"
```

Con esto puedes demostrar que cada detección tardó < 2000 ms y que la notificación fue enviada exitosamente.

## Escenarios de prueba recomendados

- **Fuerza bruta (fallos)**: enviar 3 `login` fallidos para un mismo usuario y observar la regla `repeated_failures`.
- **Geo / Multi-país**: enviar 2 requests consecutivos de la misma actividad para el mismo usuario y la misma simulación, cambiando el país en `metadata.geo`.
  También puedes enviar la metadata vía headers (el autenticador la fusiona en el payload):
  `X-Client-IP`, `X-Geo`, `X-Device-Id`, `X-Simulation-UUID`.
  Ejemplo de payload para cada evento:
  ```json
  {
    "user": "bob",
    "activity": "validate",
    "status": "success",
    "simulation_uuid": "sim-geo-1",
    "metadata": { "ip": "10.0.0.X", "geo": "MX" }
  }
  ```
  Envía un segundo evento con el mismo `simulation_uuid` y otro país para disparar la regla.
- **Replay de token**: reutilizar el mismo `auth_token` con dos usuarios distintos dentro de la misma simulación.
- **Rate limit orgánico**: realizar más de `AUTH_RATELIMIT_THRESHOLD` solicitudes `validate` exitosas en la ventana (por defecto 30/min). Ejemplo rápido:

  ```bash
  python - <<'PY'
  import asyncio, datetime, httpx
  BASE = "http://127.0.0.1:6005"

  def payload(i):
      return {
          "user": "test-rate",
          "activity": "validate",
          "status": "success",
          "detail": f"call {i}",
          "occurred_at": datetime.datetime.utcnow().isoformat() + "Z",
      }

  async def main():
      async with httpx.AsyncClient() as client:
          for i in range(1, 32):
              resp = await client.post(f"{BASE}/auth-event", json=payload(i))
              print(i, resp.json()["anomalies"])

  asyncio.run(main())
  PY
  ```

  La petición número 30 generará una anomalía `rate_limit` y disparará la notificación al bloqueador.

## Reglas actuales

- **`repeated_failures`**
  - Detecta fallos repetidos de la misma actividad dentro de la ventana configurada.

- **`multi_ip_bruteforce`**
  - Detecta `AUTH_MULTI_IP_THRESHOLD` requests consecutivos de la misma actividad, para el mismo usuario y la misma simulación, desde países distintos.
  - Utiliza `metadata.geo` y complementa el diagnóstico con la IP más frecuente observada.

- **`rate_limit`**
  - Detecta actividad autenticada que supera el límite de interacción humana esperado, por defecto en `validate` exitosos.

- **`token_replay`**
  - Solo aplica si llega `auth_token` en el evento.
  - Su memoria también queda aislada por `simulation_uuid`.

## Extensión de reglas

1. Crear una clase que herede de `BaseRule` en `auth_anomaly/rules.py`.
2. Implementar `async evaluate(...)` retornando `AnomalyDecision` cuando corresponda.
3. Registrar la regla en `build_rules` (`auth_anomaly/app.py`).
