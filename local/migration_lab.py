"""Local SQLite migration demo; this does not run Azure SQL or Databricks."""

import argparse
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DB = DATA_DIR / "source.db"
TARGET_DB = DATA_DIR / "target.db"

SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    updated_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
    change_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL,
    op TEXT NOT NULL,
    merchant_id INTEGER,
    amount_cents INTEGER,
    status TEXT
);
"""

TARGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    updated_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS migration_control (
    name TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS applied_changes (
    change_seq INTEGER PRIMARY KEY
);
"""

PAYMENT_COLUMNS = (
    "payment_id, merchant_id, amount_cents, status, updated_seq"
)


class ReconciliationError(RuntimeError):
    """Raised when source and target payment rows differ."""


def _validate_database_paths(source_db, target_db):
    source_path = Path(source_db)
    target_path = Path(target_db)
    if source_path.resolve() == target_path.resolve():
        raise ValueError("Source and target databases must be different files.")
    return source_path, target_path


def _validate_rows(rows):
    if rows < 0:
        raise ValueError("rows must be zero or greater.")


def _validate_chunk_size(chunk_size):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")


def init(rows, source_db=SOURCE_DB, target_db=TARGET_DB):
    """Recreate the source and target SQLite databases with synthetic rows."""
    _validate_rows(rows)
    source_path, target_path = _validate_database_paths(source_db, target_db)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    for database in (source_path, target_path):
        if database.exists():
            database.unlink()

    with sqlite3.connect(source_path) as connection:
        connection.executescript(SOURCE_SCHEMA)
        connection.executemany(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?)",
            (
                (
                    payment_id,
                    payment_id % 37 + 1,
                    100 + (payment_id * 73) % 100000,
                    "COMPLETED" if payment_id % 7 else "PENDING",
                    0,
                )
                for payment_id in range(1, rows + 1)
            ),
        )

    with sqlite3.connect(target_path) as connection:
        connection.executescript(TARGET_SCHEMA)
        connection.execute(
            "INSERT INTO migration_control VALUES ('payments', 0)"
        )

    print(
        f"initialized source rows={rows}; "
        f"sqlite databases in {source_path.parent}"
    )


def snapshot(chunk_size=2000, source_db=SOURCE_DB, target_db=TARGET_DB):
    """Copy source rows in keyset-paginated batches and save the CDC watermark."""
    _validate_chunk_size(chunk_size)
    source_path, target_path = _validate_database_paths(source_db, target_db)

    with sqlite3.connect(source_path) as source, sqlite3.connect(
        target_path
    ) as target:
        source.execute("BEGIN")
        high_watermark = source.execute(
            "SELECT COALESCE(MAX(change_seq), 0) FROM changes"
        ).fetchone()[0]
        total_copied = 0
        last_payment_id = 0

        while True:
            rows = source.execute(
                f"SELECT {PAYMENT_COLUMNS} FROM payments "
                "WHERE payment_id > ? ORDER BY payment_id LIMIT ?",
                (last_payment_id, chunk_size),
            ).fetchall()
            if not rows:
                break

            target.executemany(
                """
                INSERT INTO payments VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(payment_id) DO UPDATE SET
                    merchant_id = excluded.merchant_id,
                    amount_cents = excluded.amount_cents,
                    status = excluded.status,
                    updated_seq = excluded.updated_seq
                WHERE excluded.updated_seq >= payments.updated_seq
                """,
                rows,
            )
            last_payment_id = rows[-1][0]
            total_copied += len(rows)

        control = target.execute(
            "UPDATE migration_control SET last_seq = ? WHERE name = 'payments'",
            (high_watermark,),
        )
        if control.rowcount != 1:
            raise RuntimeError(
                "Target migration control is missing; run init before snapshot."
            )

    print(
        f"snapshot copied={total_copied}, "
        f"source change watermark={high_watermark}"
    )
    return total_copied


