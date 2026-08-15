#!/usr/bin/env python3
"""Swiss-style efficiency chart from results/efficiency-dataset.jsonl.

Pure-stdlib SVG: strict grid, Helvetica metrics, one red accent, no chartjunk.
  default : bar panels (means per harness)
  --lines : multi-series line chart, one series per harness across tasks

Usage:
  python3 swiss_chart.py [results/efficiency-*.jsonl] [--lines]
Writes results/efficiency-chart-<src>.svg (or -lines-<src>.svg).
"""

import argparse
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent
SRC = REPO / "results/efficiency-dataset.jsonl"
OUT = REPO / "results/efficiency-chart.svg"

RED = "#ff0000"
BLACK = "#111111"
GREY = "#c9c9c9"
LIGHT = "#efefef"
FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"

ORDER = ["fork-reasonix", "upstream-reasonix", "opencode-baseline", "hermes-agent", "prime-agent"]


def mean(rows, key):
    return statistics.mean(r[key] for r in rows)


def header(svg, title, subtitle):
    svg.append(f'<text x="64" y="72" font-family="{FONT}" font-size="11" letter-spacing="3" fill="{BLACK}">{title}</text>')
    svg.append(f'<text x="64" y="96" font-family="{FONT}" font-size="30" font-weight="700" fill="{BLACK}">{subtitle}</text>')
    svg.append(f'<rect x="64" y="112" width="56" height="4" fill="{RED}"/>')


def grid_lines(svg, top, bottom, steps, left=64, right=1136):
    for i in range(steps + 1):
        y = top + (bottom - top) * i / steps
        colour = GREY if i else BLACK
        weight = 1 if i else 1.6
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{colour}" stroke-width="{weight}"/>')
    for i in range(1, steps):
        y = top + (bottom - top) * i / steps
        svg.append(f'<text x="{right + 10}" y="{y + 3}" font-family="{FONT}" font-size="9" fill="{GREY}">{i}</text>')


def bars(svg, x, top, bottom, values, labels, unit, fmt, red_index, max_v, step_labels):
    steps = len(values)
    bar_w = 56
    gap = 116
    btop = top + 34
    bspan = bottom - btop
    grid_lines(svg, btop, bottom, 4, left=x + 24, right=x + 24 + bar_w * steps + gap * (steps - 1) + 40)
    for i, v in enumerate(values):
        h = bspan * (v / max_v if max_v else 0)
        bx = x + 24 + i * (bar_w + gap)
        colour = RED if i == red_index else BLACK
        svg.append(f'<rect x="{bx}" y="{bottom - h:.1f}" width="{bar_w}" height="{h:.1f}" fill="{colour}"/>')
        svg.append(f'<text x="{bx + bar_w / 2:.0f}" y="{bottom - h - 10:.1f}" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="20" font-weight="700" fill="{colour}">{fmt(v)}</text>')
        svg.append(f'<text x="{bx + bar_w / 2:.0f}" y="{bottom + 22}" text-anchor="middle" '
                   f'font-family="{FONT}" font-size="10" fill="{BLACK}">{labels[i]}</text>')
    for i, l in enumerate(step_labels):
        y = btop + bspan * i / 4
        svg.append(f'<text x="{x + 12}" y="{y + 3}" text-anchor="end" font-family="{FONT}" font-size="9" fill="{GREY}">{l}</text>')


def line_panel(svg, x0, y0, x1, y1, series, labels, fmt, title, ymax=None):
    """Multi-series line chart: x = task index, one polyline per harness."""
    svg.append(f'<text x="{x0}" y="{y0 - 24}" font-family="{FONT}" font-size="10" letter-spacing="2" fill="{GREY}">{title}</text>')
    svg.append(f'<line x1="{x0}" y1="{y0 - 16}" x2="{x0 + 200}" y2="{y0 - 16}" stroke="{GREY}" stroke-width="1"/>')
    n = len(labels)
    max_v = ymax or max(max((v for v in s if v is not None), default=0) for s in series) or 1
    pad = 30
    xs = [x0 + pad + (x1 - x0 - 2 * pad) * i / (n - 1) for i in range(n)]
    def Y(v):
        return y1 - (y1 - y0) * (v / max_v)
    for i in range(5):
        y = y0 + (y1 - y0) * i / 4
        c = GREY if i else BLACK
        svg.append(f'<line x1="{x0 + pad}" y1="{y:.1f}" x2="{x1 - pad}" y2="{y:.1f}" stroke="{c}" stroke-width="{1.6 if i == 0 else 1}"/>')
    for i, l in enumerate(labels):
        svg.append(f'<text x="{xs[i]:.1f}" y="{y1 + 18}" text-anchor="middle" font-family="{FONT}" font-size="9" fill="{BLACK}">{l}</text>')
    for si, s in enumerate(series):
        colour = RED if si == 0 else BLACK
        pts = " ".join(f"{xs[i]:.1f},{Y(v):.1f}" for i, v in enumerate(s) if v is not None)
        if pts:
            svg.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2"/>')
            if si == 0:
                for i, v in enumerate(s):
                    if v is not None:
                        svg.append(f'<circle cx="{xs[i]:.1f}" cy="{Y(v):.1f}" r="3" fill="{RED}"/>')
                        svg.append(f'<text x="{xs[i]:.1f}" y="{Y(v) - 8:.1f}" text-anchor="middle" font-family="{FONT}" font-size="8" fill="{RED}">{fmt(v)}</text>')


