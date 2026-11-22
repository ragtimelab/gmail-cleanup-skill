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
| `$gmail-cleanup` | The last seven days of the inbox for every connected account. |
| `$gmail-cleanup Review the whole inbox.` | Review the whole inbox. |
| `$gmail-cleanup Review the last 30 days.` | Review the requested period. |

The default covers every connected Gmail account. You can name individual accounts. The default is a rolling seven-day window and includes read and unread mail. Request a whole-inbox or longer period review to include older mail.

The skill reports how many messages it reviewed, how many were unread in that scope, what needs attention, and which messages qualify as Trash candidates. Read mail is proposed by default. The skill keeps explicit retention marks, personal financial records, and actively tracked notifications, and reports unfinished actions for confirmation regardless of read state. A Mail.app flag protects a Gmail message when it syncs as a Gmail star. See the [classification rules](skills/gmail-cleanup/SKILL.md#classification). The skill freezes the exact set you approve, uses the official Gmail connector to move eligible approved messages, and reads back their final labels and read state.

Each review starts from the requested window. The skill does not write checkpoints or require writable skill storage. The Gmail connector and Python validator must be available in the execution environment. The current review and approval remain private to the conversation.

## Release verification

Before opening a public PR, pushing, or publishing, review the prospective release locally or in private staging. Inspect the exact commit and its reachable changes, commit and tag messages, release notes, and assets for real mail content, account data, and secrets. Use synthetic fixtures for repository tests.

From a clean checkout of the release candidate, run:

```sh
python3 -m unittest discover -s tests
python3 tools/check_public.py v0.1.0
python3 tools/check_public.py v0.2.0
python3 tools/check_public.py v0.7.0
python3 tools/check_public.py HEAD
gh skill publish --dry-run
```

Verify a fresh Codex session can review all connected accounts through Gmail. Keep any real-mail report private. A separate user decision on exact messages is required for a live Trash check. CI runs the Ubuntu `verify` job on pull requests to `main` and pushes to `main`. Pushing a release tag does not start another verification run. Once the final commit on `main` passes, use the release command below with the full SHA and reviewed notes that include it. Omit `--publish` for a read-only preflight. The command checks the exact successful `main` push, packages that commit, and verifies the published immutable tag, checksum, and asset attestations.

```sh
python3 -B tools/release.py VERSION FULL_MAIN_SHA --notes-file RELEASE_NOTES --publish
```

## Migration from an older version

Locate older installations with `gh skill list` and move their skill directories outside all agent skill search paths. In-place installation with `--force` can leave obsolete files behind. Finish or let old reviews expire before changing versions. Legacy checkpoints and diagnostic files live under the old skill installation. Leave them out of the clean replacement. Once the old installation is no longer needed, deleting that old skill folder also removes its cache. Checkpoint reset requests no longer do anything. Install the verified release into a clean target, start a fresh session, and discard approvals and manifests from earlier sessions.

Report security issues via GitHub private vulnerability reporting when enabled.
