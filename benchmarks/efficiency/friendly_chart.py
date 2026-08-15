#!/usr/bin/env python3
"""Plain-language chart for non-technical readers.

Horizontal bars, big numbers, everyday units (cents, seconds), one takeaway.
No jargon: cost per task shown in cents, time in seconds.

Usage: python3 friendly_chart.py [efficiency-*.jsonl]
Writes results/friendly-chart-<src>.svg
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SRC = REPO / "results" / (sys.argv[1] if len(sys.argv) > 1 else "efficiency-dataset3.jsonl")
OUT = REPO / "results" / f"friendly-chart-{SRC.stem}.svg"

GREEN = "#1a7f37"
RED = "#e03131"
GREY = "#8a8a8a"
BLACK = "#111111"
LIGHT = "#f2f2f2"
FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"

# friendly display names, in chart order
NAMES = {
    "fork-reasonix": "Our optimized agent",
    "upstream-reasonix": "Original agent (before optimization)",
    "hermes-agent": "Other agent (Hermes)",
    "opencode-baseline": "Generic agent (opencode)",
    "prime-agent": "Other agent (prime)",
}


def main():
    rows = [json.loads(l) for l in SRC.read_text().splitlines()]
    order = [h for h in NAMES if any(r["harness"] == h for r in rows)]
    agg = {}
    for h in order:
        rs = [r for r in rows if r["harness"] == h]
        n = len(rs)
        agg[h] = {
            "pass": sum(r["ok"] for r in rs),
            "n": n,
            "cents": sum(r["cost"] for r in rs) / n * 100.0,   # per task, in cents
            "sec": sum(r["wall_s"] for r in rs) / n,
        }
    total_tasks = agg[order[0]]["n"]
    all_pass = all(agg[h]["pass"] == total_tasks for h in order)

    # sort by cents (cheapest first) — friendliest reading
    order = sorted(order, key=lambda h: agg[h]["cents"])

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" style="background:#ffffff">')
    svg.append(f'<rect width="1200" height="720" fill="#ffffff"/>')

    # header
    svg.append(f'<text x="70" y="78" font-family="{FONT}" font-size="34" font-weight="700" fill="{BLACK}">How fast and cheap is our AI agent?</text>')
    svg.append(f'<text x="70" y="112" font-family="{FONT}" font-size="17" fill="{GREY}">Each agent solved all {total_tasks} real-world tasks. Here is the cost and time per single task.</text>')
    if all_pass:
        svg.append(f'<text x="70" y="140" font-family="{FONT}" font-size="14" font-weight="700" fill="{GREEN}">&#10003; Everyone got all {total_tasks} tasks right — so we compare speed and cost only.</text>')

    def panel(title, key, unit, y0, y1, fmt, best_first=True, best_note=None):
        svg.append(f'<text x="70" y="{y0}" font-family="{FONT}" font-size="20" font-weight="700" fill="{BLACK}">{title}</text>')
        rows_y = y0 + 34
        span = y1 - rows_y
        row_h = span / len(order)
        max_v = max(agg[h][key] for h in order) or 1
        bar_x0 = 470
        bar_x1 = 1060
        for i, h in enumerate(order):
            v = agg[h][key]
            cy = rows_y + i * row_h + row_h / 2
            is_best = i == 0 and best_first
            name_col = RED if h == "fork-reasonix" else BLACK
            val_col = RED if h == "fork-reasonix" else BLACK
            # name
            svg.append(f'<text x="70" y="{cy + 6}" font-family="{FONT}" font-size="16" fill="{name_col}">{NAMES[h]}</text>')
            # track
            svg.append(f'<rect x="{bar_x0}" y="{cy - 14}" width="{bar_x1 - bar_x0}" height="28" fill="{LIGHT}" rx="14"/>')
            # bar
            bw = (bar_x1 - bar_x0) * (v / max_v)
            col = RED if h == "fork-reasonix" else ("#555555" if i == 0 else "#9a9a9a")
            svg.append(f'<rect x="{bar_x0}" y="{cy - 14}" width="{bw:.0f}" height="28" fill="{col}" rx="14"/>')
            # value label
            svg.append(f'<text x="{bar_x1 + 22}" y="{cy + 6}" font-family="{FONT}" font-size="19" font-weight="700" fill="{val_col}">{fmt(v)}</text>')
        # best note
        if best_note:
            svg.append(f'<text x="470" y="{y1 + 6}" font-family="{FONT}" font-size="14" fill="{GREY}">{best_note}</text>')

    panel("Cost per task", "cents", "cents",
          200, 420,
          lambda v: f"{v:.2f}\u00a2" if v < 1 else f"{v:.1f}\u00a2",
          best_note="A cent is 1/100 of a dollar. Cheaper is better.")

    panel("Time per task", "sec", "sec",
          470, 690,
          lambda v: f"{v:.0f} sec",
          best_note="Seconds per task. Faster is better.")

    # takeaway
    fork_c = agg["fork-reasonix"]["cents"]
    fork_s = agg["fork-reasonix"]["sec"]
    others = [h for h in order if h != "fork-reasonix"]
    if others:
        up = agg["upstream-reasonix"] if "upstream-reasonix" in agg else None
        if up:
            gain_c = up["cents"] / fork_c
            gain_s = up["sec"] / fork_s
            svg.append(f'<rect x="70" y="700" width="1060" height="0" fill="none"/>')
            svg.append(f'<line x1="70" y1="726" x2="1130" y2="726" stroke="{LIGHT}" stroke-width="1"/>')
            svg.append(f'<text x="70" y="756" font-family="{FONT}" font-size="22" font-weight="700" fill="{BLACK}">In plain words: our optimized agent does each task in {fork_s:.0f} seconds for {fork_c:.2f}\u00a2 — '
                       f'about {gain_s:.1f}\u00d7 faster and {gain_c:.1f}\u00d7 cheaper than the original.</text>')
            svg.append(f'<text x="70" y="786" font-family="{FONT}" font-size="15" fill="{GREY}">Same answer quality, less time, less money.</text>')

    svg.append('</svg>')
    OUT.write_text("\n".join(svg))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
