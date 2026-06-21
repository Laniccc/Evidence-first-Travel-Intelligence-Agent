from pydantic import BaseModel, Field


class ItineraryItem(BaseModel):
    start_time: str
    end_time: str
    activity: str
    place_name: str | None = None
    transport_note: str | None = None
    notes: list[str] = Field(default_factory=list)


class ItineraryPlan(BaseModel):
    title: str
    pace: str
    items: list[ItineraryItem] = Field(default_factory=list)
    transport_summary: list[str] = Field(default_factory=list)
    food_suggestions: list[str] = Field(default_factory=list)
    backup_plans: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
