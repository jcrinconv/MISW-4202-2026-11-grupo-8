package proccessor

import (
	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
	"context"
	"net/http"
)

type IUnauthLoginEvent interface {
	Proccess(ctx context.Context, simulationID string, user models.User) error
}

type UnauthLoginEvent struct {
	client *http.Client
}

func NewUnauthLoginEvent(client *http.Client) IUnauthLoginEvent {
	return &UnauthLoginEvent{
		client: client,
	}
}

func (e *UnauthLoginEvent) Proccess(ctx context.Context, simulationID string, user models.User) error {
	user.Password = "wrongpassword"
	metadata := models.Metadata{SimulationUUID: simulationID}
	for i := 0; i < 10; i++ {
		_, err := external_service.Login(ctx, user, metadata)
		if err != nil {
			if err.Error() == "user blocked" {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:   simulationID,
					SimulationUUID: simulationID,
					UserID:         user.User,
					ProcessorType:  "unauth_login",
					EventType:      models.EventTypeUserBlocked,
					Status:         models.StatusBlocked,
					ErrorMessage:   err.Error(),
				})
				break
			}
			external_service.SaveAuditEvent(models.AuditEvent{
				SimulationID:   simulationID,
				SimulationUUID: simulationID,
				UserID:         user.User,
				ProcessorType:  "unauth_login",
				EventType:      models.EventTypeUnauthorized,
				Status:         models.StatusError,
				ErrorMessage:   err.Error(),
			})
		} else {
			external_service.SaveAuditEvent(models.AuditEvent{
				SimulationID:   simulationID,
				SimulationUUID: simulationID,
				UserID:         user.User,
				ProcessorType:  "unauth_login",
				EventType:      models.EventTypeLogin,
				Status:         models.StatusSuccess,
			})
		}
	}
	return nil
}
