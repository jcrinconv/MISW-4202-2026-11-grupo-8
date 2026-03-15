package proccessor

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
)

var gatewayURL = os.Getenv("GATEWAY_URL")

type IBotImpersonEvent interface {
	Proccess(ctx context.Context, simulationID string, user models.User) error
}

type BotImpersonEvent struct {
	client *http.Client
}

func NewBotImpersonEvent(client *http.Client) IBotImpersonEvent {
	return &BotImpersonEvent{
		client: client,
	}
}

func (e *BotImpersonEvent) Proccess(ctx context.Context, simulationID string, user models.User) error {
	metadata := models.Metadata{
		SimulationUUID: simulationID,
		IP:             "192.168.10.10",
		DeviceID:       "bot-imperson-device",
		Geo:            "COLOMBIA",
	}
	token, err := external_service.Login(ctx, user, metadata)
	if err != nil {
		eventType := models.EventTypeLogin
		status := models.StatusError
		if errors.Is(err, external_service.ErrUserBlocked) {
			eventType = models.EventTypeUserBlocked
			status = models.StatusBlocked
		}
		external_service.SaveAuditEvent(models.AuditEvent{
			SimulationID:   simulationID,
			SimulationUUID: simulationID,
			UserID:         user.User,
			ProcessorType:  "bot_imperson",
			EventType:      eventType,
			Status:         status,
			ErrorMessage:   err.Error(),
		})
		return err
	}

	external_service.SaveAuditEvent(models.AuditEvent{
		SimulationID:   simulationID,
		SimulationUUID: simulationID,
		UserID:         user.User,
		ProcessorType:  "bot_imperson",
		EventType:      models.EventTypeLogin,
		Status:         models.StatusSuccess,
	})

	ctxTimeout, cancel := context.WithTimeout(ctx, time.Minute)
	defer cancel()

	return e.simulateActivityReservas(ctxTimeout, simulationID, user.User, token)
}

func (e *BotImpersonEvent) simulateActivityReservas(ctx context.Context, simulationID, userID, token string) error {
	const maxRequests = 35
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for i := 0; i < maxRequests; i++ {
		if i > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
			}
		}

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

		req, err := http.NewRequestWithContext(ctx, http.MethodPost, gatewayURL+"/reservas", bytes.NewBuffer(bodyBytes))
		if err != nil {
			return err
		}
		req.Header.Set("X-Auth-Token", token)
		req.Header.Set("X-Simulation-UUID", simulationID)
		req.Header.Set("X-Geo", "COLOMBIA")
		req.Header.Set("X-Device-Id", "bot-imperson-device")
		req.Header.Set("X-Client-IP", "192.168.10.10")
		req.Header.Set("Content-Type", "application/json")

		resp, err := e.client.Do(req)
		if err != nil {
			return err
		}

		if resp.StatusCode >= http.StatusBadRequest {
			bodyBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			if blocked, message := external_service.IsBlockedResponse(resp.StatusCode, bodyBytes); blocked {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:   simulationID,
					SimulationUUID: simulationID,
					UserID:         userID,
					ProcessorType:  "bot_imperson",
					EventType:      models.EventTypeUserBlocked,
					Status:         models.StatusBlocked,
					ErrorMessage:   message,
				})
				return fmt.Errorf("%w: %s", external_service.ErrUserBlocked, message)
			}
			return fmt.Errorf("bot imperson request failed with status %s", resp.Status)
		}

		external_service.SaveAuditEvent(models.AuditEvent{
			SimulationID:   simulationID,
			SimulationUUID: simulationID,
			UserID:         userID,
			ProcessorType:  "bot_imperson",
			EventType:      models.EventTypeRequest,
			Status:         models.StatusSuccess,
		})
		resp.Body.Close()
	}

	return nil
}
