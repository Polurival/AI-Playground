# notifier

A tiny multi-channel notification library. Create a `Notifier`, register one or more channels,
and broadcast a single message to all of them at once.

## Install

```bash
pip install -e .
```

## Usage

```python
from notifier import Notifier
from notifier.email_channel import register_email

notifier = Notifier()
register_email(notifier, from_addr="noreply@example.com")

results = notifier.broadcast("user@example.com", "Hello!")
print(results)  # {"EmailChannel": True}
```

## Channels

- **EmailChannel** (`notifier.email_channel`) — delivers over SMTP.

Each channel implements a `send(recipient, message) -> bool` method and registers itself with a
`Notifier` via its `register_*` helper.
