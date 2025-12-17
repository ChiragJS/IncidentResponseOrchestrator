package main

import (
	"encoding/json"
	"net/http"
	"os"
	"time"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/metrics"
	"github.com/confluentinc/confluent-kafka-go/kafka"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var producer *kafka.Producer
var topic = "events.normalized"

func main() {
	logger.InitLogger()
	logger.Log.Info("Starting Event Ingest Service...")

	kafkaBroker := os.Getenv("KAFKA_BROKER")
	if kafkaBroker == "" {
		kafkaBroker = "localhost:9092"
	}

	var err error
	producer, err = kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": kafkaBroker,
	})
	if err != nil {
		logger.Log.Fatal("Failed to create Kafka producer", zap.Error(err))
	}
	defer producer.Close()

	http.HandleFunc("/ingest", ingestHandler)
	http.HandleFunc("/health", healthHandler)
	http.Handle("/metrics", promhttp.Handler())

	logger.Log.Info("Server listening on :8080 (metrics on /metrics)")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		logger.Log.Fatal("Server failed", zap.Error(err))
	}
}

// recordMetrics helper to record event metrics
func recordEventMetrics(severity string) {
	metrics.EventsReceived.WithLabelValues("ingest", severity).Inc()
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func ingestHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var rawPayload map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&rawPayload); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	// Debug: Log the raw payload to see AlertManager structure
	payloadBytes, _ := json.MarshalIndent(rawPayload, "", "  ")
	logger.Log.Info("DEBUG: Received payload", zap.String("payload", string(payloadBytes)))

	// Convert raw payload to Struct
	structPayload, err := structpb.NewStruct(rawPayload)
	if err != nil {
		logger.Log.Error("Failed to convert payload to struct", zap.Error(err))
		http.Error(w, "Invalid Payload", http.StatusBadRequest)
		return
	}

	// Normalize
	normalized := &events.NormalizedEvent{
		EventId:    uuid.New().String(),
		Source:     "http_ingest",
		Timestamp:  timestamppb.New(time.Now()),
		Severity:   "info",
		RawPayload: structPayload,
		Metadata:   map[string]string{"received_by": "ingest-service"},
	}

	// Serialize with protojson
	msgBytes, err := protojson.Marshal(normalized)
	if err != nil {
		logger.Log.Error("Failed to marshal event", zap.Error(err))
		http.Error(w, "Internal Error", http.StatusInternalServerError)
		return
	}

	err = producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          msgBytes,
	}, nil)

	if err != nil {
		logger.Log.Error("Failed to produce message", zap.Error(err))
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{"status": "queued", "event_id": normalized.EventId})
}
