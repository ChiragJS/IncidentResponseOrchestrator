FROM golang:1.25-alpine AS builder
WORKDIR /app

# Install build dependencies for CGO (confluent-kafka-go)
RUN apk add --no-cache gcc musl-dev

COPY pkg/ ./pkg/
COPY services/ingest/ ./services/ingest/

WORKDIR /app/services/ingest
RUN go mod download
# -tags musl is required for static linking on Alpine
RUN go build -tags musl -o ingest-service .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/ingest/ingest-service .
CMD ["./ingest-service"]
