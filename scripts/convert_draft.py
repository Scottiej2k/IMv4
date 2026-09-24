#!/usr/bin/env python3
"""Convert a writer's draft (chapters/<id>/draft.txt) into chapter.json + grammar.md,
then run the normal build (validation + story/parallel/vocab/anki/tts).

The draft format is described in docs/draft-format.md. Everything mechanical is done
here, not by the writer: segment ids, turns, focus tags, vocab examples and targets,
and segment ids for the grammar lesson's quotes.

Usage: python3 scripts/convert_draft.py s01e01
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chapter as bc  # noqa: E402

ROOT = bc.ROOT
ARTICLES = ("il ", "lo ", "la ", "l'", "i ", "gli ", "le ", "un ", "uno ", "una ", "un'")
LINE_RE = re.compile(r"^([A-ZÀ-Ü][A-ZÀ-Ü' .\-]*?)\s*(?:\[([^\]]*)\])?\s*:\s*(.+?)\s*\|\|\s*(.+?)\s*$")
QUOTE_RE = re.compile(r"\[\[(.+?)\]\]")


def norm(text):
    text = text.replace("’", "'").lower()
    text = bc.strip_tags(bc.strip_bold(text))
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:!?…«»\"'—-")


def speaker_ids():
    table = {}
    for vid, v in bc.VOICES["voices"].items():
        table[vid.lower()] = vid
        table[vid.replace("-", " ").lower()] = vid
        table[v.get("name", vid).lower()] = vid
    table["narratore"] = table["narrator"] = "narrator"
    return table


def parse(text, errors):
    vocab, scenes, grammar_lines, extra_grammar = [], [], [], []
    section = None
    speakers = speaker_ids()
    scene = None
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if section == "grammar":
            grammar_lines.append(raw.rstrip())
            continue
        if not line or line.startswith("//"):
            continue
        low = line.lower()
        if low.startswith("@vocab"):
            section = "vocab"
            continue
        if low.startswith("@end"):
            section = None
            continue
        if low.startswith("@grammar_focus"):
            extra_grammar += line.split(None, 1)[1].split() if " " in line else []
            continue
        if low.startswith("@grammar"):
            section = "grammar"
            continue
        if section == "vocab":
            cols = [c.strip() for c in line.split("|")]
            if len(cols) < 4:
                errors.append(f"line {n}: vocab needs 'lemma | pos | gender | english | forms | note'")
                continue
            cols += [""] * (6 - len(cols))
            lemma, pos, gender, en, forms, note = cols[:6]
            vocab.append({"lemma": lemma, "pos": pos.lower(), "gender": gender, "en": en,
                          "forms": [f.strip() for f in forms.split(",") if f.strip()], "note": note, "line": n})
            continue
        if line.startswith("#"):
            head = line.lstrip("#").strip()
            kind, _, rest = head.partition(" ")
            if kind.upper() == "SCENE":
                parts = [p.strip() for p in rest.split("|")]
                parts += [""] * (3 - len(parts))
                chars = [speakers.get(c.strip().lower(), c.strip().lower()) for c in parts[2].split(",") if c.strip()]
                scene = {"location": parts[0], "time": parts[1], "characters": chars, "lines": []}
            elif kind.upper() == "CONFESSIONALE":
                who = speakers.get(rest.strip().lower(), rest.strip().lower())
                scene = {"location": "confessionale", "time": "", "characters": [who], "lines": []}
            else:
                errors.append(f"line {n}: unknown heading '{line}' (use '# SCENE ...' or '# CONFESSIONALE ...')")
                continue
            scenes.append(scene)
            continue
        m = LINE_RE.match(line)
        if not m:
            errors.append(f"line {n}: can't read line (expected 'SPEAKER: italiano || English'): {line[:70]}")
            continue
        if scene is None:
            errors.append(f"line {n}: dialogue before the first '# SCENE' heading")
            continue
        who, style, it, en = m.groups()
        sid = speakers.get(who.strip().lower())
        if sid is None:
            errors.append(f"line {n}: unknown speaker '{who}' (add them to config/voices.json)")
            continue
        scene["lines"].append({"speaker": sid, "style": (style or "").strip(), "it": it, "en": en, "line": n})
    return vocab, scenes, "\n".join(grammar_lines).strip(), extra_grammar


def item_id(lemma, used):
    base = norm(lemma)
    for a in ARTICLES:
        if base.startswith(a):
            base = base[len(a):]
            break
    slug = re.sub(r"[^a-z0-9]+", "-", base.translate(str.maketrans("àèéìíòóùú", "aeeiioouu"))).strip("-") or "item"
    vid, k = f"v-{slug}", 2
    while vid in used:
        vid, k = f"v-{slug}-{k}", k + 1
    used.add(vid)
    return vid


def convert(cid):
    folder = ROOT / "chapters" / cid
    draft = folder / "draft.txt"
    if not draft.exists():
        print(f"{cid}: no draft.txt")
        return False
    plan, _ = bc.load_plan(cid)
    if plan is None:
        print(f"{cid}: no curriculum plan")
        return False
    errors, notes = [], []
    vocab, scenes, grammar, extra_grammar = parse(draft.read_text(encoding="utf-8"), errors)
    grammar_id = plan["grammar"]["id"]

    # Vocabulary: ids and the forms that count as "this item" when bolded.
    used, form_to_item = set(), {}
    for v in vocab:
        v["id"] = item_id(v["lemma"], used)
        forms = {norm(v["lemma"])} | {norm(f) for f in v["forms"]}
        for a in ARTICLES:
            if norm(v["lemma"]).startswith(a):
                forms.add(norm(v["lemma"])[len(a):])
        for f in forms:
            if f in form_to_item and form_to_item[f] != v["id"]:
                errors.append(f"vocab form '{f}' belongs to two items ({form_to_item[f]}, {v['id']})")
            form_to_item[f] = v["id"]
        if v["pos"] not in bc.POS_LABEL:
            errors.append(f"line {v['line']}: unknown part of speech '{v['pos']}' for {v['lemma']}")

    # Scenes → turns → segments, with focus derived from bold spans.
    unmatched = set()
    occurrences = {v["id"]: [] for v in vocab}
    out_scenes = []
    for i, sc in enumerate(scenes, start=1):
        turns, k = [], 0
        for ln in sc["lines"]:
            k += 1
            sid = f"{cid}-{i}-{k:03d}"
            it_b, en_b = bc.BOLD_RE.findall(ln["it"]), bc.BOLD_RE.findall(ln["en"])
            focus = []
            for j, span in enumerate(it_b):
                vid = form_to_item.get(norm(span))
                if vid is None:
                    bare = norm(span)
                    for a in ARTICLES:
                        if bare.startswith(a):
                            vid = form_to_item.get(bare[len(a):].strip())
                            break
                if vid is None:
                    unmatched.add(span)
                    if grammar_id not in focus:
                        focus.append(grammar_id)
                    continue
                if vid not in focus:
                    focus.append(vid)
                en_span = en_b[j] if len(it_b) == len(en_b) else None
                occurrences[vid].append((sid, span, en_span, len(bc.words(ln["it"]))))
            if len(it_b) != len(en_b):
                notes.append(f"{sid} (draft line {ln['line']}): {len(it_b)} bold in Italian, {len(en_b)} in English")
            seg = {"id": sid, "it": ln["it"], "en": ln["en"]}
            if focus:
                seg["focus"] = focus
            prev = turns[-1] if turns else None
            if prev and prev["speaker"] == ln["speaker"] and (not ln["style"] or ln["style"] == prev.get("style", "")):
                prev["segments"].append(seg)
            else:
                turn = {"speaker": ln["speaker"], "segments": [seg]}
                if ln["style"]:
                    turn["style"] = ln["style"]
                turns.append(turn)
        if not turns:
            errors.append(f"scene {i} ({sc['location']}) has no lines")
        scene = {"n": i, "location": sc["location"], "characters": sc["characters"], "turns": turns}
        if sc["time"]:
            scene["time"] = sc["time"]
        out_scenes.append(scene)

    # Pick each item's example: a short segment where the bolds pair up cleanly.
    out_vocab = []
    for v in vocab:
        occ = [o for o in occurrences[v["id"]] if o[2] is not None]
        if not occ:
            errors.append(f"vocab '{v['lemma']}' is never bolded in a line with matching English bold "
                          f"(forms: {', '.join(sorted({norm(v['lemma'])} | {norm(f) for f in v['forms']}))})")
            continue
        best = min(occ, key=lambda o: (not 4 <= o[3] <= 14, o[3]))
        item = {"id": v["id"], "lemma": v["lemma"], "pos": v["pos"], "en": v["en"],
                "example": best[0], "target": {"it": best[1], "en": best[2]}}
        if v["gender"]:
            item["gender"] = v["gender"]
        if v["note"]:
            item["note"] = v["note"]
        out_vocab.append(item)

    # Grammar lesson: [[quoted sentence]] → quote with its segment id.
    seg_index = {}
    for sc in out_scenes:
        for t in sc["turns"]:
            for s in t["segments"]:
                seg_index.setdefault(norm(s["it"]), s)

    def cite(m):
        key = norm(m.group(1))
        seg = seg_index.get(key)
        if seg is None:
            cands = [s for k2, s in seg_index.items() if key and key in k2]
            seg = cands[0] if len(cands) == 1 else None
        if seg is None:
            errors.append(f"grammar lesson quotes a sentence that isn't in the story: [[{m.group(1)[:60]}]]")
            return m.group(0)
        return f"“{bc.reader_text(seg['it'])}” — {bc.strip_tags(seg['en'])} (`{seg['id']}`)"

    grammar_md = QUOTE_RE.sub(cite, grammar) if grammar else ""
    if not grammar:
        errors.append("no @grammar section (the grammar lesson)")

    if errors:
        print(f"== {cid}: draft has {len(errors)} error(s); nothing written")
        for e in errors:
            print(f"  ERROR   {e}")
        return False

    chapter = {
        "id": cid, "season": int(cid[1:3]), "episode": int(cid[4:6]), "level": plan["level"],
        "title": plan["title"], "grammar_focus": [grammar_id] + [g for g in extra_grammar if g != grammar_id],
        "vocab_theme": plan["theme"], "vocab": out_vocab, "scenes": out_scenes,
    }
    (folder / "chapter.json").write_text(json.dumps(chapter, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "grammar.md").write_text(grammar_md + "\n", encoding="utf-8")
    print(f"== {cid}: converted draft → chapter.json, grammar.md")
    for note in notes:
        print(f"  note    {note}")
    if unmatched:
        print(f"  note    bold spans counted as grammar focus ({grammar_id}): "
              + ", ".join(sorted(unmatched, key=str.lower)))
    return bc.build(cid)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if convert(sys.argv[1]) else 1)
