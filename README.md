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
| `schema/chapter.schema.json` | JSON Schema every `chapter.json` must pass |
| `config/voices.json` | One fixed TTS voice per character (single source of truth) |
| `bible/` | World bible: setting, cast, speech profiles, season arcs, continuity log |
| `curriculum/` | Scope and sequence, per-chapter plan, master lexicon |
| `chapters/` | One folder per chapter, e.g. `chapters/s01e01/` |
| `scripts/` | Build and validation scripts |

## Status

- [x] Production spec and repo scaffolding
- [ ] World bible
- [ ] Curriculum + master lexicon
- [ ] Build/validation scripts
- [ ] Pilot chapters (one A1, one B1)
- [ ] Production
