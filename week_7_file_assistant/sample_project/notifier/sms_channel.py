from .client import Notifier
from .retry import with_retry


class SmsChannel:
    """Sends notifications as SMS text messages."""

    def __init__(self, sender_id: str) -> None:
        self.sender_id = sender_id

    def send(self, recipient: str, message: str) -> bool:
        """Deliver one SMS; retried on transient failure."""
        return with_retry(lambda: self._deliver(recipient, message))

    def _deliver(self, recipient: str, message: str) -> bool:
        print(f"[sms] {self.sender_id} -> {recipient}: {message[:160]}")
        return True


def register_sms(notifier: Notifier, sender_id: str) -> SmsChannel:
    channel = SmsChannel(sender_id)
    notifier.register(channel)
    return channel
