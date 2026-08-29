import pytest

from fit_builder import make_activity


@pytest.fixture(scope="session")
def activity() -> bytes:
    return make_activity()


@pytest.fixture(scope="session")
def activity_be() -> bytes:
    return make_activity(big_endian=True)
