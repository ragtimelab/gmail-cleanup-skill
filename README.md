# Gmail Cleanup

A Codex skill that reviews connected Gmail accounts, identifies actions and records to keep, and moves an explicitly approved set of messages to recoverable Trash using the official Gmail connector.

## Install and run

Use the exact verified commit SHA from the release notes.

```sh
gh skill install ragtimelab/gmail-cleanup-skill gmail-cleanup --agent codex --scope user --pin VERIFIED_COMMIT_SHA
```

For a project-scope installation, use `--scope project` from that project. In a fresh Codex session with Gmail connected, ask `$gmail-cleanup` to review your mail. It defaults to the inbox of every connected account and checks related archived or sent mail when needed. You can narrow the scope in your request.

The skill reports action needed, waiting or tracked, keep, and Trash candidates by account. Ads, promotions (including unexpired offers), and newsletters are eligible for proposal by default when the individual message has no remaining action or record value. You can specify mail to keep. Review the fixed proposal and approve the exact subset you want moved. The skill rereads that subset, uses Gmail's dedicated Trash operation for eligible messages, and verifies the resulting labels and read state.

## Release verification

Before opening a public PR, pushing, or publishing, review the prospective release locally or in private staging. Inspect the exact commit and its reachable changes, commit and tag messages, release notes, and assets for real mail content, account data, and secrets. Use synthetic fixtures for repository tests.

From a clean checkout of the release candidate, run:

```sh
python3 -m unittest discover -s tests
python3 tools/check_public.py v0.1.0
python3 tools/check_public.py v0.2.0
python3 tools/check_public.py HEAD
gh skill publish --dry-run
```

Verify a fresh Codex session can review all connected accounts through Gmail. Keep any real-mail report private. A separate user decision on exact messages is required for a live Trash check. Verify the archive against the final commit and confirm the immutable release tag and asset attestation.

## Migration from an older version

Locate older installations with `gh skill list` and move their skill directories outside all agent skill search paths. In-place installation with `--force` can leave obsolete files behind. Install the verified release into a clean target, start a fresh session, and discard approvals and manifests from earlier sessions.

Report security issues via GitHub private vulnerability reporting when enabled.
