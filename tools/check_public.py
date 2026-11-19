"""Check the public package layout and all reachable blobs for private material."""

import re
import subprocess
import sys


SKILL_ROOT = "skills/gmail-cleanup/"
REVIEW_FILES = {
    SKILL_ROOT + "SKILL.md",
    SKILL_ROOT + "references/external-notifications.md",
}
SUPPORT_FILES = {".github/workflows/verify.yml", ".gitignore", "LICENSE", "README.md",
                 "tools/check_public.py"}
CLEANUP_FILES = REVIEW_FILES | {
    SKILL_ROOT + "references/execution.md",
    SKILL_ROOT + "scripts/verify.py",
}
LEGACY_LAYOUT = (CLEANUP_FILES, {"tests/test_public.py", "tests/test_verify.py"})
HISTORICAL_LAYOUTS = {
    "0497426b6cad1e751d93dda9fd0f33fd5168fa7a": LEGACY_LAYOUT,
    "2d5349ed96f4917fe5db5cd571bf8cd5c0f1ea50": LEGACY_LAYOUT,
    "15f172eb8cd8e6794a5fa696d518827ecc66b458": LEGACY_LAYOUT,
    "1b3134ff1556dfcdba7d3abdfa0d2d4345e0656b": (CLEANUP_FILES, {"tests/test_verify.py"}),
    "66a35ddf420387e88e7d523419366fe4f00b6139": (REVIEW_FILES, {"tests/test_public.py"}),
}
CURRENT_LAYOUT = (
    CLEANUP_FILES | {
        SKILL_ROOT + "references/incremental-review.md",
        SKILL_ROOT + "scripts/checkpoints.py",
    },
    LEGACY_LAYOUT[1] | {"tests/test_checkpoints.py"},
)


def git(*args):
    return subprocess.check_output(("git", *args))


def verify(ref):
    target = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    commits = git("rev-list", target).decode().splitlines()
    scanned = set()
    patterns = (
        rb"[\w.%+-]+@" rb"[\w.-]+\.[A-Za-z]{2,}",
        rb"/" rb"Users/" rb"[^/\s]+",
        rb"msg_" rb"[0-9A-Z]{26}",
        rb"\b[0-9a-f]{16}\b",
        rb"(?i)(?:ghp_|github_pat_|sk-(?:proj-)?|ya29\.)" rb"[\w-]{20,}",
        rb"-----BEGIN [A-Z ]*" rb"PRIVATE KEY-----",
        rb"(?i)(?:plugin|link)_" rb"[0-9a-f]{24,}",
    )
    for commit in commits:
        skill_files, test_files = HISTORICAL_LAYOUTS.get(commit, CURRENT_LAYOUT)
        allowed = SUPPORT_FILES | skill_files | test_files
        included_skill_files = set()
        entries = git("ls-tree", "-r", "-z", commit).split(b"\x00")
        for entry in filter(None, entries):
            header, path_bytes = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            path = path_bytes.decode()
            if path not in allowed or mode not in ("100644", "100755") or kind != "blob":
                raise ValueError("Unexpected public file or file mode")
            if path.startswith(SKILL_ROOT):
                included_skill_files.add(path)
            if oid in scanned:
                continue
            blob = git("cat-file", "blob", oid)
            if any(re.search(pattern, blob) for pattern in patterns):
                raise ValueError("Private-data pattern in " + path)
            scanned.add(oid)
        if commit == target and included_skill_files != skill_files:
            raise ValueError("Unexpected skill payload")
    print(f"Verified {len(scanned)} public blobs across {len(commits)} commits")


if __name__ == "__main__":
    verify(sys.argv[1])
