package proccessor

import (
	"context"
	"log"
	"net/http"
	"os"
	"sync"
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
	user.Password = "wrongpassword"

	token, err := external_service.Login(ctx, user, models.Metadata{})
	if err != nil {
		external_service.SaveAuditEvent(models.AuditEvent{
			SimulationID:  simulationID,
			UserID:        user.User,
			ProcessorType: "bot_imperson",
			EventType:     models.EventTypeLogin,
			Status:        models.StatusError,
			ErrorMessage:  err.Error(),
		})
		return err
	}

	external_service.SaveAuditEvent(models.AuditEvent{
		SimulationID:  simulationID,
		UserID:        user.User,
		ProcessorType: "bot_imperson",
		EventType:     models.EventTypeLogin,
		Status:        models.StatusSuccess,
	})

	ctxTimeout, cancel := context.WithTimeout(ctx, time.Minute)
	defer cancel()

	return e.simulateActivityReservas(ctxTimeout, simulationID, user.User, token)
}

func (e *BotImpersonEvent) simulateActivityReservas(ctx context.Context, simulationID, userID, token string) error {
	const maxRequests = 100
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	var wg sync.WaitGroup
	errCh := make(chan error, maxRequests)

	for i := 0; i < maxRequests; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			select {
			case <-ctx.Done():
				return
			default:
			}

			req, err := http.NewRequestWithContext(ctx, http.MethodPost, gatewayURL+"/reservas", nil)
			if err != nil {
				errCh <- err
				cancel()
				return
			}
			req.Header.Set("Authorization", "Bearer "+token)

			resp, err := e.client.Do(req)
			if err != nil {
				if err.Error() == "user blocked" {
					external_service.SaveAuditEvent(models.AuditEvent{
						SimulationID:  simulationID,
						UserID:        userID,
						ProcessorType: "bot_imperson",
						EventType:     models.EventTypeUserBlocked,
						Status:        models.StatusBlocked,
						ErrorMessage:  err.Error(),
					})
					errCh <- err
					cancel()
					return
				}
				log.Printf("bot imperson request error: %v", err)
				return
			}

			if resp.StatusCode >= http.StatusBadRequest {
				log.Printf("bot imperson request status: %s", resp.Status)
			} else {
				external_service.SaveAuditEvent(models.AuditEvent{
					SimulationID:  simulationID,
					UserID:        userID,
					ProcessorType: "bot_imperson",
					EventType:     models.EventTypeRequest,
					Status:        models.StatusSuccess,
				})
			}
			resp.Body.Close()
		}()
	}

	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-ctx.Done():
	case <-done:
	}

	close(errCh)
	for err := range errCh {
		return err
	}
	return ctx.Err()
}
