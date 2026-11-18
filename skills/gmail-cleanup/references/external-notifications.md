# External notifications

Establish what the user is still tracking and which service account owns the feed. A resolved discussion can still matter if a release, downstream result, or user-side recovery is pending. Protect messages with evidence absent from the underlying record.

For GitHub, identify the canonical repository and issue or pull request number, then compare the notification with the source event through a scoped read-only interface. Check the authenticated viewer and current individual subscription via GraphQL viewerSubscription when the interface supports it. Repository Watch is a separate signal. Email history establishes earlier delivery. Hold the message if the service account, source event, subscription state, or retention purpose cannot be confirmed. A known active feed or pending tracking goal stays protected.

Use the host's allowlisted lookup operations and send only the canonical object identifiers needed for the lookup. Keep mail text and embedded URLs out of external requests.
