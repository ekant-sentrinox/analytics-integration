
-- Check all tables


-- Sample data from each table
SELECT '--- SAMPLE LOGS ---' as section;
SELECT * FROM ollylake.main.trace_log LIMIT 2;

SELECT '--- SAMPLE TRACES ---' as section;
SELECT * FROM ollylake.main.gateway_metrics LIMIT 2;

SELECT '--- SAMPLE METRICS ---' as section;
SELECT * FROM ollylake.main.transaction_log LIMIT 2;

SELECT 'LOGS COUNT' as metric, COUNT(*) as count FROM ollylake.main.trace_log
UNION ALL
SELECT 'TRACES COUNT', COUNT(*) FROM ollylake.main.gateway_metrics
UNION ALL
SELECT 'METRICS COUNT', COUNT(*) FROM ollylake.main.transaction_log


-- to see view tables

FROM ollylake.main.trace;

FROM ollylake.main.gateway;

FROM ollylake.main.transaction;