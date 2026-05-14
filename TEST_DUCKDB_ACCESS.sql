-- Test DuckDB access to all OTEL data after configuration fix

INSTALL arrow FROM community;
LOAD arrow;
INSTALL httpfs;
LOAD httpfs;
INSTALL ducklake;
LOAD ducklake;

CREATE OR REPLACE SECRET minio_s3 (
  TYPE S3,
  PROVIDER CONFIG,
  KEY_ID 'minioadmin',
  SECRET 'minioadmin123',
  ENDPOINT 'localhost:9000',
  REGION 'us-east-1',
  USE_SSL false,
  URL_STYLE 'path'
);

ATTACH 'ducklake:postgres:
         host=localhost
         port=5432
         user=sentrinox
         password=sentrinox
         dbname=sentrinox_db'
         AS otel_catalog
         (
             DATA_PATH 's3://otel/main/',
             OVERRIDE_DATA_PATH true
         );

-- Check all tables
SELECT 'LOGS COUNT' as metric, COUNT(*) as count FROM otel_catalog.main.logs
UNION ALL
SELECT 'TRACES COUNT', COUNT(*) FROM otel_catalog.main.traces
UNION ALL
SELECT 'METRICS COUNT', COUNT(*) FROM otel_catalog.main.metrics;

-- Sample data from each table
SELECT '--- SAMPLE LOGS ---' as section;
SELECT * FROM otel_catalog.main.logs LIMIT 2;

SELECT '--- SAMPLE TRACES ---' as section;
SELECT * FROM otel_catalog.main.traces LIMIT 2;

SELECT '--- SAMPLE METRICS ---' as section;
SELECT * FROM otel_catalog.main.metrics LIMIT 2;
