# MISW-4202 — Grupo 8: Sistema de Monitoreo de Pagos

## Descripción general

Este repositorio simula un sistema distribuido donde múltiples servicios de pagos reportan su estado de salud a través de una cola de mensajes hacia un servicio de monitoreo centralizado.

---

## Arquitectura y flujo

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  payments-a │     │  payments-b │     │  payments-c │
│  :5000      │     │  :5010      │     │  :5020      │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │   xadd("reports") │                   │
       └───────────────────┴───────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │  stream:    │
                    │  "reports"  │
                    └──────┬──────┘
                           │ xreadgroup
                    ┌──────▼──────┐
                    │monitor-queue│
                    │  consumer   │
                    └──────┬──────┘
                           │ POST /api/monitor/heartbeats
                    ┌──────▼──────┐
                    │   monitor   │
                    │   :5001     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  monitor-db │
                    │  MySQL :3307│
                    └─────────────┘

       ┌─────────────┐
       │ payments-db │
       │ MySQL :3308 │  ← compartida por payments-a, b y c
       └─────────────┘
```

---

## Componentes

### `payments-a` / `payments-b` / `payments-c` (puerto 5000 / 5010 / 5020)

Simulan servicios de pagos independientes. Cada uno:

- Comparte la **misma base de datos MySQL** (`payments-db`) pero se identifica con un `SERVICE_NAME` distinto (`payments-a`, `payments-b`, `payments-c`).
- Al recibir `POST /report-windows`, genera una **ventana de monitoreo** con duración aleatoria (1–5 min) y tasas de error/omisión aleatorias.
- Lanza un hilo en background que, cada 10 segundos, publica un heartbeat en el **Redis stream `reports`** (o lo omite si el slot fue marcado como `no_reported`).
- Registra **auditoría local** en `payments-db` de cada tick: qué se envió, qué se omitió y cuál fue el estado.

**Endpoints:**
| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`  | `/health` | Estado del servicio |
| `POST` | `/report-windows` | Inicia una ventana de simulación |
| `GET`  | `/report-windows/<uuid>/stats` | Estadísticas de auditoría local |

---

### `monitor-queue`

Consumidor del Redis stream `reports`. Actúa como intermediario resiliente:

- Lee mensajes del stream usando **consumer groups** (garantiza que cada mensaje se procese exactamente una vez).
- Reenvía el payload al endpoint `POST /api/monitor/heartbeats` del servicio `monitor`.
- Implementa **reintentos con back-off exponencial** (hasta 12 intentos, máximo 5 min entre reintentos) ante fallos HTTP/red.
- Hace `XACK` al stream solo cuando el reenvío fue exitoso.

---

### `monitor` (puerto 5001)

Servicio de monitoreo centralizado. Recibe heartbeats y gestiona ventanas de observación:

- `POST /api/monitor/heartbeats` — ingesta un heartbeat, crea o actualiza la ventana correspondiente.
- `POST /api/monitor/windows/sweep` — cierra ventanas cuyo `window_to` ya pasó; marca como `ALERT` si faltan reportes.
- Persiste en **`monitor-db`** (MySQL) los modelos `MonitoringWindow` y `HeartbeatEvent`.
- Crea el esquema automáticamente al arrancar (`CREATE_SCHEMA_ON_STARTUP=true`).

---

### `redis`

Broker compartido. Transporta los heartbeats desde los servicios de pagos hacia `monitor-queue` mediante el stream `reports`.

---

### `monitor-db` / `payments-db`

Dos instancias MySQL 8 independientes:

| Instancia | Puerto host | Usado por |
|-----------|-------------|-----------|
| `monitor-db` | `3307` | `monitor` |
| `payments-db` | `3308` | `payments-a`, `payments-b`, `payments-c` |

---

## Levantar el sistema

### Requisitos previos

