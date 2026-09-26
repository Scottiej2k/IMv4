#!/usr/bin/env python3
"""Validate a chapter and generate its outputs.

Reads   chapters/<id>/chapter.json  (+ grammar.md)
Writes  story.md, parallel.md, vocab.md, anki.csv, tts.json  (same folder)

Errors stop the build. Warnings are printed but don't stop it; review them.

Usage:
  python3 scripts/build_chapter.py s01e01            # validate + build
  python3 scripts/build_chapter.py s01e01 --check    # validate only
  python3 scripts/build_chapter.py --all             # every chapter folder
"""
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_format as bf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"
VOICES = json.loads((ROOT / "config" / "voices.json").read_text(encoding="utf-8"))
LOCATIONS = json.loads((ROOT / "config" / "locations.json").read_text(encoding="utf-8"))["locations"]

# Human vocal sounds the TTS model performs (docs/tts-format.md; Google's list is longer).
AUDIO_TAGS = {"<laugh>", "<chuckle>", "<giggle>", "<sigh>", "<gasp>", "<groan>", "<tsk>", "<phew>", "<yawn>",
              "<cough>", "<breath>", "<whispers>", "<sob>", "<short pause>", "<long pause>"}
TAG_RE = re.compile(r"<[^>]+>")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
SEG_ID_RE = re.compile(r"s\d{2}e\d{2}-\d+-\d{3}")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:'[A-Za-zÀ-ÖØ-öø-ÿ]+)?")

# Story length targets in Italian words (docs/production-spec.md §1).
WORD_TARGETS = {"A1": (2700, 3200), "A2": (3600, 4200), "B1": (4800, 5500), "B2": (6000, 7000)}
FOCUS_ITEMS = {"A1": (20, 30), "A2": (25, 35), "B1": (30, 40), "B2": (35, 45)}
DIALOGUE_SHARE = (0.45, 0.60)  # book format: tags and description count as narration

# TTS chunking limits (docs/tts-format.md).
MAX_DIALOGUE_CHARS = 2500
MAX_SINGLE_CHARS = 4500

POS_LABEL = {
    "noun": "n.", "verb": "v.", "adjective": "adj.", "adverb": "adv.", "pronoun": "pron.",
    "preposition": "prep.", "conjunction": "conj.", "determiner": "det.", "interjection": "interj.",
    "expression": "expr.", "number": "num.",
}
POS_ORDER = ["expression", "verb", "noun", "adjective", "adverb", "pronoun", "preposition",
             "conjunction", "determiner", "interjection", "number"]


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


# ---------------------------------------------------------------- text helpers

def strip_tags(text):
    """Remove audio tags and tidy the spacing they leave behind."""
    text = TAG_RE.sub("", text)
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def strip_bold(text):
    return BOLD_RE.sub(r"\1", text)


def reader_text(text):
    """Text as shown to readers: bold kept, audio tags removed."""
    return strip_tags(text)


def spoken_text(text):
    """Text as sent to TTS: bold removed, audio tags kept."""
    return re.sub(r"\s{2,}", " ", strip_bold(text)).strip()


def words(text):
    return WORD_RE.findall(strip_bold(strip_tags(text)))


def speaker_name(speaker):
    return VOICES["voices"].get(speaker, {}).get("name", speaker)


def location_name(loc):
    return LOCATIONS.get(loc, loc)


def blocks(scene):
    """A scene's paragraphs (book format) or, in chapters made before it, its turns."""
    return scene.get("paragraphs") or scene.get("turns") or []


def segments(chapter):
    for scene in chapter["scenes"]:
        for block in blocks(scene):
            for seg in block["segments"]:
                yield scene, block, seg


def voice_pieces(block, seg):
    """[(speaker, text, style)] for a segment; old turn-based chapters have one speaker per turn."""
    if "voice" in seg:
        return [tuple(p) for p in seg["voice"]]
    return [(block["speaker"], seg["it"], block.get("style", ""))]


# ---------------------------------------------------------------- validation

def load_plan(chapter_id):
    season = int(chapter_id[1:3])
    path = ROOT / "curriculum" / "seasons" / f"s{season:02d}.json"
    if not path.exists():
        return None, []
    data = json.loads(path.read_text(encoding="utf-8"))
    order = []
    plan = None
    for s_path in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        for ch in json.loads(s_path.read_text(encoding="utf-8"))["chapters"]:
            order.append((ch["id"], ch["grammar"]["id"]))
    for ch in data["chapters"]:
        if ch["id"] == chapter_id:
            plan = ch
    return plan, order


