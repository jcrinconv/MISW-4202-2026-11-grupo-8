package proccessor

import (
	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
	"bytes"
	"context"
	"encoding/json"
	"math/rand"
	"net/http"
	"time"
)

type INormalUserEvent interface {
	Proccess(ctx context.Context, simulationID string, user models.User) error
}

type NormalUserEvent struct {
	client *http.Client
}

func NewNormalUserEvent(client *http.Client) INormalUserEvent {
	return &NormalUserEvent{client: client}
}

// Proccess simula un usuario normal: login y 3 requests dentro de 1 minuto.
func (e *NormalUserEvent) Proccess(ctx context.Context, simulationID string, user models.User) error {
	ctxTimeout, cancel := context.WithTimeout(ctx, time.Minute)
	defer cancel()

	metadata := models.Metadata{SimulationUUID: simulationID}
	token, err := external_service.Login(ctxTimeout, user, metadata)
	if err != nil {
		external_service.SaveAuditEvent(models.AuditEvent{
			SimulationID:   simulationID,
			SimulationUUID: simulationID,
			UserID:         user.User,
			ProcessorType:  "normal_user",
			EventType:      models.EventTypeLogin,
			Status:         models.StatusError,
			ErrorMessage:   err.Error(),
		})
		return err
	}

	external_service.SaveAuditEvent(models.AuditEvent{
		SimulationID:   simulationID,
		SimulationUUID: simulationID,
		UserID:         user.User,
		ProcessorType:  "normal_user",
		EventType:      models.EventTypeLogin,
		Status:         models.StatusSuccess,
	})

	localRng := rand.New(rand.NewSource(time.Now().UnixNano()))
	requestCount := localRng.Intn(2) + 3 // 3 o 4 requests
	interval := 10 * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for i := 0; i < requestCount; i++ {
		select {
		case <-ctxTimeout.Done():
			return ctxTimeout.Err()
		case <-ticker.C:
			payload := map[string]interface{}{
				"origen":          "BOG",
				"destino":         "MDE",
				"fecha":           "2026-03-15",
				"pasajeros":       1,
				"simulation_uuid": simulationID,
			}
			bodyBytes, err := json.Marshal(payload)
			if err != nil {
				return err
			}

			req, err := http.NewRequestWithContext(ctxTimeout, http.MethodPost, gatewayURL+"/reservas", bytes.NewBuffer(bodyBytes))
			if err != nil {
				return err
			}
			req.Header.Set("X-Auth-Token", token)
			req.Header.Set("X-Simulation-UUID", simulationID)
			req.Header.Set("Content-Type", "application/json")

			resp, err := e.client.Do(req)
			if err != nil {
				return err
			}

			if resp.StatusCode < http.StatusBadRequest {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:   simulationID,
					SimulationUUID: simulationID,
					UserID:         user.User,
					ProcessorType:  "normal_user",
					EventType:      models.EventTypeRequest,
					Status:         models.StatusSuccess,
				})
			}

			resp.Body.Close()
		}
	}

	return nil
}
