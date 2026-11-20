import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from release import verify_main


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        mocked_refs = patch("release.remote_refs", return_value={"refs/heads/main": self.sha})
        self.refs = mocked_refs.start()
        self.addCleanup(mocked_refs.stop)
        self.run = {"head_sha": self.sha, "head_branch": "main", "event": "push", "id": 19,
                    "run_attempt": 2, "html_url": "https://example.invalid/run/19",
                    "status": "completed", "conclusion": "success"}

    def test_uses_exact_main_run_and_its_specific_attempt(self):
        with patch("release.api", side_effect=[{"workflow_runs": [self.run]},
                                               {"jobs": [{"name": "verify", "conclusion": "success"}]}]) as api:
            self.assertEqual(verify_main(self.sha), self.run["html_url"])
        self.assertEqual(api.call_args.args, ("actions/runs/19/attempts/2/jobs",))

    def test_cannot_use_another_commit_or_event_or_pending_run(self):
        for changes in ({"head_sha": "b" * 40}, {"event": "pull_request"},
                        {"head_branch": "v1.0.0"}, {"status": "in_progress"},
                        {"conclusion": "failure"}):
            with self.subTest(changes=changes), patch("release.api", return_value={
                "workflow_runs": [{**self.run, **changes}]
            }), self.assertRaises(ValueError):
                verify_main(self.sha)

    def test_failed_job_or_non_main_sha_blocks_release(self):
        with patch("release.api", side_effect=[{"workflow_runs": [self.run]},
                                               {"jobs": [{"name": "verify", "conclusion": "failure"}]}]):
            with self.assertRaises(ValueError):
                verify_main(self.sha)
        self.refs.return_value = {"refs/heads/main": "b" * 40}
        with patch("release.api") as api, self.assertRaises(ValueError):
            verify_main(self.sha)
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
