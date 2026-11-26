# The channel port (NFR-9): the one shape every chat channel plugs into.
#
# A channel is HOW a Customer reaches the Business: the web Chat Page now, WhatsApp later.
# Each channel knows its people in its own way: the Chat Page by a browser cookie, WhatsApp
# by a phone number. That knowledge lives in the channel's ADAPTER (webchat.py now).
#
# inbox/service.py talks only to this port. It never sees a cookie or a phone number, so a
# new channel is a new adapter file, with no change to the save logic (seq, locks, no copies).
#
# Outbound (deliver a reply to the Customer): the web Chat Page needs none. It PULLS new
# Messages by polling (story 4.2), so a saved team reply (story 4.4) reaches it within 5 s.
# A push method is added with the first channel that needs one (WhatsApp).
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.inbox.models import Conversation


class Channel(Protocol):
    def find_conversation(self, session: Session) -> Conversation | None:
        """The sender's newest Conversation, or None. Reads only: never writes (GET routes use it)."""
        ...

    def open_conversation(self, session: Session) -> Conversation:
        """The sender's Conversation, started if needed. Returned LOCKED (SELECT … FOR UPDATE)
        until the transaction ends, so the caller can safely give the next seq."""
        ...
