# Curriculum: scope and sequence

**200 chapters, A1 → B2, one new concept per chapter, one 45-minute story per concept.**

| File | What it is |
|---|---|
| [`overview.md`](overview.md) | All 200 chapters at a glance: title, grammar, theme, A-plot *(generated)* |
| [`grammar-index.md`](grammar-index.md) | Every grammar concept in teaching order, i.e. the grammar ceiling *(generated)* |
| `seasons/s01.json` … `s08.json` | **The source.** A full plan for each chapter: grammar and scope, theme, key vocabulary, A-plot, B-plot, runner, arc beat |
| `lexicon.csv` | The master lexicon, filled in as chapters are written |

After editing a season file, run `python3 scripts/build_curriculum.py`. It validates the plan and
regenerates the two overview files.

## How the number of chapters was chosen

The rule was **one new concept per chapter, each with a full story**. So the count comes from
listing everything a learner needs to go from zero to B2 and giving each item its own chapter:

| Level | Chapters | Seasons | What those chapters cover |
|---|---|---|---|
| **A1** | 25 | S1 | Present tense (regular, irregular, reflexive, modal), articles, gender and number, adjectives, possessives, prepositions, *piacere*, numbers, time, *stare* + gerund |
| **A2** | 50 | S2–S3 | Passato prossimo (every aspect), every pronoun system, *ci* / *ne*, imperfetto and its contrast with the passato prossimo, imperative (tu/voi/Lei, with pronouns), comparisons, polite conditional, relatives *che* / *cui* |
| **B1** | 50 | S4–S5 | Future (simple, anterior, probability), conditional (present and past), trapassato, pronominal verbs, causatives, the whole congiuntivo presente/passato/imperfetto system, hypotheticals I–II, formal writing, debate |
| **B2** | 75 | S6–S8 | Congiuntivo trapassato, hypotheticals III and mixed, sequence of tenses, three kinds of passive, *si* constructions, implicit clauses (gerund, participle, infinitive), connectors, reported speech, passato remoto, then **register and text types**: legal, journalistic, technical, literary, spoken, rhetorical, humour |

**Why B2 is the largest band:** the step from B1 to B2 is the longest in the CEFR. B2 is less about
new verb forms and more about control, meaning register, precision, argument, idiom and different
kinds of text. Most of those need a whole story to practise properly.

Nothing is taught twice. The build script enforces that every grammar id is unique. Each season ends
with a **review chapter** that pulls the season together, and those also have their own concept id.

## How long the course takes

| | Per chapter | Whole course |
|---|---|---|
| Story (reading, or listening with the text) | 45 min | 150 h |
| Grammar lesson + vocabulary list | ~20 min | ~65 h |
| Anki review (daily, spread out) | ~5–10 min | ~25 h |
| **Total** | **~75 min** | **~240 h** |

This is close to your original estimate of 200 hours. Learners who listen to each story's audio a
second time, which is highly recommended, add about 100–150 hours.

**How much learners read and learn:**
- **Reading volume:** about 1 million words of Italian across the course (A1 ~75k, A2 ~195k,
  B1 ~260k, B2 ~490k), a volume associated with strong reading and listening comprehension.
- **Vocabulary:** about 6,900 focus items (words and phrases) across the course, adding up to a
  vocabulary of roughly 4,000–5,000 words by the end. That is in line with B2.

> **What this course does not cover alone:** it builds reading, listening, vocabulary and grammar
> to B2. Speaking and writing at B2 also need production practice, such as conversation and
> writing with feedback. The learner app could add optional speaking/writing prompts per chapter
> later, since the stories supply the context.

## How grammar and story fit together

Each season's story needs the grammar the season teaches:

| Season | Story | Why the grammar fits |
|---|---|---|
| S1 *Benvenuti* | Arrival, a new life | Everything happens *now*: the present tense |
| S2 *Lavori in corso* | A renovation where everything goes wrong | Everyone reports *what happened*: passato prossimo |
| S3 *Radici* | Anna's memory, old letters | *How things used to be*: imperfetto |
| S4 *Progetti* | The wedding and a new business | *Plans and advice*: future and conditional |
| S5 *Se potessi…* | The Chicago offer and an election | *Opinions, doubts, what if*: subjunctive and hypotheticals |
| S6 *Il parco* | Saving the park | *Procedures and persuasion*: passive, formal register, connectors |
| S7 *Nuovi arrivi* | The newcomers, a heart scare, the street's history | *Retelling and history*: reported speech, passato remoto |
| S8 *Maturità* | Emma's final exams | *Mastery*: register, rhetoric, style |

## Reading a chapter plan

```jsonc
{
  "id": "s01e10",                      // chapter id (season 1, episode 10)
  "level": "A1",
  "title": { "it": "...", "en": "..." },
  "grammar": {
    "id": "g-present-ere-ire",         // unique concept id; becomes grammar_focus in chapter.json
    "name": "...",
    "scope": "..."                     // exactly what is taught (and therefore allowed from here on)
  },
  "theme": "...",                      // vocabulary domain
  "key_vocab": ["..."],                // 8–10 anchor words: the backbone, not the full list
  "a_plot": "...", "b_plot": "...",    // the storylines
  "runner": "...",                     // optional running gag
  "arc": "..."                         // how it moves the season or series arc
}
```

**`key_vocab` holds anchors, not the final list.** The full vocabulary list for a chapter (20–45
items, depending on level) is written with the chapter and recorded in `lexicon.csv`. Anchors that
appear in more than one plan are deliberate: they come back in a new grammatical context, such as
*vorrei* as a fixed phrase at A1 and as a true conditional at A2.

## `lexicon.csv`

This is the running record of every focus item, written after each chapter is final.

| Column | Meaning |
|---|---|
| `lemma` | Dictionary form or full phrase |
| `pos` | Part of speech (as in the chapter schema) |
| `gender` | m / f / m/f for nouns |
| `en` | Main English gloss |
| `level` | Level of the chapter that introduced it |
| `introduced` | Chapter id where it was first a focus item |
| `recycled` | Later chapter ids where it came back (at least 2 expected) |

The build scripts will use it to check each new chapter's coverage (at least 95% known words) and
to report which items are due for recycling.
