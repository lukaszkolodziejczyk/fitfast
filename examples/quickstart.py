# /// script
# requires-python = ">=3.10"
# dependencies = ["fitfast"]
# ///
"""Summarize a FIT activity using fitfast straight from PyPI.

No install needed — uv resolves the dependency block above on the fly:

    uv run --no-project examples/quickstart.py path/to/activity.fit
"""

import sys

import numpy as np

import fitfast


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: uv run --no-project examples/quickstart.py <activity.fit>")
    path = sys.argv[1]

    n_messages, n_fields = fitfast.count(path)
    print(f"{path}\n  {n_messages:,} messages / {n_fields:,} fields (fitfast {fitfast.__version__})")

    counts = fitfast.message_counts(path)
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    print("  top kinds:", ", ".join(f"{k} ×{v}" for k, v in top))

    session = fitfast.parse(path).get("session")
    if session:
        s = session[0]
        km = s.get("total_distance", 0) / 1000
        print(f"  sport: {s.get('sport', '?')} / {s.get('sub_sport', '?')} | distance: {km:.2f} km")

    cols = fitfast.records(path)
    if cols:
        ts = cols["timestamp"]
        hours = (np.nanmax(ts) - np.nanmin(ts)) / 3600
        line = f"  records: {len(ts):,} over {hours:.1f} h"
        if "heart_rate" in cols:
            line += f" | avg HR {np.nanmean(cols['heart_rate']):.0f} bpm"
        alt = cols.get("enhanced_altitude", cols.get("altitude"))
        if alt is not None:
            gain = np.nansum(np.clip(np.diff(alt[~np.isnan(alt)]), 0, None))
            line += f" | elevation gain {gain:.0f} m"
        print(line)


if __name__ == "__main__":
    main()
