"""Database model of the shopping list."""

import datetime as dt

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from billbuddy.db import Base


class ShoppingItem(Base):
    """One entry on a group's shopping list ("Milch", "2x Klopapier")."""

    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # Who put it on the list; stays empty if that person is removed from the group
    added_by_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    # Ticked off in the shop: still shown (greyed out) until someone clears the done entries
    checked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)
