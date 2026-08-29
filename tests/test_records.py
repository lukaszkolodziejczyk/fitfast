import math

import numpy as np

import fitfast
from fit_builder import (
    FIT_EPOCH_OFFSET,
    RECORD,
    T0,
    UINT8,
    UINT16,
    UINT32,
    FitBuilder,
    deg_to_semicircles,
    encode_value,
)


def test_basic_columns(activity):
    cols = fitfast.records(activity)
    assert set(cols) >= {
        "timestamp",
        "position_lat",
        "position_long",
        "heart_rate",
        "distance",
        "speed",
        "temperature",
    }
    for arr in cols.values():
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float64
        assert len(arr) == 3

    np.testing.assert_allclose(
        cols["timestamp"], [T0 + FIT_EPOCH_OFFSET + i for i in range(3)]
    )
    np.testing.assert_allclose(cols["position_lat"][:2], [50.0, 50.001], atol=1e-7)
    assert math.isnan(cols["position_lat"][2])
    np.testing.assert_allclose(cols["distance"], [0.0, 3.21, 6.5])
    np.testing.assert_allclose(cols["speed"], [3.0, 3.21, 3.29])
    assert cols["heart_rate"][0] == 120 and cols["heart_rate"][2] == 125
    assert math.isnan(cols["heart_rate"][1])
    assert math.isnan(cols["temperature"][2])


def test_degrees_false_keeps_semicircles(activity):
    cols = fitfast.records(activity, degrees=False)
    assert cols["position_lat"][0] == deg_to_semicircles(50.0)


def test_big_endian_matches_little_endian(activity, activity_be):
    le = fitfast.records(activity)
    be = fitfast.records(activity_be)
    assert set(le) == set(be)
    for k in le:
        np.testing.assert_array_equal(le[k], be[k], err_msg=k)


def test_unknown_message_kind_returns_empty(activity):
    assert fitfast.records(activity, message="lap") == {}
    assert fitfast.records(activity, message="no_such_mesg") == {}


def test_union_of_multiple_definitions():
    """Records defined with and without `power` share one NaN-padded column."""
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (3, 1, UINT8)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT8, 100))
    b.definition(0, RECORD, [(253, 4, UINT32), (3, 1, UINT8), (7, 2, UINT16)])
    b.data(0, encode_value(UINT32, T0 + 1) + encode_value(UINT8, 110) + encode_value(UINT16, 250))
    b.data(0, encode_value(UINT32, T0 + 2) + encode_value(UINT8, 111) + encode_value(UINT16, 260))
    cols = fitfast.records(b.build())
    assert len(cols["power"]) == 3
    assert math.isnan(cols["power"][0])
    np.testing.assert_allclose(cols["power"][1:], [250.0, 260.0])
    np.testing.assert_allclose(cols["heart_rate"], [100, 110, 111])


def test_compressed_timestamp_headers():
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (3, 1, UINT8)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT8, 100))  # seeds timestamp
    b.definition(1, RECORD, [(3, 1, UINT8)])  # no timestamp field
    b.compressed(1, (T0 + 5) & 0x1F, encode_value(UINT8, 101))
    b.compressed(1, (T0 + 6) & 0x1F, encode_value(UINT8, 102))
    cols = fitfast.records(b.build())
    np.testing.assert_allclose(
        cols["timestamp"],
        [t + FIT_EPOCH_OFFSET for t in (T0, T0 + 5, T0 + 6)],
    )
    np.testing.assert_allclose(cols["heart_rate"], [100, 101, 102])


def test_altitude_scale_and_offset():
    """altitude: uint16, scale 5, offset 500 -> stored (alt+500)*5."""
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (2, 2, UINT16)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT16, (100 + 500) * 5))
    cols = fitfast.records(b.build())
    np.testing.assert_allclose(cols["altitude"], [100.0])


def test_unknown_field_gets_numbered_column():
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (250, 1, UINT8)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT8, 42))
    cols = fitfast.records(b.build())
    assert cols["unknown_250"][0] == 42


def _with_dev_field(scale: int | None = 2, offset: int | None = 10) -> bytes:
    from fit_builder import DEVELOPER_DATA_ID, FIELD_DESCRIPTION, STRING, BYTE, SINT8 as S8

    b = FitBuilder()
    # developer_data_id: application_id (1, byte[16]), developer_data_index (3, uint8)
    b.definition(0, DEVELOPER_DATA_ID, [(1, 16, BYTE), (3, 1, UINT8)])
    b.data(0, bytes(range(16)) + encode_value(UINT8, 0))
    # field_description
    fields = [(0, 1, UINT8), (1, 1, UINT8), (2, 1, UINT8), (3, 10, STRING)]
    payload = (
        encode_value(UINT8, 0)  # developer_data_index
        + encode_value(UINT8, 0)  # field_definition_number
        + encode_value(UINT8, UINT16)  # fit_base_type_id
        + encode_value(STRING, "air_power", size=10)
    )
    if scale is not None:
        fields.append((6, 1, UINT8))
        payload += encode_value(UINT8, scale)
    if offset is not None:
        fields.append((7, 1, S8))
        payload += encode_value(S8, offset)
    b.definition(0, FIELD_DESCRIPTION, fields)
    b.data(0, payload)
    # record with the developer field attached
    b.definition(1, RECORD, [(253, 4, UINT32), (3, 1, UINT8)], dev_fields=[(0, 2, 0)])
    b.data(1, encode_value(UINT32, T0) + encode_value(UINT8, 100) + encode_value(UINT16, 300))
    b.data(1, encode_value(UINT32, T0 + 1) + encode_value(UINT8, 101) + encode_value(UINT16, 0xFFFF))
    return b.build()


def test_developer_field_column_scaled():
    cols = fitfast.records(_with_dev_field())
    # (300 / 2) - 10 = 140; second row invalid -> NaN
    np.testing.assert_allclose(cols["air_power"][0], 140.0)
    assert math.isnan(cols["air_power"][1])


def test_developer_field_no_scale():
    cols = fitfast.records(_with_dev_field(scale=None, offset=None))
    np.testing.assert_allclose(cols["air_power"][0], 300.0)


def test_enum_fields_are_numeric_columns(activity):
    # file_id type is an enum; in a session mesg sport shows as numeric
    cols = fitfast.records(activity, message="session")
    np.testing.assert_allclose(cols["sport"], [1.0])
    np.testing.assert_allclose(cols["total_distance"], [6.5])
