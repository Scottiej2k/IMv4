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
7. Then the learner's introduction (`chapters/<id>/intro.md`): one English paragraph, 60–100 words,
   what the episode is about plus a hook teasing a real moment. `--intro-only` writes just that.

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

Learner app (product name **Input Masters · Italian**; built on Replit once all 200 chapters and audio
exist): prototype `app/index.html` at https://claude.ai/artifact/6nEntWJYwZ3BeFeHAGY3KN, spec and
hand-off in `docs/app-spec.md`. `python3 scripts/export_app.py` writes the content bundle `app/content/`
(git-ignored); publish the page with `content/catalog.json`, `content/chapters/*.json` and
`content/audio/*.mp3` as files.
Accounts and payment (owner, 2026-09-28; `docs/app-spec.md` §5): Clerk sign-in (email + Google); a Stripe
subscription, monthly or yearly, no trial, access until the end of the paid period after cancelling; free = the
first episode of each level (S1E1, S2E1, S4E1, S6E1). Code goes in GitHub, Replit pulls and runs it.

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
  audio (docs/read-along.md). `scripts/make_audio.py` makes a chapter's MP3 + timing.json with
  Gemini 3.8 Flash TTS **through OpenRouter** (`/api/v1/audio/speech`; style goes in
  `provider.options["google-ai-studio"].speech_metadata`, `instructions` is ignored). S1E1 has
  real audio in the reader (35 min, about $0.30). Audio isn't in git: it lives in **Cloudflare R2**
  (`scripts/storage.py`: `status`, `push <id>|--all`, `pull <id>|--all`; make_audio.py pushes each
  chapter when done). Needs R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (optional R2_BUCKET,
  default input-masters-italian) in the environment, and <account>.r2.cloudflarestorage.com allowed.
  Pull before build_reader.py/export_app.py in a new session. Raw clips stay local (too big).
  Each chapter's audio opens with the narrator reading intro.md in English (owner, 2026-09-28);
  timing.json's `intro` is its [start, end].
- **Voices cast by the owner** (casting page https://claude.ai/artifact/HuGt1bgXgNFkidbkhtGZ1T,
  `scripts/audition.py`): Narratore Charon, Kevin Puck + American accent fading by level, Chiara
  Callirrhoe, Emma Autonoe, Leo Leda, Franco Algenib, Ornella Vindemiatrix, Matteo Umbriel, Nadia
  Aoede, Roberto Orus (config/voices.json).
  The narrator has its own pace at A1/A2 (`pace_by_level`: "calm, unhurried"; the level's "slowly"
  made narration drag). Chosen on the narrator page https://claude.ai/artifact/MYc7LU4WWCCi5PY6CVyQ2g
  (`scripts/narrator_audition.py`). S1E1 audio remade with it: 29.6 min (was 35).
  The characters' A1 pace is now the A2 one, "a little slower than normal, clearly" (owner: full
  slow was hard to listen to; learners have the player's speed control).
- Dialogue target is 45–60% for the book format (owner, 2026-09-26).
- Vocabulary per chapter: A1 22–30 · A2 24–32 · B1 28–36 · B2 27–35, about 6,000 words by the end,
  a high B2 ("B2+"; owner, 2026-09-28). The outline is sent back if it re-teaches a word from
  an earlier chapter; `update_logs.py` prints the running total against the milestones.
- Reader: learner tabs only (Vocabulary, Grammar, Story, Side by side), speed control, and an Anki
  CSV download in Vocabulary (the page declares the `downloads` capability; .apkg isn't allowed).
- TTS: checked against Google's docs (docs/tts-format.md). Styles are short: level pace, Kevin's
  accent, the line's delivery.
- Known: the S5E3 plan sets the chapter in late January though S5 runs Sept–Feb (owner to decide).
  Continuity entries can over-reach or come out in Italian: skim them.

## Next steps

1. Owner's review of the book-format chapters, then production batches from S1E6 (`--jobs 1` keeps
   continuity tight).
2. Owner's listening check of S1E1's audio and read-along; then audio for the other chapters.

## Conventions

- Commit to the working branch, one commit per chapter (`s01e01: <title>`). Never commit `work/`.
- Rules that matter most for content: everything in Italian (occasional single English words only);
  Kevin's mistakes are corrected in the same scene; standard Italian, no dialect; respect
  `bible/timeline.md`; never use grammar beyond the ceiling.
