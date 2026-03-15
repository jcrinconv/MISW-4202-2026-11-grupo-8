# Experimento 2: Seguridad - Sistema de Detección de Anomalías

Sistema de microservicios para simulación y detección de anomalías en autenticación, con trazabilidad completa mediante `simulation_uuid`.

## Arquitectura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   users     │────▶│ api-gateway │────▶│    auth     │
│ (simulador) │     │   :5001     │     │   :8082     │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
      │                    │                   │
      │                    ▼                   ▼
      │             ┌─────────────┐     ┌─────────────┐
      │             │  reservas   │     │    Redis    │
      │             │   :8080     │     │   :6379     │
      │             └─────────────┘     └──────┬──────┘
      │                                        │
      ▼                                        ▼
┌─────────────┐                         ┌─────────────┐
│    MySQL    │                         │ auth-queue  │
│   :3306     │                         └──────┬──────┘
└─────────────┘                                │
                                               ▼
                                        ┌─────────────┐
                                        │auth-anomaly │
                                        │   :6005     │
                                        └─────────────┘
```

## Requisitos

- Docker y Docker Compose
- (Opcional) Cliente MySQL para consultas

## Levantar el Proyecto

```bash
# Desde el directorio Exp2_Seguridad
docker-compose up --build -d

# Verificar que todos los servicios estén corriendo
docker-compose ps

# Ver logs de todos los servicios
docker-compose logs -f

# Ver logs de un servicio específico
docker-compose logs -f users
docker-compose logs -f auth-anomaly
```

### Verificar Salud de Servicios

```bash
# API Gateway
curl http://localhost:5001/health

# Auth
curl http://localhost:8082/health

# Reservas
curl http://localhost:8080/health

