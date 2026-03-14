package external_service

import (
	"Exp2_Seguridad/users/models"
	"fmt"
	"log"
	"time"
)

func SaveAuditEvent(event models.AuditEvent) error {
	db, err := GetDB()
	if err != nil {
		return fmt.Errorf("error obteniendo conexión DB: %w", err)
	}

	if event.CreatedAt.IsZero() {
		event.CreatedAt = time.Now()
	}

	query := `
		INSERT INTO audit_events 
		(simulation_id, simulation_uuid, user_id, processor_type, event_type, status, error_message, created_at) 
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
	`

	_, err = db.Exec(query,
		event.SimulationID,
		event.SimulationUUID,
		event.UserID,
		event.ProcessorType,
		event.EventType,
		event.Status,
		event.ErrorMessage,
		event.CreatedAt,
	)

	if err != nil {
		log.Printf("Error guardando evento de auditoría: %v", err)
		return fmt.Errorf("error guardando evento de auditoría: %w", err)
	}

	return nil
}
