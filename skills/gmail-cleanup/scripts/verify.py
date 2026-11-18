#!/usr/bin/env python3
"""Validate an approved Gmail review against a current label snapshot."""

import argparse
import hashlib
import json
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(rows, fields, optional=()):
    require(isinstance(rows, list), "Expected a list of items")
    indexed = {}
    for row in rows:
        require(isinstance(row, dict), "Expected an item object")
        require(set(fields) <= row.keys() <= set(fields) | set(optional),
                "Unexpected or missing item fields")
        key = (row["account"], row["id"])
        require(all(isinstance(value, str) and value and value == value.strip()
                    for value in key), "Invalid message identity")
        require(key not in indexed, "Duplicate message identity")
        indexed[key] = row
    return indexed


def labels(row):
    values = row["labels"]
    require(isinstance(values, list) and all(isinstance(item, str) and item
                                              for item in values),
            "Invalid message labels")
    require(len(set(values)) == len(values), "Duplicate message label")
    return set(values)


def seal(manifest):
    require(isinstance(manifest, dict) and set(manifest) == {"items"},
            "Invalid review manifest")
    items = index(manifest["items"], ("account", "id", "subject", "reason", "labels"))
    canonical = []
    for key in sorted(items):
        row = items[key]
        require(isinstance(row["subject"], str) and isinstance(row["reason"], str)
                and bool(row["reason"].strip()), "Invalid subject or review reason")
        flags = labels(row)
        require(not flags.intersection({"TRASH", "SPAM", "SENT", "DRAFT"}),
                "Ineligible initial message labels")
        canonical.append({**row, "labels": sorted(flags)})
    encoded = json.dumps(canonical, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
    return items, hashlib.sha256(encoded).hexdigest()


def check(request):
    require(isinstance(request, dict)
            and set(request) == {"manifest", "approval", "batch", "observed", "phase"},
            "Invalid verification request")
    phase = request["phase"]
    require(phase in ("before", "after"), "Unknown phase")
    items, digest = seal(request["manifest"])
    approval = request["approval"]
    require(isinstance(approval, dict) and set(approval) == {"digest", "items"}
            and approval["digest"] == digest, "Approval does not match review")
    approved = index(approval["items"], ("account", "id"))
    require(approved and approved.keys() <= items.keys(), "Invalid approval subset")
    batch = index(request["batch"], ("account", "id"))
    require(batch and batch.keys() <= approved.keys(), "Invalid batch subset")
    observations = index(request["observed"], ("account", "id", "labels"), ("hold",))
    require(observations.keys() <= batch.keys(), "Observation outside approved scope")
    result = {key: [] for key in ("ready", "already_trashed", "verified", "held")}
    for key in sorted(batch):
        old = labels(items[key])
        row = observations.get(key)
        entry = approved[key]
        if row is None:
            result["held"].append({**entry, "reason": "missing_observation"})
            continue

        new = labels(row)
        require(isinstance(row.get("hold", False), bool), "Invalid hold flag")
        read_unchanged = ("UNREAD" in old) == ("UNREAD" in new)
        if row.get("hold") or not read_unchanged or new.intersection({"SPAM", "SENT", "DRAFT"}):
            result["held"].append({**entry, "reason": "hold_or_label_change"})
        elif "TRASH" in new and "INBOX" not in new:
            result["already_trashed" if phase == "before" else "verified"].append(entry)
        elif phase == "before" and new == old:
            result["ready"].append(entry)
        else:
            result["held"].append({**entry, "reason": "unexpected_labels"})
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seal", "check"))
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin, object_pairs_hook=unique_object)
        result = {"digest": seal(request)[1]} if args.command == "seal" else check(request)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        print("Invalid or inconsistent review input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
