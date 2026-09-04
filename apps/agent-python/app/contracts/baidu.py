"""Operator/catalog binding; never populated from untrusted model output."""

from pydantic import BaseModel, ConfigDict, Field


class BaiduPoiBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attraction_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    city: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    provider_uid: str | None = None
