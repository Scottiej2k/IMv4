# IMv4: Italian course content factory

This repo generates a ~200-chapter Italian course (A1 → B2) for English speakers. Each chapter is one
episode of an ensemble sitcom, *Via dei Tigli*, set in Borgoverde, a fictional commuter town north of
Milan. Each chapter has: a story of about 45 minutes' reading, a vocabulary list, an Anki deck, a
grammar lesson, a sentence-by-sentence parallel translation, and a Gemini 3.8 TTS script.
A learner app will be built on this output later. The repo is the content factory.

The owner is not a developer. Explain choices plainly, keep token use low, and ask before
expensive runs.

## Where things are

- `README.md`: layout and status.
- `docs/production-spec.md`: the rules. Lengths per level, language control, file formats, workflow.
- `docs/draft-format.md`: the plain-text format writers produce.
- `docs/tts-format.md`: Gemini 3.8 TTS request shape. At most 2 voices per request; items marked
  ⚠ verify against Google's docs.
- `bible/`: world bible, characters (speech profiles are binding), locations, season arcs,
  `timeline.md` (tu/Lei, secrets, living arrangements by chapter), `continuity-log.md`.
- `curriculum/`: 200 chapter plans in `seasons/sNN.json` (the source), plus the generated
  `overview.md` and `grammar-index.md`. A1 25 · A2 50 · B1 50 · B2 75 chapters; 8 seasons of 25.
- `config/voices.json`: one fixed TTS voice per character, including generic `uomo`/`donna`/`bambino`.
  `config/locations.json`: location ids.
- `prompts/writer-system.md`: the writer model's standing instructions.
- `chapters/<id>/`: `draft.txt` (writer output) → generated `chapter.json`, `grammar.md`,
  `story.md`, `parallel.md`, `vocab.md`, `anki.csv`, `tts.json`. `work/` is scratch (git-ignored).

## How a chapter is made (don't hand-write chapter JSON)

`scripts/pipeline.py` runs the writing scene by scene:
1. Outline: the vocabulary block, plus per scene the beats, a word budget and which vocabulary it uses.
2. Each scene, asked at about 1.3× its budget and stated in lines, because models undershoot.
   A scene under 75% of budget is sent back once.
3. The grammar lesson.
4. `convert_draft.py` (ids, turns, focus tags, vocab examples/targets, citations, then
   `build_chapter.py` for validation and all outputs) plus `grammar_rules.py` (flags forms of
   grammar not taught yet).
5. One round of line fixes. After that, warnings are for review, not loops.

Ways to run it:
- **API:** `python3 scripts/generate_chapter.py s01e01 --model <model>`.
  - Claude models need `pip install anthropic` and `ANTHROPIC_API_KEY`.
  - Any slug containing `/` goes to **OpenRouter** (e.g. `openai/gpt-6-luna`, $0.10/$0.50 per
    million tokens). The key is added by the environment's credential proxy for `openrouter.ai`,
    or read from `OPENROUTER_API_KEY`.
- **Agent-driven** (no API key): `python3 scripts/pipeline.py start <id>`, then write each answer to
  `chapters/<id>/work/answer.txt` and run `pipeline.py submit <id>` until `DONE`. A Sonnet sub-agent
  driving this used about 130–160k tokens per chapter.

Other scripts: `make_brief.py <id>` (writes `chapters/<id>/brief.md` for review) and
`build_curriculum.py` (validates plans, regenerates the overview).

## Status (end of first session, 2026-09-25)

- Done: spec, bible, curriculum (200 plans), all scripts, and two pilot chapters (S1E1 A1, S5E3 B1),
  written by Sonnet 5 through the pipeline.
- Pilot v2 results: the quality is good (natural Italian, character voices hold, grammar check
  clean, tu/Lei correct), but the stories are about 25–30% **short** (S1E1 2,002 words vs a
  2,700–3,200 target; S5E3 3,847 vs 4,800–5,500), dialogue share is about 82% (target 60–75%), and
  some vocabulary appears only twice.
- The pipeline was tuned after v2 (1.3× scene asks stated in lines, a quarter narration, article
  tolerance in bold, fewer false grammar flags) **but the tuning hasn't been tested yet**.
- The owner chose to keep the full length targets ("option 1").

## Next steps

1. Test OpenRouter: a tiny chat-completions request to `openai/gpt-6-luna` through
   `generate_chapter.call_openrouter`. In the first session it returned 401 (credential not yet
   visible to that session).
2. Pilot S1E1 again at full length on the tuned pipeline. Compare `openai/gpt-6-luna` (via
   `generate_chapter.py --force`) with Sonnet 5 on Italian quality, length, level control and cost.
   Review the output yourself before reporting.
3. Once a pilot passes review: fill `curriculum/lexicon.csv` and `bible/continuity-log.md`, and
   decide the production model.
4. Later: audition TTS voices, and verify the ⚠ items in `docs/tts-format.md` (ai.google.dev was
   blocked by the network policy in session 1).

## Conventions

- Commit to the working branch, one commit per chapter (`s01e01: <title>`). Never commit `work/`.
- Rules that matter most for content: everything in Italian (occasional single English words only);
  Ben's mistakes are corrected in the same scene; standard Italian, no dialect; respect
  `bible/timeline.md`; never use grammar beyond the ceiling.
