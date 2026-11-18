"""Check the public package layout and all reachable blobs for private material."""

import re
import subprocess
import sys
from pathlib import PurePosixPath


def git(*args):
    return subprocess.check_output(("git", *args))


def verify(ref):
    allowed = {
        ".github/workflows/verify.yml", ".gitignore", "LICENSE", "README.md",
        "skills/gmail-cleanup/SKILL.md",
        "skills/gmail-cleanup/references/execution.md",
        "skills/gmail-cleanup/references/external-notifications.md",
        "skills/gmail-cleanup/scripts/verify.py",
        "tests/test_verify.py", "tools/check_public.py",
    }
    commitments = git("rev-list", ref).decode().splitlines()
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
    for commit in commitments:
        entries = git("ls-tree", "-r", "-z", commit).split(b"\x00")
        for entry in filter(None, entries):
            header, path_bytes = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            path = path_bytes.decode()
            if path not in allowed or mode not in ("100644", "100755") or kind != "blob":
                raise ValueError("Unexpected public file: " + path)
            if oid in scanned:
                continue
            blob = git("cat-file", "blob", oid)
            if any(re.search(pattern, blob) for pattern in patterns):
                raise ValueError("Private-data pattern in " + path)
            scanned.add(oid)
    root = PurePosixPath("skills/gmail-cleanup")
    entries = set(git("ls-tree", "-r", "--name-only", ref, str(root)).decode().splitlines())
    if entries != {path for path in allowed if root in PurePosixPath(path).parents}:
        raise ValueError("Unexpected skill payload")
    print(f"Verified {len(scanned)} public blobs across {len(commitments)} commits")


if __name__ == "__main__":
    verify(sys.argv[1])
