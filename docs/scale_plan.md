# 1.2 TB target design — NOT a measured migration

Assumptions: 1.2 TB source logical data; 1 TB=1000 GB; remaining figures are illustrative capacity calculations, not achieved benchmarks.

## Sizing calculation
- For a 12-hour migration window, 1.2 TB / 12 h = 100 GB/hour ≈ 27.8 MB/sec **sustained at destination** before overhead, rereads, retries, indexes, CDC and validation.
- At a purely hypothetical effective end-to-end rate of 80 MB/sec: 1.2e12 / (80e6) = 15,000 sec ≈ 4.17 hours of raw transfer. This is not a performance prediction.
- Test throughput using bounded 10 GB, 50 GB then 100 GB representative subsets, monitor source CPU/IO, SQL throttling, JDBC concurrent connections, Spark executor skew, Delta small files.

## Migration phases and exit gates
1. Inventory: tables, primary keys, schema drift, data classification, row counts, dependency map, database tier and region.
2. Prepare: network/firewall/private endpoints, identities and secrets, storage, catalog authorization, audit/logging, recovery access.
3. Establish snapshot + CDC boundary: consistent point-in-time and source retention verified.
4. Backfill in controlled batches: partition key strategy, table order, source load limits, isolated staging, restart tokens.
5. Incremental catch-up: ordered inserts/updates/deletes, LSN gap detection, exactly-once effect at sink, replay tests.
6. Reconcile at aligned watermark: row counts, key uniqueness, amounts, nulls, checksums, sample row comparison.
7. Cutover: signed-off acceptance thresholds, pause or capture writes as appropriate, final watermark, BI switching, rollback window.
8. Hypercare: SLA dashboards, drift, CDC lag, pipeline incidents, change management.

## Risk register
- Overloading source Azure SQL: bound JDBC concurrency and measure before scaling.
- Snapshot/CDC gap: pin transactionally consistent snapshot and source LSN boundary.
- Delete reordered after insert: tombstones/version history to prevent resurrection.
- CDC retention overrun: alert on oldest unread LSN and stop cutover; resnapshot if unrecoverable.
- China region mismatch: verify 21V availability, endpoint, region, auth and Unity Catalog features in the actual tenant.
- Cost: cluster usage, storage, network egress and source database tier all require budgeting.
