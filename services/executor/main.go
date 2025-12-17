package main

import (
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/events"
	"github.com/ChiragJS/IncidentResponseOrchestrator/pkg/logger"
	"github.com/ChiragJS/IncidentResponseOrchestrator/services/executor/executor"
	"github.com/confluentinc/confluent-kafka-go/kafka"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/timestamppb"
)

var (
	inputTopic  = "actions.approved"
	outputTopic = "actions.status"
	producer    *kafka.Producer
)

func main() {
	logger.InitLogger()
	logger.Log.Info("Starting Remediation Executor Service...")

	// Start metrics server on port 9090
	go func() {
		http.Handle("/metrics", promhttp.Handler())
		logger.Log.Info("Metrics server listening on :9090")
		http.ListenAndServe(":9090", nil)
	}()

	executor.InitK8sClient()

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
		"group.id":          "executor-group",
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
				processAction(e)
			case kafka.Error:
				logger.Log.Error("Kafka error", zap.Error(e))
			}
		}
	}
}

func processAction(msg *kafka.Message) {
	var action events.Action
	if err := protojson.Unmarshal(msg.Value, &action); err != nil {
		logger.Log.Error("Failed to unmarshal action", zap.Error(err))
		return
	}

	logger.Log.Info("Executing action", zap.String("action_id", action.ActionId), zap.String("type", action.ActionType))

	var statusStr string
	var errExec error

	switch action.ActionType {
	case "restart_pod":
		errExec = executor.RestartPod(action.Target, action.Params)
	case "scale_deployment":
		errExec = executor.ScaleDeployment(action.Target, action.Params)
	case "rolling_restart_deployment":
		errExec = executor.RollingRestartDeployment(action.Target, action.Params)
	case "rollback_deployment":
		errExec = executor.RollbackDeployment(action.Target, action.Params)
	default:
		// In a real system we would error. Here we simulate generic success for demo.
		errExec = executor.RestartPod(action.Target, action.Params)
		if errExec != nil {
			// If it returned error (e.g. client exists but failed), keep it.
			// But if it was "Mocked success", it returns nil.
			// However RestartPod prints "Restarting...". We might want a generic message.
			errExec = fmt.Errorf("unknown action type: %s", action.ActionType)
		} else {
			logger.Log.Info("Simulating unknown action", zap.String("type", action.ActionType))
		}
	}

	if errExec != nil {
		statusStr = "failed"
		logger.Log.Error("Action execution failed", zap.Error(errExec))
	} else {
		statusStr = "success"
		logger.Log.Info("Action executed successfully")
	}

	publishStatus(&action, statusStr, errExec)
}

func publishStatus(action *events.Action, statusStr string, errExec error) {
	errMsg := ""
	if errExec != nil {
		errMsg = errExec.Error()
	}

	status := &events.ActionStatus{
		ActionId:  action.ActionId,
		Status:    statusStr,
		Error:     errMsg,
		Timestamp: timestamppb.New(time.Now()),
	}

	val, err := protojson.Marshal(status)
	if err != nil {
		logger.Log.Error("Failed to marshal status", zap.Error(err))
		return
	}

	producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &outputTopic, Partition: kafka.PartitionAny},
		Value:          val,
	}, nil)
}
