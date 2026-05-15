#!/bin/bash

# OTel Setup Automation Script
# This script automates the complete OTel collector setup and testing process

set -e

echo "🚀 Starting OTel Setup Automation..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    print_error "Docker or Docker Compose not found. Please install Docker first."
    exit 1
fi

# Use docker compose or docker-compose
COMPOSE_CMD="docker-compose"
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
fi

# Step 1: Start services
print_info "Starting Docker services..."
$COMPOSE_CMD up -d

# Wait for services to be healthy
print_info "Waiting for services to become healthy..."
sleep 10

# Check if services are running
print_info "Checking service status..."
if ! $COMPOSE_CMD ps | grep -q "Up"; then
    print_error "Services failed to start. Check logs with: $COMPOSE_CMD logs"
    exit 1
fi

print_success "All services are running"

# Step 2: Wait for MinIO and PostgreSQL to be healthy
print_info "Waiting for MinIO and PostgreSQL health checks..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    MINIO_HEALTH=$(docker exec minio-server curl -sf http://localhost:9000/minio/health/live || echo "unhealthy")
    POSTGRES_HEALTH=$(docker exec postgres-db pg_isready -U sentrinox 2>&1 || echo "unhealthy")

    if [[ "$MINIO_HEALTH" == *"accepting connections"* ]] || [[ "$POSTGRES_HEALTH" == *"accepting connections"* ]]; then
        print_success "Services are healthy"
        break
    fi

    attempt=$((attempt + 1))
    echo "  Attempt $attempt/$max_attempts..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    print_error "Services did not become healthy in time. Check logs with: $COMPOSE_CMD logs"
    exit 1
fi

# Step 3: Get the correct network name
print_info "Determining Docker network name..."

# Simple approach: get network from the running dazzleduck container
NETWORK_NAME=$(docker inspect dazzleduck --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null)

if [ -z "$NETWORK_NAME" ]; then
    print_error "Could not determine network name. Is the collector running?"
    exit 1
fi

print_success "Using network: $NETWORK_NAME"

# Step 4: Run OTel test
print_info "Running OTel test..."
echo ""

TEST_OUTPUT=$(docker run --rm --network "$NETWORK_NAME" \
    -v "$(pwd):/app" \
    python:3.12-slim \
    bash -c "pip install pyjwt opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q && python /app/dummy_data.py" 2>&1)

if echo "$TEST_OUTPUT" | grep -q "All collectors finished"; then
    print_success "OTel test completed successfully"
    echo "$TEST_OUTPUT" | grep -E "JWT:|Sending|Done\."
else
    print_error "OTel test failed. Output:"
    echo "$TEST_OUTPUT"
    exit 1
fi

echo ""

# Step 5: Check MinIO for data
print_info "Checking MinIO for OTel data..."
echo ""

MINIO_OUTPUT=$(docker exec minio-server mc alias set local http://localhost:9000 minioadmin minioadmin123 2>&1)
if echo "$MINIO_OUTPUT" | grep -q "Added"; then
    print_success "MinIO connection established"
else
    print_error "Failed to connect to MinIO"
    echo "$MINIO_OUTPUT"
    exit 1
fi

# List buckets and files
echo ""
echo "📊 OTel Data in MinIO:"
echo "======================"
docker exec minio-server mc ls --recursive local/ | grep -E "otel/main/gateway_metrics|otel/main/trace_log|otel/main/transaction_log"


# Step 5: Show service status
echo ""
echo "🔍 Service Status:"
echo "=================="
$COMPOSE_CMD ps

echo ""
print_success "OTel Setup completed successfully!"
echo ""
echo "📚 Next Steps:"
echo "  - View MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
echo "  - Connect to PostgreSQL: localhost:5432 (sentrinox/sentrinox)"
echo "  - View collector logs: docker logs -f dazzleduck-otel-collector"
echo "  - Stop services: $COMPOSE_CMD down"
echo ""
