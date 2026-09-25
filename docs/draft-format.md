# Draft format

Writers (human or model) write a chapter in this plain-text format as `chapters/<id>/draft.txt`.
`scripts/convert_draft.py <id>` turns it into `chapter.json` + `grammar.md` and builds every output.
The writer never deals with ids, JSON, focus tags or example selection; the converter does that.

The story is **a book**: prose paragraphs with the characters' speech in Italian quotation marks,
read like a graded reader. The marks below say who voices each piece of speech or thought, so the
same text also drives the audiobook (narrator plus one voice per character).

## Shape

```
@vocab
ciao | interjection | | hi; bye | Ciao
il vicino | noun | m | neighbour | vicino, vicina, vicini, Vicino
essere americano | expression | | to be American | sono americano, sei americana, è americano | Nationality adjectives agree: americano/americana.
@end

# SCENE via | sabato mattina | ben, ornella
È sabato mattina in Via dei Tigli. || It's Saturday morning on Via dei Tigli.
Ben esce di casa con un sorriso enorme. || Ben comes out of the house with a huge smile.

«**Ciao**!»{ben|too loud} Ben saluta la strada. «Io **sono** Ben!»{ben} || “**Hi**!” Ben greets the street. “I **am** Ben!”
_Tre frasi. Solo tre frasi._{ben} || *Three sentences. Just three sentences.*

Alla finestra del numero sedici c'è una signora elegante. || At the window of number sixteen there's an elegant lady.
«Buongiorno. <short pause> Lei è americano?»{ornella|cool, formal} || “Good morning. Are you American?”

@grammar
# Essere: "to be"
...lesson in Markdown...
From the story: [[Io sono Ben!]]
```

## Rules

**Vocabulary block** (`@vocab` … `@end`), one item per line:
`lemma | part of speech | gender | English | other bolded forms (comma-separated) | note (optional)`

- Part of speech: noun, verb, adjective, adverb, pronoun, preposition, conjunction, determiner,
  interjection, expression, number. Gender only for nouns: `m`, `f` or `m/f`.
- **Forms**: every spelling you will bold in the story for this item, other than the lemma itself.
  Examples: conjugated verbs (`abito, abita, abitano`), feminine and plural forms, and a capital
  letter at the start of a sentence. Matching ignores case and end punctuation, so `Ciao!` matches
  `ciao`. The article in the lemma is optional when you bold it (`il vicino` also matches `vicino`).
- No two items may share a form.

**Scenes**: `# SCENE location-id | time | character ids, comma-separated`
- Location ids come from `config/locations.json`; character ids from `config/voices.json`.
- There are no talking-head monologues: what a character would tell the camera becomes their
  thoughts inside a scene.

**Story lines**: `Italian || English`, one sentence per line. Each line is one row of the
side-by-side translation. **A blank line starts a new paragraph.** Paragraph as in a novel: a new
paragraph when a different character speaks; one character's action, speech and thoughts share a
paragraph.

**Speech and thoughts** (in the Italian only):
- Speech: `«…»{id}` or `«…»{id|delivery}`. The Italian inside the quotation marks is voiced by that
  character; `{id}` comes straight after the closing `»`. The English uses “…” and no marks.
- Thoughts: `_…_{id}` (shown in italics, voiced by that character quietly). The English uses `*…*`.
- `delivery` is a short English note for the audio: `whispering`, `too loud`, `dry`, `laughing`.
  Leave it out when the delivery is ordinary. Never describe the voice itself (age, accent).
- Everything outside `«…»` and `_…_` is narration, read by the narrator: dialogue tags (*dice Ben*),
  actions and descriptions.
- `id` is a character id from `config/voices.json`. A minor character without an id (a customer, a
  stranger) uses `uomo`, `donna` or `bambino`; the narration can give their name.
- Audio tags go only inside `«…»` or `_…_`, and only human sounds: `<laugh>` `<chuckle>` `<giggle>`
  `<sigh>` `<gasp>` `<groan>` `<tsk>` `<phew>` `<yawn>` `<cough>` `<breath>` `<whispers>` `<sob>`
  `<short pause>` `<long pause>`.

**Bold** marks focus items: vocabulary items (any listed form) and examples of the grammar focus.
**Bold the English equivalent too, with the same number of bold spans in the same order.** A bold
span that matches no vocabulary form counts as a grammar-focus example. Bold each vocabulary item as
its own span (`è **americano**`, not `**è americano**`).

**Grammar lesson** (`@grammar` to the end of the file): Markdown. To quote the story, write the exact
Italian sentence in double brackets, without bold and without the `{id}` marks: `[[«Io sono Ben!»]]`
or just the spoken words, `[[Io sono Ben!]]`. The converter replaces it with the quote, its
translation and its segment id.

Lines starting with `//` are comments.
