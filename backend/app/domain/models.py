"""Plain data shapes passed between layers. No logic lives here."""

from pydantic import AwareDatetime, BaseModel, ConfigDict


class ActualPoint(BaseModel):
    """Measured wind generation for one half-hour starting at start_time (UTC)."""

    model_config = ConfigDict(frozen=True)

    start_time: AwareDatetime
    generation_mw: float


class ForecastPoint(BaseModel):
    """One forecast: made at publish_time, predicting generation at start_time (UTC)."""

    model_config = ConfigDict(frozen=True)

    start_time: AwareDatetime
    publish_time: AwareDatetime
    generation_mw: float
