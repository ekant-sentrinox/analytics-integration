CREATE OR REPLACE SECRET minio_s3 (
  TYPE S3,
  PROVIDER CONFIG,
  KEY_ID 'minioadmin',
  SECRET 'minioadmin123',
  ENDPOINT 'minio:9000',
  USE_SSL false,
  URL_STYLE 'path'
);

ATTACH 'ducklake:postgres:
host=postgres
port=5432
user=sentrinox
password=sentrinox
dbname=sentrinox_db'
AS ollylake
(
    DATA_PATH 's3://ollylake/main/',
    OVERRIDE_DATA_PATH true
);


CREATE OR REPLACE VIEW ollylake.main.transaction AS
SELECT
    -- Core timestamps and severity
    timestamp,
    observed_timestamp,
    severity_number,
    severity_text,

    -- Trace context
    trace_id,
    span_id,
    flags,

    -- Event metadata
    event_name,
    body,

    -- Extracted attributes from JSON
    CAST(attributes->>'event_type' AS VARCHAR)                     AS event_type,
    CAST(attributes->>'event_time' AS TIMESTAMP)                   AS event_time,
    CAST(attributes->>'transaction_id' AS BIGINT)                  AS transaction_id,
    CAST(attributes->>'tenant_id' AS INTEGER)                     AS tenant_id,
    CAST(attributes->>'customer_id' AS INTEGER)                   AS customer_id,
    CAST(attributes->>'workspace_id' AS INTEGER)                  AS workspace_id,
    CAST(attributes->>'gateway_id' AS INTEGER)                    AS gateway_id,
    CAST(attributes->>'user_id' AS INTEGER)                       AS user_id,
    CAST(attributes->>'v_key_id' AS INTEGER)                      AS v_key_id,
    CAST(attributes->>'agent_id' AS INTEGER)                      AS agent_id,
    CAST(attributes->>'provider_id' AS INTEGER)                   AS provider_id,

    -- Status and model information
    CAST(attributes->>'status' AS VARCHAR)                        AS status,
    CAST(attributes->>'model_id' AS VARCHAR)                      AS model_id,
    CAST(attributes->>'original_model_id' AS VARCHAR)             AS original_model_id,
    CAST(attributes->>'provider_response_id' AS VARCHAR)          AS provider_response_id,
    CAST(attributes->>'usage_schema_version' AS VARCHAR)          AS usage_schema_version,

    -- Network information
    CAST(attributes->>'source_ip' AS BIGINT)                      AS source_ip,
    CAST(attributes->>'source_port' AS INTEGER)                   AS source_port,
    CAST(attributes->>'target_url' AS VARCHAR)                    AS target_url,
    CAST(attributes->>'target_ip' AS BIGINT)                      AS target_ip,
    CAST(attributes->>'target_port' AS INTEGER)                   AS target_port,
    CAST(attributes->>'target_region' AS VARCHAR)                 AS target_region,

    -- HTTP/TLS information
    CAST(attributes->>'http_method' AS VARCHAR)                   AS http_method,
    CAST(attributes->>'http_status_code' AS INTEGER)              AS http_status_code,
    CAST(attributes->>'http_version' AS VARCHAR)                  AS http_version,
    CAST(attributes->>'tls_version' AS VARCHAR)                   AS tls_version,
    CAST(attributes->>'content_type' AS VARCHAR)                  AS content_type,
    CAST(attributes->>'user_agent' AS VARCHAR)                    AS user_agent,

    -- Performance metrics
    CAST(attributes->>'total_latency_ms' AS BIGINT)               AS total_latency_ms,
    CAST(attributes->>'gateway_latency_ms' AS BIGINT)             AS gateway_latency_ms,
    CAST(attributes->>'ttft_ms' AS BIGINT)                        AS ttft_ms,

    -- Token usage
    CAST(attributes->>'input_tokens' AS BIGINT)                   AS input_tokens,
    CAST(attributes->>'output_tokens' AS BIGINT)                  AS output_tokens,

    -- Byte usage
    CAST(attributes->>'bytes_in' AS BIGINT)                       AS bytes_in,
    CAST(attributes->>'bytes_out' AS BIGINT)                      AS bytes_out,

    -- Cost
    CAST(attributes->>'estimated_cost_usd' AS DOUBLE)             AS estimated_cost_usd,

    -- Retry and stop reason
    CAST(attributes->>'retry_count' AS INTEGER)                   AS retry_count,
    CAST(attributes->>'stop_reason' AS VARCHAR)                   AS stop_reason,

    -- Rate limits
    CAST(attributes->>'rl_limit_requests' AS INTEGER)             AS rl_limit_requests,
    CAST(attributes->>'rl_remaining_requests' AS INTEGER)         AS rl_remaining_requests,
    CAST(attributes->>'rl_limit_tokens' AS BIGINT)                AS rl_limit_tokens,
    CAST(attributes->>'rl_remaining_tokens' AS BIGINT)            AS rl_remaining_tokens,
    CAST(attributes->>'rl_reset_at' AS TIMESTAMP)                 AS rl_reset_at,

    -- Prompt information
    CAST(attributes->>'user_prompt' AS VARCHAR)                   AS user_prompt,
    CAST(attributes->>'user_prompt_suppressed' AS BOOLEAN)        AS user_prompt_suppressed,

    -- Fallback and PII flags
    CAST(attributes->>'fallback_triggered' AS BOOLEAN)            AS fallback_triggered,
    CAST(attributes->>'pii_detected' AS BOOLEAN)                  AS pii_detected,
    CAST(attributes->>'pii_redacted' AS BOOLEAN)                  AS pii_redacted,

    -- Nested JSON preserved as text
    CAST(attributes->>'input_token_details' AS VARCHAR)           AS input_token_details,
    CAST(attributes->>'output_token_details' AS VARCHAR)          AS output_token_details,
    CAST(attributes->>'provider_usage' AS VARCHAR)                AS provider_usage,

    -- Resource attributes
    CAST(resource_attributes->>'service.name' AS VARCHAR)         AS service_name,
    CAST(resource_attributes->>'service.version' AS VARCHAR)      AS service_version,
    CAST(resource_attributes->>'cloud.region' AS VARCHAR)         AS cloud_region,
    CAST(resource_attributes->>'sntx.gateway_id' AS INTEGER)      AS resource_gateway_id,
    CAST(resource_attributes->>'telemetry.sdk.name' AS VARCHAR)   AS telemetry_sdk_name,
    CAST(resource_attributes->>'telemetry.sdk.language' AS VARCHAR) AS telemetry_sdk_language,
    CAST(resource_attributes->>'telemetry.sdk.version' AS VARCHAR) AS telemetry_sdk_version,

    -- Instrumentation scope
    scope_name,
    scope_version,

