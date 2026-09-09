# Cancellation Retention Skill

Use when a customer asks about canceling, pausing, downgrading, or changing subscription status.

Workflow:

- Identify whether the customer is exploring options or giving explicit authorization.
- Offer retention or downgrade paths only when relevant.
- Before a destructive cancellation, require a current-turn confirmation that names the subscription or account.
- After confirmation, call `cancel_subscription` exactly once.
- If confirmation is ambiguous, ask a clarifying question.
