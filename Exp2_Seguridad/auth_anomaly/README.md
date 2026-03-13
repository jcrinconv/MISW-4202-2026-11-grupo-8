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
  "occurred_at": "2026-03-11T15:00:00Z"
}
```

## Configuración (variables de entorno)

| Variable | Descripción | Default |
| -------- | ----------- | ------- |
| `AUTH_SERVICE_BASE_URL` | URL base del componente Auth | `http://auth:5000` |
| `AUTH_BLOCK_ENDPOINT` | Ruta relativa para bloquear usuarios | `/block-user` |
| `AUTH_NOTIFY_ENABLED` | Habilita/inhabilita notificación real | `true` |
| `AUTH_FAILURE_THRESHOLD` | Fallos consecutivos para disparar alerta | `3` |
| `AUTH_FAILURE_WINDOW_SECONDS` | Ventana para la regla de fallos | `60` |
| `AUTH_MULTI_IP_THRESHOLD` | Cantidad de IPs únicas para alertar | `3` |
| `AUTH_MULTI_IP_WINDOW_SECONDS` | Ventana para multi IP | `90` |
| `AUTH_TOKEN_REPLAY_TTL_SECONDS` | TTL para detectar reutilización de token | `180` |
| `AUTH_DETECTION_SLA_MS` | SLA máximo aceptado | `2000` |
| `AUTH_DATA_DIR` | Carpeta donde se guardan las BD SQLite por defecto | `<repo>/auth_anomaly_data` |
| `AUTH_EVENTS_DB_URL` | URL SQLAlchemy para la BD de eventos | `sqlite:///<AUTH_DATA_DIR>/auth_events.db` |
| `AUTH_ANOMALIES_DB_URL` | URL SQLAlchemy para la BD de anomalías | `sqlite:///<AUTH_DATA_DIR>/auth_anomalies.db` |
| `AUTH_CREATE_SCHEMA_ON_STARTUP` | Crear tablas automáticamente al iniciar | `true` |
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

Estas tablas permiten auditar el SLA de 2 segundos. Ejemplo usando SQLite:

```bash
sqlite3 auth_anomaly_data/auth_events.db \\
  'SELECT COUNT(*), AVG(processing_time_ms) FROM auth_events WHERE anomaly_count > 0;'
```

O para revisar las anomalías detectadas:

```bash
sqlite3 auth_anomaly_data/auth_anomalies.db \\
  'SELECT user, rule, latency_ms, notification_success FROM auth_anomalies ORDER BY detected_at DESC LIMIT 10;'
```

Con esto puedes demostrar que cada detección tardó < 2000 ms y que la notificación fue enviada exitosamente.

## Escenarios de prueba recomendados

- **Fuerza bruta (fallos)**: enviar 3 `login` fallidos para un mismo usuario y observar la regla `repeated_failures`.
- **Multi-IP**: simular fallos desde IPs distintas enviando la IP en el campo `metadata.ip`. Ejemplo de payload para cada evento:
  ```json
  {
    "user": "bob",
    "activity": "login",
    "status": "failed",
    "metadata": { "ip": "10.0.0.X", "geo": "MX" }
  }
  ```
  Repite cambiando `X` para alcanzar el umbral configurado.
- **Replay de token**: reutilizar el mismo `auth_token` con dos usuarios distintos.
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

## Extensión de reglas

1. Crear una clase que herede de `BaseRule` en `auth_anomaly/rules.py`.
2. Implementar `async evaluate(...)` retornando `AnomalyDecision` cuando corresponda.
3. Registrar la regla en `build_rules` (`auth_anomaly/app.py`).
