FROM golang:1.25-alpine AS builder
WORKDIR /app

RUN apk add --no-cache gcc musl-dev

COPY pkg/ ./pkg/
COPY services/router/ ./services/router/

WORKDIR /app/services/router
RUN go mod download
RUN go build -tags musl -o router-service .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/router/router-service .
CMD ["./router-service"]
