FROM golang:1.25-alpine AS builder

WORKDIR /app

COPY proxy/go.mod proxy/go.sum ./proxy/
WORKDIR /app/proxy
RUN go mod download

COPY proxy/ ./

RUN go build -o /app/injector-proxy .

FROM alpine:3.20

WORKDIR /app

COPY --from=builder /app/injector-proxy /app/injector-proxy

# Copy CA files (must exist in root folder)
COPY proxy_ca.crt /app/proxy_ca.crt
COPY proxy_ca.key /app/proxy_ca.key

EXPOSE 8000

ENV FRONTEND_HOST=frontend:3000
ENV BACKEND_HOST=backend:8080

CMD ["./injector-proxy", "-addr", ":8000", "-cert", "proxy_ca.crt", "-key", "proxy_ca.key"]
