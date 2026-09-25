#!/usr/bin/env python3
"""Write several chapters at once, each in its own git worktree, and commit each one as it finishes.

    python3 scripts/run_batch.py s01e02 s01e03 s01e04
    python3 scripts/run_batch.py s01e02-s01e10 --jobs 5
    python3 scripts/run_batch.py s01e02-s01e10 --dry-run      # list the chapters and stop

Options: --model (default deepseek/deepseek-v4.1-flash), --effort, --jobs (chapters at a time,
default 5), --timeout (minutes per chapter, default 45), --trailer (added to each commit message),
--dry-run.

For each chapter: `git worktree add` a copy of the current commit under .batch/, run
generate_chapter.py there, copy chapters/<id>/ back, then (one chapter at a time) rebuild the lexicon
and continuity log (update_logs.py) and commit `<id>: <title>`. A chapter that didn't build is not
committed: its folder goes to .batch/failed/<id>/ for review. Logs are in .batch/<id>.log and a summary
table in .batch/summary.tsv. Nothing is pushed.

Continuity: each chapter's brief includes the continuity entries committed before it *starts*. With
--jobs 1 every chapter sees all earlier ones; with more jobs, chapters running at the same time don't
see each other's entries (their plans and bible/timeline.md still apply).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / ".batch"
GIT_LOCK = threading.Lock()


def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def all_ids():
    ids = []
    for p in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        ids += [ch["id"] for ch in json.loads(p.read_text(encoding="utf-8"))["chapters"]]
    return ids


def expand(specs):
    ids, out = all_ids(), []
    for spec in specs:
        if "-" in spec:
            a, b = spec.split("-", 1)
            if a not in ids or b not in ids:
                raise SystemExit(f"unknown chapter in range {spec}")
            out += ids[ids.index(a):ids.index(b) + 1]
        elif spec in ids:
            out.append(spec)
        else:
            raise SystemExit(f"unknown chapter {spec}")
    return list(dict.fromkeys(out))


def stats(log, report):
    """Pull cost, tokens, calls, words and dialogue share out of the run log and the build report."""
    s = {}
    m = re.search(r"done · (\d+) calls · (\d+) output tokens · (?:estimated )?cost \$([\d.]+)", log)
    if m:
        s.update(calls=int(m.group(1)), tokens=int(m.group(2)), cost=float(m.group(3)))
    m = re.search(r"(\d+) words · \d+ segments · [\d.]+ words/segment · dialogue (\d+)%", report)
    if m:
        s.update(words=int(m.group(1)), dialogue=int(m.group(2)))
    s["warnings"] = report.count("warning ")
    s["unresolved"] = len(re.findall(r"^- ", report.split("Unresolved after the fix round:")[-1], re.M)) \
        if "Unresolved after the fix round:" in report else 0
    return s


def run_one(cid, args):
    wt = BATCH / f"wt-{cid}"
    log_path = BATCH / f"{cid}.log"
    with GIT_LOCK:
        if wt.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, capture_output=True)
        git("worktree", "add", "--detach", str(wt), "HEAD")
    print(f"[{time.strftime('%H:%M:%S')}] {cid}: started", flush=True)
    start = time.time()
    cmd = [sys.executable, "scripts/generate_chapter.py", cid, "--model", args.model,
           "--effort", args.effort, "--force"]
    try:
        res = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=args.timeout * 60)
        log = res.stdout + res.stderr
    except subprocess.TimeoutExpired as e:
        log = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        log += f"\nTIMEOUT after {args.timeout} min"
    minutes = (time.time() - start) / 60
    log_path.write_text(log, encoding="utf-8")

    src = wt / "chapters" / cid
    report_path = src / "work" / "report.txt"
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    built = bool(report) and "nothing written" not in report and (src / "chapter.json").exists()
    row = {"id": cid, "built": built, "minutes": round(minutes, 1), **stats(log, report)}

    with GIT_LOCK:
        if built:
            dest = ROOT / "chapters" / cid
            shutil.copytree(src, dest, dirs_exist_ok=True)
            subprocess.run([sys.executable, "scripts/update_logs.py"], cwd=ROOT, check=True, capture_output=True)
            title = json.loads((dest / "chapter.json").read_text(encoding="utf-8"))["title"]["it"]
            git("add", f"chapters/{cid}", "curriculum/lexicon.csv", "bible/continuity-log.md")
            git("commit", "-q", "-m", f"{cid}: {title}\n\nWritten by {args.model} via run_batch.py; "
                f"{row.get('words', '?')} words, dialogue {row.get('dialogue', '?')}%, "
                f"cost ${row.get('cost', 0):.3f}." + (f"\n\n{args.trailer}" if args.trailer else ""))
        else:
            failed = BATCH / "failed" / cid
            if src.exists():
                shutil.copytree(src, failed, dirs_exist_ok=True)
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, capture_output=True)
    status = "committed" if built else f"NOT BUILT (see .batch/failed/{cid}/ and .batch/{cid}.log)"
    print(f"[{time.strftime('%H:%M:%S')}] {cid}: {status} · {row['minutes']} min · "
          f"${row.get('cost', 0):.3f} · {row.get('words', '?')} words", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chapters", nargs="+", help="chapter ids or ranges like s01e02-s01e10")
    ap.add_argument("--model", default="deepseek/deepseek-v4.1-flash")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=45, help="minutes per chapter")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--trailer", default="", help="text added at the end of each commit message")
    args = ap.parse_args()

    ids = expand(args.chapters)
    print(f"{len(ids)} chapter(s): {' '.join(ids)}\nmodel {args.model} · {args.jobs} at a time")
    if args.dry_run:
        return
    if git("status", "--porcelain", "--", "chapters", "curriculum", "bible", "scripts", "prompts").strip():
        raise SystemExit("Commit or discard changes in chapters/, curriculum/, bible/, scripts/ and prompts/ "
                         "first: the worktrees are made from the current commit.")
    BATCH.mkdir(exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(lambda c: run_one(c, args), ids))
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT)

    cols = ["id", "built", "minutes", "cost", "tokens", "calls", "words", "dialogue", "warnings", "unresolved"]
    lines = ["\t".join(cols)] + ["\t".join(str(r.get(c, "")) for c in cols) for r in rows]
    (BATCH / "summary.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    ok = [r for r in rows if r["built"]]
    print(f"\n{len(ok)}/{len(rows)} built · total ${sum(r.get('cost', 0) for r in rows):.3f} · "
          f"{(time.time() - t0) / 60:.0f} min wall time")


if __name__ == "__main__":
    main()
