"""Quickstart: broadcast one message through every channel."""

from notifier import Notifier
from notifier.email_channel import register_email
from notifier.sms_channel import register_sms


def main() -> None:
    notifier = Notifier()
    register_email(notifier, from_addr="noreply@example.com")
    register_sms(notifier, sender_id="EXAMPLE")

    results = notifier.broadcast("user@example.com", "Hello from the notifier library!")
    print("delivery results:", results)


if __name__ == "__main__":
    main()
