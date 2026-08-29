"""Optional end-to-end test against a real device FIT file.

Set FITFAST_REAL_FIT=/path/to/activity.fit to enable. Real files are not
committed to the repository (they contain personal GPS data).
"""

import os

import numpy as np
import pytest

import fitfast

REAL = os.environ.get("FITFAST_REAL_FIT")

pytestmark = pytest.mark.skipif(
    not REAL or not os.path.exists(REAL or ""), reason="FITFAST_REAL_FIT not set"
)


def test_counts_match_garmin_sdk():
    garmin = pytest.importorskip("garmin_fit_sdk")
    data = open(REAL, "rb").read()
    stream = garmin.Stream.from_byte_array(bytearray(data))
    messages, errors = garmin.Decoder(stream).read(convert_datetimes_to_dates=False)
    assert not errors
    theirs = sum(len(v) for v in messages.values() if isinstance(v, list))
    ours, _ = fitfast.count(data)
    assert ours == theirs


def test_records_are_sane():
    cols = fitfast.records(REAL)
    n = len(cols["timestamp"])
    assert n > 0
    ts = cols["timestamp"]
    assert np.all(np.diff(ts[~np.isnan(ts)]) >= 0), "timestamps must be monotonic"
    if "heart_rate" in cols:
        hr = cols["heart_rate"]
        assert np.nanmin(hr) > 20 and np.nanmax(hr) < 250
    if "position_lat" in cols:
        lat = cols["position_lat"]
        assert np.nanmax(np.abs(lat)) <= 90.0
