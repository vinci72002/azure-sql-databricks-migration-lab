# 迁移项目技术问答

本文介绍项目的组成、迁移设计取舍和当前验证边界，便于快速了解代码与后续实施工作。

## 这个项目解决什么问题？

项目演示将 Azure SQL 支付数据迁移到 Databricks Delta Lake 的一种分阶段设计：按月进行全量读取、通过 CDC 接收后续变更、把变更合并到目标表，并在一致的数据水位上对账。它由 SQLite 本地模拟器和云端 SQL/Python 模板组成，不是已部署的生产迁移流水线。

## 本地模拟器验证了什么？

`local/migration_lab.py` 使用 Python 标准库和 SQLite。它生成合成支付记录，分页复制快照，再生成更新、删除和插入事件并按序同步。对账用 SQLite 双向 `EXCEPT` 检查两侧的完整记录；单元测试覆盖快照、重放、差异检测和输入校验。

这些验证只说明本地模拟流程有效，不代表 Azure SQL CDC、Spark、Delta Lake 或云端故障恢复已经验证。

## 全量读取为什么按月份切分？

`databricks/01_full_load.py` 根据 `payment_time` 生成半开区间 `[月初, 下月月初)`，通过 JDBC 并行读取当月数据，并用 Delta `replaceWhere` 替换对应的 `batch_month` 分区。这样便于按月份重跑，而不是每次覆盖整张目标表。

实际执行前仍需校验时间列和分区边界、目标表分区布局、JDBC 并发对源库的影响，以及快照与 CDC 起始 LSN 的协调。模板里的连接信息来自 Databricks secret scope；不得把真实密码提交到代码库。

## CDC MERGE 如何处理更新和删除？

`databricks/02_cdc_merge.sql` 对 CDC staging 按 `payment_id` 分组，选出 `sequence_id` 最大的事件，再与 Silver 目标表执行 MERGE。插入和更新写入最新业务字段及版本号；删除不物理移除目标记录，而是设置 `is_deleted = true`，以保留 key 和版本信息，降低旧事件重新“复活”记录的风险。当前有效记录查询通过 `is_deleted = false` 过滤。

该设计依赖 staging 中事件完整且序号可比较。需要保证每个 key 的事件排序确定（例如 `sequence_id` 唯一，或提供额外的稳定排序键），并在生产流程中持久化 offset、处理迟到/乱序事件，以及定义 tombstone 的保留策略。

## 如何判断迁移前后数据一致？

`databricks/03_reconciliation.sql` 分别提供 Azure SQL 源端和 Databricks 目标端查询，包括总行数/金额、按月份聚合、按商户聚合，以及目标主键重复检查。由于两端使用不同 SQL 方言，应在各自引擎执行后比较结果，并确保比较时处于相同 CDC 水位。生产对账还可结合分区校验、空值统计、校验和及抽样明细。

## JDBC 并行度设大是否一定更快？

不是。并行分区会增加 Azure SQL 并发连接和查询压力，实际吞吐还受源库资源、网络、分区键分布、Spark executor、数据倾斜和 Delta 写入限制影响。应通过有代表性的批次逐步压测，同时监控源端 CPU/IO、限流、Spark task 和写入文件大小，而不是直接把 `numPartitions` 调到最大。

## 1.2 TB 是已验证的迁移规模吗？

不是。它是容量规划中的假设目标，项目没有报告 1.2 TB 实测结果。规划文档中的速率和时长是用于估算窗口与设计压测的数字，不应解读为基准测试或 SLA。

## 距离云端端到端迁移还缺什么？

- 在测试 Azure SQL 环境配置并验证 CDC、权限、保留期和一致快照/LSN 边界。
- 实现持久化 CDC 抽取器，把有序事件可靠写入 `bronze.payment_changes`。
- 在 Databricks 配置 JDBC 驱动、secret scope、catalog/schema/table，并验证月度重跑和目标表初始化。
- 明确从全量 Bronze 快照初始化 Silver 表的步骤，并验证全量与增量之间无缺口。
- 测试断点恢复、重复执行、迟到事件、保留期过期、回滚和统一水位对账。
- 在目标 Azure 中国（21Vianet）租户验证服务可用性、网络端点和身份方案。

这些能力不由当前本地 demo 自动实现。
