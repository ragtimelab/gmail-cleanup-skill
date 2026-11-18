# Gmail Cleanup

A read-only Codex skill for reviewing Gmail, identifying outstanding actions and retention needs, and listing candidates for the user to review in Gmail.

## Install and run

Use the exact verified commit SHA from the read-only release notes.

```sh
gh skill install ragtimelab/gmail-cleanup-skill gmail-cleanup --agent codex --scope user --pin VERIFIED_COMMIT_SHA
```

For a project-scope installation, use `--scope project` from that project. Start a new session after installing the skill. Ask it to review the inbox for the specific Gmail accounts you want covered. Make any mailbox changes directly in Gmail.

### Production session requirements

Before exposing mailbox content, configure the host to restrict the session to explicitly selected accounts and allow only the Gmail profile, label-list, message-search, and message or thread read operations needed for review. If external tracking is in scope, allow only scoped canonical lookups through the relevant service's read-only interface.

Enforce these restrictions outside the model. Isolate credentials and disable alternative write paths, including other writable connectors, authenticated browser automation, and shell or network access that can reach authenticated services. A host must provide verifiable effective restrictions before this skill can process mailbox content in production.

## Release verification

Before opening a public PR, pushing, or publishing, review the prospective release locally or in a private staging environment. Inspect the exact commit and its reachable changes, commit and tag messages, release notes, and any assets for real mail content, account data, and secrets. Keep fixtures synthetic. The automated package check covers Git paths, file modes, and known private-data patterns.

From a clean checkout of the release candidate, run:

```sh
python3 -m unittest discover -s tests
python3 tools/check_public.py v0.1.0
python3 tools/check_public.py VERIFIED_COMMIT_SHA
```

Verify that the packaged skill contains only its declared read-only files. Run the host acceptance checks on synthetic mail before declaring a host supported. Confirm scoped reads work, a mailbox change remains blocked even if requested, and a same-ID message in another account stays outside the selected account. Include stale approvals, untrusted mail text, and an ambiguous account selector in the checks. Confirm that write-capable tools and alternate authenticated routes are unavailable to that session.

Create a new tag for the verified SHA and confirm its peeled commit matches before publishing. CI repeats the source checks on push and pull request. Include the migration details below in the release notes.

### Migration from v0.1.0

Locate each older `gmail-cleanup` installation with `gh skill list` and move its skill directory outside all agent skill search paths before installing the verified read-only commit. In-place installation with `--force` can leave obsolete files behind. Confirm that the new skill directory contains only `SKILL.md` and `references/external-notifications.md`. Start a fresh session and discard approvals and manifests from earlier sessions.

This release removes automated Trash moves and the local write-batch validator. Automated moves require an executor that enforces user approval for the exact account, operation, and message subset, and applies the write only while the approved state still holds. If outcome reconciliation cannot establish what happened, the executor must hold the item for user review.

Report security issues via GitHub private vulnerability reporting when enabled.
