# OTel Collector Setup and Testing Guide

Complete guide for setting up and testing the DazzleDuck Multi-Collector OTel architecture with MinIO and PostgreSQL integration.

## 🚀 Quick Start

### Option 1: Automated Script (Recommended)
```bash
./otel-setup.sh
```

This bash script automates the entire setup process including:
- Starting all Docker services
- Waiting for services to become healthy
- Running OTel data generation tests
- Verifying data in MinIO
- Displaying comprehensive status

### Option 2: Manual Setup

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
SERVICE                            STATUS                    PORTS
analytics-compaction               Up X minutes             0.0.0.0:9090->9090/tcp
dazzleduck                         Up X minutes             8081/tcp
envoy-router                       Up X minutes             0.0.0.0:443->443/tcp, 0.0.0.0:4317->4317/tcp, 0.0.0.0:59307->59307/tcp
minio-init                         Up X minutes             (no external ports)
minio-server                       Up X minutes (healthy)   0.0.0.0:9000-9001->9000-9001/tcp
otel-collector-gateway-metrics     Up X minutes             (no external ports)
otel-collector-traces-log          Up X minutes             (no external ports)
otel-collector-transaction-logs    Up X minutes             (no external ports)
postgres-db                        Up X minutes (healthy)   0.0.0.0:5432->5432/tcp
```

#### 3. Run OTel Data Generation Test
```bash
docker run --rm --network $(docker inspect dazzleduck --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}') \
  -v "$(pwd):/app" \
  python:3.12-slim \
  bash -c "pip install pyjwt opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q && python /app/dummy_data.py"
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
         │    (TLS Termination)           │
         └────────────┬──────────────────┘
                      ↓
         ┌────────────┴──────────────────┐
         ↓             ↓                 ↓
   ┌───────────┐  ┌───────────┐   ┌───────────┐
   │ Gateway   │  │Transaction│   │   Trace   │
   │  Metrics  │  │   Logs    │   │   Logs    │
   │ Collector │  │ Collector │   │ Collector │
   └─────┬─────┘  └─────┬─────┘   └─────┬─────┘
         │              │               │
         └──────────────┼───────────────┘
                        ↓
         ┌───────────────────────────────┐
         │    DuckDB Processing          │
         │    (Arrow → Parquet)          │
         └────────────┬──────────────────┘
                      ↓
         ┌────────────┴────────────────┐
         ↓                             ↓
    ┌─────────┐                    ┌──────────┐
    │  MinIO  │                    │PostgreSQL│
    │ (Data)  │                    │ (Metadata)│
    │         │                    │ DuckLake │
    └─────────┘                    └──────────┘
         ↑                             ↑
         └──────────────┬──────────────┘
                        ↓
         ┌───────────────────────────────┐
         │    Compaction Service         │
         │    (Port 9090)                │
         └───────────────────────────────┘
```

## 🔧 Configuration Files

### docker-compose.yml
Main Docker Compose configuration file that defines:
- **Services**: DazzleDuck, PostgreSQL, MinIO, Three OTel Collectors, Envoy Router, Compaction Service
- **Networks**: `otel-network` for internal service communication
- **Volumes**: Persistent storage for data, certificates, and compaction
- **Health Checks**: Service health monitoring with dependencies

### OTel Collector Configuration Files
Each collector has its own configuration:

#### gateway_metrics.conf
- **Purpose**: Collects and processes OpenTelemetry metrics
- **Output**: `s3://ollylake/main/gateway_metrics`
- **Table Schema**: Gateway metrics with aggregation support
- **Port**: 4317 (OTLP/gRPC)

#### transaction_log.conf
- **Purpose**: Collects transaction logs
- **Output**: `s3://ollylake/main/transaction_log`
- **Table Schema**: Transaction log entries with trace context
- **Port**: 4317 (OTLP/gRPC)

#### trace_log.conf
- **Purpose**: Collects trace/span logs
- **Output**: `s3://ollylake/main/trace_log`
- **Table Schema**: Trace log entries with span information
- **Port**: 4317 (OTLP/gRPC)