def validate(chapter, folder, rep):
    cid = chapter.get("id", "?")
    required = ["id", "season", "episode", "level", "title", "grammar_focus", "vocab_theme", "vocab", "scenes"]
    for k in required:
        if k not in chapter:
            rep.error(f"missing top-level field '{k}'")
    if rep.errors:
        return
    if cid != folder.name:
        rep.error(f"id '{cid}' doesn't match folder '{folder.name}'")
    if cid != f"s{chapter['season']:02d}e{chapter['episode']:02d}":
        rep.error(f"id '{cid}' doesn't match season/episode numbers")
    level = chapter["level"]
    if level not in WORD_TARGETS:
        rep.error(f"unknown level {level}")
        return

    plan, order = load_plan(cid)
    if plan is None:
        rep.warn("no curriculum plan found for this chapter")
    else:
        if plan["level"] != level:
            rep.error(f"level {level} != curriculum level {plan['level']}")
        if plan["grammar"]["id"] not in chapter["grammar_focus"]:
            rep.error(f"grammar_focus must include the planned concept {plan['grammar']['id']}")
        allowed = set()
        for ch_id, g_id in order:
            allowed.add(g_id)
            if ch_id == cid:
                break
        for g in chapter["grammar_focus"]:
            if g not in allowed:
                rep.error(f"grammar_focus {g} is not taught until later (grammar ceiling)")

    # Segments: unique ids, numbered by scene, audio tags, bold balance.
    seen = set()
    for i, scene in enumerate(chapter["scenes"], start=1):
        if scene.get("n") != i:
            rep.error(f"scene {i} has n={scene.get('n')}")
        if scene.get("location") not in LOCATIONS:
            rep.warn(f"scene {i}: location '{scene.get('location')}' not in config/locations.json")
        expected = 1
        for block in blocks(scene):
            for seg in block["segments"]:
                for sp, _, _ in voice_pieces(block, seg):
                    if sp not in VOICES["voices"]:
                        rep.error(f"{seg.get('id')}: speaker '{sp}' has no entry in config/voices.json")
                    elif sp not in ("narrator", "uomo", "donna", "bambino") and sp not in scene.get("characters", []):
                        rep.warn(f"scene {i}: speaker '{sp}' not listed in scene characters")
                sid = seg.get("id", "")
                want = f"{cid}-{i}-{expected:03d}"
                if sid != want:
                    rep.error(f"segment id '{sid}' should be '{want}' (sequential within each scene)")
                expected += 1
                if sid in seen:
                    rep.error(f"duplicate segment id {sid}")
                seen.add(sid)
                for lang in ("it", "en"):
                    txt = seg.get(lang, "")
                    if not txt.strip():
                        rep.error(f"{sid}: empty '{lang}'")
                    if txt.count("**") % 2:
                        rep.error(f"{sid}: unbalanced ** in '{lang}'")
                for tag in TAG_RE.findall(seg.get("it", "")):
                    if tag not in AUDIO_TAGS:
                        rep.error(f"{sid}: unsupported audio tag {tag}")
                if TAG_RE.search(seg.get("en", "")):
                    rep.error(f"{sid}: audio tags belong in 'it' only")
                it_b, en_b = bool(BOLD_RE.search(seg["it"])), bool(BOLD_RE.search(seg["en"]))
                if it_b != en_b:
                    rep.warn(f"{sid}: bold on one side only")
                if seg.get("focus") and not it_b:
                    rep.warn(f"{sid}: has focus ids but nothing is bolded")

    # Vocabulary: example ids exist and are bolded; focus counts.
    seg_by_id = {seg["id"]: seg for _, _, seg in segments(chapter)}
    focus_count = Counter(f for _, _, seg in segments(chapter) for f in seg.get("focus", []))
    vocab_ids = set()
    lo, hi = FOCUS_ITEMS[level]
    if not lo <= len(chapter["vocab"]) <= hi:
        rep.warn(f"{len(chapter['vocab'])} vocab items (target {lo}–{hi} for {level})")
    for v in chapter["vocab"]:
        vid = v.get("id", "?")
        if vid in vocab_ids:
            rep.error(f"duplicate vocab id {vid}")
        vocab_ids.add(vid)
        ex = seg_by_id.get(v.get("example"))
        if ex is None:
            rep.error(f"{vid}: example segment '{v.get('example')}' not found")
        elif not BOLD_RE.search(ex["it"]):
            rep.error(f"{vid}: example {v['example']} has no bolded target word")
        elif vid not in ex.get("focus", []):
            rep.warn(f"{vid}: example {v['example']} doesn't list {vid} in its focus")
        tgt = v.get("target") or {}
        if ex is not None and tgt:
            for lang in ("it", "en"):
                if tgt.get(lang) not in BOLD_RE.findall(ex[lang]):
                    rep.error(f"{vid}: target.{lang} '{tgt.get(lang)}' is not a bolded phrase in {v['example']}")
        elif not tgt:
            rep.error(f"{vid}: missing 'target' (the bolded words for this item in its example)")
        if v.get("pos") == "noun" and not v.get("gender"):
            rep.warn(f"{vid}: noun without gender")
        if focus_count[vid] < 3:
            rep.warn(f"{vid}: appears as focus in {focus_count[vid]} segment(s) (target at least 3)")
    for f in focus_count:
        if f.startswith("v-") and f not in vocab_ids:
            rep.error(f"focus id {f} is not in the vocab list")
        if f.startswith("g-") and f not in chapter["grammar_focus"]:
            rep.warn(f"focus id {f} is not in grammar_focus")

    # grammar.md: exists and cites real segments.
    gpath = folder / "grammar.md"
    if not gpath.exists():
        rep.warn("grammar.md is missing")
    else:
        cited = SEG_ID_RE.findall(gpath.read_text(encoding="utf-8"))
        for sid in cited:
            if sid not in seg_by_id:
                rep.error(f"grammar.md cites unknown segment {sid}")
        if len(set(cited)) < 5:
            rep.warn(f"grammar.md cites {len(set(cited))} story segments (target 5–10)")


