# Gmail Cleanup

A Codex skill that reviews connected Gmail accounts, identifies actions and records to keep, and moves an explicitly approved set of messages to recoverable Trash using the official Gmail connector.

## Install and run

Use the exact verified commit SHA from the release notes.

```sh
gh skill install ragtimelab/gmail-cleanup-skill gmail-cleanup --agent codex --scope user --pin VERIFIED_COMMIT_SHA
```

For a project-scope installation, use `--scope project` from that project. In a fresh Codex session with Gmail connected, use:

| Request | Review |
|---|---|
| `$gmail-cleanup` | New inbox arrivals since each account's last completed review. Accounts without a checkpoint start with a full inbox review. |
| `$gmail-cleanup 전체` or “review the whole inbox” | Review the whole inbox and refresh the checkpoint for each completed account. |
| `$gmail-cleanup 최근 7일` or “review the last seven days” | Review that period without advancing checkpoints. |
| `$gmail-cleanup 기준점 초기화` or “reset checkpoints” | Clear the local checkpoints for the selected accounts, or all accounts if none are specified. |

The default covers every connected Gmail account. You can name individual accounts. Incremental review finds new deliveries, including new replies. To review older mail after it was read or moved back to the inbox, request a whole-inbox or period review.

The skill reports how many messages it reviewed, how many were unread in that scope, what needs attention, and which messages qualify as Trash candidates. Only read messages qualify when they have no remaining action, retention signal, or evidence to preserve. The official Gmail connector moves only the exact messages you approve and verifies their final labels and read state.

The local checkpoint cache lives in `.cache/` inside the installed skill. Removing that directory clears the checkpoint state. Removing the entire installation also clears it. An in-place update can reuse compatible state if the installer preserves the cache. When storage is unavailable, review still works without saving checkpoints. The cache contains no message IDs, bodies, or approvals.

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