# Auth Anomaly
curl http://localhost:6005/health
```

## Lanzar Simulaciones

El servicio `users` expone un endpoint para iniciar simulaciones de diferentes escenarios de seguridad.

### Iniciar una Simulación

```bash
# Lanzar simulación (ejecuta 5 escenarios, cada uno con un UUID único)
curl -X POST http://localhost:8081/trigger
```

> **¡IMPORTANTE!**
> Al finalizar cada simulación, ejecuta este curl para desbloquear usuarios y evitar que
> los bloqueos persistan entre simulaciones:
>
> ```bash
> curl -X POST http://localhost:8082/unblock-users \
>   -H "Content-Type: application/json" \
>   -d '{"simulation_uuid": "<UUID-SI-LO-TIENES>"}'
> ```
>
> Si no tienes el UUID, puedes omitirlo (se desbloquean todos los usuarios bloqueados):
>
> ```bash
> curl -X POST http://localhost:8082/unblock-users
> ```

### Escenarios Simulados

Cada simulación ejecuta 5 escenarios diferentes:

| Escenario | Descripción | Comportamiento Esperado |
|-----------|-------------|------------------------|
| **normal_user** | Usuario legítimo con 3 requests en 1 minuto | Login exitoso, requests válidos |
| **bot_imperson** | Bot con 100 requests concurrentes | Detección de rate limit, posible bloqueo |
| **unauth_login** | 10 intentos de login con contraseña incorrecta | Detección de fuerza bruta, bloqueo |
| **geo_anomaly** | Login desde múltiples ubicaciones geográficas | Detección de anomalía geográfica |
| **token_replay** | (Si aplica) Reutilización de tokens | Detección de replay attack |

## Casos que detecta actualmente `Auth_Anomaly`

El microservicio `Auth_Anomaly` consume únicamente eventos publicados por `auth` en Redis y reenviados por `auth-queue` al endpoint `POST /auth-event`.

### Reglas activas

| Regla | Qué evalúa | Umbral por defecto | Fuente de eventos |
|-------|------------|--------------------|-------------------|
| **repeated_failures** | Fallos repetidos para la misma actividad (`login`, `validate`) | 3 fallos en 60s | `auth` |
| **multi_ip_bruteforce** | 2 requests consecutivos de la misma actividad, misma simulación y países diferentes | 2 eventos en 60s | `auth` |
| **rate_limit** | Alta frecuencia de eventos exitosos para actividades configuradas | 30 eventos `validate` exitosos en 60s | `auth` |
| **token_replay** | Reutilización del mismo token por usuarios distintos | TTL 180s | `auth` |

### Obtener los UUIDs de Simulación

Las simulaciones se ejecutan en background. Para obtener los `simulation_uuid` generados, consulta la base de datos:

```bash
# Ver las últimas simulaciones iniciadas
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT DISTINCT simulation_uuid, MIN(created_at) as started_at FROM audit_events GROUP BY simulation_uuid ORDER BY started_at DESC LIMIT 10;"
```

## Consultar Bases de Datos

### 1. MySQL - Auditoría de Users (Puerto 3306)

```bash
# Conectar a MySQL
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit
```

**Consultas útiles:**

- **Resumen por simulación**
  - Muestra el estado general de cada simulación y cuántos eventos terminaron en `success`, `error` o `blocked`.

  ```sql
  SELECT 
      simulation_uuid,
      processor_type AS simulation_type,
      CASE
          WHEN SUM(CASE WHEN simulation_status = 'finished' THEN 1 ELSE 0 END) > 0 THEN 'finished'
          ELSE 'running'
      END AS simulation_status,
      MIN(created_at) AS started_at,
      MAX(created_at) AS ended_at,
      COUNT(*) AS total_events,
      SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
      SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
      SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS blocked
  FROM audit_events
  WHERE simulation_uuid IS NOT NULL
  GROUP BY simulation_uuid, processor_type
  ORDER BY started_at DESC;
  ```

- **Distribución de eventos por simulación**
  - Sirve para ver qué `event_type` y qué `status` se registraron dentro de cada simulación.

  ```sql
  SELECT 
      simulation_uuid,
      processor_type AS simulation_type,
      event_type,
      status,
      COUNT(*) AS total
  FROM audit_events
  WHERE simulation_uuid IS NOT NULL
  GROUP BY simulation_uuid, processor_type, event_type, status
  ORDER BY simulation_uuid, processor_type, event_type, status;
  ```

- **Timeline reciente**
  - Lista los últimos eventos para seguir el orden en que avanzó la trazabilidad.

  ```sql
  SELECT 
      simulation_uuid,
      processor_type AS simulation_type,
      simulation_status,
      created_at,
      user_id,
      event_type,
      status
  FROM audit_events
  WHERE simulation_uuid IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 50;
  ```

### 2. MySQL - Auth Anomaly (auth_anomaly_events y auth_anomaly_anomalies)

```bash
# Conectar a MySQL
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit
```

**Consultas útiles:**

- **Eventos procesados por el detector**
  - Permite revisar qué eventos recibió `auth-anomaly` y cuánto tardó en procesarlos.

  ```sql
  SELECT user, activity, status, simulation_uuid, processing_time_ms, anomaly_count, received_at
  FROM auth_anomaly_events
  ORDER BY received_at DESC
  LIMIT 10;
  ```

- **Anomalías detectadas**
  - Muestra las decisiones del motor de reglas y la latencia con la que fueron detectadas.

  ```sql
  SELECT user, activity, rule, severity, reason, simulation_uuid, latency_ms, detected_at
  FROM auth_anomaly_anomalies
  ORDER BY detected_at DESC
  LIMIT 10;
  ```

- **Bloqueos/notificaciones emitidas**
  - Ayuda a confirmar si una anomalía terminó en una notificación exitosa hacia `auth`.

  ```sql
  SELECT user, activity, rule, severity, simulation_uuid, detected_at, notification_success, notification_detail
  FROM auth_anomaly_anomalies
  WHERE notification_success = 1
  ORDER BY detected_at DESC
  LIMIT 10;
  ```

### 3. MySQL - Auth Service (auth_audit)

```bash
# Conectar a MySQL
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit
```

**Consultas útiles:**

- **Eventos de autenticación de una simulación**
  - Sirve para seguir el flujo de `login`, `validate`, `block-user` y `unblock-user` para un `simulation_uuid` específico.

  ```sql
  SELECT user, activity, status, detail, auth_id, simulation_uuid, occurred_at
  FROM auth_audit 
  WHERE simulation_uuid = 'TU-UUID-AQUI'
  ORDER BY occurred_at;
  ```

- **Intentos de login fallidos**
  - Muestra credenciales inválidas o solicitudes incompletas registradas por el servicio de autenticación.

  ```sql
  SELECT user, activity, status, detail, simulation_uuid, occurred_at
  FROM auth_audit
  WHERE activity = 'login' AND status = 'FAILED'
  ORDER BY occurred_at DESC;
  ```

- **Bloqueos ejecutados sobre usuarios**
  - Permite verificar cuándo `auth` recibió y aplicó un bloqueo a un usuario.

  ```sql
  SELECT user, activity, status, detail, simulation_uuid, occurred_at
  FROM auth_audit
  WHERE activity = 'block-user'
  ORDER BY occurred_at DESC;
  ```

**Respuesta cuando un usuario está bloqueado:**

- `POST /login` → `403`
  ```json
  {"message": "Usuario bloqueado", "reason": "<blocked_reason>"}
  ```
- `POST /validate` → `403`
  ```json
  {"message": "Usuario bloqueado", "valid": false, "reason": "blocked_user"}
  ```

### 4. SQLite - Reservas Service

 ```bash
 # La imagen no incluye el binario sqlite3; usa el intérprete de Python
 docker exec -it exp2_seguridad-reservas-1 python
 ```

 Dentro del intérprete puedes abrir la base y ejecutar consultas sin problemas de comillas de PowerShell:

Recomendación: Una vez dentro del contenedor, ejecutar 1x1 las siguientes líneas. Luego ajustar las consultas de SQL acorde a lo que se quiera validar.

 ```python
 import sqlite3
 conn = sqlite3.connect("reservas.db")
 cursor = conn.cursor()
 cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;").fetchall()
 ```

 **Consultas útiles:**

- **Reservas recibidas por simulación**
  - Muestra cada request persistida por el servicio `reservas` con su método, ruta y momento de recepción.

  ```sql
  SELECT id, method, path, simulation_uuid, received_at
  FROM reserva_events
  WHERE simulation_uuid = 'TU-UUID-AQUI'
  ORDER BY received_at;
  ```

- **Volumen de requests por simulación**
  - Resume cuántas llamadas recibió `reservas` para cada simulación.

  ```sql
  SELECT simulation_uuid, COUNT(*) AS total_requests
  FROM reserva_events
  GROUP BY simulation_uuid
  ORDER BY simulation_uuid;
  ```

  En el intérprete de Python:

  ```python
  cursor.execute("SELECT simulation_uuid, COUNT(*) AS total_requests FROM reserva_events GROUP BY simulation_uuid ORDER BY simulation_uuid;").fetchall()
  ```

  ```bash
  docker exec -it exp2_seguridad-reservas-1 python -c "import sqlite3; conn = sqlite3.connect('reservas.db'); print(conn.execute('SELECT simulation_uuid, COUNT(*) AS total_requests FROM reserva_events GROUP BY simulation_uuid ORDER BY simulation_uuid;').fetchall())"
  ```

## Trazabilidad Completa: De Simulación a Bloqueo

Para rastrear el flujo completo de una simulación hasta un bloqueo:

### Paso 1: Iniciar simulación

```bash
# Lanzar las 5 simulaciones
curl -X POST http://localhost:8081/trigger
```

### Paso 2: Esperar procesamiento y obtener UUIDs (120 segundos)

```bash
sleep 120