def stats(chapter):
    total = dialogue = 0
    speakers = Counter()
    for _, block, seg in segments(chapter):
        total += len(words(seg["it"]))
        for sp, text, _ in voice_pieces(block, seg):
            if sp != "narrator":
                n = len(words(text))
                dialogue += n
                speakers[sp] += n
    sentences = sum(1 for _, _, seg in segments(chapter))
    distinct = len({w.lower() for _, _, seg in segments(chapter) for w in words(seg["it"])})
    return {
        "words": total,
        "dialogue_share": dialogue / total if total else 0,
        "segments": sentences,
        "avg_words_per_segment": total / sentences if sentences else 0,
        "distinct_forms": distinct,
        "speakers": speakers,
    }


def check_stats(chapter, st, rep):
    lo, hi = WORD_TARGETS[chapter["level"]]
    if not lo <= st["words"] <= hi:
        rep.warn(f"story is {st['words']} Italian words (target {lo}–{hi} for {chapter['level']})")
    dlo, dhi = DIALOGUE_SHARE
    if not dlo <= st["dialogue_share"] <= dhi:
        rep.warn(f"dialogue is {st['dialogue_share']:.0%} of words (target {dlo:.0%}–{dhi:.0%})")


# ---------------------------------------------------------------- renderers

def header(chapter, subtitle):
    t = chapter["title"]
    return [
        f"# {chapter['id'].upper()} · {t['it']}",
        "",
        f"*{t['en']}* · {chapter['level']} · {subtitle}",
        "",
        "_Generated from `chapter.json` by `scripts/build_chapter.py`. Don't edit by hand._",
        "",
    ]


def scene_heading(scene):
    head = f"## {scene['n']}. {location_name(scene['location'])}"
    if scene.get("time"):
        head += f" · {scene['time']}"
    return head


def render_story(chapter):
    out = header(chapter, "Storia")
    for scene in chapter["scenes"]:
        out += [scene_heading(scene), ""]
        for block in blocks(scene):
            out += [" ".join(reader_text(s["it"]) for s in block["segments"]), ""]
    return "\n".join(out)


def md_cell(text):
    return text.replace("|", "\\|")


def render_parallel(chapter):
    out = header(chapter, "Testo parallelo / Parallel text")
    for scene in chapter["scenes"]:
        out += [scene_heading(scene), "", "| Italiano | English |", "|---|---|"]
        for block in blocks(scene):
            for seg in block["segments"]:
                out.append(f"| {md_cell(reader_text(seg['it']))} | {md_cell(strip_tags(seg['en']))} |")
        out.append("")
    return "\n".join(out)


def lemma_label(v):
    label = f"{v['lemma']} ({POS_LABEL.get(v['pos'], v['pos'])}"
    if v.get("gender"):
        label += f", {v['gender']}"
    if v.get("plural"):
        label += f", pl. {v['plural']}"
    return label + ")"


