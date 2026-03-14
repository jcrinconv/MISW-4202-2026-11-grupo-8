package external_service

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"sync"

	_ "github.com/go-sql-driver/mysql"
)

var (
	db   *sql.DB
	once sync.Once
)

func GetDB() (*sql.DB, error) {
	var err error
	once.Do(func() {
		host := os.Getenv("DB_HOST")
		port := os.Getenv("DB_PORT")
		user := os.Getenv("DB_USER")
		password := os.Getenv("DB_PASSWORD")
		dbName := os.Getenv("DB_NAME")

		dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true", user, password, host, port, dbName)
		db, err = sql.Open("mysql", dsn)
		if err != nil {
			log.Printf("Error abriendo conexión MySQL: %v", err)
			return
		}

		if err = db.Ping(); err != nil {
			log.Printf("Error verificando conexión MySQL: %v", err)
			return
		}

		log.Println("Conexión a MySQL establecida exitosamente")
	})

	return db, err
}

func InitAuditTable() error {
	db, err := GetDB()
	if err != nil {
		return err
	}

	createTableSQL := `
	CREATE TABLE IF NOT EXISTS audit_events (
		id INT AUTO_INCREMENT PRIMARY KEY,
		simulation_id VARCHAR(36) NOT NULL,
		simulation_uuid VARCHAR(36) NULL,
		simulation_status VARCHAR(20) NULL,
		user_id VARCHAR(50) NOT NULL,
		processor_type VARCHAR(50) NOT NULL,
		event_type VARCHAR(50) NOT NULL,
		status VARCHAR(20) NOT NULL,
		error_message TEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		INDEX idx_simulation_id (simulation_id),
		INDEX idx_simulation_uuid (simulation_uuid),
		INDEX idx_simulation_status (simulation_status),
		INDEX idx_user_id (user_id),
		INDEX idx_created_at (created_at)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
	`

	_, err = db.Exec(createTableSQL)
	if err != nil {
		return fmt.Errorf("error creando tabla audit_events: %w", err)
	}

	// Migración: agregar columna simulation_uuid si no existe (para tablas creadas antes del cambio)
	addColumnSQL := `
	ALTER TABLE audit_events 
	ADD COLUMN IF NOT EXISTS simulation_uuid VARCHAR(36) NULL AFTER simulation_id;
	`
	_, _ = db.Exec(addColumnSQL) // Ignorar error si la columna ya existe

	addStatusColumnSQL := `
	ALTER TABLE audit_events 
	ADD COLUMN IF NOT EXISTS simulation_status VARCHAR(20) NULL AFTER simulation_uuid;
	`
	_, _ = db.Exec(addStatusColumnSQL) // Ignorar error si la columna ya existe

	// Agregar índice si no existe
	addIndexSQL := `
	CREATE INDEX IF NOT EXISTS idx_simulation_uuid ON audit_events(simulation_uuid);
	`
	_, _ = db.Exec(addIndexSQL) // Ignorar error si el índice ya existe

	addStatusIndexSQL := `
	CREATE INDEX IF NOT EXISTS idx_simulation_status ON audit_events(simulation_status);
	`
	_, _ = db.Exec(addStatusIndexSQL) // Ignorar error si el índice ya existe

	log.Println("Tabla audit_events creada o verificada exitosamente")
	return nil
}
