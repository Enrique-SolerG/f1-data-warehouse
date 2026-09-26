import json

import pytest
from open_f1_client import CarDataSample, Driver, Lap, Session
from pydantic import ValidationError

CAR_DATA = {
    "date": "2023-09-16T13:00:00.190000+00:00",
    "session_key": 9161,
    "meeting_key": 1219,
    "driver_number": 1,
    "speed": 0,
    "rpm": 3545,
    "brake": 0,
    "throttle": 0,
    "drs": None,
    "n_gear": 0,
}


def test_endpoint_is_bound_to_class() -> None:
    assert CarDataSample.endpoint == "car_data"
    assert Driver.endpoint == "drivers"
    assert Lap.endpoint == "laps"


def test_validate_many_parses_array_and_ignores_extra_fields() -> None:
    raw = json.dumps([CAR_DATA, {**CAR_DATA, "speed": 312, "unexpected": "x"}])

    records = CarDataSample.validate_many(raw)

    assert [r.speed for r in records] == [0, 312]
    assert records[0].date.year == 2023
    assert not hasattr(records[1], "unexpected")


def test_validate_many_accepts_bytes() -> None:
    assert len(CarDataSample.validate_many(json.dumps([CAR_DATA]).encode())) == 1


def test_validate_many_rejects_missing_field() -> None:
    raw = json.dumps([{k: v for k, v in CAR_DATA.items() if k != "speed"}])

    with pytest.raises(ValidationError):
        CarDataSample.validate_many(raw)


def test_validate_many_returns_subclass_instances() -> None:
    raw = json.dumps(
        [
            {
                "session_key": 1,
                "meeting_key": 2,
                "session_name": "Race",
                "session_type": "Race",
                "date_start": "2024-03-02T15:00:00+00:00",
                "date_end": None,
            }
        ]
    )

    (session,) = Session.validate_many(raw)

    assert isinstance(session, Session)
    assert session.date_end is None
