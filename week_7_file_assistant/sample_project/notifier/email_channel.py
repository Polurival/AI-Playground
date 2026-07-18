"""Email delivery channel for the Notifier."""

from .client import Notifier
from .retry import with_retry


class EmailChannel:
    """Sends notifications over (a pretend) SMTP connection."""

    def __init__(self, from_addr: str) -> None:
        self.from_addr = from_addr

    def send(self, recipient: str, message: str) -> bool:
        """Deliver one email; retried on transient failure."""
        return with_retry(lambda: self._deliver(recipient, message))

    def _deliver(self, recipient: str, message: str) -> bool:
        # Pretend SMTP send — always succeeds in this sample.
        print(f"[email] {self.from_addr} -> {recipient}: {message}")
        return True


def register_email(notifier: Notifier, from_addr: str) -> EmailChannel:
    """Build an EmailChannel and register it with the given Notifier."""
    channel = EmailChannel(from_addr)
    notifier.register(channel)
    return channel
