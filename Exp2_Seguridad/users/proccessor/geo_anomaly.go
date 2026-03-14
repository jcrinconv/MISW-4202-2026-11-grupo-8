package proccessor

import (
	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
	"context"
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
	// Simulate different IP addresses for each attempt
	for _, item := range mapGeoRandom {
		_, err := external_service.Login(ctx, user, item)
		if err != nil {
			if err.Error() == "geo anomaly detected" {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:  simulationID,
					UserID:        user.User,
					ProcessorType: "geo_anomaly",
					EventType:     models.EventTypeGeoAnomaly,
					Status:        models.StatusBlocked,
					ErrorMessage:  err.Error(),
				})
				break
			}
			external_service.SaveAuditEvent(models.AuditEvent{
				SimulationID:  simulationID,
				UserID:        user.User,
				ProcessorType: "geo_anomaly",
				EventType:     models.EventTypeLogin,
				Status:        models.StatusError,
				ErrorMessage:  err.Error(),
			})
		} else {
			external_service.SaveAuditEvent(models.AuditEvent{
				SimulationID:  simulationID,
				UserID:        user.User,
				ProcessorType: "geo_anomaly",
				EventType:     models.EventTypeLogin,
				Status:        models.StatusSuccess,
			})
		}
	}
	return nil
}
