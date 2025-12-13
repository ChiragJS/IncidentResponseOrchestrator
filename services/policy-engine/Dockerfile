FROM golang:1.25-alpine AS builder
WORKDIR /app

RUN apk add --no-cache gcc musl-dev

COPY pkg/ ./pkg/
COPY services/policy-engine/ ./services/policy-engine/

WORKDIR /app/services/policy-engine
RUN go mod download
RUN go build -tags musl -o policy-service .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/policy-engine/policy-service .
CMD ["./policy-service"]