### envoy.yaml
Envoy proxy configuration that:
- **Routes gRPC Traffic**: OTLP requests to collectors
- **Handles TLS**: SSL/TLS termination for secure connections
- **Load Balancing**: Distributes traffic to backend services
- **Port 443**: HTTPS to DazzleDuck API (8081)
- **Port 59307**: Direct Flight SQL access
- **Port 4317**: OTLP/gRPC proxy to collectors

### dummy_data.py
Python data generation script that:
- **Generates JWT tokens**: For authentication
- **Sends OTLP Data**: Logs, traces, and metrics to all three collectors in parallel
- **Simulates Real Data**: LLM calls, MCP tool calls, gateway metrics
- **Supports Filtering**: Can send to specific collectors only

## 🎯 Service Descriptions

### 1. Dazzleduck (Port 8081, 59307)
**Purpose**: Main SQL database and data warehouse
- **Port 8081**: HTTP API
- **Port 59307**: Flight SQL for high-performance queries
- **Features**: DuckDB-compatible SQL interface, JWT authentication
- **CORS**: Allows access from `https://dazzleduck-ui.netlify.app` and `http://localhost:5174`

### 2. PostgreSQL (Port 5432)
**Purpose**: PostgreSQL database for DuckLake metadata catalog
- **User**: sentrinox
- **Password**: sentrinox
- **Database**: sentrinox_db
- **Version**: 17.5
- **Usage**: DuckLake metadata catalog for managing parquet files

### 3. MinIO (Ports 9000, 9001)
**Purpose**: S3-compatible object storage
- **Port 9000**: S3 API endpoint
- **Port 9001**: MinIO Console
- **Access**: minioadmin / minioadmin123
- **Buckets**: ollylake/main/{gateway_metrics, transaction_log, trace_log}

### 4. OTel Collectors (3 instances, Port 4317 each)
**Purpose**: OpenTelemetry data collection and processing

#### otel-collector-gateway-metrics
- **Purpose**: Metrics collection
- **Output**: `s3://ollylake/main/gateway_metrics`
- **Schema**: Supports sum, gauge, and histogram metrics
- **Aggregation**: Monotonic and cumulative metrics

#### otel-collector-transaction-logs
- **Purpose**: Transaction log collection
- **Output**: `s3://ollylake/main/transaction_log`
- **Schema**: Logs with trace_id, span_id, attributes

#### otel-collector-traces-log
- **Purpose**: Trace/span log collection
- **Output**: `s3://ollylake/main/trace_log`
- **Schema**: Detailed trace and span information

All collectors share:
- **Port**: 4317 (OTLP/gRPC endpoint)
- **Authentication**: JWT-based
- **Processing**: Arrow → Parquet conversion
- **Storage**: Direct S3 write to MinIO
- **Ingestion**: 1MB min bucket size, 5s max delay

### 5. Envoy Router (Ports 443, 4317, 59307)
**Purpose**: API gateway and proxy
- **Port 443**: HTTPS with TLS termination (routes to dazzleduck:8081)
- **Port 4317**: OTLP gRPC proxy to collectors (routes to otel-collector:4317)
- **Port 59307**: Direct Flight SQL access to DazzleDuck
- **Features**: JWT authentication, load balancing, TLS with self-signed cert

### 6. Compaction Service (Port 9090)
**Purpose**: Data compaction for optimizing parquet files
- **Port 9090**: Metrics endpoint
- **Minor Compaction**: Every 1 minute, max file size 8 MiB
- **Major Compaction**: Every 1 hour, max file size 64 MiB
- **Retention**: 5 minutes for snapshots
- **Tables**: gateway_metrics, transaction_log, trace_log

### 7. MinIO Init (No external ports)
**Purpose**: Initializes MinIO buckets on startup
- Creates ollylake/main buckets
- Waits for MinIO to be healthy before initialization
- Runs once on startup (condition: service_completed_successfully)

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
- **Catalog**: DuckLake metadata

### OTel Collectors
- **Gateway Metrics**: otel-collector-gateway-metrics:4317
- **Transaction Logs**: otel-collector-transaction-logs:4317
- **Trace Logs**: otel-collector-traces-log:4317
- **Protocol**: OTLP/gRPC
- **Authentication**: JWT (admin/admin)

### DazzleDuck API
- **URL**: https://localhost:443 (via Envoy)
- **Port 8081** (direct container access)
- **Authentication**: JWT

