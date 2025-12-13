FROM golang:1.25-alpine AS builder
WORKDIR /app

RUN apk add --no-cache gcc musl-dev

COPY pkg/ ./pkg/
COPY services/executor/ ./services/executor/

WORKDIR /app/services/executor
RUN go mod download
RUN go build -tags musl -o executor-service .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/executor/executor-service .
CMD ["./executor-service"]
