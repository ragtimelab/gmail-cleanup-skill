import copy
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/gmail-cleanup/scripts"))
from verify import check, seal


def candidate(account, message_id):
    return {"account": account, "id": message_id, "subject": "Past event",
            "reason": "Registration closed", "labels": ["INBOX", "UNREAD"]}


def identity(account, message_id):
    return {"account": account, "id": message_id}


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.first = identity("sample-a", "abc")
        self.second = identity("sample-b", "abc")
        self.manifest = {"items": [candidate("sample-a", "abc"), candidate("sample-b", "abc")]}
        self.payload = {"manifest": self.manifest,
                        "approval": {"digest": seal(self.manifest)[1], "items": [self.first]},
                        "batch": [self.first], "observed": [], "phase": "before"}

    def observe(self, flags, **extra):
        self.payload["observed"] = [{**self.first, "labels": flags, **extra}]

    def test_identical_id_in_different_account_cannot_enter_batch(self):
        self.payload["batch"] = [self.second]
        with self.assertRaises(ValueError):
            check(self.payload)

    def test_manifest_change_requires_new_approval(self):
        self.manifest["items"][0]["reason"] = "Other reason"
        with self.assertRaises(ValueError):
            check(self.payload)

    def test_seal_canonicalizes_order(self):
        other = copy.deepcopy(self.manifest)
        other["items"].reverse()
        other["items"][0]["labels"].reverse()
        self.assertEqual(seal(other)[1], seal(self.manifest)[1])

    def test_ready_requires_unchanged_labels_and_approval(self):
        self.observe(["INBOX", "UNREAD"])
        self.assertEqual(check(self.payload)["ready"], [self.first])
        self.observe(["INBOX", "UNREAD", "STARRED"])
        self.assertEqual(len(check(self.payload)["held"]), 1)

    def test_no_blind_retry_missing_or_held(self):
        self.assertEqual(len(check(self.payload)["held"]), 1)
        self.observe(["INBOX", "UNREAD"], hold=True)
        self.assertFalse(check(self.payload)["ready"])

    def test_completed_retry_is_not_sent_again(self):
        self.observe(["TRASH", "UNREAD"])
        self.assertEqual(check(self.payload)["already_trashed"], [self.first])
        self.payload["phase"] = "after"
        self.assertEqual(check(self.payload)["verified"], [self.first])

    def test_partial_success_limits_retry_to_unmoved_approved_messages(self):
        self.payload["approval"]["items"].append(self.second)
        self.payload["batch"].append(self.second)
        self.payload["observed"] = [
            {**self.first, "labels": ["TRASH", "UNREAD"]},
            {**self.second, "labels": ["INBOX", "UNREAD"]},
        ]
        self.payload["phase"] = "after"
        self.assertEqual(check(self.payload)["verified"], [self.first])
        self.payload["phase"] = "before"
        self.assertEqual(check(self.payload)["ready"], [self.second])

    def test_inbox_or_read_state_incorrect_after_write(self):
        self.payload["phase"] = "after"
        for flags in (["TRASH"], ["TRASH", "INBOX", "UNREAD"]):
            self.observe(flags)
            self.assertFalse(check(self.payload)["verified"])

    def test_cli_rejects_duplicate_json_fields(self):
        script = Path(__file__).resolve().parents[1] / "skills/gmail-cleanup/scripts/verify.py"
        result = subprocess.run([sys.executable, str(script), "seal"],
                                input='{"items": [], "items": []}', text=True,
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_duplicate_and_ineligible_rows_are_rejected(self):
        self.manifest["items"].append(self.manifest["items"][0])
        with self.assertRaises(ValueError):
            seal(self.manifest)
        self.manifest["items"].pop()
        bad = candidate("sample-a", "def")
        bad["labels"].append("DRAFT")
        self.manifest["items"].append(bad)
        with self.assertRaises(ValueError):
            seal(self.manifest)


if __name__ == "__main__":
    unittest.main()