def build_lines(all_rows):
    tasks = sorted({r["task"] for r in all_rows})
    series = {h: {t: None for t in tasks} for h in ORDER}
    for r in all_rows:
        if r["harness"] in series and r["task"] in series[r["harness"]]:
            series[r["harness"]][r["task"]] = r
    labels = [t.split("-")[0] for t in tasks]
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="860" viewBox="0 0 1200 860" style="background:#ffffff">')
    svg.append(f'<rect width="1200" height="860" fill="#ffffff"/>')
    header(svg, "REASONIX / CROSS-HARNESS EFFICIENCY", "PER-TASK SERIES — 5 HARNESSES")
    panels = [
        ("COST PER TASK — USD", "cost", lambda v: f"${v:.4f}"),
        ("WALL TIME — SECONDS", "wall_s", lambda v: f"{v:.0f}s"),
        ("OUTPUT TOKENS PER TASK", "completion_tokens", lambda v: f"{v:.0f}"),
    ]
    ys = [(150, 330), (390, 570), (630, 810)]
    for (title, key, fmt), (y0, y1) in zip(panels, ys):
        s = []
        for h in ORDER:
            vals = []
            for t in tasks:
                r = series[h][t]
                vals.append(r[key] if r is not None else None)  # type: ignore[union-attr]
            s.append(vals)
        line_panel(svg, 64, y0, 1136, y1, s, labels, fmt, title)
    # legend
    lx = 64
    for i, h in enumerate(ORDER):
        c = RED if i == 0 else BLACK
        svg.append(f'<line x1="{lx}" y1="828" x2="{lx + 24}" y2="828" stroke="{c}" stroke-width="2"/>')
        svg.append(f'<text x="{lx + 30}" y="831" font-family="{FONT}" font-size="9" fill="{c}">{h}</text>')
        lx += 30 + 8 + len(h) * 5.6
    svg.append('</svg>')
    out = REPO / "results" / ("efficiency-lines-" + SRC.stem + ".svg")
    out.write_text("\n".join(svg))
    print(f"wrote {out}")


def build():
    all_rows = [json.loads(l) for l in SRC.read_text().splitlines()]
    data = {}
    for h in ORDER:
        data[h] = [r for r in all_rows if r["harness"] == h]
    present = [h for h in ORDER if data[h]]
    m = {h: {
        "pass": sum(r["ok"] for r in data[h]),
        "n": len(data[h]),
        "cost": mean(data[h], "cost"),
        "wall": mean(data[h], "wall_s"),
        "out": mean(data[h], "completion_tokens"),
    } for h in present}

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="860" viewBox="0 0 1200 860" '
               f'style="background:#ffffff">')
    svg.append(f'<rect width="1200" height="860" fill="#ffffff"/>')
    header(svg, "REASONIX / EFFICIENCY MEASUREMENT", "FORK 6/6 · UPSTREAM 5/6 · OPENCODE 2/6")

    # Panel titles across the four quadrants
    titles = [("PASS RATE", 64, 190), ("COST / TASK — USD", 64, 500),
              ("WALL TIME — SECONDS", 640, 190), ("OUTPUT TOKENS / TASK", 640, 500)]
    for t, x, y in titles:
        svg.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="10" letter-spacing="2" fill="{GREY}">{t}</text>')
        svg.append(f'<line x1="{x}" y1="{y + 8}" x2="{x + 200}" y2="{y + 8}" stroke="{GREY}" stroke-width="1"/>')

    labels = [h.upper() for h in present]

    # 1 — pass rate
    pass_v = [m[h]["pass"] for h in present]
    bars(svg, 64, 200, 430, pass_v, labels, "", lambda v: f"{v}/8", 0, 8, ["", "", "", "", "8"])

    # 2 — cost
    cost_v = [m[h]["cost"] for h in present]
    bars(svg, 64, 510, 730, cost_v, labels, "", lambda v: f"{v:.4f}", 0, max(cost_v), ["", "", "", "0.015"])

    # 3 — wall time
    wall_v = [m[h]["wall"] for h in present]
    bars(svg, 640, 200, 430, wall_v, labels, "s", lambda v: f"{v:.1f}", 0, 45, ["", "", "", "45.0"])

    # 4 — output tokens
    out_v = [m[h]["out"] for h in present]
    bars(svg, 640, 510, 730, out_v, labels, "", lambda v: f"{v:,.0f}", 0, 5000, ["", "", "", "5000"])

    # Footer
    svg.append(f'<line x1="64" y1="796" x2="1136" y2="796" stroke="{BLACK}" stroke-width="1.6"/>')
    svg.append(f'<text x="64" y="822" font-family="{FONT}" font-size="9" fill="{GREY}">DATASET: {m[present[0]]["n"]} TASKS · STD LIBRARY · DEEPSEEK V4 FLASH · METRICS: -metrics JSON / HERMES USAGE FILE</text>')
    svg.append(f'<text x="1136" y="822" text-anchor="end" font-family="{FONT}" font-size="9" fill="{RED}">RED = FORK</text>')
    svg.append('</svg>')

    OUT.write_text("\n".join(svg))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="results jsonl (default results/efficiency-dataset.jsonl)")
    ap.add_argument("--lines", action="store_true", help="multi-series line chart")
    a = ap.parse_args()
    if a.src:
        SRC = REPO / "results" / Path(a.src).name
        OUT = REPO / "results" / ("efficiency-chart-" + Path(a.src).stem + ".svg")
    if a.lines:
        all_rows = [json.loads(l) for l in SRC.read_text().splitlines()]
        build_lines(all_rows)
    else:
        build()