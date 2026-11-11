# Interview story — label the experience accurately

## Chinese
“我搭建了一个个人端到端数据迁移实验项目，模拟 Azure SQL 交易系统向 Databricks Delta Lake 迁移。我把迁移分为基线快照、增量 CDC、版本化 MERGE、数据对账以及上线切换。使用本地 SQLite 实现并实际验证了小规模全量+插入、更新、删除的增量重放；同时为 Azure SQL JDBC/Databricks 编写了迁移模板，并做了 1.2TB 规模的容量与风险规划。这个 1.2TB 是设计目标，不是生产实测，我还没有 21V 生产部署经验。”

## English
“I built a personal end-to-end migration lab modeled on Azure SQL to Databricks. I exercised initial snapshot, incremental changes, replay-safe upserts/deletes and reconciliation locally, and prepared Spark JDBC and Delta MERGE templates for the cloud phase. I also designed a 1.2 TB capacity plan, with source-throttling, CDC boundary, recovery and cutover risks. The 1.2 TB is a planned scale, not an executed production migration, and I have not deployed it in a 21V production tenant.”

## Questions to be ready for
1. How do you align a snapshot with the first CDC LSN without a gap?
2. Why does changing JDBC numPartitions not always improve performance?
3. How do you recover when CDC retention has expired?
4. How do you ensure a deleted order is not resurrected by late events?
5. How do you prove amounts match when source data keeps changing?
6. Who signs off on cutover and rollback?
7. Which 21V-specific endpoints and services have you actually verified?
