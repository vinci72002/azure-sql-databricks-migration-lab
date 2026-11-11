import sqlite3
import tempfile
import unittest
from pathlib import Path

from local import migration_lab


class MigrationLabTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source_db = Path(self.temp_dir.name) / "source.db"
        self.target_db = Path(self.temp_dir.name) / "target.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_snapshot_sync_and_replay_reconcile_exactly(self):
        migration_lab.init(10, self.source_db, self.target_db)

        self.assertEqual(
            migration_lab.snapshot(3, self.source_db, self.target_db), 10
        )
        migration_lab.verify(self.source_db, self.target_db)

        migration_lab.mutate(self.source_db)
        self.assertEqual(
            migration_lab.sync(self.source_db, self.target_db), 4
        )
        migration_lab.verify(self.source_db, self.target_db)

        self.assertEqual(
            migration_lab.sync(self.source_db, self.target_db), 0
        )
        migration_lab.verify(self.source_db, self.target_db)

    def test_verify_reports_row_mismatch(self):
        migration_lab.init(3, self.source_db, self.target_db)
        migration_lab.snapshot(2, self.source_db, self.target_db)

        with sqlite3.connect(self.target_db) as connection:
            connection.execute(
                "UPDATE payments SET amount_cents = amount_cents + 1 "
                "WHERE payment_id = 1"
            )

        with self.assertRaises(migration_lab.ReconciliationError):
            migration_lab.verify(self.source_db, self.target_db)

    def test_invalid_init_does_not_remove_existing_databases(self):
        self.source_db.write_text("source sentinel")
        self.target_db.write_text("target sentinel")

        with self.assertRaisesRegex(ValueError, "rows"):
            migration_lab.init(-1, self.source_db, self.target_db)

        self.assertEqual(self.source_db.read_text(), "source sentinel")
        self.assertEqual(self.target_db.read_text(), "target sentinel")

    def test_snapshot_requires_positive_chunk_size(self):
        with self.assertRaisesRegex(ValueError, "chunk_size"):
            migration_lab.snapshot(0, self.source_db, self.target_db)

    def test_source_and_target_must_be_different_files(self):
        with self.assertRaisesRegex(ValueError, "different files"):
            migration_lab.init(1, self.source_db, self.source_db)


if __name__ == "__main__":
    unittest.main()
