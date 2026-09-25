#!/usr/bin/env python3
"""Bundle the chapters for the review reader (reader/index.html).

    python3 scripts/build_reader.py

Writes reader/index.json (every planned chapter, with stats for the written ones, plus speaker and
location names) and reader/data/<id>.json (one per written chapter: the chapter, grammar lesson,
continuity entry and a compact TTS script). Both are generated and git-ignored; the reader page
itself is committed. Publish the page with these files alongside it (see CLAUDE.md).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chapter as bc  # noqa: E402
import make_brief  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reader"
PLAN_KEYS = ("theme", "a_plot", "b_plot", "runner", "arc", "key_vocab")


def compact_tts(tts):
    """Keep what a reviewer reads: who speaks with which voice, the text and its delivery note."""
    chunks = []
    for c in tts.get("chunks", []):
        req = c["request"]
        cfg = req.get("generation_config", {}).get("speech_config", {})
        if isinstance(cfg, list):  # single-voice chunk: [{"voice": ...}], speakers {"single": id}
            voices = {"single": cfg[0].get("voice", "")} if cfg else {}
        else:
            voices = {s["speaker"]: s["voice"] for s in cfg.get("speakers", [])}
        lines = []
        for part in req["input"][0]["content"]:
            meta = next((a for a in part.get("annotations", []) if a.get("type") == "speech_metadata"), {})
            label = meta.get("speaker") or "single"
            lines.append({"who": c["speakers"].get(label, label), "text": part["text"], "style": meta.get("style", "")})
        chunks.append({"index": c["index"], "scene": c["scene"], "voices": {c["speakers"].get(k, k): v
                       for k, v in voices.items()}, "lines": lines, "segments": len(c.get("segment_ids", []))})
    return {"model": tts.get("model"), "notes": tts.get("notes"), "chunks": chunks}


def stats(chapter):
    st = bc.stats(chapter)
    return {"words": st["words"], "dialogue": round(100 * st["dialogue_share"]), "segments": st["segments"],
            "scenes": len(chapter["scenes"]), "vocab": len(chapter["vocab"])}


def as_book(chapter):
    """Chapters written before the book format (one speaker per turn) shown as paragraphs:
    each turn becomes a paragraph, speech in « » after the speaker's name."""
    for scene in chapter["scenes"]:
        if "paragraphs" in scene:
            continue
        paras = []
        for turn in scene.pop("turns", []):
            sp = turn["speaker"]
            segs = []
            for i, seg in enumerate(turn["segments"]):
                seg = dict(seg, voice=[[sp, seg["it"], turn.get("style", "")]])
                if sp != "narrator":
                    name = bc.speaker_name(sp) + ": " if i == 0 else ""
                    seg["it"], seg["en"] = f"{name}«{seg['it']}»", f"{name}“{seg['en']}”"
                segs.append(seg)
            paras.append({"segments": segs})
        scene["paragraphs"] = paras
    return chapter


def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    voices = json.loads((ROOT / "config" / "voices.json").read_text(encoding="utf-8"))["voices"]
    locations = json.loads((ROOT / "config" / "locations.json").read_text(encoding="utf-8"))["locations"]
    index = {"speakers": {k: v.get("name", k) for k, v in voices.items()}, "locations": locations,
             "levels": {k: {"words": list(v["words"])} for k, v in make_brief.LEVEL_RULES.items()},
             "chapters": []}
    written = 0
    for p in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        for plan in json.loads(p.read_text(encoding="utf-8"))["chapters"]:
            cid = plan["id"]
            row = {"id": cid, "level": plan["level"], "title": plan["title"],
                   "grammar": plan["grammar"]["name"], "plan": {k: plan[k] for k in PLAN_KEYS if k in plan}}
            folder = ROOT / "chapters" / cid
            if (folder / "chapter.json").exists():
                chapter = json.loads((folder / "chapter.json").read_text(encoding="utf-8"))
                row["stats"] = stats(chapter)
                row["format"] = "book" if all("paragraphs" in sc for sc in chapter["scenes"]) else "script"
                chapter = as_book(chapter)
                data = {"chapter": chapter,
                        "grammar": (folder / "grammar.md").read_text(encoding="utf-8") if (folder / "grammar.md").exists() else "",
                        "continuity": (folder / "continuity.md").read_text(encoding="utf-8") if (folder / "continuity.md").exists() else "",
                        "tts": compact_tts(json.loads((folder / "tts.json").read_text(encoding="utf-8")))
                        if (folder / "tts.json").exists() else None}
                (OUT / "data" / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                                          encoding="utf-8")
                written += 1
            index["chapters"].append(row)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"reader: {written} written chapter(s) of {len(index['chapters'])} planned → reader/")


if __name__ == "__main__":
    main()
