import io
from pathlib import Path

import pytest

import fitfast


@pytest.fixture()
def fit_path(tmp_path, activity):
    p = tmp_path / "a.fit"
    p.write_bytes(activity)
    return p


def test_bytes(activity):
    assert fitfast.count(activity)[0] == 5


def test_bytearray_and_memoryview(activity):
    assert fitfast.count(bytearray(activity)) == fitfast.count(activity)
    assert fitfast.count(memoryview(activity)) == fitfast.count(activity)


def test_str_path_and_pathlib(fit_path, activity):
    assert fitfast.count(str(fit_path)) == fitfast.count(activity)
    assert fitfast.count(Path(fit_path)) == fitfast.count(activity)


def test_binary_file_object(fit_path, activity):
    with open(fit_path, "rb") as f:
        assert fitfast.count(f) == fitfast.count(activity)
    assert fitfast.count(io.BytesIO(activity)) == fitfast.count(activity)


def test_text_file_object_raises(fit_path):
    with open(fit_path, "r", encoding="latin-1") as f:
        with pytest.raises(TypeError, match="binary"):
            fitfast.count(f)


def test_missing_path():
    with pytest.raises(FileNotFoundError):
        fitfast.count("/no/such/file.fit")
