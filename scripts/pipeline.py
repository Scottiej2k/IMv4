#!/usr/bin/env python3
"""Scene-by-scene chapter writing: outline → scenes → grammar lesson → one round of fixes → continuity entry.

The same state machine drives both ways of writing a chapter:
  * generate_chapter.py sends each prompt to the Claude API as one continuing conversation;
  * a person or an agent can drive it by hand:

      python3 scripts/pipeline.py start s01e01      # prints where the system prompt is + the first prompt
      (write the answer to chapters/s01e01/work/answer.txt)
      python3 scripts/pipeline.py submit s01e01     # records it, prints the next prompt … until DONE

Each scene is written against its own word budget (models hit 500–900 words reliably, not 5,000),
a scene under 75% of its budget is sent back once to be expanded, and after assembly the
converter and grammar checker produce one targeted list of line fixes. A chapter that builds then
gets its continuity-log entry (chapters/<id>/continuity.md), and update_logs.py rebuilds the lexicon
and the log. After fixing a failed chapter by hand, `pipeline.py continuity <id>` asks for the entry.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chapter as bc  # noqa: E402
import convert_draft  # noqa: E402
import grammar_rules  # noqa: E402
import make_brief  # noqa: E402

ROOT = bc.ROOT
SHORT_SCENE = 0.75
# Writers reliably undershoot a word budget by about a quarter, so scenes are asked for
# ~30% more than their budget (and in lines, which models count better than words).
# That's true of Claude; some models write the full amount (see generate_chapter.ASK_FACTORS).
ASK_FACTOR = 1.3
WORDS_PER_LINE = {"A1": 6, "A2": 8, "B1": 11, "B2": 13}


def italian_words(scene_text):
    n = 0
    for line in scene_text.splitlines():
        m = convert_draft.LINE_RE.match(line.strip())
        if m:
            n += len(bc.words(m.group(3)))
    return n


class Pipeline:
    def __init__(self, cid):
        self.cid = cid
        self.folder = ROOT / "chapters" / cid
        self.work = self.folder / "work"
        self.state_path = self.work / "state.json"
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else None
        plan, _ = bc.load_plan(cid)
        self.plan = plan
        lo, hi = make_brief.LEVEL_RULES[plan["level"]]["words"]
        self.lo, self.hi, self.mid = lo, hi, (lo + hi) // 2
        self.ask_factor = ASK_FACTOR  # generate_chapter.py sets this per model

    # ------------------------------------------------------------ state

    def start(self, force=False):
        if self.state and not force:
            raise SystemExit(f"{self.cid}: already started (step '{self.state['step']}'); use --force to restart")
        self.work.mkdir(parents=True, exist_ok=True)
        (self.work / "system.md").write_text(make_brief.system_prompt() + "\n", encoding="utf-8")
        self.state = {"step": "outline", "scene": 0, "expanded": [], "retry": "", "scenes": [], "vocab": "",
                      "fixed": False}
        self.save()

    def save(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def system(self):
        return (self.work / "system.md").read_text(encoding="utf-8")

    # ------------------------------------------------------------ prompts

    def next_prompt(self):
        st = self.state
        step = st["step"]
        if step == "outline":
            p = self.outline_prompt()
        elif step == "scene":
            p = self.scene_prompt()
        elif step == "grammar":
            p = ("# Final step: the grammar lesson\n\nWrite the grammar lesson for this chapter, following the "
                 "instructions in the system prompt. Quote 5–10 lines from the scenes you wrote as "
                 "`[[exact Italian line]]`, copied exactly, without bold. Start with the line `@grammar`. "
                 "Return nothing else.")
        elif step == "fix":
            p = self.fix_prompt()
        elif step == "continuity":
            p = self.continuity_prompt()
        else:
            return None
        if st.get("retry"):
            p = st["retry"] + "\n\n" + p
        (self.work / "prompt.md").write_text(p + "\n", encoding="utf-8")
        return p

    def outline_prompt(self):
        rules = make_brief.LEVEL_RULES[self.plan["level"]]
        return make_brief.chapter_brief(self.cid) + f"""

# Step 1: outline

Plan the chapter. Return exactly this shape and nothing else:

@vocab
(the vocabulary block in the draft format: {rules['vocab'][0]}–{rules['vocab'][1]} items; list every form you will bold; no form may belong to two items)
@end

