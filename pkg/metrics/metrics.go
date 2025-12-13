package metrics

import (
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	// EventsReceived counts total events received by service
	EventsReceived = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "orchestrator_events_received_total",
			Help: "Total number of events received",
		},
		[]string{"service", "severity"},
	)

	// EventsProcessed counts total events processed by service
	EventsProcessed = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "orchestrator_events_processed_total",
			Help: "Total number of events processed",
		},
		[]string{"service", "status"},
	)

	// ProcessingDuration tracks event processing time
	ProcessingDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "orchestrator_processing_duration_seconds",
			Help:    "Time spent processing events",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"service"},
	)

	// ActionsExecuted counts actions executed by executor
	ActionsExecuted = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "orchestrator_actions_executed_total",
			Help: "Total number of remediation actions executed",
		},
		[]string{"action_type", "status"},
	)

	// PolicyDecisions counts policy engine decisions
	PolicyDecisions = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "orchestrator_policy_decisions_total",
			Help: "Total number of policy decisions made",
		},
		[]string{"decision"},
	)

	// KafkaMessagesPublished counts Kafka messages published
	KafkaMessagesPublished = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "orchestrator_kafka_messages_published_total",
			Help: "Total number of Kafka messages published",
		},
		[]string{"topic"},
	)
)

func init() {
	prometheus.MustRegister(
		EventsReceived,
		EventsProcessed,
		ProcessingDuration,
		ActionsExecuted,
		PolicyDecisions,
		KafkaMessagesPublished,
	)
}

// Handler returns the Prometheus HTTP handler
func Handler() http.Handler {
	return promhttp.Handler()
}

// ServeMetrics starts a metrics server on the given address
func ServeMetrics(addr string) {
	http.Handle("/metrics", Handler())
	go http.ListenAndServe(addr, nil)
}
