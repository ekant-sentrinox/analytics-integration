"""
send_all.py
Sends dummy OTLP data to all three collectors in parallel threads:

  - otel-collector-gateway-metrics:4317  → otel.main.gateway_metrics
  - otel-collector-transaction-logs:4317 → otel.main.transaction_log
  - otel-collector-traces-log:4317       → otel.main.trace_log

Usage:
  python send_all.py               # sends to all three collectors
  python send_all.py metrics       # metrics only
  python send_all.py logs          # transaction_log only
  python send_all.py traces        # trace_log only

Install:
  pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc pyjwt
"""

import base64
import time
import json
import math
import random
import sys
import uuid
import threading
import jwt
from datetime import datetime, timezone

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

SECRET_B64 = "Y2hhbmdlLW1lLWluLXByb2R1Y3Rpb24tdGhpcy1rZXktbXVzdC1iZS1hdC1sZWFzdC02NC1ieXRlcy1sb25nISE="
SECRET     = base64.b64decode(SECRET_B64)

ENDPOINTS = {
    "metrics": "otel-collector-gateway-metrics:4317",
    "logs":    "otel-collector-transaction-logs:4317",
    "traces":  "otel-collector-traces-log:4317",
}

NUM_EVENTS = 20

MODELS       = ["claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o", "gpt-4-turbo", "gemini-1.5-pro"]
MCP_TOOLS    = ["read_file", "search_code", "query_db", "write_file", "list_dir"]
MCP_SERVERS  = ["filesystem", "github", "postgres", "slack"]
REGIONS      = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
EVENT_TYPES  = ["llm_call", "mcp_tool_call"]
STATUSES     = ["success", "error", "timeout", "interrupted", "blocked"]
HTTP_CODES   = [200, 200, 200, 429, 500, 503]
STOP_REASONS = ["end_turn", "tool_use", "MAX_TOKENS", None]
LOG_LEVELS   = ["summary", "full"]

# Policy action/reason pools
POLICY_ACTIONS  = ["allow", "block", "redact", "flag", "reroute"]
POLICY_REASONS  = ["pii_detected", "content_policy", "rate_limit", "model_restriction", "cost_cap"]
POLICY_NAMES    = ["pii_filter", "content_guard", "rate_limiter", "model_router", "cost_control"]

# Metric instrument metadata
METRIC_INSTRUMENTS = {
    # name → (instrument_type, unit, is_monotonic, temporality)
    "sntx.requests.total":          ("Sum",       "{requests}", True,  "CUMULATIVE"),
    "sntx.requests.blocked":        ("Sum",       "{requests}", True,  "CUMULATIVE"),
    "sntx.requests.error":          ("Sum",       "{requests}", True,  "CUMULATIVE"),
    "sntx.tokens.input":            ("Sum",       "{tokens}",   True,  "CUMULATIVE"),
    "sntx.tokens.output":           ("Sum",       "{tokens}",   True,  "CUMULATIVE"),
    "sntx.cost.usd":                ("Sum",       "USD",        True,  "CUMULATIVE"),
    "sntx.bytes.in":                ("Sum",       "By",         True,  "CUMULATIVE"),
    "sntx.bytes.out":               ("Sum",       "By",         True,  "CUMULATIVE"),
    "sntx.rl.remaining_requests":   ("Gauge",     "{requests}", False, "DELTA"),
    "sntx.rl.remaining_tokens":     ("Gauge",     "{tokens}",   False, "DELTA"),
    "sntx.active_sessions":         ("Gauge",     "{sessions}", False, "DELTA"),
    "sntx.latency.total":           ("Histogram", "ms",         False, "DELTA"),
    "sntx.latency.gateway":         ("Histogram", "ms",         False, "DELTA"),
    "sntx.latency.ttft":            ("Histogram", "ms",         False, "DELTA"),
}

