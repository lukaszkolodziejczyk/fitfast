import pytest

import fitfast
from fit_builder import RECORD, T0, UINT8, UINT32, FitBuilder, encode_value, make_activity


def _mini() -> FitBuilder:
    b = FitBuilder()
    b.definition(0, RECORD, [(253, 4, UINT32), (3, 1, UINT8)])
    b.data(0, encode_value(UINT32, T0) + encode_value(UINT8, 100))
    return b


def test_empty_input():
    with pytest.raises(fitfast.FitDecodeError, match="empty"):
        fitfast.parse(b"")


def test_garbage_input():
    with pytest.raises(fitfast.FitDecodeError):
        fitfast.parse(b"this is definitely not a FIT file, not even close....")


def test_truncated_file():
    data = make_activity()
    with pytest.raises(fitfast.FitDecodeError):
        fitfast.parse(data[: len(data) // 2])


def test_corrupt_file_crc():
    data = _mini().build(corrupt_file_crc=True)
    with pytest.raises(fitfast.FitDecodeError, match="(?i)checksum"):
        fitfast.parse(data)


def test_corrupt_header_crc():
    data = _mini().build(corrupt_header_crc=True)
    with pytest.raises(fitfast.FitDecodeError, match="(?i)checksum"):
        fitfast.parse(data)


def test_lying_data_size():
    data = _mini().build(data_size=10_000)
    with pytest.raises(fitfast.FitDecodeError):
        fitfast.parse(data)


def test_12_byte_header_is_valid():
    data = _mini().build(header_size=12)
    n, _ = fitfast.count(data)
    assert n == 1


def test_trailing_garbage_after_valid_sequence():
    data = make_activity() + b"garbage garbage garbage"
    with pytest.raises(fitfast.FitDecodeError, match="after 1 valid"):
        fitfast.parse(data)


def test_error_type_hierarchy():
    assert issubclass(fitfast.FitDecodeError, ValueError)


@pytest.mark.parametrize("fn", [fitfast.count, fitfast.message_counts, fitfast.records, fitfast.parse])
def test_all_entry_points_raise(fn):
    with pytest.raises(fitfast.FitDecodeError):
        fn(b"\x00" * 64)


def test_chained_files_decode(activity):
    data = activity + activity
    n, _ = fitfast.count(data)
    assert n == 2 * fitfast.count(activity)[0]
    d = fitfast.parse(data)
    assert len(d["record"]) == 6
    assert fitfast.message_counts(data)["file_id"] == 2
