import base64
import time
import jwt
import logging
import grpc
import ssl
import os

# Disable SSL verification for gRPC
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GRPC_TRACE'] = ''

# Read the self-signed certificate
cert_path = "/app/certs/cert.pem"
if os.path.exists(cert_path):
    with open(cert_path, 'rb') as f:
        root_certificates = f.read()
else:
    # If cert doesn't exist, use None for no verification
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
    "service.version": "1.0"
})

# Create SSL credentials with the self-signed cert
ssl_credentials = grpc.ssl_channel_credentials(
    root_certificates=root_certificates,  # Use the self-signed cert
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

# Create channel options to override the target name
channel_options = [
    ('grpc.ssl_target_name_override', 'envoy-router'),
    ('grpc.max_receive_message_length', -1),
    ('grpc.max_send_message_length', -1),
]

# ==============================
# 3. LOGS
# ==============================
from opentelemetry import _logs
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

logger_provider = LoggerProvider(resource=resource)

log_exporter = OTLPLogExporter(
    endpoint="otel-collector:4317",
    insecure=True,  # Direct connection to collector
    headers=headers,  # Include JWT authentication
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
# 4. TRACES
# ==============================
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

trace_provider = TracerProvider(resource=resource)

trace_exporter = OTLPSpanExporter(
    endpoint="otel-collector:4317",
    insecure=True,  # Direct connection to collector
    headers=headers  # Include JWT authentication
)

trace_provider.add_span_processor(
    BatchSpanProcessor(trace_exporter)
)

trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# ==============================
# 5. METRICS
# ==============================
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry import metrics

metric_exporter = OTLPMetricExporter(
    endpoint="otel-collector:4317",
    insecure=True,  # Direct connection to collector
    headers=headers  # Include JWT authentication
)

reader = PeriodicExportingMetricReader(
    metric_exporter,
    export_interval_millis=5000
)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[reader]
)

metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

# Create metric
request_counter = meter.create_counter("demo_requests")

# ==============================
# 6. Emit Data
# ==============================
with tracer.start_as_current_span("demo-span") as span:
    span.set_attribute("key", "value")

    logger.info("✅ Test log message", extra={"key": "value"})

    request_counter.add(1, {"endpoint": "/test"})

print("Sent logs, traces, and metrics!")

# Keep app alive for metrics export
time.sleep(10)