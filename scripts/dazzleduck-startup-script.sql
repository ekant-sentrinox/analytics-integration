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
AS otel_catalog
(
    DATA_PATH 's3://otel/main/',
    OVERRIDE_DATA_PATH true
);