package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"Exp2_Seguridad/users"
)

func main() {
	http.HandleFunc("/trigger", triggerHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}

	log.Printf("Servidor escuchando en puerto %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Error iniciando servidor: %v", err)
	}
}

func triggerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	log.Println("Trigger recibido: lanzando 5 simulaciones en background")

	for i := 0; i < 5; i++ {
		go users.GenerateCustomSimulation(i)
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, "5 simulaciones iniciadas en background\n")
	log.Println("5 simulaciones lanzadas, request completada")
}
