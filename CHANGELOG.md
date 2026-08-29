# Changelog

## 0.1.0 (2026-08-29)

Initial release.

- `records()`: columnar NumPy decode of any message kind — scale/offset,
  Unix timestamps, semicircles→degrees, developer fields, NaN for
  missing/invalid values.
- `parse()`: dict-of-messages decode with official-SDK semantics — invalid
  sentinel omission, enum names, optional UTC datetimes, developer fields.
- `count()` / `message_counts()`: fast full-file validation and exploration.
- Chained FIT files, compressed-timestamp headers, component expansion and
  accumulated fields supported (via rustyfit).
- abi3 wheels (CPython ≥ 3.10) for Linux, macOS, Windows.
