from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Naive-UTC datetimes are serialized as ISO-8601 with a trailing Z.
UTCDt = Annotated[datetime, PlainSerializer(lambda d: d.isoformat() + "Z", return_type=str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Strict(BaseModel):
    """Input schemas forbid unknown fields (mass-assignment protection)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
