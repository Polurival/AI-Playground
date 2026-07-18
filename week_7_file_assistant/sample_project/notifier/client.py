"""Core notifier client.

`Notifier` is the central component of the library: channels register themselves with it and it
fans a single message out to every registered channel.
"""

from __future__ import annotations

from typing import Protocol


class Channel(Protocol):
    """A delivery channel: anything that can send one text message to one recipient."""

    def send(self, recipient: str, message: str) -> bool:
        ...


class Notifier:
    """Central dispatch point. Holds a set of channels and broadcasts messages to all of them."""

    def __init__(self) -> None:
        self._channels: list[Channel] = []

    def register(self, channel: Channel) -> None:
        """Add a channel to the broadcast list."""
        self._channels.append(channel)

    def broadcast(self, recipient: str, message: str) -> dict[str, bool]:
        """Send `message` to `recipient` through every registered channel.

        Returns a map of channel class name -> delivery success flag.
        """
        results: dict[str, bool] = {}
        for channel in self._channels:
            results[type(channel).__name__] = channel.send(recipient, message)
        return results
