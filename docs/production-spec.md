# Production spec

This is the rulebook for every chapter. If a chapter breaks a rule here, fix either the chapter or
this document, but not neither.

## 1. Scope

- **200 chapters**, A1 → B2, in 8 seasons of 25 episodes: one new concept per chapter
  (see `curriculum/README.md` for how the count was reached).
- Every chapter = **lesson** (vocabulary + grammar, roughly 15–25 min) **plus a story of about 45 minutes'
  reading time at the learner's level**.
- **Language:** strictly standard Italian. Colloquial phrases, figures of speech and idioms are welcome;
  regional dialect is not used for now.
- **Setting:** a residential neighbourhood outside a major Italian city. Daily life is suburban;
  city dialogue comes naturally from trips, commutes and references to the nearby metro area.

### Level plan

| Level | Seasons | Chapters | Reading speed assumed | Story length (Italian words) |
|---|---|---|---|---|
| A1 | S1 | 25 | 60–70 wpm | 2,700–3,200 |
| A2 | S2–S3 | 50 | 80–90 wpm | 3,600–4,200 |
| B1 | S4–S5 | 50 | 105–120 wpm | 4,800–5,500 |
| B2 | S6–S8 | 75 | 130–150 wpm | 6,000–7,000 |

Each season's story arc sits inside one level band, so a season finale is also a level milestone.

## 2. Language control

Graded content drifts upward unless it is measured, so every chapter is checked against the master
lexicon (`curriculum/lexicon.csv`).

- **Coverage:** at least **95%** of running words (excluding proper nouns) must be known, meaning they
  were introduced in an earlier chapter, are in this chapter's vocabulary list, or are on the level's
  "free" list (transparent cognates, numbers, names of places).
  Target **98%** at A1–A2.
- **New focus items per chapter:** A1 20–30 · A2 25–35 · B1 30–40 · B2 35–45.
- **Recycling:** each focus item appears **at least 3 times** in its own chapter and comes back in at
  least 2 later chapters (tracked in the lexicon).
- **Grammar ceiling:** a chapter may only use structures introduced up to that chapter
  (`curriculum/grammar-index.md` lists them in order). Harder structures may appear as fixed phrases
  (for example *vorrei* at A1) if they are glossed in the vocabulary list.
- **Sentence length guide** (average words per sentence): A1 ≤ 8 · A2 ≤ 12 · B1 ≤ 16 · B2 free.

## 3. Story rules

- **Dialogue-rich book:** aim for 45–60% of words in speech and thoughts (owner, 2026-09-26; the
  stories are written as a book, where dialogue tags and description count as narration). Narration sets scenes, keeps speaker
  changes clear and handles action.
- **Structure:** 4–7 scenes. There is an A-plot and usually a B-plot (sitcom style), with at least one
  beat moving the season arc forward. Each chapter works on its own but rewards people who keep reading.
- **Continuity:** before writing a chapter, read `bible/continuity-log.md`. After writing, add one entry
  (what happened, what changed, new facts established).
- **Voice:** characters talk as their speech profile in `bible/` says. At A1 the profiles are chosen so
  simple speech is believable (kids, a newcomer learning Italian, grandparents, small talk).
- **Focus items** are bolded wherever they appear in the story, and the grammar focus is bolded when it
  illustrates the chapter's point. Don't bold everything: roughly 1 bold per 2–3 sentences at most.

## 4. Files per chapter

```
chapters/s01e01/
  chapter.json   authored source (validated by schema/chapter.schema.json)
  grammar.md     authored grammar lesson
  story.md       generated
  parallel.md    generated
  vocab.md       generated
  anki.csv       generated
  tts.json       generated
```

Chapter ids are `sNNeNN`. Generated files are committed so they can be read on GitHub, but they are
never edited by hand. Change `chapter.json` and rebuild instead.

### 4.1 `chapter.json`: the source

The full definition is in `schema/chapter.schema.json`. In short:

- **Metadata:** id, season, episode, level, Italian/English titles, grammar focus ids, and the vocabulary theme.
- **`vocab[]`:** focus items. Each has an `id`, `lemma`, part of speech, gender if it's a noun, an English
  gloss, and **`example`: the id of the story segment used as its example sentence** (so the vocabulary
  list and Anki cards always quote the real story).
  **`target`** gives the exact bolded words for the item on each side (`{"it": "abita", "en": "lives"}`),
  so a card bolds only its own word even if the sentence has other focus items.
