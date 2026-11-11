# 企业支付数据迁移实验：Azure SQL → Databricks

[English](README.md) | **简体中文**

这是一个用于学习和演示 Azure SQL 到 Databricks 迁移思路的项目，包含可在本地运行的 SQLite 端到端模拟器、Azure SQL/Databricks 云端实现模板，以及 **1.2 TB 目标规模的设计规划**。

> **项目状态：** 本地小规模模拟与云端模板。并非已完成的 1.2 TB 迁移，也没有在 Azure 中国（21Vianet）环境中验证或部署。

## 快速开始

要求 Python 3。本地模拟器仅使用 Python 标准库，无需安装第三方依赖。在项目根目录运行：

```bash
python local/migration_lab.py demo --rows 10000
```

演示会初始化模拟源库和目标库，执行全量快照，对账后在源库生成 4 条示例变更（更新、删除、插入），同步变更，再次对账并重放同步以验证重复执行行为。源库和目标库均为 SQLite。

> **注意：** `demo` 会重建 `data/source.db` 和 `data/target.db`。请勿在这两个演示数据库中保存需要保留的数据。

如需逐步观察各阶段：

```bash
python local/migration_lab.py init --rows 10000
python local/migration_lab.py snapshot
python local/migration_lab.py verify
python local/migration_lab.py mutate
python local/migration_lab.py sync
python local/migration_lab.py verify
python local/migration_lab.py sync
python local/migration_lab.py verify
```

也可以调整数据量和全量加载分批大小：

```bash
python local/migration_lab.py demo --rows 100000
python local/migration_lab.py snapshot --chunk-size 5000
```

## 项目结构

```text
.
├── local/
│   └── migration_lab.py              # SQLite 本地迁移模拟器与命令行入口
├── sql/
│   └── azure_sql_cdc_setup.sql       # Azure SQL CDC 启用示例（需 DBA 审核和权限）
├── databricks/
│   ├── 01_full_load.py               # JDBC 并行全量读取到 Delta 的模板
│   ├── 02_cdc_merge.sql              # CDC 落地后的 Delta MERGE 模板
│   └── 03_reconciliation.sql         # 目标端统计与唯一性检查 SQL
├── docs/
│   ├── project_overview.md           # 结构、运行/测试说明和 Mermaid 流程图
│   ├── scale_plan.md                 # 规模估算、迁移阶段与风险
│   ├── governance.md                 # 治理与元数据检查清单
│   └── interview.md                  # 中英文项目介绍素材
├── tests/                            # 当前没有自动化测试用例
├── README.md                         # 英文说明
└── README.zh-CN.md                   # 本文件
```

## 本地演示的阶段

1. `init`：生成合成支付数据并初始化源库、目标库。
2. `snapshot`：按主键分页复制源数据，记录当前变更水位。
3. `verify`：比较源库和目标库的完整有序记录。
4. `mutate`：在源库生成示例更新、删除和插入事件。
5. `sync`：按变更序号将新事件应用到目标库。
6. 再次 `verify` 并重跑 `sync`，检查数据一致性与重放行为。

## 测试

当前 `tests/` 目录没有 pytest/unittest 用例，也没有项目级测试配置。现有本地端到端演示可作为冒烟测试：

```bash
python local/migration_lab.py demo --rows 10000
```

`verify` 会对源库和目标库的全部记录排序后逐行比较，不只比较行数或金额汇总。不一致时命令会以失败状态退出。可以先用较小数据量快速验证，再调整 `--rows` 观察本机运行表现；这**不是** 1.2 TB 性能测试。

本地模拟**不验证**以下内容：

- Azure SQL CDC 读取、LSN 边界或 CDC 保留期
- 并发写入期间的一致性和生产切换安全性
- Databricks/Spark 执行、Delta Lake 写入
- 云端凭据、网络、权限和服务可用性
- 生产级 offset 提交、断点恢复或 Azure 中国（21Vianet）兼容性

更多逐步运行说明和云端验证边界见[项目结构与运行测试说明](docs/project_overview.md)。

## 云端模板说明

- `sql/azure_sql_cdc_setup.sql`：Azure SQL CDC 启用示例；运行前需 DBA 审核数据库层级、日志使用和权限，不要未经审核用于生产环境。
- `databricks/01_full_load.py`：从 Azure SQL 通过 JDBC 并行读取并写入 Delta 的模板。需要配置 JDBC 驱动、密钥作用域、目标 catalog/schema/table，并协调一致性快照与 CDC 起始边界。
- `databricks/02_cdc_merge.sql`：针对已落地、去重且有序的 CDC staging 数据执行 Delta MERGE。
- `databricks/03_reconciliation.sql`：目标端行数、主键唯一性和按商户聚合检查。源与目标应在相同 CDC 水位比较。

以上文件是实现模板，当前没有连接到已部署的 Databricks 工作区，也没有由本地脚本自动调用。

## 已知限制与后续工程工作

1. 本地 SQLite 变更事件由演示代码显式生成，不是 Azure SQL CDC，也不是通用触发器。
2. 本地快照在事务中读取，演示变更发生在快照后；尚未证明并发切换场景的正确性。
3. Databricks 模板尚未集成到实际工作区；Unity Catalog 资源和 SQL Server JDBC 驱动需要预先配置。
4. Delta MERGE 假设 CDC staging 的模式和顺序正确。生产环境还需可靠处理 offset、乱序迟到事件和删除 tombstone。
5. Azure 中国（21Vianet）的网络端点、服务可用性和身份方案需在实际订阅中验证。
6. 1.2 TB 数据量及时间估算为规划假设，不是性能测试或迁移结果。

## 技术参考

- [Azure SQL CDC 概述](https://learn.microsoft.com/en-us/azure/azure-sql/database/change-data-capture-overview?view=azuresql)
- [Azure Databricks JDBC 并行读取参考](https://learn.microsoft.com/en-us/azure/databricks/pyspark/reference/classes/dataframereader/jdbc)
- [Azure 中国文档](https://docs.azure.cn/)
