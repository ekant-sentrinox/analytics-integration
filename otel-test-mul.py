import base64
import time
import jwt
import logging
import grpc
import ssl
import os
import random

# Disable SSL verification for gRPC
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = ''

# Read the self-signed certificate
cert_path = "/app/certs/cert.pem"
if os.path.exists(cert_path):
    with open(cert_path, 'rb') as f:
        root_certificates = f.read()
else:
    root_certificates = None

# ==============================
# 1. Generate JWT
# ==============================
SECRET_B64 = "Y2hhbmdlLW1lLWluLXByb2R1Y3Rpb24tdGhpcy1rZXktbXVzdC1iZS1hdC1sZWFzdC02NC1ieXRlcy1sb25nISE="
SECRET = base64.b64decode(SECRET_B64)

token = jwt.encode(
    {"sub": "admin", "exp": int(time.time()) + 3600},
    SECRET,
    algorithm="HS512",
)

if isinstance(token, bytes):
    token = token.decode("utf-8")

print("JWT:", token)

headers = {
    "authorization": f"Bearer {token}"
}

# ==============================
# 2. Resource (IMPORTANT)
# ==============================
from opentelemetry.sdk.resources import Resource

resource = Resource.create({
    "service.name": "demo-service",
    "service.version": "1.0",
    "deployment.environment": "production"
})

# Create SSL credentials
ssl_credentials = grpc.ssl_channel_credentials(
    root_certificates=root_certificates,
    private_key=None,
    certificate_chain=None
)

# Create call credentials for JWT
jwt_credentials = grpc.access_token_call_credentials(token)

# Create composite credentials
custom_credentials = grpc.composite_channel_credentials(
    ssl_credentials,
    jwt_credentials
)

# Create channel options
channel_options = [
    ('grpc.ssl_target_name_override', 'envoy-router'),
    ('grpc.max_receive_message_length', -1),
    ('grpc.max_send_message_length', -1),
]

# ==============================
# 3. LOGS Setup
# ==============================
from opentelemetry import _logs
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

logger_provider = LoggerProvider(resource=resource)

log_exporter = OTLPLogExporter(
    endpoint="otel-collector:4317",
    insecure=True,
    headers=headers,
    timeout=10
)

logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(log_exporter)
)

_logs.set_logger_provider(logger_provider)

handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

logger = logging.getLogger("otel-logger")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ==============================
# 4. TRACES Setup
# ==============================
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

trace_provider = TracerProvider(resource=resource)

trace_exporter = OTLPSpanExporter(
    endpoint="otel-collector:4317",
    insecure=True,
    headers=headers
)

trace_provider.add_span_processor(
    BatchSpanProcessor(trace_exporter)
)

trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# ==============================
# 5. METRICS Setup
# ==============================
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry import metrics

metric_exporter = OTLPMetricExporter(
    endpoint="otel-collector:4317",
    insecure=True,
    headers=headers
)

reader = PeriodicExportingMetricReader(
    metric_exporter,
    export_interval_millis=2000  # Faster export for demo
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[reader]
)

metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

# Create metrics
request_counter = meter.create_counter("demo_requests_total")
response_time_histogram = meter.create_histogram("demo_response_time_seconds")
active_connections = meter.create_up_down_counter("demo_active_connections")

# ==============================
# 6. Send Multiple Batches
# ==============================

def send_log_batch(batch_id, num_logs=10):
    """Send a batch of logs representing one 'file'"""
    log_levels = ['INFO', 'WARNING', 'ERROR', 'DEBUG']
    services = ['api-gateway', 'auth-service', 'payment-service', 'user-service', 'inventory-service']

    for i in range(num_logs):
        level = random.choice(log_levels)
        service = random.choice(services)
        message = f"[Batch {batch_id}] Log entry {i+1} from {service}"

        if level == 'INFO':
            logger.info(message, extra={
                "batch_id": str(batch_id),
                "log_index": i,
                "service": service,
                "severity": level.lower()
            })
        elif level == 'WARNING':
            logger.warning(message, extra={
                "batch_id": str(batch_id),
                "log_index": i,
                "service": service,
                "severity": level.lower()
            })
        elif level == 'ERROR':
            logger.error(message, extra={
                "batch_id": str(batch_id),
                "log_index": i,
                "service": service,
                "severity": level.lower()
            })
        else:
            logger.debug(message, extra={
                "batch_id": str(batch_id),
                "log_index": i,
                "service": service,
                "severity": level.lower()
            })

    print(f"✅ Sent log batch {batch_id} with {num_logs} entries")

