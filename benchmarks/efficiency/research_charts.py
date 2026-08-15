#!/usr/bin/env python3
"""Researcher-style chart pack from a results jsonl.

Modes (one SVG each, Swiss styling, red accent):
  scatter : accuracy-cost frontier (log cost, pass-rate y)
  tokens  : stacked prompt(cache-hit)/miss/output per harness
  steps   : steps-per-task bars
  heatmap : task x harness pass/fail matrix
  radar   : normalized multi-axis profile per harness

Usage: python3 research_charts.py efficiency-tricky25.jsonl [--all]
Writes results/research-<mode>-<src>.svg
"""

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
RED = "#d7261e"
BLACK = "#17181a"
GREY = "#8a8a8a"
GREEN = "#1a7f37"
LIGHT = "#ececec"
FONT = "'Adwaita Sans', sans-serif"
HARNESS_COLORS = {"fork-reasonix": RED, "upstream-reasonix": "#333333",
                  "claude-agent": "#1f6feb", "opencode-v4": "#9a9a9a"}
ORDER = ["fork-reasonix", "upstream-reasonix", "claude-agent", "opencode-v4"]
SHORT = {"fork-reasonix": "FORK", "upstream-reasonix": "UPSTREAM",
         "claude-agent": "CLAUDE", "opencode-v4": "OPENCODE"}


def load(src):
    rows = [json.loads(l) for l in src.read_text().splitlines()]
    agg = {}
    for h in ORDER:
        rs = [r for r in rows if r["harness"] == h]
        if not rs:
            continue
        n = len(rs)
        agg[h] = {
            "pass": sum(r["ok"] for r in rs), "n": n,
            "acc": sum(r["ok"] for r in rs) / n,
            "cost": sum(r["cost"] for r in rs) / n,
            "wall": sum(r["wall_s"] for r in rs) / n,
            "steps": sum(r["steps"] for r in rs) / n,
            "out": sum(r["completion_tokens"] for r in rs) / n,
            "hit": sum(r["cache_hit_tokens"] for r in rs) / n,
            "miss": sum(r["cache_miss_tokens"] for r in rs) / n,
        }
    return rows, agg


def header(svg, title, sub):
    svg.append(f'<text x="56" y="52" font-family="{FONT}" font-size="10" letter-spacing="3" fill="{GREY}">EFFICIENCY EVALUATION / RESEARCH VIEW</text>')
    svg.append(f'<rect x="56" y="60" width="48" height="3" fill="{RED}"/>')
    svg.append(f'<text x="56" y="92" font-family="{FONT}" font-size="22" font-weight="700" fill="{BLACK}">{title}</text>')
    svg.append(f'<text x="56" y="112" font-family="{FONT}" font-size="11" fill="{GREY}">{sub}</text>')


def legend(svg, x, y, hs):
    for i, h in enumerate(hs):
        c = HARNESS_COLORS[h]
        svg.append(f'<line x1="{x}" y1="{y}" x2="{x + 22}" y2="{y}" stroke="{c}" stroke-width="3"/>')
        svg.append(f'<text x="{x + 28}" y="{y + 4}" font-family="{FONT}" font-size="10" fill="{BLACK}">{SHORT[h]} — {h}</text>')
        x += 28 + len(h) * 6.2 + 30