@outline
# SCENE location-id | time | character ids
words: (Italian words in this scene)
beats: (2–4 sentences: what happens, the joke, how the scene ends)
vocab: (lemmas of the vocabulary items this scene uses, comma-separated)

# CONFESSIONALE character-id
words: …
beats: …
vocab: …
@end

Requirements:
- 4–6 story scenes and 2–4 confessionali, in story order, ending with a short tag scene.
- Word budgets add up to about {self.mid} (between {self.lo} and {self.hi}).
- Every vocabulary item appears in the `vocab:` list of at least 3 scenes.
- The A-plot, B-plot, runner and arc beat from the brief are all there."""

    def scene_prompt(self):
        k = self.state["scene"]
        sc = self.state["scenes"][k]
        n = len(self.state["scenes"])
        forbidden = "; ".join(r["what"] for r in grammar_rules.active_rules(self.cid))
        ask = int(round(sc["words"] * self.ask_factor / 10) * 10)
        lines = max(5, round(ask / WORDS_PER_LINE[self.plan["level"]]))
        confessionale = sc["heading"].upper().startswith("# CONFESSIONALE")
        if confessionale:
            lines = max(5, round(ask / (WORDS_PER_LINE[self.plan["level"]] + 2)))
            mix = "Mostly the character speaking to camera; one or two short NARRATOR lines at most."
        else:
            # Confessionali are all speech, so story scenes carry about a third narration to land
            # the chapter at 60–75% dialogue. Writers drop narration unless given a number.
            mix = (f"Mix: about two thirds dialogue, one third narration. That means about "
                   f"{max(2, round(lines / 3))} of the {lines} lines are NARRATOR lines (setting, action, "
                   f"gestures, reactions), spread through the scene.")
        p = f"""# Scene {k + 1} of {n}

Write this scene now:
{sc['heading']}
Beats: {sc['beats']}
Length: **about {ask} Italian words, roughly {lines} lines.** Keep count as you go; don't wrap up early.
{mix}
Vocabulary to use, each bolded at least once as its own span, with the matching English bolded: {sc['vocab']}
Also bold clear examples of the grammar focus where they come up naturally.

