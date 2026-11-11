# Governance & metadata checklist

- Catalog/schema/table inventory and business data owner mapping
- Sensitive data classification: customer and payment identifiers; do not expose PII in shared logs
- Least privilege roles: migration operator, ETL service principal, BI reader, auditor
- Centralized lineage (if supported in deployed workspace), pipeline/job audit, schema evolution approvals
- Data contracts: schema, nullability, uniqueness, currency, timezone, soft deletes
- Reconciliation evidence stored with run_id, source LSN, data timestamp, checksums and approver
- Restore/runbook tabletop exercise + sign-off
- Verify Azure China (21Vianet) feature parity in the customer's tenant before claiming UC support