FROM  ollylake.main.transaction_log;

CREATE OR REPLACE VIEW ollylake.main.trace AS
SELECT
    -- Core timestamps
    timestamp,
    observed_timestamp,

    -- Log severity
    severity_number,
    severity_text,

    -- Trace context
    trace_id,
    span_id,
    flags,

    -- Optional fields
    event_name,
    body,

    -- Extracted attributes
    CAST(attributes->>'event_type' AS VARCHAR)        AS event_type,
    CAST(attributes->>'event_time' AS TIMESTAMP)      AS event_time,
    CAST(attributes->>'transaction_id' AS BIGINT)     AS transaction_id,
    CAST(attributes->>'tenant_id' AS INTEGER)         AS tenant_id,
    CAST(attributes->>'customer_id' AS INTEGER)       AS customer_id,
    CAST(attributes->>'workspace_id' AS INTEGER)      AS workspace_id,
    CAST(attributes->>'gateway_id' AS INTEGER)        AS gateway_id,
    CAST(attributes->>'user_id' AS INTEGER)           AS user_id,
    CAST(attributes->>'v_key_id' AS INTEGER)          AS v_key_id,

    -- Trace-specific fields
    CAST(attributes->>'log_level' AS VARCHAR)         AS log_level,

    -- Resource attributes
    CAST(resource_attributes->>'service.name' AS VARCHAR)          AS service_name,
    CAST(resource_attributes->>'service.version' AS VARCHAR)       AS service_version,
    CAST(resource_attributes->>'cloud.region' AS VARCHAR)          AS cloud_region,
    CAST(resource_attributes->>'sntx.gateway_id' AS INTEGER)       AS resource_gateway_id,
    CAST(resource_attributes->>'telemetry.sdk.name' AS VARCHAR)    AS telemetry_sdk_name,
    CAST(resource_attributes->>'telemetry.sdk.language' AS VARCHAR) AS telemetry_sdk_language,
    CAST(resource_attributes->>'telemetry.sdk.version' AS VARCHAR) AS telemetry_sdk_version,

    -- Instrumentation scope
    scope_name,
    scope_version,

FROM ollylake.main.trace_log;

CREATE OR REPLACE VIEW ollylake.main.gateway AS
SELECT
    -- Metric metadata
    name,
    description,
    unit,
    metric_type,

    -- Timestamps
    start_time_ms,
    time_ms,

    -- Metric values
    value_double,
    value_int,
    count,
    sum,
    aggregation_temporality,

    -- Extracted metric attributes
    CAST(attributes->>'env' AS VARCHAR)                     AS env,
    CAST(attributes->>'index' AS INTEGER)                   AS metric_index,
    CAST(attributes->>'sntx.tenant_id' AS INTEGER)          AS tenant_id,
    CAST(attributes->>'sntx.customer_id' AS INTEGER)        AS customer_id,
    CAST(attributes->>'sntx.workspace_id' AS INTEGER)       AS workspace_id,
    CAST(attributes->>'sntx.gateway_id' AS INTEGER)         AS gateway_id,
    CAST(attributes->>'cloud.region' AS VARCHAR)            AS metric_cloud_region,
    CAST(attributes->>'sntx.event_type' AS VARCHAR)         AS event_type,
    CAST(attributes->>'llm.provider_id' AS INTEGER)         AS provider_id,
    CAST(attributes->>'llm.model_id' AS VARCHAR)            AS model_id,

    -- Resource attributes
    CAST(resource_attributes->>'service.name' AS VARCHAR)           AS service_name,
    CAST(resource_attributes->>'service.version' AS VARCHAR)        AS service_version,
    CAST(resource_attributes->>'cloud.region' AS VARCHAR)           AS resource_cloud_region,
    CAST(resource_attributes->>'sntx.gateway_id' AS INTEGER)        AS resource_gateway_id,
    CAST(resource_attributes->>'telemetry.sdk.name' AS VARCHAR)     AS telemetry_sdk_name,
    CAST(resource_attributes->>'telemetry.sdk.language' AS VARCHAR) AS telemetry_sdk_language,
    CAST(resource_attributes->>'telemetry.sdk.version' AS VARCHAR)  AS telemetry_sdk_version,

    -- Instrumentation scope
    scope_name,
    scope_version,


FROM ollylake.main.gateway_metrics;