def render_vocab(chapter):
    seg_by_id = {seg["id"]: seg for _, _, seg in segments(chapter)}
    out = header(chapter, f"Vocabolario · {chapter['vocab_theme']}")
    groups = {}
    for v in chapter["vocab"]:
        groups.setdefault(v["pos"], []).append(v)
    for pos in POS_ORDER:
        if pos not in groups:
            continue
        out += [f"## {pos.capitalize()}s" if pos != "expression" else "## Expressions",
                "", "| Parola | Italiano | English |", "|---|---|---|"]
        for v in groups[pos]:
            seg = seg_by_id[v["example"]]
            word = f"**{v['lemma']}**<br>{md_cell(lemma_label(v)[len(v['lemma']) + 1:])} · {md_cell(v['en'])}"
            if v.get("note"):
                word += f"<br>_{md_cell(v['note'])}_"
            it, en = example_pair(v, seg)
            out.append(f"| {word} | {md_cell(it)} | {md_cell(en)} |")
        out.append("")
    return "\n".join(out)


def to_html_bold(text):
    return BOLD_RE.sub(r"<b>\1</b>", text)


def only_target_bold(text, target):
    """Keep bold on the item's own target phrase; drop bold from other focus items."""
    done = False

    def keep(m):
        nonlocal done
        if not done and m.group(1) == target:
            done = True
            return m.group(0)
        return m.group(1)
    return BOLD_RE.sub(keep, text)


def example_pair(v, seg):
    it = only_target_bold(reader_text(seg["it"]), v["target"]["it"])
    en = only_target_bold(strip_tags(seg["en"]), v["target"]["en"])
    return it, en


def render_anki(chapter):
    seg_by_id = {seg["id"]: seg for _, _, seg in segments(chapter)}
    buf = io.StringIO()
    buf.write("#separator:comma\n#html:true\n#columns:Italiano,English,Lemma,Notes,Tags\n#tags column:5\n")
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    tags = f"IMv4 {chapter['level']} {chapter['id']}"
    for v in chapter["vocab"]:
        seg = seg_by_id[v["example"]]
        notes = v["en"] + (f" — {v['note']}" if v.get("note") else "")
        it, en = example_pair(v, seg)
        w.writerow([to_html_bold(it), to_html_bold(en), lemma_label(v), notes, tags])
    return buf.getvalue()


# ---------------------------------------------------------------- TTS

def piece_style(chapter, own):
    """Short style only: the level's pace plus the line's own delivery. Google: persona text (age,
    accent, character) in `style` makes voices drift; it belongs in the voice itself."""
    parts = [VOICES["level_styles"].get(chapter["level"], ""), own or ""]
    return ", ".join(p for p in parts if p)


def word_span(seg_id, first, count):
    """Read-along reference to words first..first+count-1 of a segment: "s01e01-1-004:0-3"."""
    return f"{seg_id}:{first}-{first + count - 1}"


def voiced_items(chapter, scene, rep=None):
    """The scene as a list of (speaker, text, style, segment ids, word spans): consecutive pieces
    with the same voice and style are merged. Word spans say which displayed words each piece
    speaks, so audio timings (docs/read-along.md) map back onto the text."""
    items = []
    for block in blocks(scene):
        for seg in block["segments"]:
            wi = 0
            for sp, text, own in voice_pieces(block, seg):
                n = len(bf.spoken_words(strip_bold(text)))
                span = [word_span(seg["id"], wi, n)] if n else []
                wi += n
                text = spoken_text(text).strip("«» ")
                if not text:
                    continue
                style = piece_style(chapter, own)
                if items and items[-1][0] == sp and items[-1][2] == style and len(items[-1][1]) + len(text) < MAX_DIALOGUE_CHARS:
                    prev = items[-1]
                    items[-1] = (sp, prev[1] + " " + text, style,
                                 prev[3] + ([seg["id"]] if seg["id"] not in prev[3] else []), prev[4] + span)
                else:
                    items.append((sp, text, style, [seg["id"]], span))
            shown = sum(1 for t in seg.get("tokens", []) if t[1] >= 0)
            if rep is not None and "tokens" in seg and shown != wi:
                rep.warn(f"{seg['id']}: {shown} words shown but {wi} spoken (read-along would drift)")
    return items