_transaction_counter      = 0
_transaction_counter_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    """
    Return current UTC time as an ISO-8601 string with millisecond precision
    and a 'Z' suffix — universally parseable by JavaScript, DuckDB, Arrow, etc.
    e.g. "2026-05-15T16:23:09.123Z"
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def make_jwt() -> str:
    token = jwt.encode(
        {"sub": "admin", "exp": int(time.time()) + 3600},
        SECRET,
        algorithm="HS512",
    )
    return token.decode("utf-8") if isinstance(token, bytes) else token


def make_resource():
    from opentelemetry.sdk.resources import Resource
    return Resource.create({
        "service.name":    "sentrinox-gateway-prod",
        "service.version": "1.0",
        "sntx.gateway_id": "1",
        "cloud.region":    "us-east-1",
    })


def random_ip_int() -> int:
    """Generate a random IP as a large integer (UHUGEINT-compatible)."""
    return (0xFFFF << 32) | random.randint(0, 0xFFFFFFFF)


def next_transaction_id() -> int:
    global _transaction_counter
    with _transaction_counter_lock:
        _transaction_counter += 1
        return _transaction_counter


def log_line(collector: str, index: int, detail: str):
    print(f"  [{index:02d}] {collector:40s}  {detail}")


def make_policies() -> dict | None:
    """
    Generate a random policies MAP(VARCHAR, STRUCT(rule_id, policy_action, policy_reason)).
    Returns None ~40% of the time (no policies triggered).
    """
    if random.random() < 0.4:
        return None
    num_policies = random.randint(1, 3)
    policies = {}
    for _ in range(num_policies):
        name = random.choice(POLICY_NAMES)
        policies[name] = {
            "rule_id":       random.randint(1, 100),
            "policy_action": random.choice(POLICY_ACTIONS),
            "policy_reason": random.choice(POLICY_REASONS),
        }
    return policies


def make_provider_usage(model_id: str, in_tok: int, out_tok: int) -> dict | None:
    """
    Generate provider-specific usage blob (VARIANT field).
    Structure varies by provider to simulate real-world variance.
    """
    if random.random() < 0.3:
        return None
    if "claude" in model_id:
        return {
            "input_tokens":  in_tok,
            "output_tokens": out_tok,
            "cache_creation_input_tokens": random.randint(0, 500),
            "cache_read_input_tokens":     random.randint(0, 300),
        }
    elif "gpt" in model_id:
        return {
            "prompt_tokens":     in_tok,
            "completion_tokens": out_tok,
            "total_tokens":      in_tok + out_tok,
            "prompt_tokens_details": {
                "cached_tokens": random.randint(0, 200),
                "audio_tokens":  0,
            },
        }
    else:  # gemini
        return {
            "promptTokenCount":     in_tok,
            "candidatesTokenCount": out_tok,
            "totalTokenCount":      in_tok + out_tok,
        }


# ══════════════════════════════════════════════════════════════════════════════
# METRICS  →  otel-collector-gateway-metrics:4317
# ══════════════════════════════════════════════════════════════════════════════

def run_metrics():
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    token    = make_jwt()
    resource = make_resource()
    headers  = {"authorization": f"Bearer {token}"}

    exporter = OTLPMetricExporter(
        endpoint=ENDPOINTS["metrics"],
        insecure=True,
        headers=headers,
        timeout=10,
    )
    reader   = PeriodicExportingMetricReader(exporter, export_interval_millis=1000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    meter    = metrics.get_meter("send_all.metrics")

    # ── instruments ──────────────────────────────────────────────────────────
    COUNTERS = {
        "sntx.requests.total":   meter.create_counter("sntx.requests.total",   unit="{requests}"),
        "sntx.requests.blocked": meter.create_counter("sntx.requests.blocked", unit="{requests}"),
        "sntx.requests.error":   meter.create_counter("sntx.requests.error",   unit="{requests}"),
        "sntx.tokens.input":     meter.create_counter("sntx.tokens.input",     unit="{tokens}"),
        "sntx.tokens.output":    meter.create_counter("sntx.tokens.output",    unit="{tokens}"),
        "sntx.cost.usd":         meter.create_counter("sntx.cost.usd",         unit="USD"),
        "sntx.bytes.in":         meter.create_counter("sntx.bytes.in",         unit="By"),
        "sntx.bytes.out":        meter.create_counter("sntx.bytes.out",        unit="By"),
    }
    GAUGES = {
        "sntx.rl.remaining_requests": meter.create_up_down_counter("sntx.rl.remaining_requests", unit="{requests}"),
        "sntx.rl.remaining_tokens":   meter.create_up_down_counter("sntx.rl.remaining_tokens",   unit="{tokens}"),
        "sntx.active_sessions":       meter.create_up_down_counter("sntx.active_sessions",       unit="{sessions}"),
    }
    HISTOGRAMS = {
        "sntx.latency.total":   meter.create_histogram("sntx.latency.total",   unit="ms"),
        "sntx.latency.gateway": meter.create_histogram("sntx.latency.gateway", unit="ms"),
        "sntx.latency.ttft":    meter.create_histogram("sntx.latency.ttft",    unit="ms"),
    }

    def metric_attrs(index: int) -> dict:
        event_type = random.choice(EVENT_TYPES)
        attrs = {
            "env":               "production",
            "index":             str(index),
            "sntx.tenant_id":    str(random.randint(1, 5)),
            "sntx.customer_id":  str(random.randint(1, 20)),
            "sntx.workspace_id": str(random.randint(1, 10)),
            "sntx.gateway_id":   str(random.randint(1, 3)),
            "cloud.region":      random.choice(REGIONS),
            "sntx.event_type":   event_type,
        }
        if event_type == "llm_call":
            attrs["llm.provider_id"] = str(random.randint(1, 4))
            attrs["llm.model_id"]    = random.choice(MODELS)
        else:
            attrs["mcp.tool.name"]   = random.choice(MCP_TOOLS)
            attrs["mcp.server.name"] = random.choice(MCP_SERVERS)
        return attrs

    print(f"\n[metrics ] Sending {NUM_EVENTS} events → {ENDPOINTS['metrics']}")

    for i in range(NUM_EVENTS):
        kind = random.choice(["counter", "gauge", "histogram"])

        if kind == "counter":
            name = random.choice(list(COUNTERS.keys()))
            inst = COUNTERS[name]
            val  = random.uniform(0.001, 5.0) if "cost" in name else float(random.randint(1, 50000))
            inst.add(val, metric_attrs(i + 1))
            info = f"counter  {name:40s}  +{val:.1f}"

        elif kind == "gauge":
            name = random.choice(list(GAUGES.keys()))
            inst = GAUGES[name]
            val  = float(random.randint(0, 10000))
            inst.add(val if random.random() > 0.5 else -val, metric_attrs(i + 1))
            info = f"gauge    {name:40s}  ≈{abs(val):.0f}"

        else:
            name = random.choice(list(HISTOGRAMS.keys()))
            inst = HISTOGRAMS[name]
            mean   = 400.0 if "ttft" in name else (20.0 if "gateway" in name else 1200.0)
            spread = mean * 0.75
            attrs  = metric_attrs(i + 1)
            pts    = random.randint(10, 100)
            for _ in range(pts):
                u1, u2 = random.random(), random.random()
                z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
                inst.record(max(1.0, mean + z * spread), attrs)
            info = f"histo    {name:40s}  pts={pts} mean≈{mean:.0f}ms"

        log_line("metrics", i + 1, info)
        time.sleep(0.1)

    print("[metrics ] Flushing...")
    provider.force_flush()
    time.sleep(3)
    print("[metrics ] Done.")


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTION LOGS  →  otel-collector-transaction-logs:4317
# ══════════════════════════════════════════════════════════════════════════════

def run_transaction_logs():
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry._logs import LogRecord
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import SeverityNumber
    from opentelemetry.trace import TraceFlags

    token    = make_jwt()
    resource = make_resource()
    headers  = {"authorization": f"Bearer {token}"}

    exporter = OTLPLogExporter(
        endpoint=ENDPOINTS["logs"],
        insecure=True,
        headers=headers,
        timeout=10,
    )
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    logger   = provider.get_logger("transaction-log-sender", "1.0")

    def make_record(index: int) -> dict:
        event_type     = random.choice(EVENT_TYPES)
        # FIX: use now_iso() → "2026-05-15T16:23:09.123Z" instead of
        #      isoformat() → "2026-05-15T16:23:09.123456+00:00"
        #      The +00:00 suffix and microsecond precision broke parsers
        #      downstream (JavaScript Date, DuckDB TIMESTAMP cast, Arrow),
        #      causing the body column to store "Invalid Date".
        now_ts         = now_iso()
        status         = random.choices(STATUSES, weights=[70, 10, 5, 5, 10])[0]
        transaction_id = next_transaction_id()

        rec = {
            "event_type":         event_type,
            "event_time":         now_ts,          # ← fixed
            "transaction_id":     transaction_id,
            "session_id":         str(uuid.uuid4()) if event_type == "mcp_tool_call" else None,
            "tool_call_seq":      random.randint(1, 5) if event_type == "mcp_tool_call" else None,
            "tenant_id":          random.randint(1, 5),
            "customer_id":        random.randint(1, 20),
            "workspace_id":       random.randint(1, 10),
            "user_id":            random.randint(1, 100),
            "v_key_id":           random.randint(1, 50) if event_type == "llm_call" else None,
            "agent_id":           random.randint(1, 10),
            "source_ip":          random_ip_int(),
            "source_port":        random.randint(1024, 65535),
            "gateway_service":    "sentrinox-gateway-prod",
            "gateway_id":         random.randint(1, 3),
            "total_latency_ms":   random.randint(50, 5000),
            "gateway_latency_ms": random.randint(1, 50),
            "bytes_in":           random.randint(100, 8192),
            "bytes_out":          random.randint(100, 32768),
            "status":             status,
            "provider_id":        None,
            "model_id":           None,
            "input_tokens":       0,
            "output_tokens":      0,
            "input_token_details":  {},
            "output_token_details": {},
            "provider_usage":       None,
            "usage_schema_version": None,
            "tool_name":          None,
            "mcp_server_name":    None,
            "tool_error_code":    None,
        }

        if event_type == "llm_call":
            in_tok  = random.randint(100, 10000)
            out_tok = random.randint(50, 4000)
            http    = random.choice(HTTP_CODES)
            model   = random.choice(MODELS)

            rec.update({
                "provider_id":            random.randint(1, 4),
                "model_id":               model,
                "provider_response_id":   str(uuid.uuid4()),
                "input_tokens":           in_tok,
                "output_tokens":          out_tok,
                "input_token_details": {
                    "cache_read_tokens":    random.randint(0, 500),
                    "cache_write_tokens":   random.randint(0, 200),
                },
                "output_token_details": {
                    "reasoning_tokens": random.randint(0, 200),
                    "audio_tokens":     0,
                },
                "provider_usage":       make_provider_usage(model, in_tok, out_tok),
                "usage_schema_version": "1.0",
                "estimated_cost_usd":   round(in_tok * 0.000003 + out_tok * 0.000015, 8),
                "ttft_ms":              random.randint(100, 2000),
                "target_url":           "https://api.anthropic.com/v1/messages",
                "target_ip":            random_ip_int(),
                "target_port":          443,
                "target_region":        random.choice(REGIONS),
                "http_method":          "POST",
                "http_status_code":     http,
                "http_version":         "2",
                "tls_version":          "TLS 1.3",
                "content_type":         "application/json",
                "retry_count":          0 if http == 200 else random.randint(0, 3),
                "stop_reason":          random.choice(STOP_REASONS),
                "user_agent":           "anthropic-sdk-python/0.40.0",
                "rl_limit_requests":    1000,
                "rl_remaining_requests": random.randint(0, 1000),
                "rl_limit_tokens":      100000,
                "rl_remaining_tokens":  random.randint(0, 100000),
                "rl_reset_at":          now_iso(),   # ← fixed
                "retry_after_ms":       random.randint(1000, 60000) if http == 429 else None,
                "user_prompt":          f"Dummy user prompt #{index}",
                "user_prompt_suppressed": False,
                "prompt_enc_key_id":    None,
                "policies":             make_policies(),
                "original_model_id":    random.choice([None, None, random.choice(MODELS)]),
                "fallback_triggered":   random.choice([True, False]),
                "pii_detected":         random.choice([True, False]),
                "pii_redacted":         random.choice([True, False]),
            })

        else:  # mcp_tool_call
            rec.update({
                "tool_name":       random.choice(MCP_TOOLS),
                "mcp_server_name": random.choice(MCP_SERVERS),
                "tool_error_code": "ToolError" if status == "error" else None,
            })

        return rec

    print(f"\n[txn-logs] Sending {NUM_EVENTS} events → {ENDPOINTS['logs']}")

    for i in range(NUM_EVENTS):
        from opentelemetry._logs import SeverityNumber
        rec        = make_record(i + 1)
        event_type = rec["event_type"]
        status     = rec["status"]
        severity   = SeverityNumber.INFO if status == "success" else SeverityNumber.WARN

        attrs = {
            "event_type":     event_type,
            "tenant_id":      str(rec["tenant_id"]),
            "customer_id":    str(rec["customer_id"]),
            "workspace_id":   str(rec["workspace_id"]),
            "gateway_id":     str(rec["gateway_id"]),
            "transaction_id": str(rec["transaction_id"]),
            "status":         status,
        }
        if event_type == "llm_call":
            attrs["model_id"]    = rec.get("model_id", "")
            attrs["provider_id"] = str(rec.get("provider_id", ""))
        else:
            attrs["tool_name"]       = rec.get("tool_name", "")
            attrs["mcp_server_name"] = rec.get("mcp_server_name", "")

        # Add all fields to attributes as strings
        for key, value in rec.items():
            if value is not None:
                # Convert complex types to JSON strings
                if isinstance(value, dict):
                    attrs[key] = json.dumps(value)
                elif isinstance(value, list):
                    attrs[key] = json.dumps(value)
                else:
                    attrs[key] = str(value)

        from opentelemetry.trace import TraceFlags
        logger.emit(LogRecord(
            timestamp=int(time.time_ns()),
            observed_timestamp=int(time.time_ns()),
            trace_id=random.getrandbits(128),
            span_id=random.getrandbits(64),
            trace_flags=TraceFlags(0x01),
            severity_number=severity,
            severity_text=severity.name,
            body=None,  # No body - all data in attributes
            attributes=attrs,
        ))

        log_line("txn-logs", i + 1,
                 f"{event_type:15s}  status={status:12s}  txn_id={rec['transaction_id']}")
        time.sleep(0.1)

    print("[txn-logs] Flushing...")
    provider.force_flush()
    time.sleep(3)
    print("[txn-logs] Done.")


# ══════════════════════════════════════════════════════════════════════════════
# TRACE LOGS  →  otel-collector-traces-log:4317
# ══════════════════════════════════════════════════════════════════════════════

def run_trace_logs():
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry._logs import LogRecord
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import SeverityNumber
    from opentelemetry.trace import TraceFlags

    token    = make_jwt()
    resource = make_resource()
    headers  = {"authorization": f"Bearer {token}"}

    exporter = OTLPLogExporter(
        endpoint=ENDPOINTS["traces"],
        insecure=True,
        headers=headers,
        timeout=10,
    )
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    logger   = provider.get_logger("trace-log-sender", "1.0")

    def make_req_body(model_id: str, index: int) -> dict:
        return {
            "model":       model_id,
            "max_tokens":  random.choice([1024, 2048, 4096, 8192]),
            "temperature": round(random.uniform(0.0, 1.0), 2),
            "system":      "You are a helpful assistant.",
            "messages":    [
                {"role": "user", "content": f"Dummy message #{index}. " + "x" * random.randint(10, 200)}
            ],
            "tools": [],
        }

    def make_resp_body(model_id: str, in_tok: int, out_tok: int) -> dict:
        return {
            "id":          f"msg_{uuid.uuid4().hex[:24]}",
            "type":        "message",
            "role":        "assistant",
            "model":       model_id,
            "stop_reason": random.choice(["end_turn", "tool_use", "max_tokens"]),
            "content":     [{"type": "text", "text": "Dummy response. " + "y" * random.randint(10, 300)}],
            "usage":       {
                "input_tokens":  in_tok,
                "output_tokens": out_tok,
            },
        }

    def make_record(index: int) -> dict:
        # FIX: use now_iso() for event_time — same reason as transaction logs
        now_ts    = now_iso()           # ← fixed
        model_id  = random.choice(MODELS)
        log_level = random.choice(LOG_LEVELS)
        in_tok    = random.randint(100, 10000)
        out_tok   = random.randint(50, 4000)

        return {
            "event_type":      "llm_call",
            "event_time":      now_ts,  # ← fixed
            "tenant_id":       random.randint(1, 5),
            "gateway_id":      random.randint(1, 3),
            "transaction_id":  index,
            "customer_id":     random.randint(1, 20),
            "workspace_id":    random.randint(1, 10),
            "user_id":         random.randint(1, 100),
            "v_key_id":        random.randint(1, 50),
            "log_level":       log_level,
            "body_enc_key_id": None,
            "request_body":    json.dumps(make_req_body(model_id, index)) if log_level == "full" else None,
            "response_body":   json.dumps(make_resp_body(model_id, in_tok, out_tok)) if log_level == "full" else None,
        }

    print(f"\n[traces  ] Sending {NUM_EVENTS} events → {ENDPOINTS['traces']}")

    for i in range(NUM_EVENTS):
        from opentelemetry._logs import SeverityNumber
        rec       = make_record(i + 1)
        log_level = rec["log_level"]
        severity  = SeverityNumber.DEBUG if log_level == "summary" else SeverityNumber.INFO

        attrs = {
            "event_type":     rec["event_type"],
            "tenant_id":      str(rec["tenant_id"]),
            "customer_id":    str(rec["customer_id"]),
            "workspace_id":   str(rec["workspace_id"]),
            "gateway_id":     str(rec["gateway_id"]),
            "transaction_id": str(rec["transaction_id"]),
            "log_level":      log_level,
        }

        # Add all fields to attributes as strings
        for key, value in rec.items():
            if value is not None:
                # Convert complex types to JSON strings
                if isinstance(value, dict):
                    attrs[key] = json.dumps(value)
                elif isinstance(value, list):
                    attrs[key] = json.dumps(value)
                else:
                    attrs[key] = str(value)

        from opentelemetry.trace import TraceFlags
        logger.emit(LogRecord(
            timestamp=int(time.time_ns()),
            observed_timestamp=int(time.time_ns()),
            trace_id=random.getrandbits(128),
            span_id=random.getrandbits(64),
            trace_flags=TraceFlags(0x01),
            severity_number=severity,
            severity_text=severity.name,
            body=None,  # No body - all data in attributes
            attributes=attrs,
        ))

        body_bytes = len(rec.get("request_body") or "") + len(rec.get("response_body") or "")
        log_line("traces", i + 1,
                 f"log_level={log_level:8s}  txn_id={rec['transaction_id']:4d}  "
                 f"tenant={rec['tenant_id']}  body_bytes={body_bytes}")
        time.sleep(0.1)

    print("[traces  ] Flushing...")
    provider.force_flush()
    time.sleep(3)
    print("[traces  ] Done.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

RUNNERS = {
    "metrics": run_metrics,
    "logs":    run_transaction_logs,
    "traces":  run_trace_logs,
}

if __name__ == "__main__":
    args = sys.argv[1:]

    selected = {k: v for k, v in RUNNERS.items() if not args or k in args}

    if not selected:
        print(f"Unknown collector(s): {args}. Choose from: {list(RUNNERS.keys())}")
        sys.exit(1)

    jwt_token = make_jwt()
    print("=" * 60)
    print(f"JWT : {jwt_token}")
    print(f"Sending {NUM_EVENTS} events each to: {list(selected.keys())}")
    print("=" * 60)

    threads = [threading.Thread(target=fn, name=name, daemon=True)
               for name, fn in selected.items()]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    print("\n" + "=" * 60)
    print("All collectors finished.")
    print("=" * 60)