- Docker Desktop (o Docker Engine + Compose plugin)
- Puertos libres: `5002`, `5010`, `5020`, `5001`, `6379`, `3307`, `3308`

### Comandos

```bash
# Construir imágenes y levantar todos los servicios
docker compose up --build

# Solo levantar (si las imágenes ya están construidas)
docker compose up

# En background
docker compose up -d --build

# Ver logs de un servicio específico
docker compose logs -f monitor-queue
docker compose logs -f monitor

# Detener y eliminar contenedores
docker compose down

# Detener y eliminar contenedores + volúmenes (borra las BDs)
docker compose down -v
```

### Verificar que todo está corriendo

```bash
docker compose ps
```

### Disparar una ventana de simulación

```bash
# payments-a
curl -X POST http://localhost:5002/report-windows

# payments-b
curl -X POST http://localhost:5010/report-windows

# payments-c
curl -X POST http://localhost:5020/report-windows
```

### Cerrar ventanas expiradas manualmente en el monitor

```bash
curl -X POST http://localhost:5001/api/monitor/windows/sweep
```

---

## Consultar y comparar bases de datos

### Conectarse a las bases de datos

```bash
# payments-db (compartida por los 3 servicios de pagos)
docker compose exec payments-db mysql -upayments -ppayments payments

# monitor-db
docker compose exec monitor-db mysql -umonitor -pmonitor monitor
```

### Consultas útiles en `payments-db`

```sql
-- Todas las ventanas de simulación creadas (por servicio)
SELECT window_uuid, service, window_from, window_to,
       error_status_generado, error_status_no_reportado
FROM report_windows
ORDER BY window_from DESC;

-- Auditoría de ticks por ventana
SELECT window_uuid, service, status, sent_to_queue, timestamp
FROM report_audit
WHERE window_uuid = '<UUID>'
ORDER BY timestamp;

-- Resumen por ventana: enviados vs omitidos vs errores
SELECT
    window_uuid,
    service,
    COUNT(*)                                        AS total_ticks,
    SUM(sent_to_queue)                              AS enviados_a_queue,
    SUM(NOT sent_to_queue)                          AS omitidos,
    SUM(status LIKE 'error:%')                      AS errores,
    SUM(status = 'ok')                              AS ok
FROM report_audit
GROUP BY window_uuid, service
ORDER BY window_uuid;
```

### Consultas útiles en `monitor-db`

```sql
-- Ventanas de monitoreo registradas
SELECT window_uuid, service_name, status,
       expected_reports, received_reports, error_reports, missing_reports,
       window_from, window_to, closed_at
FROM monitoring_windows
ORDER BY created_at DESC;

-- Heartbeats recibidos por ventana
SELECT window_id, service_name, status, report_timestamp, error_message
FROM heartbeat_events
WHERE window_id = (
    SELECT id FROM monitoring_windows WHERE window_uuid = '<UUID>'
)
ORDER BY report_timestamp;
```

### Comparación payments vs monitor (misma ventana)

Ejecutar en `payments-db`:
```sql
SELECT
    window_uuid,
    service,
    COUNT(*)               AS ticks_auditados,
    SUM(sent_to_queue)     AS enviados_queue,
    SUM(NOT sent_to_queue) AS omitidos_local,
    SUM(status LIKE 'error:%') AS errores
FROM report_audit

GROUP BY window_uuid, service;
```

Ejecutar en `monitor-db`:
```sql
SELECT
    window_uuid,
    service_name,
    received_reports,
    error_reports,
    missing_reports,
    status
FROM monitoring_windows;
```

**Interpretación:**
- `enviados_queue` (payments) ≈ `received_reports` (monitor): diferencia indica mensajes perdidos en tránsito.
- `omitidos_local` (payments) ≈ `missing_reports` (monitor): el monitor detecta los ticks que nunca llegaron.
- Si `status = 'ALERT'` en monitor y `omitidos_local > 0` en payments, el sistema funcionó correctamente.
