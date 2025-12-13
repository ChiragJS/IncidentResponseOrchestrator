package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"github.com/ChiragJS/IncidentResponseOrchestrator/services/router/enrich"
	"github.com/confluentinc/confluent-kafka-go/kafka"
	"go.uber.org/zap"
	"google.golang.org/protobuf/encoding/protojson"
)

var (
	inputTopic = "events.normalized"
	producer   *kafka.Producer
)

func main() {
	logger.InitLogger()
	logger.Log.Info("Starting Event Router Service...")

	// Initialize K8s client for enrichment
	enrich.InitK8sClient()

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
		"group.id":          "router-group",
		"auto.offset.reset": "earliest",
	})
	if err != nil {
		logger.Log.Fatal("Failed to create consumer", zap.Error(err))
	}
	defer consumer.Close()

	consumer.SubscribeTopics([]string{inputTopic}, nil)

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
				processMessage(e)
			case kafka.Error:
				logger.Log.Error("Kafka error", zap.Error(e))
			}
		}
	}
}

func processMessage(msg *kafka.Message) {
	var normalized events.NormalizedEvent
	if err := protojson.Unmarshal(msg.Value, &normalized); err != nil {
		logger.Log.Error("Failed to unmarshal event", zap.Error(err))
		return
	}

	logger.Log.Info("Processing event", zap.String("event_id", normalized.EventId))

	domainEvent := enrich.Enrich(&normalized)
	route(domainEvent)
}

func route(ev *events.DomainEvent) {
	topic := fmt.Sprintf("events.%s", ev.Domain)
	val, err := protojson.Marshal(ev)
	if err != nil {
		logger.Log.Error("Failed to marshal domain event", zap.Error(err))
		return
	}

	err = producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          val,
	}, nil)

	if err != nil {
		logger.Log.Error("Failed to route event", zap.String("topic", topic), zap.Error(err))
	} else {
		logger.Log.Info("Routed event", zap.String("topic", topic), zap.String("event_id", ev.EventId))
	}
}
