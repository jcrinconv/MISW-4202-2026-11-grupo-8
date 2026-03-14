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

### Escenarios Simulados

Cada simulación ejecuta 5 escenarios diferentes:

| Escenario | Descripción | Comportamiento Esperado |
|-----------|-------------|------------------------|
| **normal_user** | Usuario legítimo con 3 requests en 1 minuto | Login exitoso, requests válidos |
| **bot_imperson** | Bot con 100 requests concurrentes | Detección de rate limit, posible bloqueo |
| **unauth_login** | 10 intentos de login con contraseña incorrecta | Detección de fuerza bruta, bloqueo |
| **geo_anomaly** | Login desde múltiples ubicaciones geográficas | Detección de anomalía geográfica |
| **token_replay** | (Si aplica) Reutilización de tokens | Detección de replay attack |

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

```sql
-- Ver todos los eventos de una simulación específica
SELECT * FROM audit_events 
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY created_at;

-- Ver eventos agrupados por tipo y estado
SELECT simulation_uuid, processor_type, event_type, status, COUNT(*) as total
FROM audit_events
GROUP BY simulation_uuid, processor_type, event_type, status
ORDER BY simulation_uuid, created_at;

-- Ver últimas 20 simulaciones
SELECT DISTINCT simulation_uuid, MIN(created_at) as started_at
FROM audit_events
GROUP BY simulation_uuid
ORDER BY started_at DESC
LIMIT 20;

-- Trazar una simulación completa
SELECT 
    created_at,
    user_id,
    processor_type,
    event_type,
    status,
    error_message
FROM audit_events
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY created_at;
```

### 2. SQLite - Auth Service

```bash
# Acceder al contenedor de auth
docker exec -it exp2_seguridad-auth-1 sqlite3 auth.db
```

**Consultas útiles:**

```sql
-- Ver eventos de autenticación de una simulación
SELECT * FROM auth_audit 
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY occurred_at;

-- Ver intentos de login fallidos
SELECT user, activity, status, detail, simulation_uuid, occurred_at
FROM auth_audit
WHERE status = 'FAILED' AND activity = 'login'
ORDER BY occurred_at DESC;

-- Ver usuarios bloqueados
SELECT user, activity, status, detail, simulation_uuid, occurred_at
FROM auth_audit
WHERE activity = 'block-user'
ORDER BY occurred_at DESC;
```

### 3. SQLite - Reservas Service

```bash
# Acceder al contenedor de reservas
docker exec -it exp2_seguridad-reservas-1 sqlite3 reservas.db
```

**Consultas útiles:**

```sql
-- Ver reservas de una simulación
SELECT id, method, path, simulation_uuid, received_at
FROM reserva_events
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY received_at;

-- Contar requests por simulación
SELECT simulation_uuid, COUNT(*) as total_requests
FROM reserva_events
GROUP BY simulation_uuid;
```

### 4. SQLite - Auth Anomaly Service

```bash
# Acceder al contenedor de auth-anomaly
docker exec -it exp2_seguridad-auth-anomaly-1 sh

# Eventos procesados
sqlite3 /data/events.db

# Anomalías detectadas
sqlite3 /data/anomalies.db
```

**Consultas útiles:**

```sql
-- En events.db: Ver eventos procesados de una simulación
SELECT user, activity, status, simulation_uuid, anomaly_count, occurred_at
FROM auth_events
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY occurred_at;

-- En anomalies.db: Ver anomalías detectadas
SELECT user, activity, rule, severity, reason, simulation_uuid, detected_at
FROM auth_anomalies
WHERE simulation_uuid = 'TU-UUID-AQUI'
ORDER BY detected_at;

-- Ver todas las anomalías con bloqueos
SELECT user, rule, severity, reason, notification_success, simulation_uuid
FROM auth_anomalies
WHERE notification_success = 1
ORDER BY detected_at DESC;
```

## Trazabilidad Completa: De Simulación a Bloqueo

Para rastrear el flujo completo de una simulación hasta un bloqueo:

### Paso 1: Iniciar simulación

```bash
# Lanzar las 5 simulaciones
curl -X POST http://localhost:8081/trigger
```

### Paso 2: Esperar procesamiento y obtener UUIDs (30-60 segundos)

```bash
sleep 60

# Obtener los UUIDs de las simulaciones recientes
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT DISTINCT simulation_uuid FROM audit_events ORDER BY created_at DESC LIMIT 5;"

# Guardar un UUID para consultas (reemplazar con uno de los obtenidos)
SIMULATION_UUID="tu-uuid-aqui"
```

### Paso 3: Consultar eventos en cada servicio

```bash
# 1. Eventos en users (MySQL)
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit \
  -e "SELECT created_at, user_id, processor_type, event_type, status FROM audit_events WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY created_at;"

# 2. Eventos en auth (SQLite)
docker exec -it exp2_seguridad-auth-1 sqlite3 auth.db \
  "SELECT occurred_at, user, activity, status, detail FROM auth_audit WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY occurred_at;"

# 3. Anomalías detectadas (SQLite)
docker exec -it exp2_seguridad-auth-anomaly-1 sqlite3 /data/anomalies.db \
  "SELECT detected_at, user, rule, severity, reason, notification_success FROM auth_anomalies WHERE simulation_uuid='$SIMULATION_UUID' ORDER BY detected_at;"
```

### Paso 4: Verificar bloqueos

```bash
# Ver usuarios bloqueados en esta simulación
docker exec -it exp2_seguridad-auth-1 sqlite3 auth.db \
  "SELECT user, detail, occurred_at FROM auth_audit WHERE simulation_uuid='$SIMULATION_UUID' AND activity='block-user';"
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
│     └─▶ Persiste en SQLite: auth_audit.simulation_uuid                       │
│     └─▶ Emite a Redis Stream con simulation_uuid                             │
│                                                                              │
│  3. auth-queue → auth-anomaly                                                │
│     └─▶ Reenvía payload completo con simulation_uuid                         │
│     └─▶ Persiste en SQLite: auth_events.simulation_uuid                      │
│     └─▶ Si anomalía: auth_anomalies.simulation_uuid                          │
│                                                                              │
│  4. auth-anomaly → auth (bloqueo)                                            │
│     └─▶ Notifica bloqueo con simulation_uuid                                 │
│     └─▶ Persiste en auth_audit con simulation_uuid                           │
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

## Troubleshooting

### Servicios no inician
```bash
# Ver logs detallados
docker-compose logs --tail=100

# Reiniciar un servicio específico
docker-compose restart auth-anomaly
```

### Base de datos no accesible
```bash
# Verificar que MySQL esté healthy
docker-compose ps mysql

# Verificar conexión
docker exec -it security-audit-db mysqladmin ping -u root -prootpass123
```

### Eventos no llegan a auth-anomaly
```bash
# Verificar Redis Stream
docker exec -it exp2_seguridad-redis-1 redis-cli XLEN reports

# Ver mensajes pendientes
docker exec -it exp2_seguridad-redis-1 redis-cli XRANGE reports - + COUNT 10
```
