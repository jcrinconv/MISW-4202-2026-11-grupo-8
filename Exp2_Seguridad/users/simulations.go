package users

import (
	"context"
	"log"
	"math/rand"
	"net/http"
	"os"
	"time"

	"github.com/google/uuid"

	"Exp2_Seguridad/users/external_service"
	"Exp2_Seguridad/users/models"
	"Exp2_Seguridad/users/proccessor"
)

var gatewayURL = os.Getenv("GATEWAY_URL")
var rng = rand.New(rand.NewSource(time.Now().UnixNano()))

// Processor define la estrategia para ejecutar una anomalía
type Processor interface {
	Proccess(ctx context.Context, simulationID string, user models.User) error
}

var proccessors = map[int]Processor{
	1: proccessor.NewUnauthLoginEvent(&http.Client{Timeout: 5 * time.Second}),
	2: proccessor.NewGeoAnomalyEvent(&http.Client{Timeout: 5 * time.Second}),
	3: proccessor.NewNormalUserEvent(&http.Client{Timeout: 5 * time.Second}),
	4: proccessor.NewBotImpersonEvent(&http.Client{Timeout: 5 * time.Second}),
}

var processorNames = map[int]string{
	1: "unauth_login",
	2: "geo_anomaly",
	3: "normal_user",
	4: "bot_imperson",
}

func getProcessor(index int) (Processor, bool) {
	p, ok := proccessors[index]
	return p, ok
}

// GenerateCustomSimulation ejecuta una simulación para un usuario específico
func GenerateCustomSimulation(userIndex int) {
	simulationID := uuid.New().String()
	ctx := context.Background()
	user := models.GetUserByIndex(userIndex)
	idx := generateRandomIndexEvent()
	processorName := processorNames[idx]

	log.Printf("[%s] Usuario %s ejecutando processor %s", simulationID, user.User, processorName)

	if proc, ok := getProcessor(idx); ok {
		if err := proc.Proccess(ctx, simulationID, user); err != nil {
			log.Printf("[%s] Usuario %s - processor %s error: %v", simulationID, user.User, processorName, err)
		} else {
			log.Printf("[%s] Usuario %s - processor %s completado", simulationID, user.User, processorName)
		}
		if err := external_service.UpdateSimulationStatus(simulationID, models.SimulationStatusFinished); err != nil {
			log.Printf("[%s] Error actualizando estado de simulación: %v", simulationID, err)
		}
	} else {
		log.Printf("[%s] Usuario %s - no hay processor para el índice %d", simulationID, user.User, idx)
	}
}

func generateRandomIndexEvent() int {
	n := rng.Intn(len(proccessors)) + 1 // 0..len-1 -> 1..len
	return n
}
