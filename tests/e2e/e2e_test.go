package e2e

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

// TestEndToEndFlow assumes the docker-compose environment is running.
// It sends an alert to the Ingest service and waits (naively) to verify the flow.
// In a real scenario, we would consume from the 'actions.status' Kafka topic to verify completion.
func TestEndToEndFlow(t *testing.T) {
	ingestURL := "http://localhost:8080/ingest"

	payload := map[string]interface{}{
		"source":      "integration_test",
		"severity":    "critical",
		"description": "Integration test CPU spike",
		// Mock data that the Router expects to trigger 'events.k8s'
		"source_details": "k8s_cluster_metrics",
	}
	body, _ := json.Marshal(payload)

	// 1. Send Alert
	resp, err := http.Post(ingestURL, "application/json", bytes.NewBuffer(body))
	if err != nil {
		t.Fatalf("Failed to send alert to Ingest service: %v", err)
	}
	defer resp.Body.Close()

	assert.Equal(t, http.StatusAccepted, resp.StatusCode, "Ingest service should accept the alert")

	var responseMap map[string]string
	json.NewDecoder(resp.Body).Decode(&responseMap)
	eventID := responseMap["event_id"]
	fmt.Printf("Alert accepted. Event ID: %s\n", eventID)

	// 2. Wait for Processing (Naive wait, real test should consume Kafka)
	fmt.Println("Waiting for async processing...")
	time.Sleep(5 * time.Second)

	// Note: To fully verify, we'd need to create a temporary Kafka consumer here
	// and listen to 'actions.status' or check logs.
	// For this scaffold, we confirm API ingestion works.
	fmt.Println("Test finished. Check docker logs for full trace.")
}
