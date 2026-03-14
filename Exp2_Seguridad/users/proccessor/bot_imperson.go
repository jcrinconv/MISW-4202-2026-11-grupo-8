package proccessor

import (
	"context"
	"errors"
	"fmt"
	"io"
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

	metadata := models.Metadata{SimulationUUID: simulationID}
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
			req.Header.Set("X-Auth-Token", token)
			req.Header.Set("X-Simulation-UUID", simulationID)

			resp, err := e.client.Do(req)
			if err != nil {
				log.Printf("bot imperson request error: %v", err)
				return
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
					errCh <- fmt.Errorf("%w: %s", external_service.ErrUserBlocked, message)
					cancel()
					return
				}
				log.Printf("bot imperson request status: %s", resp.Status)
				return
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
