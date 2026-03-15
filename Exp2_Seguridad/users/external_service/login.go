package external_service

import (
	"Exp2_Seguridad/users/models"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

type loginRequest struct {
	User     string          `json:"user"`
	Password string          `json:"pass"`
	Metadata models.Metadata `json:"metadata"`
}

type loginResponse struct {
	Message string `json:"message"`
	Token   string `json:"token"`
	Reason  string `json:"reason"`
}

type blockedResponse struct {
	Message string `json:"message"`
	Reason  string `json:"reason"`
}

var ErrUserBlocked = errors.New("user blocked")

func IsBlockedResponse(statusCode int, body []byte) (bool, string) {
	if statusCode != http.StatusForbidden {
		return false, ""
	}

	var resp blockedResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return false, ""
	}

	message := strings.TrimSpace(resp.Message)
	reason := strings.TrimSpace(resp.Reason)
	if reason == "blocked_user" || strings.Contains(strings.ToLower(message), "bloqueado") {
		if message == "" {
			message = "Usuario bloqueado"
		}
		return true, message
	}
	return false, ""
}

func Login(ctx context.Context, user models.User, metadata models.Metadata) (string, error) {
	gatewayURL := strings.TrimSpace(os.Getenv("GATEWAY_URL"))
	if gatewayURL == "" {
		return "", fmt.Errorf("missing GATEWAY_URL")
	}

	body := loginRequest{
		User:     user.User,
		Password: user.Password,
		Metadata: metadata,
	}
	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return "", fmt.Errorf("marshal login request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(gatewayURL, "/")+"/login", bytes.NewBuffer(bodyBytes))
	if err != nil {
		return "", fmt.Errorf("build login request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("login request failed: %w", err)
	}
	defer resp.Body.Close()

	var loginResp loginResponse
	if err := json.NewDecoder(resp.Body).Decode(&loginResp); err != nil {
		return "", fmt.Errorf("decode login response: %w", err)
	}

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		if resp.StatusCode == http.StatusForbidden && (loginResp.Reason == "blocked_user" || strings.Contains(strings.ToLower(loginResp.Message), "bloqueado")) {
			reason := strings.TrimSpace(loginResp.Message)
			if reason == "" {
				reason = "Usuario bloqueado"
			}
			return "", fmt.Errorf("%w: %s", ErrUserBlocked, reason)
		}
		if loginResp.Message != "" {
			return "", fmt.Errorf(loginResp.Message)
		}
		return "", fmt.Errorf("login failed with status %d", resp.StatusCode)
	}

	if strings.TrimSpace(loginResp.Token) == "" {
		return "", fmt.Errorf("login response without token")
	}

	return loginResp.Token, nil
}
