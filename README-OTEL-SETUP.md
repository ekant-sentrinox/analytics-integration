# OTel Collector Setup and Testing Guide

Complete guide for setting up and testing the DazzleDuck OpenTelemetry Collector with MinIO and PostgreSQL integration.

## 🚀 Quick Start

### Option 1: Automated Script (Recommended)
```bash
./otel-setup.sh
```

This bash script automates the entire setup process including:
- Starting all Docker services
- Waiting for services to become healthy
- Running the OTel test script
- Verifying data in MinIO
- Displaying comprehensive status

### Option 2: Using the OTel Setup Skill
```bash
/otel-setup
```

This Claude Code skill automates the entire setup process including starting services and running tests.

### Option 3: Manual Setup

#### 1. Start All Services
```bash
docker-compose up -d
```

#### 2. Verify Services are Running
```bash
docker-compose ps
```

Expected output:
```
SERVICE                  STATUS                    PORTS
dazzleduck               Up X minutes             8081/tcp, 59307/tcp
dazzleduck-otel-collector   Up X minutes             (no external ports)
envoy-router               Up X minutes             0.0.0.0:443->443/tcp, 0.0.0.0:4317->4317/tcp
minio-server              Up X minutes (healthy)   0.0.0.0:9000-9001->9000-9001/tcp
postgres-db               Up X minutes (healthy)   0.0.0.0:5432->5432/tcp
```

#### 3. Run OTel Test
```bash
docker run --rm --network analytics-integration_default \
  -v "$(pwd):/app" \
  python:3.12-slim \
  bash -c "pip install pyjwt opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q && python /app/test_otel.py"
```

## 📊 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      OTel Clients                            │
│  (Python, Java, JavaScript, Go, .NET, etc.)                │
└────────────────────┬────────────────────────────────────────┘
                     │ OTLP/gRPC :4317
                     ↓
         ┌───────────────────────────────┐
         │       Envoy Router             │
         │    (JWT Authentication)        │
         └────────────┬──────────────────┘
                      ↓
         ┌───────────────────────────────┐
         │    OTel Collector             │
         │  • Arrow → Parquet           │
         │  • S3 Secret Configuration  │
         │  • JWT Authentication        │
         └────────────┬──────────────────┘
                      ↓
         ┌────────────┴────────────────┐
         ↓                             ↓
    ┌─────────┐                    ┌──────────┐
    │  MinIO  │                    │PostgreSQL│
    │ (Data)  │                    │ (Metadata)│
    └─────────┘                    └──────────┘
