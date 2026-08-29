"""Cross-check fitfast output against the official garmin-fit-sdk package.

Documented, intentional differences:
- fitfast groups messages as "record", garmin-fit-sdk as "record_mesgs".
- fitfast timestamps are Unix epoch; garmin-fit-sdk (without datetime
  conversion) returns raw FIT epoch seconds — they differ by exactly
  FIT_EPOCH_OFFSET.
"""

import math

import pytest

garmin = pytest.importorskip("garmin_fit_sdk")

import fitfast
from fit_builder import FIT_EPOCH_OFFSET


def garmin_decode(data: bytes) -> dict:
    stream = garmin.Stream.from_byte_array(bytearray(data))
    messages, errors = garmin.Decoder(stream).read(convert_datetimes_to_dates=False)
    assert not errors, errors
    return messages


@pytest.mark.parametrize("endian", ["le", "be"])
def test_record_values_match(activity, activity_be, endian):
    data = activity if endian == "le" else activity_be
    ours = fitfast.parse(data)["record"]
    theirs = garmin_decode(data)["record_mesgs"]
    assert len(ours) == len(theirs) == 3
    for o, t in zip(ours, theirs):
        assert o["timestamp"] == t["timestamp"] + FIT_EPOCH_OFFSET
        for key in ("heart_rate", "distance", "speed", "position_lat", "temperature"):
            if key in t:
                assert o[key] == pytest.approx(t[key]), key
            else:
                assert key not in o, f"{key} should be omitted as invalid"


def test_session_values_match(activity):
    ours = fitfast.parse(activity)["session"][0]
    theirs = garmin_decode(activity)["session_mesgs"][0]
    assert ours["sport"] == theirs["sport"] == "running"
    assert ours["total_distance"] == theirs["total_distance"] == 6.5


def test_records_columns_match_garmin_values(activity):
    cols = fitfast.records(activity, degrees=False)
    theirs = garmin_decode(activity)["record_mesgs"]
    for i, t in enumerate(theirs):
        for key in ("heart_rate", "distance", "speed", "position_lat"):
            if key in t:
                assert cols[key][i] == pytest.approx(t[key]), (key, i)
            else:
                assert math.isnan(cols[key][i]), (key, i)


def test_developer_fields_match():
    """garmin-fit-sdk returns developer fields raw, keyed by field number;
    fitfast names them via field_description and applies its scale/offset
    (scale 2, offset 10 in this fixture)."""
    from test_records import _with_dev_field

    data = _with_dev_field()
    ours = fitfast.parse(data)["record"]
    theirs = garmin_decode(data)["record_mesgs"]
    raw = theirs[0]["developer_fields"][0]
    assert ours[0]["air_power"] == pytest.approx(raw / 2 - 10)