- **`scenes[]`**, each with a location, the characters present, and `turns[]`.
  - A **turn** is one speaker's uninterrupted stretch: `speaker` (a character id or `narrator`), an
    optional `style` (spoken delivery, used by TTS only), and `segments[]`.
  - A **segment** is one sentence or phrase: `id`, `it`, `en`, and optional `focus` (vocab or grammar
    ids it illustrates). **Segments are the rows of the parallel translation.**

Inline markup in `it` / `en`:

| Markup | Meaning | Story / parallel | TTS |
|---|---|---|---|
| `**parola**` | focus item | bold | markers removed |
| `<laugh>`, `<sigh>`, `<cough>`, `<gasp>`, `<breath>`, `<short pause>`, `<long pause>` | audio tag (in `it` only) | removed | kept verbatim |

Segment ids are stable and globally unique: `s01e01-3-014` means chapter s01e01, scene 3, segment 14.

### 4.2 `vocab.md` (generated)

| Italiano | English |
|---|---|
| Mia sorella **abita** a Milano. | My sister **lives** in Milan. |

Grouped by part of speech, with the lemma and gender shown above each example.

### 4.3 `anki.csv` (generated)

UTF-8 CSV that uses Anki's file headers, so it imports without any setup:

```
#separator:comma
#html:true
#columns:Italiano,English,Lemma,Notes,Tags
#tags column:5
"Mia sorella <b>abita</b> a Milano.","My sister <b>lives</b> in Milan.","abitare (v.)","","IMv4 A1 s01e01"
```

### 4.4 `parallel.md` (generated)

A two-column table, one row per segment, with a scene heading before each scene. Speaker names appear
in the Italian column (`**Giulia:** …`).

### 4.5 `grammar.md` (authored)

1. What it is (short, plain English).
2. How it works (tables and rules).
3. **From the story:** 5–10 examples quoted by segment id (the build step checks the ids exist).
4. Common mistakes for English speakers.
5. A short practice section with an answer key.

### 4.6 `tts.json` (generated)

See `docs/tts-format.md`.

## 5. Workflow per chapter

The writer never hand-writes JSON, and never writes a whole chapter in one go.

1. **Scene by scene** (`scripts/pipeline.py`): the writer first returns the vocabulary block and an
   outline (scenes, beats, a word budget per scene, which vocabulary each scene uses), then writes
   each scene against its budget, then the grammar lesson. A scene under 75% of its budget is sent
   back once to be expanded. With an API key, `python3 scripts/generate_chapter.py <id>` runs the
   whole conversation; an agent or person can drive the same steps with `pipeline.py start/submit`.
2. The prompts come from `scripts/make_brief.py`: standing instructions (`prompts/writer-system.md`),
   the draft format (`docs/draft-format.md`), the world bible, and a chapter brief with level rules,
   the grammar ceiling as concrete forbidden forms, **where things stand** (`bible/timeline.md`:
   tu/Lei, secrets, who lives where), the plan, the characters and the story so far.
3. The pipeline assembles `draft.txt` and runs `scripts/convert_draft.py` (ids, turns, focus tags,
   vocab examples and targets, grammar citations, validation, all outputs) and
   `scripts/grammar_rules.py` (flags forms of grammar not taught yet).
4. Converter errors, grammar-ceiling flags and bold mismatches go back as **one** list of line fixes.
   Remaining warnings are for review; don't loop on them.
5. A chapter that builds gets its continuity-log entry from the writer (`chapters/<id>/continuity.md`),
   then `scripts/update_logs.py` rebuilds `curriculum/lexicon.csv` and the log's episode entries from
   all chapters, in chapter order. Review the entry; if the chapter changes something lasting, update
   `bible/timeline.md` by hand.
6. Commit the chapter as one commit: `s01e01: <title>`. `scripts/run_batch.py` does steps 1–6 for
   several chapters at once, each in its own git worktree.

## 6. Quality

- A native speaker spot-checks at least 2 chapters per season (register, idiom, naturalness).
- The first chapters of each level are pilots. Adjust this spec before mass production, not after.
