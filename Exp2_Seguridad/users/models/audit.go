package models

import "time"

type AuditEvent struct {
	SimulationID  string
	UserID        string
	ProcessorType string
	EventType     string
	Status        string
	ErrorMessage  string
	CreatedAt     time.Time
}

const (
	EventTypeLogin        = "login"
	EventTypeRequest      = "request"
	EventTypeUserBlocked  = "user_blocked"
	EventTypeGeoAnomaly   = "geo_anomaly"
	EventTypeUnauthorized = "unauthorized"

	StatusSuccess = "success"
	StatusError   = "error"
	StatusBlocked = "blocked"
)
