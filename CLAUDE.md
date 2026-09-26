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
2. Each scene, stated in lines, with a narration share and the scene's tu/Lei facts. Asked at 1.3×
   its budget for Claude (it undershoots); DeepSeek per level: A1/A2 1.05×, B1/B2 1.0×
   (`ASK_FACTORS` in generate_chapter.py). A scene under 75% of budget is sent back once.
3. The grammar lesson.
4. `convert_draft.py` (ids, turns, focus tags, vocab examples/targets, citations, then
   `build_chapter.py` for validation and all outputs) plus `grammar_rules.py` (flags forms of
   grammar not taught yet).
5. One round of line fixes. After that, warnings are for review, not loops.
6. If it built: a ~150-word continuity entry (`chapters/<id>/continuity.md`), then `update_logs.py`
   rebuilds `curriculum/lexicon.csv` and `bible/continuity-log.md` from all chapters in order.
   Briefs include only earlier chapters' entries.

Ways to run it:
- **Batches (normal):** `python3 scripts/run_batch.py s01e02-s01e10 --jobs 5 --trailer "<commit
  attribution>"`. Each chapter runs in its own git worktree under `.batch/` (git-ignored) and is
  committed as it finishes; failures go to `.batch/failed/<id>/`, logs and `summary.tsv` to `.batch/`.
  It doesn't push. Chapters running at the same time don't see each other's continuity entries
  (`--jobs 1` if that matters).
- **One chapter:** `python3 scripts/generate_chapter.py s01e01 --model <model> --force`.
  - Any slug containing `/` goes to **OpenRouter**. The environment's proxy adds the key only for
    subdomains (`www.openrouter.ai`, which the script uses); Cloudflare needs a User-Agent (set).
  - Claude models need `pip install anthropic` and `ANTHROPIC_API_KEY`.
  - `--continuity-only` writes just the entry, e.g. after a failed chapter was fixed by hand and
    rebuilt with `convert_draft.py`.
- **Agent-driven** (no API key): `python3 scripts/pipeline.py start <id>`, then write each answer to
  `chapters/<id>/work/answer.txt` and run `pipeline.py submit <id>` until `DONE`.

Review reader: https://claude.ai/artifact/R3XejAxbx7k2a74RiCiTwT (private artifact; the owner's review
page for every chapter: story, side by side, vocabulary, grammar, audio script, plan and continuity).
To refresh it after new chapters: `python3 scripts/build_reader.py`, then publish `reader/index.html`
to that URL with `index.json` and every `data/<id>.json` as files (both generated, git-ignored).

Other scripts: `make_brief.py <id>` (writes `chapters/<id>/brief.md` for review),
`build_curriculum.py` (validates plans, regenerates the overview), `update_logs.py`.

## Status (session 3, 2026-09-26)

- **Stories are written as a book** (the owner's decision): prose paragraphs, speech as «…»{id},
  thoughts as _…_{id} (confessionali became thoughts), present tense through A2. The same text
  drives the audiobook: the narrator reads the prose, each character voices their own words.
  See docs/draft-format.md. The converter enforces one speaker per paragraph and joins
  back-to-back narration paragraphs (DeepSeek does neither reliably).
- Written in book format: S1E1–S1E5 and the S5E3 pilot (grammar check clean on all).
- Production model `deepseek/deepseek-v4.1-flash`, pinned to DeepSeek's own provider for caching:
  about $0.03–0.08 a chapter, 10–30 min each. OpenRouter key: about $2.5 spent of $50.
- **Read-along** (owner's feature): words underline as the audio plays, played words stay
  underlined, play from any sentence, resume. Content is ready: word ids in every segment
  (`tokens`), word spans per TTS item; timings will come from forced alignment of the finished
  audio (docs/read-along.md). `scripts/make_audio.py` makes a chapter's MP3 + timing.json (Gemini,
  or `--engine standin` via OpenRouter for testing). S1E1 has stand-in audio in the reader; real
  Gemini voices need a `GEMINI_API_KEY` environment variable (owner to add) and the voice casting.
- Dialogue target is 45–60% for the book format (owner, 2026-09-26).
- TTS: checked against Google's docs (docs/tts-format.md). Styles are now short; character
  voices (Italian voices from the Extended Voice Library, a designed voice for Ben) are still to
  choose.
- Known: the S5E3 plan sets the chapter in late January though S5 runs Sept–Feb (owner to decide).
  Continuity entries can over-reach or come out in Italian: skim them.

## Next steps

1. Owner's review of the book-format chapters, then production batches from S1E6 (`--jobs 1` keeps
   continuity tight).
2. Later: audition TTS voices, and verify the ⚠ items in `docs/tts-format.md` (ai.google.dev was
   blocked by the network policy in session 1).

## Conventions

- Commit to the working branch, one commit per chapter (`s01e01: <title>`). Never commit `work/`.
- Rules that matter most for content: everything in Italian (occasional single English words only);
  Ben's mistakes are corrected in the same scene; standard Italian, no dialect; respect
  `bible/timeline.md`; never use grammar beyond the ceiling.
