from datetime import datetime
from functools import cache
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, TypeAdapter


class OpenF1Record(BaseModel):
    """A record returned by one OpenF1 endpoint.

    Subclasses bind their endpoint at class definition:
    ``class Driver(OpenF1Record, endpoint="drivers")``. Only the fields we use
    are declared; anything else in the payload is ignored.
    """

    model_config = ConfigDict(frozen=True)

    endpoint: ClassVar[str]

    def __init_subclass__(cls, *, endpoint: str, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.endpoint = endpoint

    @classmethod
    def validate_many(cls, raw: str | bytes) -> list[Self]:
        """Parse a raw OpenF1 JSON array into validated records."""
        return _list_adapter(cls).validate_json(raw)


@cache
def _list_adapter[T: OpenF1Record](model: type[T]) -> TypeAdapter[list[T]]:
    # Built lazily: the model must be fully defined before pydantic can adapt it.
    return TypeAdapter(list[model])


class CarDataSample(OpenF1Record, endpoint="car_data"):
    date: datetime
    session_key: int
    meeting_key: int
    driver_number: int
    speed: int
    n_gear: int
    # Not published for every session - 2026 sessions return it null for
    # every sample. Absent telemetry, not a broken contract.
    drs: int | None
    throttle: int
    brake: int
    rpm: int


class Driver(OpenF1Record, endpoint="drivers"):
    session_key: int
    meeting_key: int
    driver_number: int
    first_name: str
    last_name: str
    broadcast_name: str
    name_acronym: str
    team_name: str
    team_colour: str
    country_code: str | None
    headshot_url: str | None


class Session(OpenF1Record, endpoint="sessions"):
    session_key: int
    meeting_key: int
    session_name: str
    session_type: str
    date_start: datetime
    date_end: datetime | None


class Meeting(OpenF1Record, endpoint="meetings"):
    meeting_key: int
    meeting_name: str
    date_start: datetime
    date_end: datetime
    year: int
    circuit_key: int
    circuit_short_name: str
    country_name: str
    location: str
    circuit_type: str
    circuit_info_url: str | None


class Weather(OpenF1Record, endpoint="weather"):
    date: datetime
    session_key: int
    meeting_key: int
    air_temperature: float
    track_temperature: float
    pressure: float
    humidity: float
    wind_speed: float
    rainfall: bool


class Lap(OpenF1Record, endpoint="laps"):
    session_key: int
    meeting_key: int
    driver_number: int
    lap_number: int
    # May be null if the car joins the lap from the pit exit.
    date_start: datetime | None
    lap_duration: float | None


class Pit(OpenF1Record, endpoint="pit"):
    date: datetime
    session_key: int
    meeting_key: int
    driver_number: int
    lap_number: int
    pit_duration: float | None


class Position(OpenF1Record, endpoint="position"):
    date: datetime
    session_key: int
    meeting_key: int
    driver_number: int
    position: int
