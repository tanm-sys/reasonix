#!/usr/bin/env python3
import csv
from xml.sax.saxutils import escape


def round2(x):
    return round(x + 1e-9, 2)


with open("data.csv", newline="") as f:
    rows = list(csv.DictReader(f))
months = [r["Month"] for r in rows]
revenue = [int(r["revenue"]) for r in rows]
costs = [int(r["costs"]) for r in rows]
profit = [int(r["profit"]) for r in rows]

W, H = 900, 500
ML, MR, MT, MB = 70, 20, 40, 60
cw = (W - ML - MR) / len(months)
bar_w = cw * 0.36
gap = cw * 0.08
max_y = max(max(revenue), max(costs), max(profit)) * 1.1


def y(v):
    return H - MB - v / max_y * (H - MT - MB)


def x(i):
    return ML + cw * i + cw / 2


parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">']
parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="white"/>')
parts.append(f'<text x="{W/2}" y="22" font-size="18" font-weight="bold" '
             f'text-anchor="middle">Monthly Revenue vs Costs and Profit</text>')

for gv in range(0, int(max_y) + 1, 50):
    py = y(gv)
    parts.append(f'<line x1="{ML}" y1="{py}" x2="{W-MR}" y2="{py}" '
                 f'stroke="#ddd" stroke-width="1"/>')
    parts.append(f'<text x="{ML-8}" y="{py+4}" font-size="11" '
                 f'text-anchor="end" fill="#444">{gv}</text>')

for i, m in enumerate(months):
    bxc = ML + cw * i
    parts.append(f'<rect x="{round2(bxc+cw*0.5-bar_w-gap/2)}" y="{round2(y(revenue[i]))}" '
                 f'width="{round2(bar_w)}" height="{round2(H-MB-y(revenue[i]))}" fill="#4c78a8"/>')
    parts.append(f'<rect x="{round2(bxc+cw*0.5+gap/2)}" y="{round2(y(costs[i]))}" '
                 f'width="{round2(bar_w)}" height="{round2(H-MB-y(costs[i]))}" fill="#f58518"/>')
    parts.append(f'<text x="{round2(x(i))}" y="{H-MB+16}" font-size="11" '
                 f'text-anchor="middle">{escape(m)}</text>')

pts = " ".join(f"{round2(x(i))},{round2(y(profit[i]))}" for i in range(len(months)))
parts.append(f'<polyline points="{pts}" fill="none" stroke="#72b754" stroke-width="3"/>')
for i, p in enumerate(profit):
    parts.append(f'<circle cx="{round2(x(i))}" cy="{round2(y(p))}" r="3.5" fill="#72b754"/>')

ly, lx0 = y(max_y) + 6, ML + 10
for (label, color) in (("Revenue", "#4c78a8"), ("Costs", "#f58518"), ("Profit", "#72b754")):
    parts.append(f'<rect x="{lx0}" y="{ly}" width="14" height="14" fill="{color}"/>')
    parts.append(f'<text x="{lx0+20}" y="{ly+12}" font-size="12">{label}</text>')
    ly += 20

parts.append('<text x="20" y="' + str(H - MB + 28) + '" font-size="12" '
             'text-anchor="middle" transform="rotate(-90 20 ' + str(H - MB + 28) + ')">Amount ($)</text>')

parts.append("</svg>")

with open("chart.svg", "w") as f:
    f.write("\n".join(parts))
print("wrote chart.svg")