"""Fast Garmin FIT file parsing, backed by the `rustyfit`_ Rust crate.

Quick start::

    import fitfast

    cols = fitfast.records("activity.fit")        # dict[str, np.ndarray]
    data = fitfast.parse("activity.fit")          # dict[str, list[dict]]
    n_messages, n_fields = fitfast.count("activity.fit")

All functions accept a file path (``str`` / ``os.PathLike``), raw ``bytes``,
a ``bytearray``/``memoryview``, or a binary file-like object.

.. _rustyfit: https://github.com/muktihari/rustyfit
"""

from __future__ import annotations

import os
from typing import IO, Any, Union

import numpy as np

from fitfast._native import (
    FitDecodeError,
    __profile_version__,
    count as _count,
    message_counts as _message_counts,
    parse as _parse,
    records as _records,
)

__version__ = "0.1.0"

#: The Garmin FIT profile version this build decodes with (via rustyfit).
PROFILE_VERSION: int = __profile_version__

FitSource = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, IO[bytes]]

__all__ = [
    "FitDecodeError",
    "FitSource",
    "PROFILE_VERSION",
    "count",
    "message_counts",
    "parse",
    "records",
    "__version__",
]


def _as_bytes(source: FitSource) -> bytes:
    """Normalize any supported input into ``bytes``."""
    if isinstance(source, bytes):
        return source
    if isinstance(source, (bytearray, memoryview)):
        return bytes(source)
    if hasattr(source, "read"):
        data = source.read()
        if not isinstance(data, bytes):
            raise TypeError(
                f"file-like source must be opened in binary mode, got {type(data).__name__}"
            )
        return data
    with open(os.fspath(source), "rb") as f:
        return f.read()


def count(source: FitSource) -> tuple[int, int]:
    """Fully decode ``source`` and return ``(n_messages, n_fields)``.

    The cheapest way to validate a FIT file end to end (structure and CRCs
    are checked while decoding).

    Raises:
        FitDecodeError: if the input is not a valid FIT file.
    """
    return _count(_as_bytes(source))


def message_counts(source: FitSource) -> dict[str, int]:
    """Return the number of decoded messages per message kind.

    Keys are FIT profile message names (``"record"``, ``"session"``, ...);
    manufacturer-specific message numbers appear as ``"unknown_<num>"``.
    """
    return _message_counts(_as_bytes(source))


def records(
    source: FitSource,
    message: str = "record",
    *,
    degrees: bool = True,
) -> dict[str, np.ndarray]:
    """Decode ``source`` and return columnar NumPy arrays for one message kind.

    Every numeric scalar field that occurs in any ``message`` message becomes a
    ``float64`` column of equal length; missing or invalid values are ``NaN``.
    Profile scale/offset are applied, ``date_time`` fields become Unix
    timestamps, and developer fields are included under their declared names.

    Args:
        source: FIT file path, bytes, or binary file-like object.
        message: FIT message kind to extract (``"record"``, ``"lap"``,
            ``"session"``, ``"monitoring"``, ...). Unknown kinds yield ``{}``.
        degrees: convert semicircle-typed coordinate fields
            (``position_lat``, ``position_long``, ...) to degrees.
            Set to ``False`` to keep raw semicircles.

    Returns:
        Mapping of field name to ``numpy.ndarray`` (dtype ``float64``).
        String and array-valued fields are skipped; use :func:`parse` for those.

    Raises:
        FitDecodeError: if the input is not a valid FIT file.
    """
    return _records(_as_bytes(source), message, degrees=degrees)


def parse(
    source: FitSource,
    *,
    enum_names: bool = True,
    datetimes: bool = False,
) -> dict[str, list[dict[str | int, Any]]]:
    """Decode ``source`` into dictionaries, keyed by message kind.

    Semantics match the official Garmin FIT SDKs: profile scale/offset are
    applied, fields holding the FIT "invalid" sentinel are omitted, and
    developer fields are decoded via their ``field_description`` messages.
    Fields not in the FIT profile are keyed by their integer field number.

    Args:
        source: FIT file path, bytes, or binary file-like object.
        enum_names: map FIT enum values to profile names (``sport: "running"``
            instead of ``sport: 1``).
        datetimes: convert ``date_time`` fields to timezone-aware
            :class:`datetime.datetime` (UTC) instead of Unix epoch integers.

    Returns:
        ``{"file_id": [...], "record": [...], "session": [...], ...}``;
        manufacturer-specific message numbers appear as ``"unknown_<num>"``.

    Raises:
        FitDecodeError: if the input is not a valid FIT file.
    """
    return _parse(_as_bytes(source), enum_names=enum_names, datetimes=datetimes)
