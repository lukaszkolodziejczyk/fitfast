"""Array-valued fields: per-element invalid handling and BYTE passthrough."""

import pytest

import fitfast
from fit_builder import (
    BYTE,
    FLOAT32,
    RECORD,
    T0,
    UINT8,
    UINT16,
    UINT32,
    FitBuilder,
    encode_value,
)


def _speed_1s_file() -> bytes:
    """record.speed_1s: uint8 array, scale 16 — one valid and one invalid element."""
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (17, 2, UINT8)])
    b.data(0, encode_value(UINT32, T0) + bytes([32, 0xFF]))
    return b.build()


def test_partially_invalid_array_elements_become_none():
    d = fitfast.parse(_speed_1s_file())
    assert d["record"][0]["speed_1s"] == [2.0, None]  # 32/16 = 2.0, 0xFF invalid


def test_partially_invalid_array_matches_garmin_sdk():
    garmin = pytest.importorskip("garmin_fit_sdk")
    data = _speed_1s_file()
    stream = garmin.Stream.from_byte_array(bytearray(data))
    messages, errors = garmin.Decoder(stream).read(convert_datetimes_to_dates=False)
    assert not errors
    theirs = messages["record_mesgs"][0]["speed_1s"]
    ours = fitfast.parse(data)["record"][0]["speed_1s"]
    assert list(ours) == list(theirs)


def test_fully_invalid_array_omitted():
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (17, 2, UINT8)])
    b.data(0, encode_value(UINT32, T0) + bytes([0xFF, 0xFF]))
    d = fitfast.parse(b.build())
    assert "speed_1s" not in d["record"][0]


def test_byte_array_elements_kept_verbatim():
    """BYTE arrays are opaque: a 0xFF element is data, not an invalid hole."""
    from fit_builder import DEVELOPER_DATA_ID

    payload = bytes(range(15)) + bytes([0xFF])
    b = FitBuilder()
    b.definition(0, DEVELOPER_DATA_ID, [(1, 16, BYTE), (3, 1, UINT8)])
    b.data(0, payload + encode_value(UINT8, 0))
    d = fitfast.parse(b.build())
    app_id = d["developer_data_id"][0]["application_id"]
    assert isinstance(app_id, bytes)  # BYTE arrays surface as Python bytes
    assert app_id == payload  # 0xFF survives as data


def _float_dev_field_file() -> bytes:
    """A float32 developer field with a declared scale: stored pre-scaled."""
    from fit_builder import FIELD_DESCRIPTION, SINT8, STRING

    b = FitBuilder()
    b.definition(
        0,
        FIELD_DESCRIPTION,
        [(0, 1, UINT8), (1, 1, UINT8), (2, 1, UINT8), (3, 8, STRING), (6, 1, UINT8), (7, 1, SINT8)],
    )
    b.data(
        0,
        encode_value(UINT8, 0)
        + encode_value(UINT8, 0)
        + encode_value(UINT8, FLOAT32)
        + encode_value(STRING, "ratio", size=8)
        + encode_value(UINT8, 2)  # scale (must NOT apply to float values)
        + encode_value(SINT8, 10),  # offset
    )
    b.definition(1, RECORD, [(253, 4, UINT32)], dev_fields=[(0, 4, 0)])
    b.data(1, encode_value(UINT32, T0) + encode_value(FLOAT32, 3.5))
    return b.build()


def test_float_dev_field_not_scaled_in_parse_and_records():
    data = _float_dev_field_file()
    assert fitfast.parse(data)["record"][0]["ratio"] == pytest.approx(3.5)
    assert fitfast.records(data)["ratio"][0] == pytest.approx(3.5)


def test_integer_array_with_scale_in_records_is_skipped():
    """records() returns only scalars; array fields never become columns."""
    cols = fitfast.records(_speed_1s_file())
    assert "speed_1s" not in cols