# Obtener los UUIDs de las simulaciones recientes
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT simulation_uuid, MAX(created_at) AS last_seen FROM audit_events WHERE simulation_uuid IS NOT NULL GROUP BY simulation_uuid ORDER BY last_seen DESC LIMIT 5;"

# Guardar un UUID para consultas (reemplazar con uno de los obtenidos)
SIMULATION_UUID="tu-uuid-aqui"
```

### Paso 3: Consultar eventos en cada servicio

```bash
# 1. Eventos en users (MySQL)
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT created_at, user_id, processor_type, event_type, status FROM audit_events WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY created_at;"

# 2. Eventos en auth (MySQL)
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT occurred_at, user, activity, status, detail FROM auth_audit WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY occurred_at;"

# 3. Anomalías detectadas (MySQL)
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT detected_at, user, rule, severity, reason, notification_success FROM auth_anomaly_anomalies WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY detected_at;"
```

### Paso 4: Verificar bloqueos

```bash
# Ver usuarios bloqueados en esta simulación
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT user, detail, occurred_at FROM auth_audit WHERE simulation_uuid='$SIMULATION_UUID' AND activity='block-user' ORDER BY occurred_at;"
```

## Flujo de Datos con simulation_uuid

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO DE TRAZABILIDAD                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. users genera simulation_uuid (UUIDv4)                                    │
│     └─▶ Persiste en MySQL: audit_events.simulation_uuid                      │
 │                                                                              │
 │  2. users → api-gateway → auth (login)                                       │
 │     └─▶ metadata.simulation_uuid en body JSON                                │
 │     └─▶ Persiste en MySQL: auth_audit.simulation_uuid                        │
 │     └─▶ Emite a Redis Stream con simulation_uuid                             │
 │                                                                              │
 │  3. auth-queue → auth-anomaly                                                │
 │     └─▶ Reenvía payload completo con simulation_uuid                         │
 │     └─▶ Persiste en MySQL: auth_anomaly_events.simulation_uuid               │
 │     └─▶ Si anomalía: auth_anomaly_anomalies.simulation_uuid                  │
 │                                                                              │
 │  4. auth-anomaly → auth (bloqueo)                                            │
 │     └─▶ Notifica bloqueo con simulation_uuid                                 │
 │     └─▶ Persiste en MySQL: auth_audit.simulation_uuid                        │
 │                                                                              │
 │  5. users → api-gateway → reservas                                           │
 │     └─▶ Header X-Simulation-UUID + body.simulation_uuid                      │
 │     └─▶ Persiste en SQLite: reserva_events.simulation_uuid                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Detener el Proyecto

```bash
# Detener todos los servicios
docker-compose down

# Detener y eliminar volúmenes (borra datos)
docker-compose down -v
```

## Puertos Expuestos

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| api-gateway | 5001 | Gateway principal |
| auth | 8082 | Servicio de autenticación |
| reservas | 8080 | Servicio de reservas (mock) |
| auth-anomaly | 6005 | Detector de anomalías |
| users | 8081 | Simulador de usuarios |
| MySQL | 3306 | Base de datos de auditoría |
| Redis | 6379 | Message broker |