```

## 🔧 Configuration Files

### docker-compose.yml
Main Docker Compose configuration file that defines:
- **Services**: DazzleDuck, PostgreSQL, MinIO, OTel Collector, Envoy Router
- **Networks**: Internal Docker network for service communication
- **Volumes**: Persistent storage for data and certificates
- **Health Checks**: Service health monitoring

### application-minio.conf
OTel collector configuration that defines:
- **S3 Output Paths**: Where to store logs, traces, and metrics in MinIO
- **Authentication**: JWT configuration and user management
- **Service Settings**: Port, service name, token expiration

### envoy.yaml
Envoy proxy configuration that:
- **Routes gRPC Traffic**: OTLP requests to the collector
- **Handles TLS**: SSL/TLS termination for secure connections
- **Load Balancing**: Distributes traffic to backend services

### test_otel.py
Python test script that:
- **Generates JWT tokens**: For authentication
- **Sends OTLP Data**: Logs, traces, and metrics
- **Verifies Connectivity**: Tests the complete data pipeline

## 🎯 Service Descriptions

### 1. Dazzleduck (Port 8081, 59307)
**Purpose**: Main SQL database and data warehouse
- **Port 8081**: HTTP API
- **Port 59307**: Flight SQL for high-performance queries
- **Features**: DuckDB-compatible SQL interface, JWT authentication

### 2. PostgreSQL (Port 5432)
**Purpose**: PostgreSQL database for metadata storage
- **User**: sentrinox
- **Password**: sentrinox
- **Database**: sentrinox_db
- **Usage**: Can be used for metadata catalogs or application data

### 3. MinIO (Ports 9000, 9001)
**Purpose**: S3-compatible object storage
- **Port 9000**: S3 API endpoint
- **Port 9001**: MinIO Console
- **Access**: minioadmin / minioadmin123
- **Buckets**: otel-logs, otel-traces, otel-metrics, otel-metadata

### 4. OTel Collector (Port 4317)
**Purpose**: OpenTelemetry data collection and processing
- **Port 4317**: OTLP gRPC endpoint
- **Authentication**: JWT-based
- **Processing**: Arrow → Parquet conversion
- **Storage**: Direct S3 write to MinIO

### 5. Envoy Router (Ports 443, 4317, 59307)
**Purpose**: API gateway and proxy
- **Port 443**: HTTPS with TLS termination
- **Port 4317**: OTLP gRPC proxy to collector
- **Port 59307: Direct access to DazzleDuck Flight SQL
- **Features**: JWT authentication, load balancing

## 🔍 Access Points

### MinIO Console
- **URL**: http://localhost:9001
- **Username**: minioadmin
- **Password**: minioadmin123
- **Usage**: Browse and manage S3 buckets and files

### PostgreSQL
- **Host**: localhost
- **Port**: 5432
- **Database**: sentrinox_db
- **User**: sentrinox
- **Password**: sentrinox

### OTel Collector
- **Endpoint**: localhost:4317 (via Envoy) or directly on container network
- **Protocol**: OTLP/gRPC
- **Authentication**: JWT (admin/admin)

### DazzleDuck API
- **URL**: https://localhost:443 (via Envoy)
- **Port 8081** (direct container access)
- **Authentication**: JWT

## 📊 Data Flow

### 1. Ingestion Flow
```
OTel Clients → (OTLP/gRPC) → Envoy Router → OTel Collector → (JWT Auth)
OTel Collector → Arrow Format → DuckDB Processing → Parquet → MinIO Storage
```

### 2. Data Storage
- **Logs**: `s3://otel-logs/dd_*.parquet`
- **Traces**: `s3://otel-traces/dd_*.parquet`
- **Metrics**: `s3://otel-metrics/dd_*.parquet`

### 3. File Naming Convention
- **Pattern**: `dd_{uuid}.parquet`
- **Format**: Apache Parquet (columnar storage)
- **Compression**: Optimized for analytics workloads

## 🧪 Testing

### Automated Test
The `test_otel.py` script automatically:
1. Generates JWT authentication token
2. Creates OpenTelemetry resources (logs, traces, metrics)
3. Sends data via OTLP/gRPC to the collector
4. Verifies successful transmission

### Test Output
```
JWT: eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...
Sent logs, traces, and metrics!
```

### Manual Verification
```bash
# Check MinIO buckets
docker exec minio-server mc alias set local http://localhost:9000 minioadmin minioadmin123
docker exec minio-server mc ls local/otel-logs/
docker exec minio-server mc ls local/otel-traces/
docker exec minio-server mc ls local/otel-metrics/

# Check collector logs
docker logs --tail 20 dazzleduck-otel-collector

# Check service health
docker-compose ps
```

## 🛠️ Common Operations

### Start Services
```bash
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### Restart Services
```bash
docker-compose restart
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker logs -f dazzleduck-otel-collector
docker logs -f minio-server
docker logs -f postgres-db
```

### Clean Restart (Remove Volumes)
```bash
docker-compose down -v
docker-compose up -d
```

## 🔐 Authentication

### JWT Secret Key
**Default** (CHANGE IN PRODUCTION):
```
Y2hhbmdlLW1lLWluLXByb2R1Y3Rpb24tdGhpcy1rZXktbXVzdC1iZS1hdC1sZWFzdC02NC1ieXRlcy1sb25nISE=
```

**Generate New Key**:
```bash
# Generate 64-byte random key and base64 encode
openssl rand -base64 32
```

### User Credentials
- **Username**: admin
- **Password**: admin (CHANGE IN PRODUCTION)

### MinIO Credentials
- **Username**: minioadmin
- **Password**: minioadmin123 (CHANGE IN PRODUCTION)

## 📈 Monitoring and Debugging

### Check Service Health
```bash
docker-compose ps
```

### View Recent Data
```bash
# MinIO buckets
docker exec minio-server mc ls local/otel-logs/
docker exec minio-server mc ls local/otel-traces/
docker exec minio-server mc ls local/otel-metrics/

# Recent files with sizes
docker exec minio-server mc ls --recursive local/
```
