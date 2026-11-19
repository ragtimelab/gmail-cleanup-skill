import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "tools/check_public.py"
SKILL = Path("skills/gmail-cleanup")


class PublicPackageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.git("init", "--quiet")
        self.write(SKILL / "SKILL.md", "# Synthetic review\n")
        self.write(SKILL / "references/external-notifications.md", "# Synthetic reference\n")
        self.write(SKILL / "references/execution.md", "# Synthetic execution\n")
        self.write(SKILL / "scripts/verify.py", "# Synthetic validator\n")
        self.write(SKILL / "scripts/checkpoints.py", "# Synthetic checkpoint helper\n")
        self.write(SKILL / "references/incremental-review.md", "# Synthetic scope reference\n")

    def git(self, *args):
        subprocess.run(("git", *args), cwd=self.repo, check=True, capture_output=True)

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
                 "commit", "--quiet", "--no-gpg-sign", "-m", "Synthetic package")

    def check_package(self, ref="HEAD"):
        return subprocess.run((sys.executable, str(CHECKER), ref), cwd=self.repo,
                              capture_output=True, text=True, check=False)

    def test_allows_cleanup_payload(self):
        self.commit()
        result = self.check_package()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_committed_runtime_cache(self):
        self.write(SKILL / ".cache/checkpoints.json", "{}")
        self.commit()
        self.assertNotEqual(self.check_package().returncode, 0)

    def test_rejects_undeclared_script(self):
        self.write(SKILL / "scripts/other.py", "# Synthetic extra script\n")
        self.commit()
        result = self.check_package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected public file", result.stderr)

    def test_rejects_missing_validator(self):
        (self.repo / SKILL / "scripts/verify.py").unlink()
        self.commit()
        result = self.check_package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected skill payload", result.stderr)

    def test_rejects_removed_required_reference(self):
        (self.repo / SKILL / "references/external-notifications.md").unlink()
        self.commit()
        result = self.check_package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected skill payload", result.stderr)

    def test_checks_historical_blobs(self):
        self.write("README.md", "Synthetic address: fixture" + "@" + "example.invalid\n")
        self.commit()
        self.write("README.md", "# Clean release\n")
        self.commit()
        result = self.check_package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Private-data pattern in README.md", result.stderr)

    def test_rejects_symlink_in_payload(self):
        skill = self.repo / SKILL / "SKILL.md"
        skill.unlink()
        skill.symlink_to("references/external-notifications.md")
        self.commit()
        result = self.check_package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected public file or file mode", result.stderr)
