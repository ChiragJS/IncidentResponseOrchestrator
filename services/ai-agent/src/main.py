import os
import signal
import sys
import threading
from confluent_kafka import Consumer, Producer, KafkaError
from google.protobuf.json_format import Parse, MessageToJson
from protos.contracts import orchestrator_pb2
from agent.agent import IncidentAgent
from prometheus_client import start_http_server, Counter, Histogram

# Prometheus metrics
EVENTS_RECEIVED = Counter('orchestrator_events_received_total', 'Total events received', ['service', 'domain'])
EVENTS_PROCESSED = Counter('orchestrator_events_processed_total', 'Total events processed', ['service', 'status'])
PROCESSING_DURATION = Histogram('orchestrator_processing_duration_seconds', 'Event processing time', ['service'])

# Config
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPICS = ["events.k8s", "events.infra", "events.db"]
OUTPUT_TOPIC_PREFIX = "decisions."

def main():
    print("Starting AI Incident Analysis Agent (Protobuf + Gemini)...")
    
    # Start Prometheus metrics server
    start_http_server(9090)
    print("Metrics server listening on :9090")
    
    producer = Producer({'bootstrap.servers': KAFKA_BROKER})
    
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'ai-agent-group',
        'auto.offset.reset': 'earliest'
    })
    consumer.subscribe(TOPICS)

    agent = IncidentAgent()


    running = True
    def signal_handler(sig, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)

    while running:
        msg = consumer.poll(1.0)
        if msg is None: continue
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                print(f"Consumer error: {msg.error()}")
            continue

        try:
            # Deserialize (Protobuf JSON)
            event = orchestrator_pb2.DomainEvent()
            Parse(msg.value().decode('utf-8'), event)
            
            print(f"Received event: {event.event_id} Domain: {event.domain}")
            
            # Analyze
            decision = agent.analyze(event)
            print( decision )
            # Serialize (Protobuf JSON)
            output_topic = f"{OUTPUT_TOPIC_PREFIX}{event.domain}"
            val = MessageToJson(decision)
            
            producer.produce(output_topic, val.encode('utf-8'))
            producer.flush()
            
            print(f"Published decision to {output_topic}")
            
        except Exception as e:
            print(f"Error processing message: {e}")

    consumer.close()

if __name__ == "__main__":
    main()
