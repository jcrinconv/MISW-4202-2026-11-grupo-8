package external_service

import (
	"Exp2_Seguridad/users/models"
	"context"
	"fmt"
)

func Login(ctx context.Context, user models.User, metadata models.Metadata) (string, error) {
	// TODO: implementar lógica real y eliminar este mock
	stored, ok := models.Users[user.User]
	if !ok || stored.Password != user.Password {
		return "", fmt.Errorf("invalid credentials")
	}

	// JWT mock (header.payload.signature) sin verificación real
	const mockJWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIiwiaXNzIjoiZXhhbXBsZSIsImV4cCI6MTk5OTk5OTk5OX0.c2lnbmF0dXJlLW1vY2s"
	return mockJWT, nil
}