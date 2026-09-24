# IMv4 — Italian from A1 to B2, one story at a time

About 200 chapters of graded Italian learning content (A1 → B2), built around one continuing
ensemble sitcom set in a residential neighbourhood outside a major Italian city. Every chapter pairs a
lesson (vocabulary + grammar) with roughly 45 minutes of original, dialogue-heavy reading, plus a
parallel translation, an Anki deck and a script ready for Gemini 3.8 TTS audio.

This repository is the **content factory**. A learner-facing app will be built later on top of the
JSON it produces.

## How the content is made

Each chapter has **one hand-authored source file** (`chapters/<id>/chapter.json`) and one authored
grammar lesson (`chapters/<id>/grammar.md`). Everything else is **generated** from the source by
scripts, so the Italian, the English, the bolding and the audio can never drift apart.

```
chapter.json ──► story.md        Italian story, focus items bolded
             ──► parallel.md     Italian | English, one row per sentence/phrase
             ──► vocab.md        Italian phrase | English, target word bolded on both sides
             ──► anki.csv        importable Anki deck
             ──► tts.json        ordered, ready-to-send Gemini 3.8 TTS requests
grammar.md   (authored; cites story lines by id)
```

## Layout

| Path | What lives there |
|---|---|
| `docs/production-spec.md` | The rules: chapter lengths, level targets, file formats, workflow |
| `docs/tts-format.md` | How the Gemini 3.8 TTS scripts are structured and chunked |
| `docs/draft-format.md` | The plain-text format writers use (converted to `chapter.json` by script) |
| `schema/chapter.schema.json` | JSON Schema every `chapter.json` must pass |
| `config/voices.json` | One fixed TTS voice per character (single source of truth; provisional until auditioned) |
| `bible/` | World bible: [premise & format](bible/world-bible.md), [cast](bible/characters.md), [locations](bible/locations.md), [season arcs](bible/season-arcs.md), [continuity log](bible/continuity-log.md), [timeline](bible/timeline.md) |
| `curriculum/` | [Scope and sequence](curriculum/README.md), per-chapter plans (`seasons/`), [overview](curriculum/overview.md), [grammar index](curriculum/grammar-index.md), master lexicon |
| `chapters/` | One folder per chapter, e.g. `chapters/s01e01/` |
| `scripts/` | `generate_chapter.py` (API) / `pipeline.py` (scene-by-scene steps) → `convert_draft.py` → `build_chapter.py`; plus `make_brief.py`, `grammar_rules.py`, `build_curriculum.py` |
| `prompts/` | The writer's standing instructions |

## Status

- [x] Production spec and repo scaffolding
- [x] World bible (`bible/`)
- [x] Curriculum: 200 chapters planned ([overview](curriculum/overview.md))
- [x] Build and validation scripts (`scripts/build_curriculum.py`, `scripts/build_chapter.py`)
- [ ] Pilot chapters (one A1, one B1)
- [ ] Production