def send_trace_batch(batch_id, num_spans=8):
    """Send a batch of traces representing one 'file'"""
    operations = ['http_get', 'http_post', 'database_query', 'cache_lookup', 'external_api_call']
    status_codes = ['OK', 'OK', 'OK', 'ERROR', 'OK']  # Mostly successful

    for i in range(num_spans):
        operation = random.choice(operations)
        status = random.choice(status_codes)

        with tracer.start_as_current_span(f"batch_{batch_id}_span_{i}") as span:
            span.set_attribute("batch_id", str(batch_id))
            span.set_attribute("span_index", i)
            span.set_attribute("operation", operation)
            span.set_attribute("service", random.choice(['frontend', 'backend', 'database']))

            if status == 'ERROR':
                span.set_status({
                    "status_code": "ERROR",
                    "description": "Simulated error"
                })
                span.set_attribute("error", True)
                span.set_attribute("error.message", f"Error in {operation}")
            else:
                span.set_status({
                    "status_code": "OK"
                })

            # Add random duration
            time.sleep(random.uniform(0.01, 0.05))

    print(f"✅ Sent trace batch {batch_id} with {num_spans} spans")

def send_metrics_batch(batch_id, num_points=15):
    """Send a batch of metrics representing one 'file'"""
    endpoints = ['/api/users', '/api/orders', '/api/products', '/api/payments', '/api/auth']

    for i in range(num_points):
        # Counter
        request_counter.add(
            random.randint(1, 10),
            {
                "endpoint": random.choice(endpoints),
                "batch_id": str(batch_id),
                "metric_index": i,
                "status": random.choice(['success', 'error', 'timeout'])
            }
        )

        # Histogram
        response_time_histogram.record(
            random.uniform(0.1, 2.0),
            {
                "endpoint": random.choice(endpoints),
                "batch_id": str(batch_id),
                "metric_index": i
            }
        )

        # UpDownCounter (gauge-like)
        if random.random() > 0.5:
            active_connections.add(
                random.randint(-5, 5),
                {
                    "service": random.choice(['web', 'api', 'worker']),
                    "batch_id": str(batch_id)
                }
            )

    print(f"✅ Sent metrics batch {batch_id} with {num_points} data points")

# ==============================
# 7. Execute Multiple Batches
# ==============================

def send_multiple_data_files():
    """Send 5 files (batches) each of logs, metrics, and traces"""

    print("🚀 Starting multi-batch OTEL data transmission...")
    print("=" * 50)

    # Send 5 batches of each type
    for batch_id in range(1, 6):
        print(f"\n📦 Processing Batch {batch_id}/5...")

        # Send logs for this batch
        print(f"  📝 Sending logs for batch {batch_id}...")
        send_log_batch(batch_id, num_logs=12)
        time.sleep(1)  # Small delay between batches

        # Send metrics for this batch
        print(f"  📊 Sending metrics for batch {batch_id}...")
        send_metrics_batch(batch_id, num_points=20)
        time.sleep(1)

        # Send traces for this batch
        print(f"  🔍 Sending traces for batch {batch_id}...")
        send_trace_batch(batch_id, num_spans=10)
        time.sleep(1)

        print(f"✅ Completed batch {batch_id}")
        print("-" * 30)

    print("\n" + "=" * 50)
    print("🎉 All 5 batches completed successfully!")
    print("📊 Summary:")
    print("  - 5 log batches (12 logs each = 60 total logs)")
    print("  - 5 metric batches (20 data points each = 100 total metric points)")
    print("  - 5 trace batches (10 spans each = 50 total spans)")
    print("=" * 50)

# Alternative: Send interleaved data
def send_interleaved_data():
    """Send interleaved batches across all types"""

    print("🔄 Starting interleaved OTEL data transmission...")
    print("=" * 50)

    # Send 5 interleaved rounds
    for round_num in range(1, 6):
        print(f"\n🔄 Round {round_num}/5...")

        # Alternate between types in each round
        for batch_id in range(1, 6):
            if batch_id % 3 == 1:  # Logs
                send_log_batch(f"{round_num}_{batch_id}", num_logs=5)
            elif batch_id % 3 == 2:  # Metrics
                send_metrics_batch(f"{round_num}_{batch_id}", num_points=8)
            else:  # Traces
                send_trace_batch(f"{round_num}_{batch_id}", num_spans=6)

        time.sleep(0.5)

    print("\n🎉 All interleaved data sent successfully!")

if __name__ == "__main__":
    # Choose which mode to run:

    # Option 1: Send 5 distinct files/batches of each type
    send_multiple_data_files()

    # Option 2: Send interleaved data (uncomment to use)
    # send_interleaved_data()

    print("\n⏳ Waiting for metrics export to complete...")
    time.sleep(10)  # Allow time for metric exports
