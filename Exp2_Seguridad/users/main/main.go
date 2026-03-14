package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"Exp2_Seguridad/users"
	"Exp2_Seguridad/users/external_service"
)

func main() {
	// Inicializar conexión a base de datos
	if err := external_service.InitAuditTable(); err != nil {
		log.Printf("WARNING: No se pudo inicializar tabla de auditoría: %v", err)
		log.Println("El servidor continuará pero sin auditoría en DB")
	} else {
		log.Println("Sistema de auditoría inicializado correctamente")
	}

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
