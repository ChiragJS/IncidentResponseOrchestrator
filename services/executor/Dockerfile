FROM golang:1.25-bookworm AS builder
WORKDIR /app

COPY pkg/ ./pkg/
COPY services/executor/ ./services/executor/

WORKDIR /app/services/executor
RUN go mod download
RUN go build -o executor-service .

FROM debian:bookworm-slim
WORKDIR /root/
# Install kubectl and CA certs
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && curl -LO "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/
COPY --from=builder /app/services/executor/executor-service .
CMD ["./executor-service"]
