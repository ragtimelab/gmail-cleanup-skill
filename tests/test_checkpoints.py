import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/gmail-cleanup/scripts"))
from checkpoints import LEASE_SECONDS, operate, review_query


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
        with self.assertRaises(OSError):
            self.run_state("begin", end=180)
        self.assertEqual(self.cache.read_text(), "blocked")

    def test_one_off_query_has_no_checkpoint_dependency(self):
        self.assertEqual(review_query(100, 200), "in:inbox after:100 before:200")
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
