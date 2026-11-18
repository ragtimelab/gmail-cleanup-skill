# Gmail Cleanup

A Codex skill for reviewing Gmail, identifying outstanding action and retention needs, and moving an explicitly approved set of messages to recoverable Trash. Requires the Gmail plugin connected in the session. Python 3 is required to validate a write batch. A GitHub connection or browser is useful only when verifying external tracking evidence.

Install the verified release using GitHub CLI:

```sh
gh skill install ragtimelab/gmail-cleanup-skill gmail-cleanup@v0.1.0 --agent codex --scope user
```

See the release notes for the exact commit to use with `--pin` in place of the tag. Start a new Codex session and ask: “Use $gmail-cleanup to review the inbox for the Gmail accounts I specify.”

The review is read-only. An explicit approval covering a fixed list is required for Trash movement. The skill checks the approved scope and verifies Gmail's resulting labels. The validator is a local consistency check, not a permission broker. No software from this repository stores OAuth credentials or calls Gmail directly.

Run the synthetic regression suite with `python3 -m unittest discover -s tests`. Report security issues via GitHub private vulnerability reporting when enabled.
