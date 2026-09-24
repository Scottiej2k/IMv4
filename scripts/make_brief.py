#!/usr/bin/env python3
"""Build the writer's prompt for a chapter.

  system prompt  = prompts/writer-system.md + docs/draft-format.md + bible/world-bible.md
                   (identical for every chapter, so the API can cache it)
  chapter brief  = level rules, grammar ceiling, the plan, the characters involved,
                   the story so far, and what NOT to use yet

Usage:
  python3 scripts/make_brief.py s01e01          # writes chapters/s01e01/brief.md (system + brief, for review)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grammar_rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

LEVEL_RULES = {
    "A1": {"words": (2700, 3200), "vocab": (20, 30), "sentence": "at most about 8 words per line on average",
           "grammar": "Present tense only. No past, future, conditional or subjunctive (vorrei only as a fixed "
                      "phrase). Very high-frequency words; lots of natural repetition."},
    "A2": {"words": (3600, 4200), "vocab": (25, 35), "sentence": "at most about 12 words per line on average",
           "grammar": "Only the structures in the grammar ceiling below. Simple, clear sentences."},
    "B1": {"words": (4800, 5500), "vocab": (30, 40), "sentence": "about 16 words per line on average at most",
           "grammar": "Only the structures in the grammar ceiling below. Natural, varied sentences."},
    "B2": {"words": (6000, 7000), "vocab": (35, 45), "sentence": "free, but keep lines readable",
           "grammar": "The full language up to the grammar ceiling; rich, natural, varied register."},
}


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def system_prompt():
    return "\n\n".join([
        read("prompts/writer-system.md").strip(),
        "# Draft format (exact)\n\n" + read("docs/draft-format.md").split("\n", 1)[1].strip(),
        "# World bible\n\n" + read("bible/world-bible.md").split("\n", 1)[1].strip(),
    ])


def all_plans():
    seasons = []
    for p in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        seasons.append(json.loads(p.read_text(encoding="utf-8")))
    return seasons


def character_sections():
    """Map character id -> profile text from bible/characters.md (main cast) and minor-table rows."""
    text = read("bible/characters.md")
    profiles = {}
    for m in re.finditer(r"^### (.+?) · `([a-z-]+)`.*?$(.*?)(?=^### |^---|^## |\Z)", text, re.M | re.S):
        profiles[m.group(2)] = {"name": m.group(1).strip(), "text": m.group(0).strip()}
    for m in re.finditer(r"^\| `([a-z-]+)` \| (.+?) \| (.+?) \| (.+?) \|$", text, re.M):
        profiles.setdefault(m.group(1), {"name": m.group(2).strip(),
                                         "text": f"**{m.group(2)}** (`{m.group(1)}`): {m.group(3)}. {m.group(4)}"})
    return profiles


def season_arc_section(n):
    text = read("bible/season-arcs.md")
    m = re.search(rf"^## S{n} ·.*?(?=^## S\d+ ·|\Z)", text, re.M | re.S)
    return m.group(0).strip() if m else ""


def timeline_facts(cid):
    facts = []
    for m in re.finditer(r"^\| (s\d{2}e\d{2}) \| (s\d{2}e\d{2})? ?\| (.+?) \|$", read("bible/timeline.md"), re.M):
        start, until, fact = m.group(1), m.group(2), m.group(3)
        if start <= cid and (not until or cid < until):
            facts.append(fact)
    return facts


def continuity_entries():
    text = read("bible/continuity-log.md")
    start = text.split("## State at series start", 1)
    return ("## State at series start" + start[1]).strip() if len(start) > 1 else ""


def plan_block(ch, full=True):
    lines = [f"**{ch['id']} · {ch['title']['it']}** ({ch['title']['en']}). Grammar: {ch['grammar']['name']}. "
             f"Theme: {ch['theme']}."]
    lines.append(f"- A-plot: {ch['a_plot']}")
    if full:
        lines.append(f"- B-plot: {ch['b_plot']}")
        for k in ("runner", "arc"):
            if ch.get(k):
                lines.append(f"- {k.capitalize()}: {ch[k]}")
    return "\n".join(lines)


def chapter_brief(cid):
    seasons = all_plans()
    flat = [(s, ch) for s in seasons for ch in s["chapters"]]
    idx = next(i for i, (_, ch) in enumerate(flat) if ch["id"] == cid)
    season, plan = flat[idx]
    level = plan["level"]
    rules = LEVEL_RULES[level]
    lo, hi = rules["words"]
    mid = (lo + hi) // 2
    voices = json.loads(read("config/voices.json"))["voices"]
    locations = json.loads(read("config/locations.json"))["locations"]

    later_same = [ch["grammar"]["name"] for _, ch in flat[idx + 1:]
                  if ch["level"] == level and "review" not in ch["grammar"]["id"]]
    later_levels = [ch["grammar"]["name"] for _, ch in flat[idx + 1:]
                    if ch["level"] != level and "review" not in ch["grammar"]["id"]]

    # Characters: anyone named in this plan, plus the family members the plan implies.
    plan_text = " ".join(str(plan.get(k, "")) for k in ("a_plot", "b_plot", "runner", "arc", "theme"))
    profiles = character_sections()
    involved = [cid_ for cid_, p in profiles.items()
                if re.search(rf"\b{re.escape(p['name'].split()[0])}\b", plan_text)
                or re.search(rf"\b{re.escape(cid_)}\b", plan_text)]
    for fam in ("leo", "emma", "chiara", "ben"):
        if fam not in involved:
            involved.insert(0, fam)
    speakable = [f"`{v.get('name', k).upper()}` ({k})" for k, v in voices.items()]

    out = [f"# Chapter brief: {cid}", ""]
    out += ["## The episode", "", plan_block(plan), "",
            f"Season {season['season']}: *{season['title']['it']}* ({season['title']['en']}), "
            f"{season['months']}. Key vocabulary anchors to include where natural: "
            + ", ".join(plan["key_vocab"]) + ".", ""]

    out += ["## Level and length", "",
            f"- Level **{level}**. {rules['grammar']}",
            f"- Story length: **{lo}–{hi} Italian words** (aim for about {mid}). Plan 4–6 story scenes of roughly "
            f"{int(mid * 0.85 / 5)} words each plus 2–4 short confessionali (about {int(mid * 0.15 / 3)} words each).",
            f"- Line length: {rules['sentence']}.",
            f"- Dialogue: 60–75% of the words.",
            f"- Vocabulary block: **{rules['vocab'][0]}–{rules['vocab'][1]} items**, each bolded in at least 3 lines.", ""]

    out += ["## Grammar focus", "",
            f"**{plan['grammar']['name']}** (`{plan['grammar']['id']}`): {plan['grammar']['scope']}", "",
            "Bold clear examples of it throughout the story (they count as grammar-focus examples).", ""]

    levels = ["A1", "A2", "B1", "B2"]
    done_levels = levels[:levels.index(level)]
    out += ["## Grammar ceiling", ""]
    if done_levels:
        out += [f"You may use **all of {', '.join(done_levels)}** grammar, plus what has been taught so far at {level}:", ""]
    else:
        out += ["Taught so far:", ""]
    out += [f"- {ch['grammar']['name']}" for _, ch in flat[:idx + 1] if ch["level"] == level]
    if later_same and level == "A1":
        out += ["", "Coming later at A1 (basic building blocks: use them where the story needs them, in their "
                "simplest, most common forms, without featuring them): " + "; ".join(later_same) + "."]
    elif later_same:
        out += ["", f"**Coming later at {level}. Do not use yet:** " + "; ".join(later_same) + "."]
    if later_levels:
        out += ["", "**Higher-level structures. Do not use** (at most a very common fixed phrase, if unavoidable): "
                + "; ".join(later_levels[:40]) + ("; …and everything after." if len(later_levels) > 40 else ".")]
    forms = grammar_rules.forbidden_forms_text(cid)
    if forms:
        out += ["", "**Concretely, these forms must not appear anywhere in the story** (a script checks for them):", "",
                forms]
    out.append("")

    out += ["## Where things stand at this episode", "",
            "These are facts at this point in the series. Respect them exactly (especially tu/Lei).", ""]
    out += [f"- {f}" for f in timeline_facts(cid)]
    out.append("")

    out += ["## Characters in this episode", ""]
    for k in involved:
        out += [profiles[k]["text"], ""]

    others = [k for k, p in profiles.items() if k not in involved and p["text"].startswith("###")]
    if others:
        out += ["Other main characters (they may appear briefly, in keeping with their profiles in the world bible):", ""]
        for k in others:
            first = re.search(r"\*\*(.+?)\*\*", profiles[k]["text"])
            out.append(f"- {profiles[k]['name']} (`{k}`): {first.group(1) if first else ''}")
        out.append("")

    out += ["## Speakers and places", "",
            "Speakers available (use the capitalised name; anyone else needs adding to config/voices.json first): "
            + ", ".join(speakable) + ".", "",
            "Location ids: " + ", ".join(f"`{k}` ({v})" for k, v in locations.items()) + ".", ""]

    out += ["## Story so far", ""]
    if season["season"] > 1:
        for n in range(1, season["season"]):
            out += [season_arc_section(n), ""]
    else:
        out += [continuity_entries(), ""]
    earlier = [ch for ch in season["chapters"] if ch["id"] < cid]
    if earlier:
        out += [f"### Earlier this season (canon)", ""]
        out += [plan_block(ch) + "\n" for ch in earlier]
    upcoming = [ch for ch in season["chapters"] if ch["id"] > cid][:3]
    if upcoming:
        out += ["### Coming next (don't use this material yet)", ""]
        out += [plan_block(ch, full=False) + "\n" for ch in upcoming]

    out += ["## Output", "",
            "Return only the draft: the `@vocab` block, the scenes, then `@grammar` and the lesson."]
    return "\n".join(out)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    cid = sys.argv[1]
    folder = ROOT / "chapters" / cid
    folder.mkdir(parents=True, exist_ok=True)
    brief = chapter_brief(cid)
    (folder / "brief.md").write_text(
        "<!-- SYSTEM PROMPT -->\n\n" + system_prompt() + "\n\n<!-- USER MESSAGE -->\n\n" + brief + "\n",
        encoding="utf-8")
    print(f"wrote chapters/{cid}/brief.md (~{len((system_prompt() + brief).split())} words)")


if __name__ == "__main__":
    main()
