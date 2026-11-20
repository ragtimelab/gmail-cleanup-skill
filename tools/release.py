"""Publish the verified main commit and confirm the immutable release assets."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

from check_public import verify


REPO = "ragtimelab/gmail-cleanup-skill"
REMOTE = f"https://github.com/{REPO}.git"
SKILL = "skills/gmail-cleanup"


def run(*args):
    return subprocess.check_output(args)


def api(path, *args):
    return json.loads(run("gh", "api", f"repos/{REPO}/{path}", *args))


def remote_refs(*refs):
    return {ref: sha for line in run("git", "ls-remote", REMOTE, *refs).decode().splitlines()
            for sha, ref in [line.split()]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_main(sha):
    require(remote_refs("refs/heads/main").get("refs/heads/main") == sha,
            "Target must match current remote main")
    result = api("actions/workflows/verify.yml/runs", "-X", "GET",
                 "-f", "branch=main", "-f", "event=push", "-f", f"head_sha={sha}")
    runs = [item for item in result["workflow_runs"]
            if item["head_sha"] == sha and item["head_branch"] == "main"
            and item["event"] == "push"]
    require(runs and runs[0]["status"] == "completed" and runs[0]["conclusion"] == "success",
            "Latest exact-SHA main Verify run must have succeeded")
    run_info = runs[0]
    jobs = api(f"actions/runs/{run_info['id']}/attempts/{run_info['run_attempt']}/jobs")["jobs"]
    required = [job for job in jobs if job["name"] == "verify"]
    require(len(required) == 1 and required[0]["conclusion"] == "success",
            "The required verify job did not pass")
    return run_info["html_url"]


def package(directory, sha, tag):
    archive = directory / f"gmail-cleanup-{tag}.tar.gz"
    archive.write_bytes(run("git", "archive", "--format=tar.gz", "--prefix=gmail-cleanup/",
                            f"{sha}:{SKILL}"))
    expected = set(run("git", "ls-tree", "-r", "--name-only", f"{sha}:{SKILL}").decode().splitlines())
    with tarfile.open(archive) as bundle:
        members = [m for m in bundle.getmembers() if not m.isdir()]
        require(len(members) == len(expected)
                and {m.name for m in members} == {f"gmail-cleanup/{p}" for p in expected},
                "Archive file inventory differs from source")
        for member in members:
            require(member.isfile() and bundle.extractfile(member).read() ==
                    run("git", "show", f"{sha}:{SKILL}/{member.name.removeprefix('gmail-cleanup/')}"),
                    "Archive contents differ from source")
    checksum = directory / "SHA256SUMS"
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    return [archive, checksum]


def find_release(tag):
    rows = run("gh", "api", "--paginate", f"repos/{REPO}/releases",
               "--jq", f'.[] | select(.tag_name == "{tag}")').splitlines()
    require(len(rows) <= 1, "Multiple releases match tag")
    return json.loads(rows[0]) if rows else None


def verify_assets(release, assets):
    remote_assets = {asset["name"]: asset for asset in release["assets"]}
    require(set(remote_assets) <= {asset.name for asset in assets},
            "Release contains unexpected assets")
    missing = []
    for asset in assets:
        remote_asset = remote_assets.get(asset.name)
        if remote_asset is None:
            missing.append(asset)
            continue
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        require(remote_asset["state"] == "uploaded" and remote_asset.get("digest") == f"sha256:{digest}",
                f"Remote asset does not match {asset.name}")
    return missing


def publish(directory, sha, tag, notes, assets):
    ref = f"refs/tags/{tag}"
    refs = remote_refs(ref, ref + "^{}")
    tag_sha = refs.get(ref + "^{}", refs.get(ref))
    require(tag_sha in (None, sha), "Existing release tag points elsewhere")
    release = find_release(tag)
    require(tag_sha or release is None, "Release exists without the expected tag")
    if release is None or release["draft"]:
        require(api("immutable-releases")["enabled"], "Repository must enable immutable releases")
    if not tag_sha:
        run("git", "push", REMOTE, f"{sha}:{ref}")
    if release is None:
        run("gh", "release", "create", tag, "-R", REPO, "--verify-tag", "--draft",
            "--title", f"Gmail Cleanup {tag}", "--notes-file", str(notes))
        release = find_release(tag)
    require(release is not None and (release.get("body") or "").rstrip("\n") == notes.read_text().rstrip("\n"),
            "Existing release notes differ from the requested release")
    missing = verify_assets(release, assets)
    if release["draft"]:
        if missing:
            run("gh", "release", "upload", tag, "-R", REPO, *(str(p) for p in missing))
        require(not verify_assets(find_release(tag), assets), "Draft assets incomplete")
        verify_main(sha)
        run("gh", "release", "edit", tag, "-R", REPO, "--draft=false", "--latest")
    else:
        require(not missing, "Published release assets incomplete")

    refs = remote_refs(ref, ref + "^{}")
    require(refs.get(ref + "^{}", refs.get(ref)) == sha, "Published tag target mismatch")
    release = find_release(tag)
    require(release["immutable"] and not release["draft"] and not verify_assets(release, assets),
            "Expected an immutable public release with all assets")
    download = directory / "download"
    download.mkdir()
    run("gh", "release", "download", tag, "-R", REPO, "--dir", str(download))
    for asset in assets:
        fetched = download / asset.name
        require(fetched.read_bytes() == asset.read_bytes(), f"Downloaded {asset.name} differs")
        run("gh", "release", "verify-asset", tag, str(fetched), "-R", REPO)
    print(release["html_url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("sha")
    parser.add_argument("--notes-file", type=Path, required=True)
    parser.add_argument("--publish", action="store_true", help="Otherwise only check prerequisites")
    args = parser.parse_args()
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", args.tag), "Expected a release version")
    require(re.fullmatch(r"[0-9a-f]{40}", args.sha), "Expected the full SHA")
    require(args.sha in args.notes_file.read_text(), "Release notes must include the full SHA")
    print("Verified release CI:", verify_main(args.sha), flush=True)
    verify(args.sha)
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        assets = package(directory, args.sha, args.tag)
        print(assets[1].read_text().strip(), flush=True)
        if args.publish:
            publish(directory, args.sha, args.tag, args.notes_file, assets)


if __name__ == "__main__":
    main()
