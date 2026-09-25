#!/usr/bin/env python3
"""Rebuild the master lexicon and the continuity log's episode entries from the finished chapters.

    python3 scripts/update_logs.py

Both are derived, in chapter order, from what is in `chapters/`:
- `curriculum/lexicon.csv`: one row per vocabulary item, from each chapter's `@vocab` block (draft.txt).
  `introduced` is the first chapter that teaches it; `recycled` lists the later chapters whose story
  uses one of its forms.
- `bible/continuity-log.md`, section "## Episodes": each chapter's `continuity.md`, which the pipeline
  writes as its last step.

Rebuilding (rather than appending) keeps the files right when chapters are made out of order, in
parallel batches, or re-run. Run it after any chapter is added or changed; the pipeline and
run_batch.py do.
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_draft as cd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEXICON = ROOT / "curriculum" / "lexicon.csv"
LOG = ROOT / "bible" / "continuity-log.md"
FIELDS = ["lemma", "pos", "gender", "en", "level", "introduced", "recycled", "forms"]
EPISODES = "## Episodes"


def finished_chapters():
    """Chapter ids with a built chapter.json and a draft, in order."""
    return sorted(p.parent.name for p in (ROOT / "chapters").glob("*/chapter.json")
                  if (p.parent / "draft.txt").exists())


def item_forms(v):
    forms = {cd.norm(v["lemma"])} | {cd.norm(f) for f in v["forms"]}
    for a in cd.ARTICLES:
        if cd.norm(v["lemma"]).startswith(a):
            forms.add(cd.norm(v["lemma"])[len(a):])
    return sorted(f for f in forms if f)


def story_text(cid):
    data = json.loads((ROOT / "chapters" / cid / "chapter.json").read_text(encoding="utf-8"))
    segs = [s["it"] for _, _, s in cd.bc.segments(data)]
    return " " + cd.norm(" ".join(segs)).replace("'", "' ") + " "


def uses(text, form):
    return re.search(r"(?<![\w])" + re.escape(form.replace("'", "' ")) + r"(?![\w])", text) is not None


def build_lexicon(chapters):
    rows = {}
    for cid in chapters:
        level = json.loads((ROOT / "chapters" / cid / "chapter.json").read_text(encoding="utf-8"))["level"]
        vocab, _, _, _ = cd.parse((ROOT / "chapters" / cid / "draft.txt").read_text(encoding="utf-8"), [])
        for v in vocab:
            key = cd.norm(v["lemma"])
            if key not in rows:
                rows[key] = {"lemma": v["lemma"], "pos": v["pos"], "gender": v["gender"], "en": v["en"],
                             "level": level, "introduced": cid, "recycled": [], "forms": item_forms(v)}
    texts = {cid: story_text(cid) for cid in chapters}
    for row in rows.values():
        row["recycled"] = [cid for cid in chapters
                           if cid > row["introduced"] and any(uses(texts[cid], f) for f in row["forms"])]
    ordered = sorted(rows.values(), key=lambda r: (r["introduced"], cd.norm(r["lemma"])))
    with LEXICON.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in ordered:
            w.writerow({**r, "recycled": " ".join(r["recycled"]), "forms": ", ".join(r["forms"])})
    return ordered


def build_log(chapters):
    entries = []
    for cid in chapters:
        path = ROOT / "chapters" / cid / "continuity.md"
        if path.exists():
            entries.append(path.read_text(encoding="utf-8").strip())
    text = LOG.read_text(encoding="utf-8")
    head = text.split(EPISODES, 1)[0].rstrip()
    body = "\n\n".join(entries) if entries else "*(none yet)*"
    LOG.write_text(f"{head}\n\n{EPISODES}\n\n{body}\n", encoding="utf-8")
    return len(entries)


def main():
    chapters = finished_chapters()
    rows = build_lexicon(chapters)
    n = build_log(chapters)
    print(f"lexicon: {len(rows)} items from {len(chapters)} chapter(s) · continuity log: {n} entr{'y' if n == 1 else 'ies'}")


if __name__ == "__main__":
    main()
