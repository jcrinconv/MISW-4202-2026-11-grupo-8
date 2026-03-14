package proccessor

import (
	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
)

type IGeoAnomalyEvent interface {
	Proccess(ctx context.Context, simulationID string, user models.User) error
}

type GeoAnomalyEvent struct {
	client *http.Client
}

func NewGeoAnomalyEvent(client *http.Client) IGeoAnomalyEvent {
	return &GeoAnomalyEvent{
		client: client,
	}
}

var mapGeoRandom = map[string]models.Metadata{
	"CO":    {IP: "192.168.1.1", DeviceID: "1", Geo: "COLOMBIA"},
	"US":    {IP: "192.168.1.2", DeviceID: "2", Geo: "ESTADOS UNIDOS"},
	"BR":    {IP: "192.168.1.3", DeviceID: "3", Geo: "BRASIL"},
	"AR":    {IP: "192.168.1.4", DeviceID: "4", Geo: "ARGENTINA"},
	"MX":    {IP: "192.168.1.5", DeviceID: "5", Geo: "MEXICO"},
	"PE":    {IP: "192.168.1.6", DeviceID: "6", Geo: "PERU"},
	"CHINA": {IP: "192.168.1.7", DeviceID: "7", Geo: "CHINA"},
	"ES":    {IP: "192.168.1.8", DeviceID: "8", Geo: "ESPAÑA"},
	"NOR":   {IP: "192.168.1.9", DeviceID: "9", Geo: "NORUEGA"},
	"SUI":   {IP: "192.168.1.10", DeviceID: "10", Geo: "SUIZA"},
}

func (e *GeoAnomalyEvent) Proccess(ctx context.Context, simulationID string, user models.User) error {
	var locations []models.Metadata
	for _, item := range mapGeoRandom {
		item.SimulationUUID = simulationID
		locations = append(locations, item)
	}
	if len(locations) == 0 {
		return nil
	}

	loginMeta := locations[0]
	loginDetailBytes, _ := json.Marshal(map[string]string{
		"geo":       loginMeta.Geo,
		"ip":        loginMeta.IP,
		"device_id": loginMeta.DeviceID,
	})
	loginDetailJSON := string(loginDetailBytes)

	token, err := external_service.Login(ctx, user, loginMeta)
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
			ProcessorType:  "geo_anomaly",
			EventType:      eventType,
			Status:         status,
			ErrorMessage:   err.Error(),
			DetailJSON:     loginDetailJSON,
		})
		return err
	}

	external_service.SaveAuditEvent(models.AuditEvent{
		SimulationID:   simulationID,
		SimulationUUID: simulationID,
		UserID:         user.User,
		ProcessorType:  "geo_anomaly",
		EventType:      models.EventTypeLogin,
		Status:         models.StatusSuccess,
		DetailJSON:     loginDetailJSON,
	})

	for _, item := range locations {
		detailBytes, _ := json.Marshal(map[string]string{
			"geo":       item.Geo,
			"ip":        item.IP,
			"device_id": item.DeviceID,
		})
		detailJSON := string(detailBytes)
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
		req.Header.Set("X-Geo", item.Geo)
		req.Header.Set("X-Device-Id", item.DeviceID)
		req.Header.Set("X-Client-IP", item.IP)
		req.Header.Set("X-Forwarded-For", item.IP)
		req.Header.Set("Content-Type", "application/json")

		resp, err := e.client.Do(req)
		if err != nil {
			external_service.SaveAuditEvent(models.AuditEvent{
				SimulationID:   simulationID,
				SimulationUUID: simulationID,
				UserID:         user.User,
				ProcessorType:  "geo_anomaly",
				EventType:      models.EventTypeRequest,
				Status:         models.StatusError,
				ErrorMessage:   err.Error(),
				DetailJSON:     detailJSON,
			})
			return nil
		}

		status := models.StatusSuccess
		errorMessage := ""
		if resp.StatusCode >= http.StatusBadRequest {
			bodyBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			if blocked, message := external_service.IsBlockedResponse(resp.StatusCode, bodyBytes); blocked {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:   simulationID,
					SimulationUUID: simulationID,
					UserID:         user.User,
					ProcessorType:  "geo_anomaly",
					EventType:      models.EventTypeUserBlocked,
					Status:         models.StatusBlocked,
					ErrorMessage:   message,
					DetailJSON:     detailJSON,
				})
				return fmt.Errorf("%w: %s", external_service.ErrUserBlocked, message)
			}
			status = models.StatusError
			errorMessage = resp.Status
		}
		external_service.SaveAuditEvent(models.AuditEvent{
			SimulationID:   simulationID,
			SimulationUUID: simulationID,
			UserID:         user.User,
			ProcessorType:  "geo_anomaly",
			EventType:      models.EventTypeRequest,
			Status:         status,
			ErrorMessage:   errorMessage,
			DetailJSON:     detailJSON,
		})
		resp.Body.Close()
	}
	return nil
}
