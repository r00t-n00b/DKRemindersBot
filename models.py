"""Data models for reminders."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Reminder:
    id: int
    chat_id: int
    text: str
    remind_at: datetime
    created_by: Optional[int]
    template_id: Optional[int] = None
    sent_at: Optional[datetime] = None
