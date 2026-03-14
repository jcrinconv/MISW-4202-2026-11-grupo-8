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
	if event.SimulationStatus == "" {
		event.SimulationStatus = models.SimulationStatusRunning
	}

	query := `
		INSERT INTO audit_events 
		(simulation_id, simulation_uuid, simulation_status, user_id, processor_type, event_type, status, error_message, created_at) 
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`

	_, err = db.Exec(query,
		event.SimulationID,
		event.SimulationUUID,
		event.SimulationStatus,
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

func UpdateSimulationStatus(simulationUUID string, status string) error {
	if simulationUUID == "" {
		return fmt.Errorf("simulation UUID requerido")
	}
	if status == "" {
		return fmt.Errorf("simulation status requerido")
	}

	db, err := GetDB()
	if err != nil {
		return fmt.Errorf("error obteniendo conexión DB: %w", err)
	}

	_, err = db.Exec(
		"UPDATE audit_events SET simulation_status = ? WHERE simulation_uuid = ?",
		status,
		simulationUUID,
	)
	if err != nil {
		log.Printf("Error actualizando estado de simulación: %v", err)
		return fmt.Errorf("error actualizando estado de simulación: %w", err)
	}

	return nil
}
