# Databricks notebook source
# WARNING: Template only. Requires real Azure SQL, driver, Key Vault-backed secret scope,
# permissions, and governed UC target schema. Not validated against a live workspace.
from pyspark.sql import functions as F

jdbc_url = dbutils.secrets.get('migration-secrets','azure-sql-jdbc-url')
username = dbutils.secrets.get('migration-secrets','azure-sql-user')
password = dbutils.secrets.get('migration-secrets','azure-sql-password')
target_table = 'migration_dev.bronze.payment_snapshot'

# IMPORTANT: For a consistent full load, source snapshot isolation and a durable CDC
# boundary/LSN must be coordinated externally. This snippet alone is NOT cutover-safe.
reader = (spark.read.format('jdbc')
    .option('url', jdbc_url)
    .option('dbtable','dbo.payments')
    .option('user',username).option('password',password)
    .option('driver','com.microsoft.sqlserver.jdbc.SQLServerDriver')
    .option('partitionColumn','payment_id')
    .option('lowerBound','1').option('upperBound','1000000')
    .option('numPartitions','8').option('fetchsize','10000'))
df=reader.load().withColumn('_ingested_at',F.current_timestamp())
# In real migration write to isolated run-specific staging, verify counts, then publish atomically.
(df.write.format('delta').mode('overwrite').option('overwriteSchema','true').saveAsTable(target_table))
print('loaded_rows=',df.count())
