-- Azure SQL Database: DBA must review tier, log utilization and permissions before enabling.
-- This is a controlled-lab example, not an instruction to modify production blindly.
EXEC sys.sp_cdc_enable_db;
GO
EXEC sys.sp_cdc_enable_table
    @source_schema = N'dbo',
    @source_name = N'payments',
    @role_name = NULL,
    @supports_net_changes = 1;
GO
-- During initial snapshot, record a consistent source boundary and CDC retention.
-- Build an extractor using supported CDC functions and durable LSN checkpointing.
