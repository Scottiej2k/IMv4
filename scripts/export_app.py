#!/usr/bin/env python3
"""Package the finished chapters for the learner app (the prototype in app/, later the Replit app).

    python3 scripts/export_app.py

Writes app/content/ (generated, git-ignored):
    catalog.json            the course: every planned chapter in order, with what the library needs
    chapters/<id>.json      one written chapter: story, vocabulary, grammar, introduction, Anki, timings
    audio/<id>.mp3          the chapter's audio, where made (make_audio.py)
The format is described in docs/app-spec.md. Review-only data (plans, continuity, TTS script, delivery
notes) is left out.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chapter as bc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "content"
FREE_CHAPTERS = 3


def read(path):
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def lean_chapter(ch):
    """Scenes → paragraphs → segments, keeping what a learner's screen and the player use."""
    scenes = []
    for sc in ch["scenes"]:
        paras = []
        for p in sc.get("paragraphs", []):
            paras.append([{"id": s["id"], "it": s["it"], "en": s["en"], "tokens": s.get("tokens", []),
                           "speakers": sorted({v[0] for v in s.get("voice", []) if v[0] != "narrator"})}
                          for s in p["segments"]])
        scenes.append({"n": sc.get("n"), "location": sc.get("location"), "time": sc.get("time", ""),
                       "paragraphs": paras})
    vocab = [{k: v[k] for k in ("id", "lemma", "pos", "en", "note", "example") if k in v} for v in ch["vocab"]]
    return scenes, vocab


def main():
    for sub in ("chapters", "audio"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    voices = json.loads((ROOT / "config" / "voices.json").read_text(encoding="utf-8"))["voices"]
    locations = json.loads((ROOT / "config" / "locations.json").read_text(encoding="utf-8"))["locations"]
    catalog = {"title": "Input Masters · Italian", "series": "Via dei Tigli", "free_chapters": FREE_CHAPTERS,
               "levels": {lv: {"vocab_by_end": n} for lv, n in bc.VOCAB_MILESTONES.items()},
               "speakers": {k: v.get("name", k) for k, v in voices.items()}, "locations": locations,
               "chapters": []}
    n = met = written = 0
    for p in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        for plan in json.loads(p.read_text(encoding="utf-8"))["chapters"]:
            n += 1
            cid, folder = plan["id"], ROOT / "chapters" / plan["id"]
            row = {"id": cid, "n": n, "level": plan["level"], "season": int(cid[1:3]), "episode": int(cid[4:6]),
                   "theme": plan.get("theme", ""), "title": plan["title"], "grammar": plan["grammar"]["name"],
                   "free": n <= FREE_CHAPTERS, "written": False}
            lo, hi = bc.FOCUS_ITEMS[plan["level"]]
            if (folder / "chapter.json").exists():
                ch = json.loads((folder / "chapter.json").read_text(encoding="utf-8"))
                scenes, vocab = lean_chapter(ch)
                st = bc.stats(ch)
                data = {"id": cid, "n": n, "level": row["level"], "title": row["title"], "theme": row["theme"],
                        "grammar_name": row["grammar"], "intro": read(folder / "intro.md"), "scenes": scenes,
                        "vocab": vocab, "grammar": read(folder / "grammar.md"), "anki": read(folder / "anki.csv")}
                audio = folder / "audio"
                if (audio / "timing.json").exists() and (audio / "chapter.mp3").exists():
                    t = json.loads((audio / "timing.json").read_text(encoding="utf-8"))
                    data["timing"] = {k: t[k] for k in ("duration", "segments", "words")}
                    data["audio"] = f"audio/{cid}.mp3"
                    shutil.copyfile(audio / "chapter.mp3", OUT / "audio" / f"{cid}.mp3")
                    row["audio_minutes"] = round(t["duration"] / 60, 1)
                (OUT / "chapters" / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                                              encoding="utf-8")
                row.update(written=True, intro=data["intro"], words=st["words"], segments=st["segments"],
                           vocab=len(vocab))
                met += len(vocab)
                written += 1
            else:
                met += (lo + hi) // 2  # not written yet: the level's typical count
            row["vocab_through"] = met  # vocabulary items taught up to and including this chapter
            catalog["chapters"].append(row)
    (OUT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"app: {written} written chapter(s) of {n} → {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
