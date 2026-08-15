#!/usr/bin/env python3
"""Cross-harness efficiency benchmark: opencode vs upstream-reasonix vs fork-reasonix.

Two modes:
  default : one fixed graph-generation task (see TASK below)
  --dataset : ordered 6-task dataset under /tmp/eff-test/dataset/tasks, each task
              with a prompt.txt and a verify.py pass check

Runs the identical prompt per harness in a clean task workspace, then collects
token/cache/cost/step data:
  - reasonix (upstream ece9b77, fork): `run -metrics` JSON
  - opencode: usage extracted from its session DB (session.updated.1 events)

Usage:
  DEEPSEEK_API_KEY=... python3 runner.py [--reps N] [--dataset] [--only HARNESS]
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = Path("/tmp/eff-test/dataset/tasks")  # override with --dir

TASK = (
    "Write a Python program that generates a graph: read data.csv "
    "(Month,revenue,costs,profit), draw a grouped bar chart (revenue vs costs) "
    "with a profit line, using ONLY the Python standard library (no matplotlib, "
    "no pandas). Save it as chart.svg with axes, labels, legend, and title. "
    "Run the program and verify chart.svg exists."
)

OPCODE_DB = Path.home() / ".local/share/opencode/opencode.db"
BASELINE_XDG = "/tmp/opencode/baseline-cfg"  # empty config dir: unoptimized reasonix


def harness_cmds():
    return {
        "upstream-reasonix": {
            "cmd": ["/tmp/reasonix-upstream", "run"],
            # no user config.toml: pure built-in defaults (thinking on, all tools)
            "env": {"XDG_CONFIG_HOME": BASELINE_XDG},
        },
        "fork-reasonix": {
            "cmd": ["/tmp/reasonix-bin", "run"],
            "env": {},  # optimized: economy prompt, thinking off, lean tools, caps
        },
        "hermes-agent": {
            "cmd": ["hermes", "-z"],  # args appended by run_hermes
            "env": {},  # DEEPSEEK_API_KEY inherited from environment
        },
    }


def run_reasonix(cfg, metrics_path, task, workspace):
    full = cfg["cmd"] + ["-dir", workspace, "-metrics", str(metrics_path), task]
    start = time.monotonic()
    env = dict(os.environ, **cfg["env"])
    proc = subprocess.run(full, cwd=workspace, capture_output=True, text=True,
                          timeout=1800, env=env)
    wall = time.monotonic() - start
    m = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    return proc.returncode, wall, m


def opencode_usage(start_rowid):
    con = sqlite3.connect(f"file:{OPCODE_DB}?mode=ro", uri=True)
    cur = con.cursor()
    sessions = [r[0] for r in cur.execute(
        "SELECT DISTINCT aggregate_id FROM event WHERE rowid > ? AND type='session.created.1'",
        (start_rowid,))]
    tot = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
           "cost": 0.0, "steps": 0, "compactions": 0}
    for sid in sessions:
        row = cur.execute(
            "SELECT data FROM event WHERE aggregate_id=? AND type='session.updated.1' ORDER BY seq DESC LIMIT 1",
            (sid,)).fetchone()
        if row:
            info = json.loads(row[0]).get("info", {})
            t = info.get("tokens") or {}
            tot["input"] += t.get("input", 0)
            tot["output"] += t.get("output", 0)
            tot["cache_read"] += (t.get("cache") or {}).get("read", 0)
            tot["cache_write"] += (t.get("cache") or {}).get("write", 0)
            tot["cost"] += info.get("cost", 0.0)
        n = cur.execute(
            "SELECT count(*) FROM event WHERE aggregate_id=? AND type='message.part.updated.1'",
            (sid,)).fetchone()[0]
        tot["steps"] += n
    con.close()
    return tot


def run_opencode(start_rowid, task, workspace):
    start = time.monotonic()
    proc = subprocess.run(["opencode", "run", "--pure", task], cwd=workspace,
                          capture_output=True, text=True, timeout=1800,
                          env=dict(os.environ, OPENCODE_CONFIG="/dev/null"))
    wall = time.monotonic() - start
    return proc.returncode, wall, opencode_usage(start_rowid)


def run_hermes(cfg, task, workspace):
    mp = Path("/tmp/eff-hermes-usage.json")
    mp.unlink(missing_ok=True)
    full = cfg["cmd"] + [task, "--provider", "deepseek", "-m", "deepseek-v4-flash",
                         "--ignore-user-config", "--usage-file", str(mp)]
    start = time.monotonic()
    proc = subprocess.run(full, cwd=workspace, capture_output=True, text=True,
                          timeout=1800, env=dict(os.environ, **cfg["env"]))
    wall = time.monotonic() - start
    if mp.exists():
        u = json.loads(mp.read_text())
        m = {"prompt_tokens": u.get("input_tokens") or 0,
             "completion_tokens": u.get("output_tokens") or 0,
             "cache_hit_tokens": u.get("cache_read_tokens") or 0,
             "cache_miss_tokens": u.get("cache_write_tokens") or 0,
             "steps": u.get("api_calls") or 0,
             "cost": u.get("estimated_cost_usd") or 0.0,
             "currency": "USD"}
        mp.unlink(missing_ok=True)
    else:
        m = {}
    return proc.returncode, wall, m


def run_prime(cfg, task, workspace):
    start = time.monotonic()
    proc = subprocess.run(cfg["cmd"] + ["--cwd", workspace, task], cwd=workspace,
                          capture_output=True, text=True, timeout=1800,
                          env=dict(os.environ, **cfg["env"]))
    wall = time.monotonic() - start
    m = {"prompt_tokens": 0, "completion_tokens": 0, "cache_hit_tokens": 0,
         "cache_miss_tokens": 0, "steps": 0, "cost": 0.0, "currency": "USD"}
    # last message_end event carries final cumulative usage
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "message_end":
            u = (ev.get("message") or {}).get("usage") or {}
            m["prompt_tokens"] = u.get("input", m["prompt_tokens"])
            m["completion_tokens"] = u.get("output", m["completion_tokens"])
            m["cache_hit_tokens"] = u.get("cacheRead", m["cache_hit_tokens"])
            m["cache_miss_tokens"] = u.get("cacheWrite", m["cache_miss_tokens"])
            m["steps"] += 1
            c = u.get("cost") or {}
            m["cost"] = c.get("total", m["cost"])
    return proc.returncode, wall, m


def verify(task_dir):
    try:
        v = subprocess.run(["python3", "verify.py"], cwd=task_dir,
                           capture_output=True, text=True, timeout=120)
        return v.returncode == 0
    except Exception:
        return False


# Files models may create; removed so each run starts from the clean seed state.
ARTIFACTS = {"hello.py", "sorted.txt", "stats.py", "chart.svg", "__pycache__", ".codegraph"}


def fresh_workspace(task_dir, rep):
    """Scratch copy of a task dir per run: no stale artifacts, no cross-run bleed."""
    run_dir = Path(f"/tmp/eff-run/{task_dir.name}-{rep}")
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(task_dir, run_dir, ignore=shutil.ignore_patterns(*ARTIFACTS))
    return str(run_dir)


def row(harness, task, rep, ok, wall, m):
    return {
        "harness": harness, "task": task, "rep": rep, "ok": ok,
        "wall_s": round(wall, 2),
        "prompt_tokens": m.get("prompt_tokens", m.get("input", 0)),
        "completion_tokens": m.get("completion_tokens", m.get("output", 0)),
        "cache_hit_tokens": m.get("cache_hit_tokens", m.get("cache_read", 0)),
        "cache_miss_tokens": m.get("cache_miss_tokens", m.get("cache_write", 0)),
        "steps": m.get("steps", 0),
        "cost": m.get("cost", 0.0), "currency": m.get("currency", "USD"),
        "compactions": m.get("compactions", 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--only", choices=["opencode-baseline", "upstream-reasonix",
                                       "fork-reasonix", "hermes-agent", "prime-agent"])
    ap.add_argument("--dataset", action="store_true")
    ap.add_argument("--dir", help="dataset dir with task subdirs (default /tmp/eff-test/dataset/tasks)")
    ap.add_argument("--task", help="single dataset task dir name (e.g. 03-csvstats)")
    args = ap.parse_args()
    global DATASET_DIR
    if args.dir:
        DATASET_DIR = Path(args.dir)

    if args.only != "opencode-baseline" and not os.environ.get("DEEPSEEK_API_KEY"):
        print("WARN: DEEPSEEK_API_KEY not set; reasonix runs will fail", file=sys.stderr)

    tasks = [("graphgen", TASK)]
    workspaces = {"graphgen": "/tmp/eff-test/graphgen"}
    if args.dataset:
        dirs = sorted(p for p in DATASET_DIR.iterdir() if p.is_dir())
        if args.task:
            dirs = [d for d in dirs if d.name == args.task]
        tasks = [(d.name, (d / "prompt.txt").read_text().strip()) for d in dirs]
        workspaces.update({d.name: str(d) for d in dirs})

    outdir = REPO / "benchmarks/efficiency/results"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (f"efficiency-{DATASET_DIR.parent.name}.jsonl" if DATASET_DIR.parent.name.startswith("dataset") else
                    ("efficiency-dataset.jsonl" if args.dataset else "efficiency-results.jsonl"))

    with open(out, "w") as f:
        for harness, hcfg in harness_cmds().items():
            if args.only and args.only != harness:
                continue
            for tname, task in tasks:
                for rep in range(1, args.reps + 1):
                    ws = fresh_workspace(Path(workspaces[tname]), rep) if args.dataset else workspaces[tname]
                    if harness == "opencode-baseline":
                        rid = next(sqlite3.connect(f"file:{OPCODE_DB}?mode=ro", uri=True).execute(
                            "SELECT COALESCE(MAX(rowid),0) FROM event"))[0]
                        rc, wall, m = run_opencode(rid, task, ws)
                    elif harness == "hermes-agent":
                        rc, wall, m = run_hermes(hcfg, task, ws)
                    elif harness == "prime-agent":
                        rc, wall, m = run_prime(hcfg, task, ws)
                    else:
                        mp = Path(f"/tmp/eff-metrics-{harness}-{rep}.json")
                        rc, wall, m = run_reasonix(hcfg, mp, task, ws)
                        mp.unlink(missing_ok=True)
                    passed = verify(Path(ws)) if "verify.py" in os.listdir(ws) else rc == 0
                    r = row(harness, tname, rep, rc == 0 and passed, wall, m)
                    f.write(json.dumps(r) + "\n")
                    f.flush()
                    print(f"  {harness:<20} {tname:<14} rep {rep}: pass={r['ok']} "
                          f"wall={r['wall_s']}s prompt={r['prompt_tokens']} out={r['completion_tokens']} "
                          f"hit={r['cache_hit_tokens']} miss={r['cache_miss_tokens']} "
                          f"steps={r['steps']} cost=${r['cost']:.4f}")

    rows = [json.loads(l) for l in out.read_text().splitlines()]
    print(f"\n=== summary ===")
    print(f"{'harness':<20}{'pass':>6}{'wall_s':>8}{'prompt':>10}{'out':>10}{'hit':>9}{'miss':>9}{'steps':>6}{'cost$':>9}")
    for h in set(r["harness"] for r in rows):
        rs = [r for r in rows if r["harness"] == h]
        n = len(rs)
        g = lambda k: round(sum(r[k] for r in rs) / n, 1)
        print(f"{h:<20}{sum(r['ok'] for r in rs):>3}/{n:<3}{g('wall_s'):>8}{g('prompt_tokens'):>10}"
              f"{g('completion_tokens'):>10}{g('cache_hit_tokens'):>9}{g('cache_miss_tokens'):>9}"
              f"{g('steps'):>6}{sum(r['cost'] for r in rs) / n:>9.4f}")
    print(f"\nraw data: {out}")


if __name__ == "__main__":
    main()