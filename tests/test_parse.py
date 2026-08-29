from datetime import datetime, timezone

import pytest

import fitfast
from fit_builder import (
    ENUM,
    FIT_EPOCH_OFFSET,
    RECORD,
    SPORT_MESG,
    STRING,
    T0,
    UINT8,
    UINT16,
    UINT32,
    FitBuilder,
    encode_value,
)


def test_message_grouping(activity):
    d = fitfast.parse(activity)
    assert list(d) == ["file_id", "record", "session"]
    assert len(d["record"]) == 3
    assert len(d["file_id"]) == 1
    assert len(d["session"]) == 1


def test_enum_names(activity):
    d = fitfast.parse(activity)
    assert d["file_id"][0]["type"] == "activity"
    assert d["file_id"][0]["manufacturer"] == "garmin"
    assert d["session"][0]["sport"] == "running"


def test_enum_names_disabled(activity):
    d = fitfast.parse(activity, enum_names=False)
    assert d["file_id"][0]["type"] == 4
    assert d["session"][0]["sport"] == 1


def test_scale_offset_applied(activity):
    d = fitfast.parse(activity)
    assert d["session"][0]["total_distance"] == 6.5
    assert d["record"][1]["distance"] == 3.21
    assert d["record"][1]["speed"] == 3.21


def test_invalid_fields_omitted(activity):
    recs = fitfast.parse(activity)["record"]
    assert "heart_rate" in recs[0] and "heart_rate" not in recs[1]
    assert "position_lat" not in recs[2]
    assert "temperature" not in recs[2]


def test_timestamps_are_unix_ints(activity):
    d = fitfast.parse(activity)
    ts = d["record"][0]["timestamp"]
    assert isinstance(ts, int)
    assert ts == T0 + FIT_EPOCH_OFFSET
    assert d["session"][0]["start_time"] == T0 + FIT_EPOCH_OFFSET


def test_datetimes_option(activity):
    d = fitfast.parse(activity, datetimes=True)
    ts = d["record"][0]["timestamp"]
    assert isinstance(ts, datetime)
    assert ts.tzinfo is not None
    assert ts == datetime.fromtimestamp(T0 + FIT_EPOCH_OFFSET, tz=timezone.utc)


def test_unknown_message_and_field():
    b = FitBuilder()
    # 65290 is in the manufacturer-specific range and has no profile name
    b.definition(0, 65290, [(0, 2, UINT16)])
    b.data(0, encode_value(UINT16, 7))
    b.definition(1, RECORD, [(253, 4, UINT32), (250, 1, UINT8)])
    b.data(1, encode_value(UINT32, T0) + encode_value(UINT8, 42))
    d = fitfast.parse(b.build())
    assert d["unknown_65290"][0][0] == 7  # unknown mesg, field keyed by number
    assert d["record"][0][250] == 42  # unknown field in known mesg


def test_named_mfg_range_message():
    """0xFF00 is a named profile value (mfg_range_min), not an unknown."""
    b = FitBuilder()
    b.definition(0, 0xFF00, [(0, 2, UINT16)])
    b.data(0, encode_value(UINT16, 7))
    assert "mfg_range_min" in fitfast.parse(b.build())


def test_string_field():
    b = FitBuilder()
    b.definition(0, SPORT_MESG, [(0, 1, ENUM), (3, 12, STRING)])
    b.data(0, encode_value(ENUM, 1) + encode_value(STRING, "Trail", size=12))
    d = fitfast.parse(b.build())
    assert d["sport"][0]["name"] == "Trail"
    assert d["sport"][0]["sport"] == "running"


def test_empty_string_omitted():
    b = FitBuilder()
    b.definition(0, SPORT_MESG, [(0, 1, ENUM), (3, 12, STRING)])
    b.data(0, encode_value(ENUM, 1) + encode_value(STRING, "", size=12))
    d = fitfast.parse(b.build())
    assert "name" not in d["sport"][0]


def test_unknown_enum_value_stays_numeric():
    b = FitBuilder()
    b.definition(0, SPORT_MESG, [(0, 1, ENUM)])
    b.data(0, encode_value(ENUM, 200))  # not a defined sport
    d = fitfast.parse(b.build())
    assert d["sport"][0]["sport"] == 200


def test_developer_fields_parsed():
    from test_records import _with_dev_field

    d = fitfast.parse(_with_dev_field())
    recs = d["record"]
    assert recs[0]["air_power"] == 140.0
    assert "air_power" not in recs[1]  # invalid sentinel omitted
    fd = d["field_description"][0]
    assert fd["field_name"] == "air_power"  # singleton string array -> scalar


def test_dev_field_without_description_is_skipped():
    """rustyfit drops developer fields lacking a field_description; no crash."""
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32)], dev_fields=[(0, 2, 0)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT16, 300))
    d = fitfast.parse(b.build())
    assert len(d["record"]) == 1
    assert set(d["record"][0]) == {"timestamp"}


def test_parse_kwargs_are_keyword_only(activity):
    with pytest.raises(TypeError):
        fitfast.parse(activity, True)  # noqa: too many positional args
