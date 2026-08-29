# fitfast

Fast Garmin FIT file parsing for Python — a thin [PyO3](https://pyo3.rs) binding around the excellent
[rustyfit](https://github.com/muktihari/rustyfit) Rust crate.

**30–60× faster** than existing pure-Python FIT parsers for the common
"FIT file → NumPy/DataFrame" workflow, with output semantics that match the
official Garmin FIT SDK.

```python
import fitfast

# Columnar decode: every numeric record field as a float64 NumPy array
cols = fitfast.records("activity.fit")
cols["heart_rate"]      # array([ 96., 101., 103., ...])
cols["timestamp"]       # Unix epoch seconds
cols["position_lat"]    # degrees (semicircles converted for you)

# Works for any message kind
laps = fitfast.records("activity.fit", message="lap")

# Classic dict output (garmin-fit-sdk-style), enums as names
data = fitfast.parse("activity.fit")
data["session"][0]["sport"]           # "running"
data["session"][0]["total_distance"]  # 77265.02  (scale/offset applied)

# Cheap full-file validation and exploration
n_messages, n_fields = fitfast.count("activity.fit")
fitfast.mesg_counts("activity.fit")   # {"file_id": 1, "record": 35079, ...}
```

All functions accept a path, `bytes`, `bytearray`, `memoryview`, or a binary
file-like object.

## Install

```bash
pip install fitfast
```

Prebuilt wheels are available for Linux, macOS, and Windows (CPython ≥ 3.10,
one abi3 wheel per platform). Building from source requires a Rust toolchain.

## Why this package

Every existing Python FIT parser decodes the binary format in pure Python.
The [FIT format](https://developer.garmin.com/fit/) is dense — a single long
activity is easily 100k+ messages and >1M fields — and pure-Python decoding
costs seconds per file, which hurts anyone batch-processing an activity
archive. Meanwhile the fastest FIT decoder in any language is a Rust crate.
`fitfast` bridges that gap: it is (to our knowledge) the first Python FIT
package backed by a native core.

Two design choices keep the speedup from evaporating at the FFI boundary:

1. **Columnar first.** `records()` returns NumPy arrays built in Rust — no
   per-message Python objects at all. This is the fast path for analytics
   (pandas/polars/matplotlib) and the reason the end-to-end speedup stays ~50×.
2. **Dicts when you want them.** `parse()` produces the familiar
   dict-of-messages shape with profile names, scale/offset, enum names, and
   invalid-value handling matching the official SDK — still >10× faster than
   pure-Python parsers, because only the final objects are built in Python.

## Benchmarks

Decoding a 3.6 MB, 147,482-message activity file (a 77 km ultra with 35k GPS
records), Apple M-series, median of repeated in-process runs:

| Task: FIT → NumPy columns for all `record` messages (31 columns) | Time | Relative |
|---|---:|---:|
| `fitfast.records()` | **0.075 s** | **1×** |
| `garmin-fit-sdk` (official) + NumPy conversion | 2.68 s | 36× slower |

| Task: FIT → per-message dicts | Time | Relative |
|---|---:|---:|
| `fitfast.parse()` | **0.15 s** | **1×** |
| `garmin-fit-sdk` (official, pure Python) | 2.57 s | 17× slower |
| `fitdecode` | 3.88 s | 26× slower |
| `fitparse` | 6.72 s | 45× slower |

| Task: validate the whole file (structure + CRCs) | Time | Relative |
|---|---:|---:|
| `fitfast.count()` | **0.043 s** | **1×** |
| `garmin-fit-sdk` (official) | 2.57 s | 60× slower |

Reproduce with [`benchmarks/bench.py`](benchmarks/bench.py) and any FIT file:

```bash
python benchmarks/bench.py path/to/activity.fit
```

## API

### `fitfast.records(source, message="record", *, degrees=True)`

Columnar decode of one message kind → `dict[str, np.ndarray]` (float64).

- Every numeric scalar field that occurs in any message of that kind becomes a
  column; rows where the field is absent or invalid are `NaN`.
- Profile **scale/offset applied**; `date_time` fields become **Unix seconds**;
  semicircle coordinates become **degrees** (disable with `degrees=False`).
- **Developer fields** are included under their `field_description` names.
- String- and array-valued fields are skipped (use `parse()` for those).
- Unknown message kinds return `{}`.

### `fitfast.parse(source, *, enum_names=True, datetimes=False)`

Full decode → `dict[str, list[dict]]`, keyed by message name
(`"record"`, `"session"`, ...; manufacturer-specific messages as
`"unknown_<num>"`).

- Semantics follow the official Garmin FIT SDK: scale/offset applied, fields
  holding the FIT "invalid" sentinel omitted, developer fields resolved.
- `enum_names=True` renders profile enums as names (`"running"`), unknown
  values stay numeric. `datetimes=True` yields timezone-aware UTC `datetime`
  objects instead of Unix epoch ints.
- Fields not in the profile are keyed by integer field number.

### `fitfast.count(source)` / `fitfast.mesg_counts(source)`

Fast full-file validation → `(n_messages, n_fields)`, and per-kind message
counts. Structure and CRCs are verified while decoding; invalid input raises
`fitfast.FitDecodeError` (a `ValueError` subclass).

### Notes and current limitations

- Chained FIT files (multiple FIT sequences in one file) are decoded fully.
- Compressed-timestamp headers, component expansion (`enhanced_speed`, ...)
  and accumulated fields are handled by the rustyfit decoder.
- Dynamic sub-fields are not yet resolved (the main field's name is used) —
  planned for a future release.
- `records()` intentionally returns only numeric scalars.

## Credits

All of the actual FIT decoding is done by
**[rustyfit](https://github.com/muktihari/rustyfit)** by
[Hikmatulloh Hari Mukti](https://github.com/muktihari) (BSD-3-Clause), the
fastest FIT implementation we measured in any language — see also their Go
implementation [muktihari/fit](https://github.com/muktihari/fit). If you need
FIT parsing in Rust or Go, use those crates directly. `fitfast` adds only the
Python-facing layer: columnar extraction, official-SDK-compatible value
semantics, and the PyO3 bindings.

Cross-language performance context: [roznet/fit-benchmarks](https://github.com/roznet/fit-benchmarks).

## License

`fitfast` is licensed under the [BSD 3-Clause License](LICENSE).

Bundled third-party code: the compiled extension statically links
[rustyfit](https://crates.io/crates/rustyfit) (BSD-3-Clause), see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

The FIT Protocol itself is proprietary to Garmin; use of FIT-decoding software
may require compliance with the
[FIT Protocol License](https://www.thisisant.com/developer/ant/licensing/flexible-and-interoperable-data-transfer-fit-protocol-license).
This project is not affiliated with or endorsed by Garmin.

## Development

```bash
uv venv && uv pip install -e '.[dev]'   # or: pip install -e '.[dev]'
maturin develop --release               # rebuild the extension
pytest                                  # run the test suite
```

The test suite builds synthetic FIT files byte-by-byte (little/big endian,
compressed timestamps, developer fields, chained files, corrupt CRCs) and
cross-checks output against the official `garmin-fit-sdk`.