Return only the scene: the heading line exactly as above, then its lines in the draft format."""
        # Repeat the chapter's tu/Lei facts for this scene's characters: the brief is many turns back,
        # and the general rules ("Ornella uses Lei") otherwise win (S5E3 pilot, 2026-09-25).
        cast = [c.strip().capitalize() for c in sc["heading"].split("|")[-1].split(",")]
        address = [f for f in make_brief.timeline_facts(self.cid)
                   if re.search(r"\*\*(tu|Lei)\*\*", f) and sum(c in f for c in cast) >= 2]
        if confessionale:
            address = []
        if address:
            p += "\nTu/Lei in this chapter (binding): " + " ".join(address)
        if forbidden:
            p += f"\nNever use (not taught yet): {forbidden}."
        return p

    def fix_prompt(self):
        issues = self.state["issues"]
        return ("# Corrections\n\nThe checker found these problems in the assembled draft. Each shows the draft "
                "line number and the current line.\n\n" + issues + "\n\nReturn only replacement lines, one per "
                "line, in this form:\n\nN | SPEAKER [delivery]: italiano || English\n\nwhere N is the draft line "
                "number. Fix each problem with the smallest change that keeps the meaning and sounds natural "
                "(e.g. rewrite with a structure that has been taught). To bold a vocabulary item that is never "
                "bolded, choose a line that already contains it (or rewrite one line to include it). "
                "If a flag is a false positive, leave that line out.")

    # ------------------------------------------------------------ answers

    def submit(self, answer):
        answer = re.sub(r"^```\w*\n|\n```\s*$", "", answer.strip())
        st = self.state
        st["retry"] = ""
        step = st["step"]
        if step == "outline":
            self.take_outline(answer)
        elif step == "scene":
            self.take_scene(answer)
        elif step == "grammar":
            if not answer.lower().startswith("@grammar"):
                answer = "@grammar\n" + answer
            (self.work / "grammar.txt").write_text(answer + "\n", encoding="utf-8")
            self.assemble_and_check()
        elif step == "fix":
            self.apply_fixes(answer)
        elif step == "continuity":
            self.take_continuity(answer)
        self.save()

    def take_outline(self, answer):
        (self.work / "outline.txt").write_text(answer + "\n", encoding="utf-8")
        vocab = re.search(r"@vocab\s*\n(.*?)\n@end", answer, re.S)
        outline = re.search(r"@outline\s*\n(.*?)(?:\n@end|\Z)", answer, re.S)
        scenes = []
        if outline:
            for block in re.split(r"\n(?=#\s*(?:SCENE|CONFESSIONALE))", outline.group(1).strip()):
                lines = block.strip().splitlines()
                if not lines or not lines[0].startswith("#"):
                    continue
                fields = {}
                for ln in lines[1:]:
                    key, _, val = ln.partition(":")
                    fields[key.strip().lower()] = val.strip()
                words = int(re.sub(r"\D", "", fields.get("words", "")) or 0)
                scenes.append({"heading": lines[0].strip(), "words": words or 300,
                               "beats": fields.get("beats", ""), "vocab": fields.get("vocab", "")})
        if not vocab or len(scenes) < 3:
            self.state["retry"] = ("Your outline couldn't be read (it needs an @vocab … @end block and at least "
                                   "3 scenes under @outline, each starting with '# SCENE' or '# CONFESSIONALE').")
            return
        total = sum(s["words"] for s in scenes)
        if not 0.9 * self.lo <= total <= 1.1 * self.hi:
            scale = self.mid / total
            for s in scenes:
                s["words"] = max(60, int(round(s["words"] * scale / 10) * 10))
            print(f"  note: outline budgets added up to {total}; rescaled to about {self.mid}")
        counts = {}
        for s in scenes:
            for lemma in [v.strip().lower() for v in s["vocab"].split(",") if v.strip()]:
                counts[lemma] = counts.get(lemma, 0) + 1
        thin = [l for l, c in counts.items() if c < 3]
        if thin:
            print(f"  note: vocab planned for fewer than 3 scenes: {', '.join(thin)}")
        self.state.update(vocab=vocab.group(1).strip(), scenes=scenes, step="scene", scene=0)

    def take_scene(self, answer):
        k = self.state["scene"]
        sc = self.state["scenes"][k]
        if not answer.lstrip().startswith("#"):
            answer = sc["heading"] + "\n" + answer
        n = italian_words(answer)
        (self.work / f"scene-{k + 1:02d}.txt").write_text(answer.strip() + "\n", encoding="utf-8")
        print(f"  scene {k + 1}: {n} words (budget {sc['words']})")
        if n < SHORT_SCENE * sc["words"] and k not in self.state["expanded"]:
            self.state["expanded"].append(k)
            self.state["retry"] = (f"That scene has {n} Italian words; it needs about {sc['words']}. Write it again, "
                                   "complete and longer: add real exchanges and beats that fit the scene, not "
                                   "padding or repeated lines. Same format, heading first.")
            return
        if k + 1 < len(self.state["scenes"]):
            self.state["scene"] = k + 1
        else:
            self.state["step"] = "grammar"

    def assemble(self):
        parts = ["@vocab", self.state["vocab"], "@end", ""]
        for k in range(len(self.state["scenes"])):
            parts += [(self.work / f"scene-{k + 1:02d}.txt").read_text(encoding="utf-8").strip(), ""]
        parts.append((self.work / "grammar.txt").read_text(encoding="utf-8").strip())
        (self.folder / "draft.txt").write_text("\n".join(parts) + "\n", encoding="utf-8")

    def check(self):
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / "convert_draft.py"), self.cid],
                             capture_output=True, text=True)
        report = res.stdout
        draft = (self.folder / "draft.txt").read_text(encoding="utf-8").splitlines()
        issues = []
        for line in report.splitlines():
            if "ERROR" in line:
                issues.append(line.strip().replace("ERROR   ", "- "))
        for n, text, hits in grammar_rules.lint_draft(self.cid, "\n".join(draft)):
            what = "; ".join(f"{r['what']} ('{w}') is not taught until {r['intro']}" for r, w in hits)
            issues.append(f"- line {n}: {what}\n    {text}")
        return report, issues

    def assemble_and_check(self):
        self.assemble()
        report, issues = self.check()
        if issues:
            self.state.update(step="fix", issues="\n".join(issues))
            print(f"  {len(issues)} issue(s) to fix")
        else:
            self.finish(report)

    def apply_fixes(self, answer):
        path = self.folder / "draft.txt"
        lines = path.read_text(encoding="utf-8").splitlines()
        applied = 0
        for row in answer.splitlines():
            m = re.match(r"^\s*(\d+)\s*\|\s*(.+?)\s*$", row)
            if not m:
                continue
            n, new = int(m.group(1)), m.group(2)
            if 1 <= n <= len(lines) and convert_draft.LINE_RE.match(new):
                lines[n - 1] = new
                applied += 1
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  applied {applied} fix(es)")
        report, issues = self.check()
        self.finish(report, issues)

    def finish(self, report, remaining=()):
        # A chapter that built goes on to its continuity entry; one that didn't needs a person first.
        self.state["built"] = "nothing written" not in report
        self.state["step"] = "continuity" if self.state["built"] else "done"
        text = report + ("\nUnresolved after the fix round:\n" + "\n".join(remaining) if remaining else "")
        (self.work / "report.txt").write_text(text, encoding="utf-8")
        print(text)

    def ask_continuity(self):
        """Jump to the continuity entry, e.g. after a failed chapter was fixed by hand and rebuilt."""
        if not (self.folder / "story.md").exists():
            raise SystemExit(f"{self.cid}: no story.md; build the chapter first (convert_draft.py {self.cid})")
        if self.state is None:
            self.start()
        self.state.update(step="continuity", retry="", continuity_retry=False)
        self.save()

    def continuity_prompt(self):
        """Self-contained (it carries the final story), so it can be sent without the conversation."""
        story = (self.folder / "story.md").read_text(encoding="utf-8")
        title = self.plan["title"]["it"]
        return f"""# Continuity log entry