def scatter(svg, rows, agg, src_name):
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="620" viewBox="0 0 900 620" style="background:#ffffff">')
    header(svg, "Accuracy–cost frontier", "Pass rate vs cost per task (log scale). Up-left = best. " + src_name)
    xs = [60, 840]
    ys = [150, 500]
    # log cost range
    costs = [agg[h]["cost"] for h in agg]
    lo, hi = min(costs) / 1.5, max(costs) * 1.5
    def X(c): return xs[0] + (xs[1] - xs[0]) * (math.log(c) - math.log(lo)) / (math.log(hi) - math.log(lo))
    def Y(a): return ys[1] - (ys[1] - ys[0]) * a
    for i in range(5):
        y = ys[0] + (ys[1] - ys[0]) * i / 4
        svg.append(f'<line x1="{xs[0]}" y1="{y:.1f}" x2="{xs[1]}" y2="{y:.1f}" stroke="{LIGHT}" stroke-width="1"/>')
    for f in (0.25, 0.5, 1.0):
        svg.append(f'<line x1="{X(lo * f * 4):.1f}" y1="{ys[0]}" x2="{X(lo * f * 4):.1f}" y2="{ys[1]}" stroke="{LIGHT}" stroke-width="1"/>')
    svg.append(f'<line x1="{xs[0]}" y1="{ys[1]}" x2="{xs[1]}" y2="{ys[1]}" stroke="{BLACK}" stroke-width="1.4"/>')
    svg.append(f'<line x1="{xs[0]}" y1="{ys[0]}" x2="{xs[0]}" y2="{ys[1]}" stroke="{BLACK}" stroke-width="1.4"/>')
    for i, h in enumerate(agg):
        a = agg[h]
        cx, cy = X(a["cost"]), Y(a["acc"])
        r = 9 + a["out"] / max(agg[x]["out"] for x in agg) * 16
        svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.0f}" fill="{HARNESS_COLORS[h]}" opacity="0.85"/>')
        svg.append(f'<text x="{cx:.1f}" y="{cy - r - 8:.0f}" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="11" font-weight="700" fill="{HARNESS_COLORS[h]}">{SHORT[h]}</text>')
        svg.append(f'<text x="{cx:.1f}" y="{cy + r + 14:.0f}" text-anchor="middle" font-family="{FONT}" '
                   f'font-size="9" fill="{GREY}">{a["pass"]}/{a["n"]} · ${a["cost"]:.4f}</text>')
    svg.append(f'<text x="60" y="540" font-family="{FONT}" font-size="9" fill="{GREY}">COST PER TASK USD (LOG)</text>')
    svg.append(f'<text x="48" y="325" font-family="{FONT}" font-size="9" fill="{GREY}" transform="rotate(-90 48 325)">PASS RATE</text>')
    svg.append(f'<text x="60" y="575" font-family="{FONT}" font-size="9" fill="{GREY}">Bubble size = output tokens per task. claude-agent cost = its own meter; others = DeepSeek billing.</text>')
    svg.append('</svg>')


def tokens(svg, rows, agg, src_name):
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="620" viewBox="0 0 900 620" style="background:#ffffff">')
    header(svg, "Token discipline", "Average per task: cache-hit context, cache-miss context, output. " + src_name)
    x0, x1 = 120, 780
    y0, y1 = 170, 480
    hs = list(agg)
    bw = (x1 - x0) / len(hs) * 0.55
    maxv = max(agg[h]["hit"] + agg[h]["miss"] + agg[h]["out"] for h in hs)
    for i in range(5):
        y = y0 + (y1 - y0) * i / 4
        svg.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{LIGHT}" stroke-width="1"/>')
    for i, h in enumerate(hs):
        a = agg[h]
        cx = x0 + (x1 - x0) * (i + 0.5) / len(hs)
        hit_h = (y1 - y0) * a["hit"] / maxv
        miss_h = (y1 - y0) * a["miss"] / maxv
        out_h = (y1 - y0) * a["out"] / maxv
        y = y1
        svg.append(f'<rect x="{cx - bw / 2:.0f}" y="{y - hit_h:.1f}" width="{bw:.0f}" height="{hit_h:.1f}" fill="{HARNESS_COLORS[h]}" opacity="0.5"/>')
        svg.append(f'<rect x="{cx - bw / 2:.0f}" y="{y - hit_h - miss_h:.1f}" width="{bw:.0f}" height="{miss_h:.1f}" fill="#ffb3ae"/>')
        svg.append(f'<rect x="{cx - bw / 2:.0f}" y="{y - hit_h - miss_h - out_h:.1f}" width="{bw:.0f}" height="{out_h:.1f}" fill="{HARNESS_COLORS[h]}"/>')
        svg.append(f'<text x="{cx:.0f}" y="{y + 24}" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="700" fill="{BLACK}">{SHORT[h]}</text>')
        svg.append(f'<text x="{cx:.0f}" y="{y - hit_h - miss_h - out_h - 8:.0f}" text-anchor="middle" font-family="{FONT}" font-size="9" fill="{GREY}">{a["hit"] + a["miss"] + a["out"]:.0f}</text>')
    svg.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{BLACK}" stroke-width="1.4"/>')
    ly = 530
    for label, col in [("cache-hit context (cached prefix)", "#b0b0b0"),
                       ("cache-miss context (new bytes)", "#ffb3ae"),
                       ("output tokens", "#000000")]:
        svg.append(f'<rect x="120" y="{ly - 10}" width="18" height="10" fill="{col}"/>')
        svg.append(f'<text x="148" y="{ly}" font-family="{FONT}" font-size="10" fill="{BLACK}">{label}</text>')
        ly += 22
    svg.append(f'<text x="120" y="{ly + 4}" font-family="{FONT}" font-size="9" fill="{GREY}">Upstream re-sends ~161K tokens/task; fork stays at ~62K with 91% cache hits. claude/opencode report cache hits only.</text>')
    svg.append('</svg>')