def mutate(source_db=SOURCE_DB):
    """Create representative update, delete, and insert events in the source."""
    with sqlite3.connect(source_db) as connection:
        changes = (
            ("UPDATE", 1, 1, 219900, "REFUNDED"),
            ("UPDATE", 2, 2, 10100, "COMPLETED"),
            ("DELETE", 3, None, None, None),
            ("INSERT", 999999, 99, 5500, "COMPLETED"),
        )

        for operation, payment_id, merchant_id, amount, status in changes:
            connection.execute(
                """
                INSERT INTO changes
                    (payment_id, op, merchant_id, amount_cents, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (payment_id, operation, merchant_id, amount, status),
            )
            sequence_id = connection.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]

            if operation == "DELETE":
                connection.execute(
                    "DELETE FROM payments WHERE payment_id = ?", (payment_id,)
                )
            else:
                connection.execute(
                    """
                    INSERT INTO payments VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(payment_id) DO UPDATE SET
                        merchant_id = excluded.merchant_id,
                        amount_cents = excluded.amount_cents,
                        status = excluded.status,
                        updated_seq = excluded.updated_seq
                    """,
                    (
                        payment_id,
                        merchant_id,
                        amount,
                        status,
                        sequence_id,
                    ),
                )

    print("created UPDATE/DELETE/INSERT events in source")


def sync(source_db=SOURCE_DB, target_db=TARGET_DB):
    """Apply ordered source events in one target transaction."""
    source_path, target_path = _validate_database_paths(source_db, target_db)

    with sqlite3.connect(source_path) as source, sqlite3.connect(
        target_path
    ) as target:
        control = target.execute(
            "SELECT last_seq FROM migration_control WHERE name = 'payments'"
        ).fetchone()
        if control is None:
            raise RuntimeError(
                "Target migration control is missing; run init before sync."
            )

        changes = source.execute(
            """
            SELECT change_seq, payment_id, op, merchant_id, amount_cents, status
            FROM changes
            WHERE change_seq > ?
            ORDER BY change_seq
            """,
            (control[0],),
        ).fetchall()
        applied = 0

        for sequence_id, payment_id, operation, merchant_id, amount, status in changes:
            already_applied = target.execute(
                "SELECT 1 FROM applied_changes WHERE change_seq = ?",
                (sequence_id,),
            ).fetchone()
            if already_applied:
                continue

            if operation == "DELETE":
                target.execute(
                    "DELETE FROM payments WHERE payment_id = ?", (payment_id,)
                )
            else:
                target.execute(
                    """
                    INSERT INTO payments VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(payment_id) DO UPDATE SET
                        merchant_id = excluded.merchant_id,
                        amount_cents = excluded.amount_cents,
                        status = excluded.status,
                        updated_seq = excluded.updated_seq
                    WHERE excluded.updated_seq >= payments.updated_seq
                    """,
                    (
                        payment_id,
                        merchant_id,
                        amount,
                        status,
                        sequence_id,
                    ),
                )

            target.execute(
                "INSERT INTO applied_changes VALUES (?)", (sequence_id,)
            )
            target.execute(
                "UPDATE migration_control SET last_seq = ? "
                "WHERE name = 'payments'",
                (sequence_id,),
            )
            applied += 1

    print(f"applied {applied} change events; safe to rerun")
    return applied


def verify(source_db=SOURCE_DB, target_db=TARGET_DB):
    """Compare every payment row in both directions without loading all rows."""
    source_path, target_path = _validate_database_paths(source_db, target_db)

    with sqlite3.connect(target_path) as target:
        target.execute(
            "ATTACH DATABASE ? AS source_db", (str(source_path.resolve()),)
        )
        summary_query = (
            "SELECT COUNT(*), COALESCE(SUM(amount_cents), 0) FROM {}.payments"
        )
        source_summary = target.execute(
            summary_query.format("source_db")
        ).fetchone()
        target_summary = target.execute(
            summary_query.format("main")
        ).fetchone()
        source_only = target.execute(
            f"SELECT {PAYMENT_COLUMNS} FROM source_db.payments "
            f"EXCEPT SELECT {PAYMENT_COLUMNS} FROM main.payments LIMIT 1"
        ).fetchone()
        target_only = target.execute(
            f"SELECT {PAYMENT_COLUMNS} FROM main.payments "
            f"EXCEPT SELECT {PAYMENT_COLUMNS} FROM source_db.payments LIMIT 1"
        ).fetchone()

    print(
        f"source count,sum_cents={source_summary}; "
        f"target count,sum_cents={target_summary}; "
        f"exact_match={source_only is None and target_only is None}"
    )
    if source_only is not None or target_only is not None:
        raise ReconciliationError("FAIL: reconciliation mismatch")

    print("PASS: 100% exact row reconciliation (local test only)")


def demo(rows=10000, chunk_size=2000):
    """Run the full local migration and replay demonstration."""
    init(rows)
    snapshot(chunk_size)
    verify()
    mutate()
    sync()
    verify()
    sync()
    verify()


def _non_negative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the local SQLite migration demonstration."
    )
    parser.add_argument(
        "command",
        choices=("init", "snapshot", "mutate", "sync", "verify", "demo"),
    )
    parser.add_argument(
        "--rows", type=_non_negative_int, default=10000,
        help="synthetic source row count for init/demo (default: 10000)",
    )
    parser.add_argument(
        "--chunk-size", type=_positive_int, default=2000,
        help="snapshot page size (default: 2000)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    commands = {
        "init": lambda: init(args.rows),
        "snapshot": lambda: snapshot(args.chunk_size),
        "mutate": mutate,
        "sync": sync,
        "verify": verify,
        "demo": lambda: demo(args.rows, args.chunk_size),
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
