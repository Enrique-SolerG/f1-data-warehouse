from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel


class OpenF1Model(BaseModel):
    endpoint: ClassVar[str]


class CarDataSample(OpenF1Model):
    endpoint: ClassVar[str] = "car_data"

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


class Driver(OpenF1Model):
    endpoint: ClassVar[str] = "drivers"

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


class Session(OpenF1Model):
    endpoint: ClassVar[str] = "sessions"

    session_key: int
    meeting_key: int
    session_name: str
    session_type: str
    date_start: datetime
    date_end: datetime | None


class Meeting(OpenF1Model):
    endpoint: ClassVar[str] = "meetings"

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


class Weather(OpenF1Model):
    endpoint: ClassVar[str] = "weather"

    date: datetime
    session_key: int
    meeting_key: int
    air_temperature: float
    track_temperature: float
    pressure: float
    humidity: float
    wind_speed: float
    rainfall: bool


class Lap(OpenF1Model):
    endpoint: ClassVar[str] = "laps"

    session_key: int
    meeting_key: int
    driver_number: int
    lap_number: int
    date_start: (
        datetime | None
    )  # may be null if the car joins the lap from the pit exit
    lap_duration: float | None


class Pit(OpenF1Model):
    endpoint: ClassVar[str] = "pit"

    date: datetime
    session_key: int
    meeting_key: int
    driver_number: int
    lap_number: int
    pit_duration: float | None


class Position(OpenF1Model):
    endpoint: ClassVar[str] = "position"

    date: datetime
    session_key: int
    meeting_key: int
    driver_number: int
    position: int