def steps(svg, rows, agg, src_name):
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="620" viewBox="0 0 900 620" style="background:#ffffff">')
    header(svg, "Step efficiency", "Average agent steps per task. Fewer steps = less surface, fewer decisions. " + src_name)
    x0, x1 = 120, 780
    y0, y1 = 180, 480
    hs = list(agg)
    maxv = max(agg[h]["steps"] for h in hs)
    for i in range(5):
        y = y0 + (y1 - y0) * i / 4
        svg.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{LIGHT}" stroke-width="1"/>')
    for i, h in enumerate(hs):
        a = agg[h]
        cx = x0 + (x1 - x0) * (i + 0.5) / len(hs)
        hh = (y1 - y0) * a["steps"] / maxv
        col = HARNESS_COLORS[h]
        svg.append(f'<rect x="{cx - 30:.0f}" y="{y1 - hh:.1f}" width="60" height="{hh:.1f}" fill="{col}"/>')
        svg.append(f'<text x="{cx:.0f}" y="{y1 - hh - 10:.0f}" text-anchor="middle" font-family="{FONT}" font-size="13" font-weight="700" fill="{col}">{a["steps"]:.1f}</text>')
        svg.append(f'<text x="{cx:.0f}" y="{y1 + 24}" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{BLACK}">{SHORT[h]}</text>')
    svg.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{BLACK}" stroke-width="1.4"/>')
    svg.append(f'<text x="120" y="530" font-family="{FONT}" font-size="9" fill="{GREY}">opencode burns ~51 steps per task and still solves none. fork solves in 4.1 — 2x fewer than upstream, 12x fewer than opencode.</text>')
    svg.append('</svg>')


def heatmap(svg, rows, agg, src_name):
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640" viewBox="0 0 900 640" style="background:#ffffff">')
    header(svg, "Failure map", "Task x harness: green = solved, red = failed. Rows sorted by how many harnesses failed. " + src_name)
    hs = [h for h in ORDER if any(r["harness"] == h for r in rows)]
    tasks = sorted({r["task"] for r in rows}, key=lambda t: -sum(1 for r in rows if r["task"] == t and not r["ok"]))
    x0, x1 = 250, 830
    y0 = 150
    row_h = 16
    col_w = (x1 - x0) / len(hs)
    for i, t in enumerate(tasks):
        y = y0 + i * row_h
        svg.append(f'<text x="{x0 - 12}" y="{y + 11}" text-anchor="end" font-family="{FONT}" font-size="9" fill="{GREY}">{t}</text>')
        for j, h in enumerate(hs):
            r = next((r for r in rows if r["harness"] == h and r["task"] == t), None)
            ok = r["ok"] if r else None
            col = GREEN if ok else (RED if ok is False else LIGHT)
            svg.append(f'<rect x="{x0 + j * col_w:.1f}" y="{y}" width="{col_w - 4:.1f}" height="{row_h - 3}" fill="{col}"/>')
    for j, h in enumerate(hs):
        svg.append(f'<text x="{x0 + j * col_w + 6:.0f}" y="{y0 - 8}" font-family="{FONT}" font-size="9" font-weight="700" fill="{HARNESS_COLORS[h]}">{SHORT[h]}</text>')
    svg.append(f'<text x="250" y="{y0 + len(tasks) * row_h + 26}" font-family="{FONT}" font-size="9" fill="{GREY}">All harnesses fail 04-secret-scan (secret-key extraction). fork alone misses 06-budget-trip and 08-reconcile, which upstream solves with 10-11 steps.</text>')
    svg.append('</svg>')


