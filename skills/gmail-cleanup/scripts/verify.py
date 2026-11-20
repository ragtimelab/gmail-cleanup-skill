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


INELIGIBLE = {"TRASH", "SPAM", "SENT", "DRAFT", "UNREAD", "STARRED"}


def seal(manifest):
    require(isinstance(manifest, dict) and set(manifest) == {"items", "protected_labels"},
            "Invalid review manifest")
    items = index(manifest["items"], ("account", "id", "subject", "reason", "labels"))
    protected = manifest["protected_labels"]
    require(isinstance(protected, dict) and set(protected) == {key[0] for key in items},
            "Missing or unexpected account label policy")
    protection = {account: labels({"labels": flags}) for account, flags in protected.items()}
    canonical = []
    for key in sorted(items):
        row = items[key]
        require(isinstance(row["subject"], str) and isinstance(row["reason"], str)
                and bool(row["reason"].strip()), "Invalid subject or review reason")
        flags = labels(row)
        require("INBOX" in flags and not flags.intersection(INELIGIBLE | protection[key[0]]),
                "Ineligible initial message labels")
        canonical.append({**row, "labels": sorted(flags)})
    encoded = json.dumps({"items": canonical, "protected_labels": {
        account: sorted(flags) for account, flags in protection.items()
    }}, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
    return items, hashlib.sha256(encoded).hexdigest()


def approve(items, digest, approval):
    require(isinstance(approval, dict) and set(approval) == {"digest", "items"}
            and approval["digest"] == digest, "Approval does not match review")
    approved = index(approval["items"], ("account", "id"))
    require(approved and approved.keys() <= items.keys(), "Invalid approval subset")
    encoded = json.dumps([digest, sorted(approved)], ensure_ascii=True,
                         separators=(",", ":")).encode("ascii")
    return approved, hashlib.sha256(encoded).hexdigest()


def reconcile(request):
    require(isinstance(request, dict) and set(request) == {"expected", "reviewed"},
            "Invalid coverage input")
    expected = index(request["expected"], ("account", "id"))
    reviewed = index(request["reviewed"], ("account", "id"))
    return {"status": "complete" if expected.keys() == reviewed.keys() else "incomplete",
            "missing": [expected[key] for key in sorted(expected.keys() - reviewed.keys())],
            "unexpected": [reviewed[key] for key in sorted(reviewed.keys() - expected.keys())]}


def check(request):
    require(isinstance(request, dict)
            and set(request) == {"manifest", "approval", "approval_digest", "batch", "observed", "phase"},
            "Invalid verification request")
    phase = request["phase"]
    require(phase in ("before", "after"), "Unknown phase")
    items, digest = seal(request["manifest"])
    approved, approval_digest = approve(items, digest, request["approval"])
    require(request["approval_digest"] == approval_digest, "Approval subset changed")
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
        if row.get("hold") or not read_unchanged or new.intersection({"SPAM", "SENT", "DRAFT", "STARRED"} |
                                set(request["manifest"]["protected_labels"][key[0]])):
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
    parser.add_argument("command", choices=("seal", "approve", "check", "reconcile"))
    args = parser.parse_args()
    try:
        request = json.load(sys.stdin, object_pairs_hook=unique_object)
        if args.command == "seal":
            result = {"digest": seal(request)[1]}
        elif args.command == "approve":
            require(isinstance(request, dict) and set(request) == {"manifest", "approval"},
                    "Invalid approval request")
            items, digest = seal(request["manifest"])
            result = {"approval_digest": approve(items, digest, request["approval"])[1]}
        elif args.command == "reconcile":
            result = reconcile(request)
        else:
            result = check(request)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        print("Invalid or inconsistent review input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
