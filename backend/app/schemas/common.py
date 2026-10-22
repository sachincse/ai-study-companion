from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def to_iso_utc(value: datetime | None) -> str | None:
    """Serialize naive-UTC datetimes with an explicit Z so browsers do not read them as local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


_to_iso_utc = to_iso_utc
UtcDatetime = Annotated[datetime, PlainSerializer(to_iso_utc, return_type=str)]
OptUtcDatetime = Annotated[datetime | None, PlainSerializer(to_iso_utc, return_type=str | None)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str