def radar(svg, rows, agg, src_name):
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640" viewBox="0 0 900 640" style="background:#ffffff">')
    header(svg, "Normalized capability profile", "Each axis 0-1, best observed = 1.0. " + src_name)
    hs = list(agg)
    axes = [
        ("Accuracy", lambda a: a["acc"]),
        ("Cost eff.", lambda a: min(1.0, max(0.02, min(x["cost"] for x in agg)) / max(0.02, a["cost"]))),
        ("Speed", lambda a: min(1.0, max(x["wall"] for x in agg) / max(a["wall"], 0.1))),
        ("Step eff.", lambda a: min(1.0, max(x["steps"] for x in agg) / max(a["steps"], 0.1))),
        ("Output eff.", lambda a: min(1.0, max(x["out"] for x in agg) / max(a["out"], 1))),
        ("Cache disc.", lambda a: min(1.0, a["hit"] / max(a["hit"] + a["miss"], 1))),
    ]
    cx, cy = 450, 330
    R = 190
    n = len(axes)
    pts = [(cx + R * math.cos(-math.pi / 2 + 2 * math.pi * i / n),
            cy + R * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]
    for i, (x, y) in enumerate(pts):
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LIGHT}" stroke-width="1"/>')
        svg.append(f'<text x="{x + (12 if x >= cx else -12):.0f}" y="{y + 4:.0f}" text-anchor="middle" font-family="{FONT}" font-size="10" fill="{BLACK}">{axes[i][0]}</text>')
    for ring in (0.33, 0.66, 1.0):
        rr = R * ring
        poly = " ".join(f"{cx + rr * math.cos(-math.pi / 2 + 2 * math.pi * i / n):.1f},{cy + rr * math.sin(-math.pi / 2 + 2 * math.pi * i / n):.1f}" for i in range(n))
        svg.append(f'<polygon points="{poly}" fill="none" stroke="{LIGHT}" stroke-width="1"/>')
    for h in hs:
        a = agg[h]
        vals = [f(a) for _, f in axes]
        poly = " ".join(f"{cx + R * v * math.cos(-math.pi / 2 + 2 * math.pi * i / n):.1f},{cy + R * v * math.sin(-math.pi / 2 + 2 * math.pi * i / n):.1f}" for i, v in enumerate(vals))
        svg.append(f'<polygon points="{poly}" fill="{HARNESS_COLORS[h]}" opacity="0.18" stroke="{HARNESS_COLORS[h]}" stroke-width="2"/>')
        svg.append(f'<circle cx="{cx + R * vals[0] * math.cos(-math.pi / 2):.1f}" cy="{cy + R * vals[0] * math.sin(-math.pi / 2):.1f}" r="4" fill="{HARNESS_COLORS[h]}"/>')
    legend(svg, 60, 560, hs)
    svg.append('</svg>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="results jsonl filename in results/")
    ap.add_argument("--all", action="store_true", help="all five chart types")
    ap.add_argument("--type", choices=["scatter", "tokens", "steps", "heatmap", "radar"])
    a = ap.parse_args()
    src = REPO / "results" / a.src
    rows, agg = load(src)
    types = ["scatter", "tokens", "steps", "heatmap", "radar"] if a.all else [a.type or "scatter"]
    fn = {"scatter": scatter, "tokens": tokens, "steps": steps, "heatmap": heatmap, "radar": radar}
    for t in types:
        out = REPO / "results" / f"research-{t}-{Path(a.src).stem}.svg"
        svg = []
        fn[t](svg, rows, agg, a.src)
        out.write_text("\n".join(svg))
        print("wrote", out)


if __name__ == "__main__":
    main()
