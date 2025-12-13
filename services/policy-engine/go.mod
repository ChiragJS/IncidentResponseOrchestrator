module github.com/ChiragJS/IncidentResponseOrchestrator/services/policy-engine

go 1.25.4

replace github.com/ChiragJS/IncidentResponseOrchestrator/pkg => ../../pkg

require (
	github.com/ChiragJS/IncidentResponseOrchestrator/pkg v0.0.0-00010101000000-000000000000
	github.com/confluentinc/confluent-kafka-go v1.9.2
	go.uber.org/zap v1.27.1
	google.golang.org/protobuf v1.36.11
)

require go.uber.org/multierr v1.10.0 // indirect
