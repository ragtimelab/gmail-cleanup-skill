#!/usr/bin/env python3
"""Manage local review checkpoints. This helper does not access Gmail."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl


LEASE_SECONDS = 30 * 60


class StateError(ValueError):
    pass


def timestamp(value):
    return type(value) is int and value > 0


def account_key(value):
    if not value or value != value.strip():
        raise StateError("Invalid connector account identifier")
    return value


def review_query(start, end):
    lower = f" after:{start}" if start is not None else ""
    return f"in:inbox{lower} before:{end}"


def load(path):
    if path.is_symlink():
        raise StateError("Cache paths must not be symbolic links")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def save(path, value):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(cache):
    if cache.is_symlink():
        raise StateError("Cache directory must not be a symbolic link")
    cache.mkdir(mode=0o700, exist_ok=True)
    lock_path = cache / "checkpoints.lock"
    if lock_path.is_symlink():
        raise StateError("Lock path must not be a symbolic link")
    with os.fdopen(os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600), "r+b") as lock:
        if os.name == "nt":
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def read_checkpoints(path):
    try:
        state = load(path)
        if state is None:
            return {}, path.exists()
        entries = state["accounts"]
        if state["version"] != 1 or not isinstance(entries, dict):
            raise ValueError
        valid = {key: end for key, end in entries.items()
                 if key and key == key.strip() and timestamp(end)}
        return valid, len(valid) != len(entries)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, StateError):
            raise
        return {}, True


def operate(cache, command, account=None, *, end=None, full=False, token=None, now=None):
    if account is not None:
        account_key(account)
    with locked(cache):
        now = int(time.time()) if now is None else now
        state_path = cache / "checkpoints.json"
        lease_path = cache / "leases.json"
        entries, damaged = read_checkpoints(state_path)
        leases = load(lease_path) or {}
        if not isinstance(leases, dict) or any(
            not isinstance(lease, dict)
            or not isinstance(lease.get("token"), str)
            or not timestamp(lease.get("end"))
            or not timestamp(lease.get("expires"))
            for lease in leases.values()
        ):
            raise StateError("Invalid execution leases")
        leases = {key: lease for key, lease in leases.items() if lease["expires"] > now}

        def write_entries():
            save(state_path, {"version": 1, "accounts": entries})

        if command == "reset":
            if account is None:
                if leases:
                    return {"status": "busy"}
                entries.clear()
            elif account in leases:
                return {"status": "busy"}
            else:
                entries.pop(account, None)
            write_entries()
            return {"status": "reset"}

        previous = entries.get(account)
        if command == "begin":
            if not timestamp(end) or end > now:
                raise StateError("Invalid review end")
            if account in leases:
                return {"status": "busy"}
            if previous is not None and end < previous:
                return {"status": "clock_regressed", "previous": previous}
            token = secrets.token_hex(16)
            leases[account] = {"token": token, "end": end, "expires": now + LEASE_SECONDS}
            save(lease_path, leases)
            start = None if full else previous
            return {"status": "started", "token": token, "start": start, "end": end,
                    "query": review_query(start, end), "cache_rebuild": damaged}

        lease = leases.get(account)
        if not lease or not secrets.compare_digest(lease["token"], token or ""):
            return {"status": "lease_lost"}
        if command == "renew":
            lease["expires"] = now + LEASE_SECONDS
            save(lease_path, leases)
            return {"status": "renewed"}
        del leases[account]
        save(lease_path, leases)
        if command == "finish":
            entries[account] = lease["end"]
            write_entries()
        return {"status": "saved" if command == "finish" else "released"}


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
    args = vars(parser.parse_args())
    cache = Path(__file__).resolve().parents[1] / ".cache"
    try:
        result = operate(cache, **args)
    except (OSError, StateError, ValueError):
        result = {"status": "cache_unavailable"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
