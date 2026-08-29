import importlib.metadata

import fitfast


def test_version_matches_package_metadata():
    assert fitfast.__version__ == importlib.metadata.version("fitfast")


def test_profile_version_exported():
    assert isinstance(fitfast.PROFILE_VERSION, int)
    assert fitfast.PROFILE_VERSION >= 21_212


def test_public_api_surface():
    assert set(fitfast.__all__) == {
        "FitDecodeError",
        "FitSource",
        "PROFILE_VERSION",
        "count",
        "message_counts",
        "parse",
        "records",
        "__version__",
    }
