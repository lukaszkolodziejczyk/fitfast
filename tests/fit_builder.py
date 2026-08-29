"""Build FIT files byte-by-byte for tests.

Implements the FIT container format (header, definition/data messages,
compressed-timestamp headers, developer fields, CRC-16) so tests can create
precisely controlled inputs, including malformed ones. Values follow the
Garmin FIT Protocol specification.
"""

from __future__ import annotations

import struct

# FIT base type codes
ENUM = 0x00
SINT8 = 0x01
UINT8 = 0x02
SINT16 = 0x83
UINT16 = 0x84
SINT32 = 0x85
UINT32 = 0x86
STRING = 0x07
FLOAT32 = 0x88
FLOAT64 = 0x89
UINT8Z = 0x0A
UINT16Z = 0x8B
UINT32Z = 0x8C
BYTE = 0x0D
SINT64 = 0x8E
UINT64 = 0x8F
UINT64Z = 0x90

_FMT = {
    ENUM: "B", UINT8: "B", UINT8Z: "B", BYTE: "B", SINT8: "b",
    UINT16: "H", UINT16Z: "H", SINT16: "h",
    UINT32: "I", UINT32Z: "I", SINT32: "i",
    UINT64: "Q", UINT64Z: "Q", SINT64: "q",
    FLOAT32: "f", FLOAT64: "d",
}

_SIZE = {k: struct.calcsize(v) for k, v in _FMT.items()}

# invalid sentinels per base type
INVALID = {
    ENUM: 0xFF, UINT8: 0xFF, BYTE: 0xFF, SINT8: 0x7F,
    UINT16: 0xFFFF, SINT16: 0x7FFF,
    UINT32: 0xFFFFFFFF, SINT32: 0x7FFFFFFF,
    UINT64: 0xFFFFFFFFFFFFFFFF, SINT64: 0x7FFFFFFFFFFFFFFF,
    UINT8Z: 0, UINT16Z: 0, UINT32Z: 0, UINT64Z: 0,
}

# global message numbers used in tests
FILE_ID = 0
SESSION = 18
LAP = 19
RECORD = 20
SPORT_MESG = 12
FIELD_DESCRIPTION = 206
DEVELOPER_DATA_ID = 207

# seconds between Unix epoch and FIT epoch
FIT_EPOCH_OFFSET = 631_065_600

CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def encode_value(base_type: int, value, size: int | None = None, big_endian: bool = False) -> bytes:
    """Encode one field value. Strings are NUL-terminated and padded to size."""
    if base_type == STRING:
        raw = value.encode() + b"\x00"
        if size is not None:
            raw = raw.ljust(size, b"\x00")
        return raw
    order = ">" if big_endian else "<"
    if isinstance(value, (list, tuple)):
        return b"".join(struct.pack(order + _FMT[base_type], v) for v in value)
    return struct.pack(order + _FMT[base_type], value)


class FitBuilder:
    """Accumulates FIT records; `build()` wraps them in a header and CRC."""

    def __init__(self) -> None:
        self.body = bytearray()

    def definition(
        self,
        local: int,
        global_num: int,
        fields: list[tuple[int, int, int]],
        *,
        big_endian: bool = False,
        dev_fields: list[tuple[int, int, int]] | None = None,
    ) -> "FitBuilder":
        """fields: [(field_num, size, base_type)], dev_fields: [(num, size, ddi)]."""
        header = 0x40 | (0x20 if dev_fields else 0x00) | local
        order = ">" if big_endian else "<"
        out = bytearray([header, 0x00, 1 if big_endian else 0])
        out += struct.pack(order + "H", global_num)
        out.append(len(fields))
        for num, size, base in fields:
            out += bytes([num, size, base])
        if dev_fields:
            out.append(len(dev_fields))
            for num, size, ddi in dev_fields:
                out += bytes([num, size, ddi])
        self.body += out
        return self

    def data(self, local: int, payload: bytes) -> "FitBuilder":
        self.body += bytes([local]) + payload
        return self

    def compressed(self, local: int, time_offset: int, payload: bytes) -> "FitBuilder":
        """Compressed-timestamp data message (local 0-3, offset 0-31 seconds)."""
        header = 0x80 | (local << 5) | (time_offset & 0x1F)
        self.body += bytes([header]) + payload
        return self

    def build(
        self,
        *,
        header_size: int = 14,
        protocol_version: int = 0x20,
        profile_version: int = 21_212,
        corrupt_file_crc: bool = False,
        corrupt_header_crc: bool = False,
        data_size: int | None = None,
    ) -> bytes:
        size = len(self.body) if data_size is None else data_size
        header = struct.pack(
            "<BBHI4s", header_size, protocol_version, profile_version, size, b".FIT"
        )
        if header_size == 14:
            hcrc = crc16(header)
            if corrupt_header_crc:
                hcrc ^= 0xFFFF
            header += struct.pack("<H", hcrc)
        fcrc = crc16(header + bytes(self.body))
        if corrupt_file_crc:
            fcrc ^= 0xFFFF
        return header + bytes(self.body) + struct.pack("<H", fcrc)