def build_tts(chapter, rep):
    model = VOICES["model"]
    chunks = []

    def voice_of(sp):
        return VOICES["voices"][sp]["voice"]

    def flush(scene_n, items):
        if not items:
            return
        voices = []
        for sp, *_ in items:
            if sp not in voices:
                voices.append(sp)
        if len(voices) == 1:
            content = [{"type": "text", "text": text, "annotations": [{"type": "speech_metadata", "style": style}]}
                       for _, text, style, *_ in items]
            speech_config = [{"voice": voice_of(voices[0])}]
        else:
            # Speaker labels can be any names (Google docs); we use the character ids.
            content = [{"type": "text", "text": text,
                        "annotations": [{"type": "speech_metadata", "speaker": sp, "style": style}]}
                       for sp, text, style, *_ in items]
            speech_config = {"mode": "conversational",
                             "speakers": [{"speaker": sp, "voice": voice_of(sp)} for sp in voices]}
        seg_ids = []
        for _, _, _, ids, _ in items:
            seg_ids += [i for i in ids if i not in seg_ids]
        chunks.append({
            "index": len(chunks),
            "scene": scene_n,
            "speakers": {sp: sp for sp in voices} if len(voices) > 1 else {"single": voices[0]},
            "segment_ids": seg_ids,
            # For each text item in the request, the displayed words it speaks (read-along).
            "words": [spans for *_, spans in items],
            "request": {
                "model": model,
                "input": [{"type": "user_input", "content": content}],
                "response_format": {"type": "audio", "mime_type": "audio/l16"},
                "generation_config": {"speech_config": speech_config},
            },
        })

    for scene in chapter["scenes"]:
        items, voices, size = [], [], 0
        for sp, text, style, ids, spans in voiced_items(chapter, scene, rep):
            if VOICES["voices"].get(sp, {}).get("voice", "TBD") == "TBD":
                rep.warn(f"TTS: speaker '{sp}' has no voice assigned")
            new_voices = voices + ([sp] if sp not in voices else [])
            limit = MAX_DIALOGUE_CHARS if len(new_voices) > 1 else MAX_SINGLE_CHARS
            if items and (len(new_voices) > 2 or size + len(text) > limit):
                flush(scene["n"], items)
                items, voices, size = [], [], 0
                new_voices = [sp]
            items.append((sp, text, style, ids, spans))
            voices = new_voices
            size += len(text)
        flush(scene["n"], items)
    return {"chapter": chapter["id"], "model": model,
            "notes": "POST each chunk's 'request' to /v1beta/interactions in index order. Each reply is raw "
                     "24 kHz PCM (audio/l16): join the clips in order, with a <long pause> of silence between "
                     "scenes. See docs/tts-format.md.",
            "chunks": chunks}


# ---------------------------------------------------------------- main

def build(chapter_id, check_only=False):
    folder = CHAPTERS / chapter_id
    path = folder / "chapter.json"
    if not path.exists():
        print(f"{chapter_id}: no chapter.json")
        return False
    try:
        chapter = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"{chapter_id}: invalid JSON: {e}")
        return False
    rep = Report()
    validate(chapter, folder, rep)
    st = None
    if not rep.errors:
        st = stats(chapter)
        check_stats(chapter, st, rep)
    print(f"== {chapter_id}")
    for e in rep.errors:
        print(f"  ERROR   {e}")
    for w in rep.warnings:
        print(f"  warning {w}")
    if rep.errors:
        print(f"  {len(rep.errors)} error(s): nothing written.")
        return False
    print(f"  {st['words']} words · {st['segments']} segments · {st['avg_words_per_segment']:.1f} words/segment · "
          f"dialogue {st['dialogue_share']:.0%} · {st['distinct_forms']} distinct word forms · "
          f"{len(chapter['vocab'])} vocab items")
    if check_only:
        return True
    tts = build_tts(chapter, rep)
    (folder / "story.md").write_text(render_story(chapter), encoding="utf-8")
    (folder / "parallel.md").write_text(render_parallel(chapter), encoding="utf-8")
    (folder / "vocab.md").write_text(render_vocab(chapter), encoding="utf-8")
    (folder / "anki.csv").write_text(render_anki(chapter), encoding="utf-8")
    (folder / "tts.json").write_text(json.dumps(tts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote story.md, parallel.md, vocab.md, anki.csv, tts.json ({len(tts['chunks'])} TTS chunks)")
    return True


def main(argv):
    check_only = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if "--all" in argv:
        args = sorted(p.name for p in CHAPTERS.iterdir() if (p / "chapter.json").exists())
    if not args:
        print(__doc__)
        return 2
    ok = all([build(a, check_only) for a in args])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