### Compaction Service
- **Metrics**: http://localhost:9090
- **Usage**: View compaction status and metrics

## 📊 Data Flow

### 1. Ingestion Flow
```
OTel Clients → (OTLP/gRPC) → Envoy Router → OTel Collectors (JWT Auth)
OTel Collectors → Arrow Format → DuckDB Processing → Parquet → MinIO Storage
DuckLake (PostgreSQL) → Metadata Catalog → Track Parquet Files
Compaction Service → Optimize Parquet Files → MinIO
```

### 2. Multi-Collector Routing
```
                    +---------------------+
                    |   Envoy Router     |
                    |      :4317         |
                    +----------+----------+
                               |
          +--------------------+--------------------+
          |                    |                    |
          v                    v                    v
+----------------+   +----------------+   +----------------+
| Gateway Metrics|   |Transaction Logs|   |   Trace Logs   |
|    Collector   |   |    Collector   |   |    Collector   |
|     :4317      |   |     :4317      |   |     :4317      |
+-------+--------+   +-------+--------+   +-------+--------+
        |                    |                    |
        v                    v                    v
   gateway_metrics/    transaction_log/     trace_log/
```

### 3. Data Storage
- **Gateway Metrics**: `s3://ollylake/main/gateway_metrics/dd_*.parquet`
- **Transaction Logs**: `s3://ollylake/main/transaction_log/dd_*.parquet`
- **Trace Logs**: `s3://ollylake/main/trace_log/dd_*.parquet`

### 4. File Naming Convention
- **Pattern**: `dd_{uuid}.parquet`
- **Format**: Apache Parquet (columnar storage)
- **Compression**: Optimized for analytics workloads

## 🧪 Testing

### Automated Data Generation
The `dummy_data.py` script automatically:
1. Generates JWT authentication tokens
2. Creates OpenTelemetry resources (logs, traces, metrics)
3. Sends data via OTLP/gRPC to all three collectors in parallel
4. Supports selective sending: `python dummy_data.py metrics` (or `logs`/`traces`)

### Running Specific Tests
```bash
# Send to all collectors
docker run --rm --network $(docker inspect dazzleduck --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}') \
  -v "$(pwd):/app" \
  python:3.12-slim \
  bash -c "pip install pyjwt opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q && python /app/dummy_data.py"

# Send only metrics
docker run --rm --network $(docker inspect dazzleduck --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}') \
  -v "$(pwd):/app" \
  python:3.12-slim \
  bash -c "pip install pyjwt opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc -q && python /app/dummy_data.py metrics"
```

### Manual Verification
```bash
# Check MinIO buckets
docker exec minio-server mc alias set local http://localhost:9000 minioadmin minioadmin123
docker exec minio-server mc ls local/ollylake/main/gateway_metrics/
docker exec minio-server mc ls local/ollylake/main/transaction_log/
docker exec minio-server mc ls local/ollylake/main/trace_log/

# Check collector logs
docker logs --tail 20 otel-collector-gateway-metrics
docker logs --tail 20 otel-collector-transaction-logs
docker logs --tail 20 otel-collector-traces-log

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
docker logs -f otel-collector-gateway-metrics
docker logs -f otel-collector-transaction-logs
docker logs -f otel-collector-traces-log
docker logs -f minio-server
docker logs -f postgres-db
docker logs -f analytics-compaction
```

### Clean Restart (Remove Volumes)
```bash
docker-compose down -v
docker-compose up -d
```

### Query DuckLake Tables
```sql
-- Connect to DazzleDuck (via DuckDB) or query directly
-- The tables are available under the 'ollylake' catalog

-- Query gateway metrics
SELECT * FROM ollylake.main.gateway_metrics LIMIT 10;

-- Query transaction logs
SELECT * FROM ollylake.main.transaction_log LIMIT 10;

-- Query trace logs
SELECT * FROM ollylake.main.trace_log LIMIT 10;
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
- **Token Expiration**: 24 hours

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
docker exec minio-server mc alias set local http://localhost:9000 minioadmin minioadmin123
docker exec minio-server mc ls local/ollylake/main/gateway_metrics/
docker exec minio-server mc ls local/ollylake/main/transaction_log/
docker exec minio-server mc ls local/ollylake/main/trace_log/

# Recent files with sizes
docker exec minio-server mc ls --recursive local/ollylake/

# Count files per bucket
docker exec minio-server mc ls --recursive local/ollylake/main/gateway_metrics/ | wc -l
docker exec minio-server mc ls --recursive local/ollylake/main/transaction_log/ | wc -l
docker exec minio-server mc ls --recursive local/ollylake/main/trace_log/ | wc -l
```