The chapter below is final. Write its entry for the series continuity log, which later chapters'
writers read so that 200 chapters stay consistent. In English, factual, only what the story below
actually says, and **at most about 150 words in all**: later briefs carry every entry, so be terse.
Record only what this chapter adds: invented details a later writer could contradict (names, ages,
jobs, places, possessions, dates), who now knows which secret, and a tu/Lei switch if one happens.
Don't restate facts from the plan or the bible, or relationships that didn't change.

Return exactly this shape and nothing else:

### {self.cid} · {title}
- **Happened:** 2–4 bullets of plot.
- **New facts:** names, places, ages, possessions, relationships, anything later chapters must respect.
- **Changed:** relationship shifts, secrets now known (and by whom), open threads.
- **Planted:** set-ups that need a payoff later (with the planned episode if known).

(Each label is one bullet of at most two sentences or a short semicolon list; write "none" if
there is nothing.)

---

{story}"""

    def take_continuity(self, answer):
        m = re.search(r"^###\s.*", answer, re.M | re.S)
        if not m or "**New facts:**" not in answer:
            if not self.state.get("continuity_retry"):
                self.state["continuity_retry"] = True
                self.state["retry"] = "That entry couldn't be read: start with the '###' heading and keep the four labelled bullets."
                return
            print("  warning: continuity entry not in the expected shape; saved as is for review")
        (self.folder / "continuity.md").write_text((m.group(0) if m else answer).strip() + "\n", encoding="utf-8")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "update_logs.py")], check=False)
        self.state["step"] = "done"


def main(argv):
    if len(argv) < 2 or argv[0] not in ("start", "submit", "status", "continuity"):
        print(__doc__)
        return 2
    cmd, cid = argv[0], argv[1]
    pipe = Pipeline(cid)
    if cmd == "start":
        pipe.start(force="--force" in argv)
        print(f"System prompt: read {pipe.work.relative_to(ROOT)}/system.md once, then answer each prompt.\n"
              f"Write each answer to {pipe.work.relative_to(ROOT)}/answer.txt and run: "
              f"python3 scripts/pipeline.py submit {cid}\n")
    elif cmd == "continuity":
        pipe.ask_continuity()
    elif cmd == "submit":
        pipe.submit((pipe.work / "answer.txt").read_text(encoding="utf-8"))
    elif cmd == "status":
        print(json.dumps({k: v for k, v in pipe.state.items() if k != "vocab"}, ensure_ascii=False, indent=1))
        return 0
    prompt = pipe.next_prompt()
    if prompt is None:
        print("DONE")
    else:
        print("=" * 30 + " NEXT PROMPT " + "=" * 30 + "\n" + prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
