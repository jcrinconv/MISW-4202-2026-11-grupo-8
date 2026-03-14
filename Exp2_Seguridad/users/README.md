# Servicio Simulador de Anomalías de Seguridad

Sistema de simulación de anomalías de seguridad que genera tráfico controlado para probar sistemas de detección de amenazas. Simula comportamientos de usuarios normales y anómalos, registrando todos los eventos en una base de datos MySQL para auditoría.

## 📋 Índice

- [Arquitectura](#arquitectura)
- [Tipos de Procesadores](#tipos-de-procesadores)
- [Sistema de Auditoría](#sistema-de-auditoría)
- [Configuración](#configuración)
- [Instalación y Ejecución](#instalación-y-ejecución)
- [Uso de la API](#uso-de-la-api)
- [Estructura del Proyecto](#estructura-del-proyecto)

## 🏗️ Arquitectura

El servicio está construido en Go y utiliza un patrón de diseño basado en procesadores independientes:

```
┌─────────────────────┐
│   HTTP Server       │
│   (Puerto 8081)     │
└──────────┬──────────┘
           │
           ▼
    POST /trigger
           │
           ▼
┌──────────────────────────┐
│  Genera 5 simulaciones   │
│  concurrentes con UUID   │
└──────────┬───────────────┘
           │
     ┌─────┴─────┬─────────┬─────────┬─────────┐
     ▼           ▼         ▼         ▼         ▼
┌─────────┐ ┌─────────┐ ┌──────┐ ┌──────┐ ┌──────┐
│ User1   │ │ User2   │ │User3 │ │User4 │ │User5 │
│Random   │ │Random   │ │Random│ │Random│ │Random│
│Processor│ │Processor│ │Proc. │ │Proc. │ │Proc. │
└─────────┘ └─────────┘ └──────┘ └──────┘ └──────┘
     │           │         │         │         │
     └───────────┴─────────┴─────────┴─────────┘
                      │
                      ▼
              ┌──────────────┐
              │ MySQL Audit  │
              │   Database   │
              └──────────────┘
```

### Flujo de Ejecución

1. **Recepción de Trigger**: El endpoint `/trigger` recibe una petición POST
2. **Generación de UUID**: Se genera un UUID v4 único para cada simulación
3. **Selección Aleatoria**: Cada usuario se asigna aleatoriamente a uno de los 4 procesadores
4. **Ejecución Asíncrona**: Las 5 simulaciones se ejecutan en goroutines independientes
5. **Respuesta Inmediata**: El servidor responde HTTP 200 sin esperar las simulaciones
6. **Auditoría Continua**: Cada evento se registra en MySQL con su UUID de trazabilidad

## 🎯 Tipos de Procesadores

Cada procesador simula un patrón de comportamiento específico:

### 1. **Bot Impersonation Event** (`bot_imperson`)
Simula un ataque de bot realizando hasta 100 peticiones en 1 minuto.

**Comportamiento:**
- Login con contraseña incorrecta
- 100 requests concurrentes a `/reservas` en 1 minuto (600ms de intervalo)
- Se detiene si detecta bloqueo de usuario

**Eventos auditados:**
- Login fallido/exitoso
- Cada request exitoso
- Bloqueo de usuario detectado

### 2. **Unauthorized Login Event** (`unauth_login`)
Simula intentos de acceso no autorizado con credenciales incorrectas.

**Comportamiento:**
- 10 intentos de login con contraseña incorrecta
- Se detiene si el usuario es bloqueado

**Eventos auditados:**
- Cada intento de login fallido
- Login exitoso (si ocurre)
- Bloqueo de usuario

### 3. **Geo Anomaly Event** (`geo_anomaly`)
Simula accesos desde múltiples ubicaciones geográficas sospechosas.

**Comportamiento:**
- Login desde 10 ubicaciones diferentes (Colombia, USA, Brasil, Argentina, México, Perú, China, España, Noruega, Suiza)
- Cambia IP, DeviceID y Geo en cada intento
- Se detiene si detecta anomalía geográfica

**Eventos auditados:**
- Login desde cada ubicación
- Detección de anomalía geográfica
- Errores de autenticación

### 4. **Normal User Event** (`normal_user`)
Simula comportamiento de usuario legítimo.

**Comportamiento:**
- Login exitoso con credenciales correctas
- 3 requests espaciadas en 1 minuto (20 segundos de intervalo)
- Uso normal del sistema

**Eventos auditados:**
- Login exitoso/fallido
- Cada request exitoso

## 📊 Sistema de Auditoría

### Base de Datos MySQL

Todos los eventos se registran en la tabla `audit_events`:

```sql
CREATE TABLE audit_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    simulation_id VARCHAR(36) NOT NULL,      -- UUID de la simulación
    user_id VARCHAR(50) NOT NULL,            -- Usuario afectado
    processor_type VARCHAR(50) NOT NULL,     -- Tipo de procesador
    event_type VARCHAR(50) NOT NULL,         -- Tipo de evento
    status VARCHAR(20) NOT NULL,             -- success/error/blocked
    error_message TEXT,                      -- Mensaje de error (opcional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_simulation_id (simulation_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);
```

### Tipos de Eventos

- `login`: Intento de autenticación
- `request`: Petición a endpoint protegido
- `user_blocked`: Usuario bloqueado por el sistema
- `geo_anomaly`: Anomalía geográfica detectada
- `unauthorized`: Acceso no autorizado

### Estados

- `success`: Operación exitosa
- `error`: Error en la operación
- `blocked`: Usuario/acción bloqueado

### Trazabilidad

Cada simulación tiene un **UUID v4 único** que permite:
- Identificar todos los eventos de una simulación específica
- Correlacionar eventos relacionados
- Debugging y análisis de comportamiento
- Auditoría completa del sistema

**Ejemplo de consulta:**
```sql
SELECT * FROM audit_events 
WHERE simulation_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
ORDER BY created_at;
```

## ⚙️ Configuración

### Variables de Entorno (`.env`)

```bash
# Gateway URL del sistema a testear
GATEWAY_URL=http://localhost:8080

# MySQL Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=audit_user
DB_PASSWORD=secure_audit_pass_2024
DB_NAME=security_audit

# Server Port (opcional, default: 8081)
PORT=8081
```

### Usuarios Simulados

El sistema incluye 5 usuarios pre-configurados en `models/models.go`:

```go
var Users = map[string]User{
    "user1": {"user1", "user1"},
    "user2": {"user2", "user2"},
    "user3": {"user3", "user3"},
    "user4": {"user4", "user4"},
    "user5": {"user5", "user5"},
}
```

## 🚀 Instalación y Ejecución

### Prerequisitos

- Go 1.23+
- MySQL 5.7+ o 8.0+
- Docker (opcional)

### Opción 1: Ejecución Local

1. **Configurar MySQL:**
```sql
CREATE DATABASE security_audit;
CREATE USER 'audit_user'@'localhost' IDENTIFIED BY 'secure_audit_pass_2024';
GRANT ALL PRIVILEGES ON security_audit.* TO 'audit_user'@'localhost';
FLUSH PRIVILEGES;
```

2. **Configurar variables de entorno:**
```bash
cp .env.example .env
# Editar .env con tus valores
```

3. **Instalar dependencias:**
```bash
cd users
go mod tidy
```

4. **Ejecutar el servicio:**
```bash
cd main
go run .
```

El servidor iniciará en `http://localhost:8081`

### Opción 2: Docker

1. **Construir imagen:**
```bash
cd users
docker build -t security-simulator .
```

2. **Ejecutar contenedor:**
```bash
docker run -p 8081:8081 \
  -e GATEWAY_URL=http://host.docker.internal:8080 \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=3306 \
  -e DB_USER=audit_user \
  -e DB_PASSWORD=secure_audit_pass_2024 \
  -e DB_NAME=security_audit \
  security-simulator
```

### Opción 3: Docker Compose (Recomendado)

El proyecto incluye un archivo `docker-compose.yml` que levanta el simulador y MySQL automáticamente.

**Características:**
- MySQL 8.0 con persistencia de datos
- Healthcheck para asegurar que MySQL esté listo antes de iniciar el simulador
- Red dedicada para comunicación entre servicios
- Script de inicialización automático de la base de datos

**1. Configurar GATEWAY_URL (opcional):**

Puedes especificar el GATEWAY_URL como variable de entorno:

```bash
# Linux/Mac
export GATEWAY_URL=http://host.docker.internal:8080

# Windows PowerShell
$env:GATEWAY_URL="http://host.docker.internal:8080"
```

O editar directamente en `docker-compose.yml` si tu gateway está en un host específico.

**2. Iniciar servicios:**

```bash
cd users
docker-compose up -d
```

**3. Verificar estado:**

```bash
# Ver logs
docker-compose logs -f

# Ver estado de contenedores
docker-compose ps

# Ver logs solo del simulador
docker-compose logs -f simulator

# Ver logs solo de MySQL
docker-compose logs -f mysql
```

**4. Verificar conexión a base de datos:**

```bash
# Conectarse a MySQL
docker exec -it security-audit-db mysql -u audit_user -psecure_audit_pass_2024 security_audit

# Verificar tabla de auditoría
mysql> SHOW TABLES;
mysql> SELECT COUNT(*) FROM audit_events;
```

**5. Detener servicios:**

```bash
# Detener sin eliminar volúmenes (datos persisten)
docker-compose down

# Detener y eliminar volúmenes (borra datos)
docker-compose down -v
```

**Servicios disponibles:**
- **Simulador**: `http://localhost:8081`
- **MySQL**: `localhost:3306`

## 📡 Uso de la API

### Endpoint: POST /trigger

Inicia 5 simulaciones concurrentes, una por cada usuario.

**Request:**
```bash
curl -X POST http://localhost:8081/trigger
```

**Response:**
```
HTTP/1.1 200 OK
5 simulaciones iniciadas en background
```

**Logs del servidor:**
```
2026/03/12 23:39:00 Sistema de auditoría inicializado correctamente
2026/03/12 23:39:00 Servidor escuchando en puerto 8081
2026/03/12 23:39:15 Trigger recibido: lanzando 5 simulaciones en background
2026/03/12 23:39:15 5 simulaciones lanzadas, request completada
2026/03/12 23:39:15 [a1b2c3d4-...] Usuario user1 ejecutando processor 3
2026/03/12 23:39:15 [b2c3d4e5-...] Usuario user2 ejecutando processor 1
2026/03/12 23:39:15 [c3d4e5f6-...] Usuario user3 ejecutando processor 4
2026/03/12 23:39:15 [d4e5f6a7-...] Usuario user4 ejecutando processor 2
2026/03/12 23:39:15 [e5f6a7b8-...] Usuario user5 ejecutando processor 3
```

### Verificar Auditoría

```sql
-- Ver todas las simulaciones
SELECT simulation_id, user_id, processor_type, COUNT(*) as events
FROM audit_events
GROUP BY simulation_id, user_id, processor_type
ORDER BY created_at DESC;

-- Ver eventos de una simulación específica
SELECT *
FROM audit_events
WHERE simulation_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
ORDER BY created_at;

-- Contar eventos por tipo
SELECT event_type, status, COUNT(*) as count
FROM audit_events
GROUP BY event_type, status;
```

## 📁 Estructura del Proyecto

```
users/
├── main/
│   └── main.go                 # Servidor HTTP y punto de entrada
├── proccessor/
│   ├── bot_imperson.go        # Procesador de ataque de bot
│   ├── unauth_login.go        # Procesador de login no autorizado
│   ├── geo_anomaly.go         # Procesador de anomalía geográfica
│   └── normal_user.go         # Procesador de usuario normal
├── models/
│   ├── models.go              # Modelos de User y Metadata
│   └── audit.go               # Modelo de eventos de auditoría
├── external_service/
│   ├── login.go               # Mock de servicio de login
│   ├── db.go                  # Conexión a MySQL
│   └── audit.go               # Funciones de auditoría
├── simulations.go             # Orquestador de simulaciones
├── go.mod                     # Dependencias del proyecto
├── .env                       # Variables de entorno
├── Dockerfile                 # Imagen Docker
└── README.md                  # Este archivo
```

## 🔧 Desarrollo

### Agregar un Nuevo Procesador

1. Crear archivo en `proccessor/`:
```go
package proccessor

type INewProcessor interface {
    Proccess(ctx context.Context, simulationID string, user models.User) error
}

type NewProcessor struct {
    client *http.Client
}

func NewNewProcessor(client *http.Client) INewProcessor {
    return &NewProcessor{client: client}
}

func (e *NewProcessor) Proccess(ctx context.Context, simulationID string, user models.User) error {
    // Implementar lógica
    // Auditar eventos con external_service.SaveAuditEvent()
    return nil
}
```

2. Registrar en `simulations.go`:
```go
var proccessors = map[int]Processor{
    1: proccessor.NewUnauthLoginEvent(...),
    2: proccessor.NewGeoAnomalyEvent(...),
    3: proccessor.NewNormalUserEvent(...),
    4: proccessor.NewBotImpersonEvent(...),
    5: proccessor.NewNewProcessor(...),  // Nuevo procesador
}
```

## 📈 Monitoreo

### Métricas Importantes

- **Simulaciones totales**: `SELECT COUNT(DISTINCT simulation_id) FROM audit_events;`
- **Tasa de bloqueos**: `SELECT COUNT(*) FROM audit_events WHERE status = 'blocked';`
- **Eventos por usuario**: `SELECT user_id, COUNT(*) FROM audit_events GROUP BY user_id;`
- **Distribución de procesadores**: `SELECT processor_type, COUNT(*) FROM audit_events GROUP BY processor_type;`

## 🐛 Troubleshooting

### El servidor no se conecta a MySQL
- Verificar credenciales en `.env`
- Confirmar que MySQL está corriendo: `mysql -u audit_user -p`
- Revisar firewall y permisos de red

### Las simulaciones no se ejecutan
- Verificar logs del servidor
- Confirmar que `GATEWAY_URL` es accesible
- Revisar timeout de HTTP client (default: 5s)

### No se registran eventos en la base de datos
- Verificar que la tabla fue creada correctamente
- Revisar permisos del usuario MySQL
- Confirmar que `InitAuditTable()` se ejecutó sin errores

## 📄 Licencia

Este es un proyecto educativo para pruebas de sistemas de seguridad.

## 👥 Contribuciones

Para contribuir al proyecto:
1. Fork del repositorio
2. Crear rama de feature: `git checkout -b feature/nueva-funcionalidad`
3. Commit de cambios: `git commit -am 'Agregar nueva funcionalidad'`
4. Push a la rama: `git push origin feature/nueva-funcionalidad`
5. Crear Pull Request