### Compaction Service Monitoring
```bash
# View compaction logs
docker logs -f analytics-compaction

# Check compaction metrics
curl http://localhost:9090/metrics
```

### DuckLake Metadata Queries
```sql
-- Connect to PostgreSQL to view DuckLake metadata
psql -h localhost -U sentrinox -d sentrinox_db

-- View all tables
SELECT * FROM ducklake_tables;

-- View parquet files
SELECT * FROM ducklake_files;

-- View metadata for a specific table
SELECT * FROM ducklake_table_schema WHERE table_name = 'gateway_metrics';
```

## 🌐 Network Configuration

### Docker Network
- **Name**: otel-network
- **Type**: bridge
- **All services communicate on this internal network**

### Service Communication
Services communicate using container names:
- `dazzleduck` → DazzleDuck service
- `postgres` → PostgreSQL database
- `minio` → MinIO S3 storage
- `otel-collector-gateway-metrics` → Gateway metrics collector
- `otel-collector-transaction-logs` → Transaction logs collector
- `otel-collector-traces-log` → Trace logs collector
- `envoy` → Envoy router

## 📁 Directory Structure

```
.
├── certs/                    # TLS certificates (generated on first run)
├── scripts/                  # DazzleDuck startup scripts
│   └── dazzleduck-startup-script.sql
├── gateway_metrics.conf      # Gateway metrics collector config
├── transaction_log.conf      # Transaction logs collector config
├── trace_log.conf           # Trace logs collector config
├── envoy.yaml               # Envoy proxy configuration
├── docker-compose.yml       # Main docker-compose file
├── otel-setup.sh           # Automated setup script
├── dummy_data.py           # Data generation script
└── README-OTEL-SETUP.md    # This file
```

## 🔧 Troubleshooting

### Services Not Starting
```bash
# Check individual service logs
docker-compose logs <service-name>

# Restart specific service
docker-compose restart <service-name>
```

### MinIO Connection Issues
```bash
# Check MinIO is healthy
docker exec minio-server curl -f http://localhost:9000/minio/health/live

# Reinitialize buckets
docker-compose up -d minio-init
```

### OTel Collector Issues
```bash
# Check collector is listening
docker exec otel-collector-gateway-metrics netstat -tlnp | grep 4317

# Verify JWT token (Python)
python -c "
import jwt, base64, time
SECRET = base64.b64decode('Y2hhbmdlLW1lLWluLXByb2R1Y3Rpb24tdGhpcy1rZXktbXVzdC1iZS1hdC1sZWFzdC02NC1ieXRlcy1sb25nISE=')
token = jwt.encode({'sub': 'admin', 'exp': int(time.time()) + 3600}, SECRET, algorithm='HS512')
print('JWT:', token)
"
```

### Compaction Not Running
```bash
# Check compaction logs
docker logs analytics-compaction

# Verify configuration
docker exec analytics-compaction cat /tmp/duckdb/compaction.conf
```

### Certificate Issues
```bash
# Regenerate certificates
rm -rf certs/
docker-compose up -d generate-cert
```

## 🚦 Performance Tuning

### Ingestion Tuning
Edit collector config files to adjust:
- `min_bucket_size`: Minimum size before flushing (default: 1MB)
- `max_delay_ms`: Maximum delay before flushing (default: 5000ms)
- `queue_config_refresh_delay_ms`: Queue refresh interval (default: 120000ms)

### Compaction Tuning
Edit docker-compose.yml compaction service:
- `compaction.minor.frequency`: Minor compaction interval (default: 1 minute)
- `compaction.minor.max-file-size`: Target file size for minor compaction (default: 8 MiB)
- `compaction.major.frequency`: Major compaction interval (default: 1 hour)
- `compaction.major.max-file-size`: Target file size for major compaction (default: 64 MiB)