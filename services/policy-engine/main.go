package main

import (
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"github.com/ChiragJS/IncidentResponseOrchestrator/services/policy-engine/policy"
	"github.com/confluentinc/confluent-kafka-go/kafka"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"google.golang.org/protobuf/encoding/protojson"
)

var (
	inputTopics = []string{"decisions.k8s", "decisions.infra", "decisions.db"}
	outputTopic = "actions.approved"
	producer    *kafka.Producer
)

func main() {
	logger.InitLogger()
	logger.Log.Info("Starting Policy Engine Service...")

	// Start metrics server on port 9090
	go func() {
		http.Handle("/metrics", promhttp.Handler())
		logger.Log.Info("Metrics server listening on :9090")
		http.ListenAndServe(":9090", nil)
	}()

	kafkaBroker := os.Getenv("KAFKA_BROKER")

	if kafkaBroker == "" {
		kafkaBroker = "localhost:9092"
	}

	var err error
	producer, err = kafka.NewProducer(&kafka.ConfigMap{"bootstrap.servers": kafkaBroker})
	if err != nil {
		logger.Log.Fatal("Failed to create producer", zap.Error(err))
	}
	defer producer.Close()

	consumer, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": kafkaBroker,
		"group.id":          "policy-group",
		"auto.offset.reset": "earliest",
	})
	if err != nil {
		logger.Log.Fatal("Failed to create consumer", zap.Error(err))
	}
	defer consumer.Close()

	consumer.SubscribeTopics(inputTopics, nil)

	sigchan := make(chan os.Signal, 1)
	signal.Notify(sigchan, syscall.SIGINT, syscall.SIGTERM)

	run := true
	for run {
		select {
		case sig := <-sigchan:
			logger.Log.Info("Caught signal, terminating", zap.String("signal", sig.String()))
			run = false
		default:
			ev := consumer.Poll(100)
			if ev == nil {
				continue
			}

			switch e := ev.(type) {
			case *kafka.Message:
				processDecision(e)
			case kafka.Error:
				logger.Log.Error("Kafka error", zap.Error(e))
			}
		}
	}
}

func processDecision(msg *kafka.Message) {
	var decision events.Decision
	if err := protojson.Unmarshal(msg.Value, &decision); err != nil {
		logger.Log.Error("Failed to unmarshal decision", zap.Error(err))
		return
	}

	logger.Log.Info("Processing decision", zap.String("decision_id", decision.DecisionId))

	for _, action := range decision.ProposedActions {
		if allowed, reason := policy.Evaluate(action); allowed {
			action.Approver = "policy_engine_auto"
			approveAction(action)
		} else {
			logger.Log.Warn("Action rejected", zap.String("action_id", action.ActionId), zap.String("reason", reason))
		}
	}
}

func approveAction(action *events.Action) {
	val, err := protojson.Marshal(action)
	if err != nil {
		logger.Log.Error("Failed to marshal approved action", zap.Error(err))
		return
	}

	err = producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &outputTopic, Partition: kafka.PartitionAny},
		Value:          val,
	}, nil)

	if err != nil {
		logger.Log.Error("Failed to publish approved action", zap.Error(err))
	} else {
		logger.Log.Info("Action approved and published", zap.String("action_id", action.ActionId))
	}
}
