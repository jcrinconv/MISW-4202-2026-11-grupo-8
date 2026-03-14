-- Script de inicialización de la base de datos de auditoría
-- Se ejecuta automáticamente cuando el contenedor MySQL arranca por primera vez

USE security_audit;

CREATE TABLE IF NOT EXISTS audit_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    simulation_id VARCHAR(36) NOT NULL COMMENT 'UUID v4 de la simulación',
    simulation_uuid VARCHAR(36) NULL COMMENT 'UUID de simulación para trazabilidad',
    simulation_status VARCHAR(20) NULL COMMENT 'Estado de la simulación (running/finished)',
    user_id VARCHAR(50) NOT NULL COMMENT 'ID del usuario simulado',
    processor_type VARCHAR(50) NOT NULL COMMENT 'Tipo de procesador (bot_imperson, normal_user, etc.)',
    event_type VARCHAR(50) NOT NULL COMMENT 'Tipo de evento (login, request, user_blocked, etc.)',
    status VARCHAR(20) NOT NULL COMMENT 'Estado del evento (success, error, blocked)',
    error_message TEXT COMMENT 'Mensaje de error si aplica',
    detail_json TEXT COMMENT 'Detalle JSON del evento (opcional)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp del evento',
    INDEX idx_simulation_id (simulation_id),
    INDEX idx_simulation_uuid (simulation_uuid),
    INDEX idx_simulation_status (simulation_status),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    INDEX idx_processor_type (processor_type),
    INDEX idx_event_type (event_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tabla de auditoría de eventos de seguridad';

-- Insertar evento de inicialización
INSERT INTO audit_events (simulation_id, user_id, processor_type, event_type, status, error_message)
VALUES ('00000000-0000-0000-0000-000000000000', 'system', 'system', 'database_init', 'success', 'Database initialized successfully');
