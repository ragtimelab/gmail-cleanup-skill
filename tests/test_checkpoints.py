import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/gmail-cleanup/scripts"))
from checkpoints import Failure, LEASE_SECONDS, diagnose, locked, operate, review_query


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / ".cache"

    def run_state(self, command, account="sample-a", now=200, **kwargs):
        return operate(self.cache, command, account, now=now, **kwargs)

    def test_first_review_then_contiguous_increment_and_explicit_full(self):
        first = self.run_state("begin", end=180)
        self.assertEqual(first["query"], "in:inbox before:180")
        self.assertEqual(self.run_state("finish", token=first["token"])["status"], "saved")
        next_run = self.run_state("begin", end=195)
        self.assertEqual(next_run["query"], "in:inbox after:180 before:195")
        self.assertEqual(self.run_state("finish", token=next_run["token"])["status"], "saved")
        full = self.run_state("begin", end=200, full=True)
        self.assertEqual(full["query"], "in:inbox before:200")

    def test_independent_accounts_failure_and_empty_completion(self):
        first = self.run_state("begin", end=170)
        self.run_state("finish", token=first["token"])
        a = self.run_state("begin", end=180)
        b = self.run_state("begin", "sample-b", end=180)
        self.run_state("finish", "sample-b", token=b["token"])
        self.run_state("release", token=a["token"])
        self.assertEqual(self.run_state("begin", end=195)["start"], 170)
        self.assertEqual(self.run_state("begin", "sample-b", end=195)["start"], 180)

    def test_same_account_busy_expiry_and_stale_writer(self):
        first = self.run_state("begin", end=180)
        self.assertEqual(self.run_state("begin", end=181)["status"], "busy")
        self.assertEqual(self.run_state("reset")["status"], "busy")
        later = 200 + LEASE_SECONDS
        second = self.run_state("begin", end=190, now=later)
        self.assertEqual(self.run_state("finish", token=first["token"], now=later)["status"],
                         "lease_lost")
        self.assertEqual(self.run_state("finish", token=second["token"], now=later)["status"],
                         "saved")

    def test_renew_and_clock_regression(self):
        first = self.run_state("begin", end=180)
        self.run_state("renew", token=first["token"], now=205)
        later = 200 + LEASE_SECONDS
        self.assertEqual(self.run_state("begin", end=190, now=later)["status"], "busy")
        self.run_state("finish", token=first["token"], now=later)
        self.assertEqual(self.run_state("begin", end=179)["status"], "clock_regressed")

    def test_damaged_cache_preserves_valid_accounts_and_reset_is_scoped(self):
        self.cache.mkdir()
        path = self.cache / "checkpoints.json"
        path.write_text('{"version":1,"accounts":{"sample-a":"invalid","sample-b":100}}')
        first = self.run_state("begin", end=180)
        self.assertTrue(first["cache_rebuild"])
        self.assertIsNone(first["start"])
        self.run_state("finish", token=first["token"])
        self.assertEqual(self.run_state("reset")["status"], "reset")
        self.assertEqual(json.loads(path.read_text())["accounts"], {"sample-b": 100})
        self.run_state("reset", None)
        self.assertEqual(json.loads(path.read_text())["accounts"], {})

    def test_unavailable_cache_never_touches_another_path(self):
        self.cache.write_text("blocked")
        with self.assertRaises(Failure) as raised:
            self.run_state("begin", end=180)
        self.assertEqual(raised.exception.result["phase"], "mkdir")
        self.assertEqual(self.cache.read_text(), "blocked")

    def test_finish_write_failure_keeps_prior_boundary_and_active_lease(self):
        first = self.run_state("begin", end=170)
        self.run_state("finish", token=first["token"])
        second = self.run_state("begin", end=180)
        path = self.cache / "checkpoints.json"
        before = path.read_bytes()
        with patch("checkpoints.os.replace", side_effect=OSError(errno.ENOSPC, "full")):
            with self.assertRaises(Failure) as raised:
                self.run_state("finish", token=second["token"])
        self.assertEqual(raised.exception.result,
                         {"status": "storage_error", "phase": "replace", "errno": errno.ENOSPC})
        self.assertEqual(path.read_bytes(), before)
        expected = {"status": "saved", "end": 180}
        self.assertEqual(self.run_state("finish", token=second["token"]), expected)
        self.assertEqual(self.run_state("finish", token=second["token"]), expected)

    def test_active_legacy_run_blocks_migration_and_corrupt_state_fails_closed(self):
        self.cache.mkdir()
        leases = self.cache / "leases.json"
        leases.write_text(json.dumps({"sample-a": {"token": "a" * 32, "end": 150, "expires": 205}}))
        self.assertEqual(self.run_state("begin", end=180)["reason"], "legacy_active")
        leases.write_text("{")
        with self.assertRaises(Failure) as raised:
            self.run_state("begin", end=180)
        self.assertEqual(raised.exception.result["status"], "state_invalid")
        self.assertEqual(leases.read_text(), "{")

    def test_lock_timeout_does_not_delete_lock(self):
        with locked(self.cache), patch("checkpoints.LOCK_SECONDS", 0):
            with self.assertRaises(Failure) as raised:
                self.run_state("begin", end=180)
        self.assertEqual(raised.exception.result["status"], "lock_timeout")
        self.assertTrue((self.cache / "checkpoints.lock").is_file())

    def test_diagnose_round_trip_does_not_touch_real_cache(self):
        root = self.cache.parent
        result = diagnose(root, "create")
        self.assertEqual(diagnose(root, "read", result["probe_id"])["status"], "probe_found")
        self.assertEqual(diagnose(root, "clean", result["probe_id"])["status"], "probe_removed")
        self.assertFalse(self.cache.exists())
        self.assertFalse(list(root.iterdir()))

    def test_installed_cli_reports_structured_failure_without_echoing_inputs(self):
        scripts = self.cache.parent / "scripts"
        scripts.mkdir()
        source = Path(sys.modules["checkpoints"].__file__)
        script = shutil.copy2(source, scripts)
        self.cache.write_text("not a directory")
        result = subprocess.run([sys.executable, script, "begin", "sample-private", "42"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["phase"], "mkdir")
        self.assertNotIn("sample-private", result.stdout + result.stderr)

    def test_one_off_query_has_no_checkpoint_dependency(self):
        self.assertEqual(review_query(100, 200), "in:inbox after:100 before:200")
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