# ---------------------------------------------------------------------------
# Standard synthetic activity shared across tests
# ---------------------------------------------------------------------------

T0 = 1_000_000_000  # FIT epoch seconds; Unix = T0 + FIT_EPOCH_OFFSET

FILE_ID_FIELDS = [(0, 1, ENUM), (1, 2, UINT16), (4, 4, UINT32)]  # type, manufacturer, time_created
RECORD_FIELDS = [
    (253, 4, UINT32),  # timestamp
    (0, 4, SINT32),    # position_lat (semicircles)
    (1, 4, SINT32),    # position_long
    (3, 1, UINT8),     # heart_rate
    (5, 4, UINT32),    # distance (scale 100)
    (6, 2, UINT16),    # speed (scale 1000)
    (13, 1, SINT8),    # temperature
]
SESSION_FIELDS = [
    (253, 4, UINT32),  # timestamp
    (2, 4, UINT32),    # start_time
    (5, 1, ENUM),      # sport
    (9, 4, UINT32),    # total_distance (scale 100)
]


def deg_to_semicircles(deg: float) -> int:
    return round(deg * (2**31) / 180.0)


def record_payload(
    ts: int,
    lat_deg: float | None,
    lon_deg: float | None,
    hr: int | None,
    distance_m: float | None,
    speed_ms: float | None,
    temp_c: int | None,
    big_endian: bool = False,
) -> bytes:
    be = big_endian
    return b"".join(
        [
            encode_value(UINT32, ts, big_endian=be),
            encode_value(SINT32, deg_to_semicircles(lat_deg) if lat_deg is not None else INVALID[SINT32], big_endian=be),
            encode_value(SINT32, deg_to_semicircles(lon_deg) if lon_deg is not None else INVALID[SINT32], big_endian=be),
            encode_value(UINT8, hr if hr is not None else INVALID[UINT8], big_endian=be),
            encode_value(UINT32, round(distance_m * 100) if distance_m is not None else INVALID[UINT32], big_endian=be),
            encode_value(UINT16, round(speed_ms * 1000) if speed_ms is not None else INVALID[UINT16], big_endian=be),
            encode_value(SINT8, temp_c if temp_c is not None else INVALID[SINT8], big_endian=be),
        ]
    )


def make_activity(*, big_endian: bool = False) -> bytes:
    """A small activity: file_id + 3 records + session, with some invalid values."""
    be = big_endian
    b = FitBuilder()
    b.definition(0, FILE_ID, FILE_ID_FIELDS, big_endian=be)
    b.data(
        0,
        encode_value(ENUM, 4, big_endian=be)          # type = activity
        + encode_value(UINT16, 1, big_endian=be)      # manufacturer = garmin
        + encode_value(UINT32, T0, big_endian=be),    # time_created
    )
    b.definition(1, RECORD, RECORD_FIELDS, big_endian=be)
    b.data(1, record_payload(T0 + 0, 50.0, 16.25, 120, 0.0, 3.0, 21, be))
    b.data(1, record_payload(T0 + 1, 50.001, 16.251, None, 3.21, 3.21, 21, be))  # hr invalid
    b.data(1, record_payload(T0 + 2, None, None, 125, 6.5, 3.29, None, be))      # gps + temp invalid
    b.definition(2, SESSION, SESSION_FIELDS, big_endian=be)
    b.data(
        2,
        encode_value(UINT32, T0 + 2, big_endian=be)
        + encode_value(UINT32, T0, big_endian=be)
        + encode_value(ENUM, 1, big_endian=be)        # sport = running
        + encode_value(UINT32, 650, big_endian=be),   # total_distance = 6.50 m
    )
    return b.build()
