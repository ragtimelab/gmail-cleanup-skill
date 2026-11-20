#!/usr/bin/env python3
"""Manage installation-local review state without accessing Gmail."""

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl


LEASE_SECONDS = 30 * 60
LOCK_SECONDS = 5


class Failure(Exception):
    def __init__(self, status, phase, error=None):
        self.result = {"status": status, "phase": phase}
        if error is not None:
            self.result["errno"] = error


@contextmanager
def phase(name):
    try:
        yield
    except OSError as error:
        raise Failure("storage_error", name, error.errno) from None


def timestamp(value):
    return type(value) is int and value > 0


def account_key(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def token_key(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def review_query(start, end):
    lower = f" after:{start}" if start is not None else ""
    return f"in:inbox{lower} before:{end}"


def reject_symlink(path, step):
    if path.is_symlink():
        raise Failure("state_invalid", step)


def load(path):
    with phase("read"):
        reject_symlink(path, "read")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (ValueError, RecursionError):
            raise Failure("state_invalid", "validate") from None


def save(path, value):
    with phase("write"):
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with phase("write"), os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        with phase("replace"):
            os.replace(temporary, path)
    finally:
        with phase("write"):
            Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(cache):
    with phase("mkdir"):
        reject_symlink(cache, "mkdir")
        cache.mkdir(mode=0o700, exist_ok=True)
    lock_path = cache / "checkpoints.lock"
    with phase("lock"):
        reject_symlink(lock_path, "lock")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock = os.fdopen(os.open(lock_path, flags, 0o600), "r+b")
    with lock:
        deadline = time.monotonic() + LOCK_SECONDS
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise Failure("storage_error", "lock", error.errno) from None
                if time.monotonic() >= deadline:
                    raise Failure("lock_timeout", "lock") from None
                time.sleep(0.05)
        yield


def valid_leases(leases):
    return isinstance(leases, dict) and all(
        account_key(key) and isinstance(lease, dict)
        and token_key(lease.get("token")) and timestamp(lease.get("end"))
        and timestamp(lease.get("expires"))
        for key, lease in leases.items()
    )


def valid_receipts(receipts, entries):
    return isinstance(receipts, dict) and all(
        key in entries and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
        for key, digest in receipts.items()
    )


def read_state(cache, now):
    path = cache / "checkpoints.json"
    state = load(path)
    if state is None and not path.exists():
        state = {"version": 1, "accounts": {}}
    if not isinstance(state, dict) or type(state.get("version")) is not int:
        raise Failure("state_invalid", "validate")
    entries = state.get("accounts")
    if not isinstance(entries, dict):
        raise Failure("state_invalid", "validate")
    valid = {key: end for key, end in entries.items() if account_key(key) and timestamp(end)}
    damaged = len(valid) != len(entries)
    if state["version"] == 1:
        legacy_path = cache / "leases.json"
        leases = load(legacy_path)
        if leases is None and not legacy_path.exists():
            leases = {}
        if not valid_leases(leases):
            raise Failure("state_invalid", "validate")
        if any(lease["expires"] > now for lease in leases.values()):
            return None, damaged
        return {"version": 2, "accounts": valid, "leases": {}, "receipts": {}}, damaged
    leases = state.get("leases")
    receipts = state.get("receipts")
    if state["version"] != 2 or damaged or not valid_leases(leases) or not valid_receipts(receipts, valid):
        raise Failure("state_invalid", "validate")
    state["leases"] = {key: lease for key, lease in leases.items() if lease["expires"] > now}
    return state, False


def operate(cache, command, account=None, *, end=None, full=False, token=None, now=None):
    if (command != "reset" or account is not None) and not account_key(account):
        raise Failure("invalid_input", "validate")
    if command == "begin" and not timestamp(end):
        raise Failure("invalid_input", "validate")
    if command in {"renew", "finish", "release"} and not token_key(token):
        raise Failure("invalid_input", "validate")

    with locked(cache):
        now = int(time.time()) if now is None else now
        if command == "begin" and end > now:
            raise Failure("invalid_input", "validate")
        state, damaged = read_state(cache, now)
        if state is None:
            return {"status": "busy", "reason": "legacy_active"}
        entries = state["accounts"]
        leases = state["leases"]
        receipts = state["receipts"]
        state_path = cache / "checkpoints.json"

        if command == "reset":
            if (account is None and leases) or account in leases:
                return {"status": "busy"}
            if account is None:
                entries.clear()
                receipts.clear()
            else:
                entries.pop(account, None)
                receipts.pop(account, None)
            save(state_path, state)
            return {"status": "reset"}

        previous = entries.get(account)
        if command == "begin":
            if account in leases:
                return {"status": "busy"}
            if previous is not None and end < previous:
                return {"status": "clock_regressed", "previous": previous}
            token = secrets.token_hex(16)
            leases[account] = {"token": token, "end": end, "expires": now + LEASE_SECONDS}
            receipts.pop(account, None)
            save(state_path, state)
            start = None if full else previous
            return {"status": "started", "token": token, "start": start, "end": end,
                    "query": review_query(start, end), "cache_rebuild": damaged}

        lease = leases.get(account)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        if not lease or not secrets.compare_digest(lease["token"], token):
            if command == "finish" and not lease and receipts.get(account) == digest:
                return {"status": "saved", "end": entries[account]}
            return {"status": "lease_lost"}
        if command == "renew":
            lease["expires"] = now + LEASE_SECONDS
            save(state_path, state)
            return {"status": "renewed"}
        del leases[account]
        if command == "finish":
            entries[account] = lease["end"]
            receipts[account] = digest
        save(state_path, state)
        if command == "finish":
            return {"status": "saved", "end": lease["end"]}
        return {"status": "released"}


def diagnose(root, action, probe_id=None):
    if action == "create":
        probe_id = secrets.token_hex(16)
    elif not token_key(probe_id):
        raise Failure("invalid_input", "validate")
    probe = root / f".cache-probe-{probe_id}"
    if action in {"read", "clean"}:
        reject_symlink(probe, "read")
        marker = load(probe / "marker.json")
        if marker != {"probe": probe_id}:
            return {"status": "probe_missing"}
        if action == "clean":
            with phase("write"):
                (probe / "marker.json").unlink()
                (probe / "checkpoints.lock").unlink()
                probe.rmdir()
        return {"status": "probe_found" if action == "read" else "probe_removed"}
    marker = probe / "marker.json"
    try:
        with locked(probe):
            save(marker, {"probe": probe_id})
            save(marker, {"probe": probe_id})
            if load(marker) != {"probe": probe_id}:
                raise Failure("state_invalid", "validate")
    except Failure:
        if probe.is_dir() and not probe.is_symlink():
            try:
                marker.unlink(missing_ok=True)
                (probe / "checkpoints.lock").unlink(missing_ok=True)
                probe.rmdir()
            except OSError:
                pass
        raise
    return {"status": "probe_created", "probe_id": probe_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("account")
    begin.add_argument("end", type=int)
    begin.add_argument("--full", action="store_true")
    for name in ("renew", "finish", "release"):
        command = commands.add_parser(name)
        command.add_argument("account")
        command.add_argument("token")
    commands.add_parser("reset").add_argument("account", nargs="?")
    probe = commands.add_parser("diagnose")
    probe.add_argument("action", choices=("create", "read", "clean"))
    probe.add_argument("probe_id", nargs="?")
    args = vars(parser.parse_args())
    root = Path(__file__).resolve().parents[1]
    diagnostic = args.get("command") == "diagnose"
    code = 0
    try:
        if diagnostic:
            args.pop("command")
            result = diagnose(root, **args)
        else:
            result = operate(root / ".cache", **args)
    except Failure as error:
        result = error.result
        code = 1
    if diagnostic:
        fingerprint = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result.update({"installation": str(root), "helper_sha256": fingerprint, "state_version": 2})
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
