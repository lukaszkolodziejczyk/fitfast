"""Benchmark fitfast against other Python FIT parsers on a file you provide.

Usage:
    python benchmarks/bench.py path/to/activity.fit

fitfast and garmin-fit-sdk are always benchmarked; fitparse and fitdecode are
included when installed (`pip install fitparse fitdecode`).
"""

import statistics
import sys
import time


def bench(name: str, fn, iters: int) -> None:
    fn()  # warmup + correctness
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    print(f"{name:<40} {statistics.median(times) * 1000:>10.1f} ms  (median of {iters})")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python benchmarks/bench.py path/to/activity.fit")
    path = sys.argv[1]
    data = open(path, "rb").read()
    print(f"file: {path} ({len(data) / 1e6:.1f} MB)\n")

    import fitfast

    n, nf = fitfast.count(data)
    print(f"messages: {n:,}, fields: {nf:,}\n")

    bench("fitfast.count", lambda: fitfast.count(data), 20)
    bench("fitfast.records", lambda: fitfast.records(data), 20)
    bench("fitfast.parse", lambda: fitfast.parse(data), 10)

    try:
        from garmin_fit_sdk import Decoder, Stream

        def garmin():
            msgs, errs = Decoder(Stream.from_byte_array(bytearray(data))).read(
                convert_datetimes_to_dates=False
            )
            assert not errs

        bench("garmin-fit-sdk (official)", garmin, 3)
    except ImportError:
        print("garmin-fit-sdk not installed, skipping")

    try:
        import fitdecode

        def fdec():
            with fitdecode.FitReader(path) as f:
                for frame in f:
                    pass

        bench("fitdecode", fdec, 3)
    except ImportError:
        pass

    try:
        from fitparse import FitFile

        def fparse():
            for msg in FitFile(path).get_messages():
                msg.get_values()

        bench("fitparse", fparse, 2)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
