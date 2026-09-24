# Draft format

Writers (human or model) write a chapter in this plain-text format as `chapters/<id>/draft.txt`.
`scripts/convert_draft.py <id>` turns it into `chapter.json` + `grammar.md` and builds every output.
The writer never deals with ids, JSON, focus tags or example selection; the converter does that.

## Shape

```
@vocab
ciao | interjection | | hi; bye | Ciao
il vicino | noun | m | neighbour | vicino, vicina, vicini, Vicino
essere americano | expression | | to be American | sono americano, sei americana, è americano | Nationality adjectives agree: americano/americana.
@end

# SCENE via | sabato mattina | ben, ornella, roberto
NARRATOR: È sabato mattina in Via dei Tigli. || It's Saturday morning on Via dei Tigli.
BEN [nervous, too loud]: **Ciao!** Io **sono** Ben. || **Hi!** I **am** Ben.
BEN: Sono il nuovo **vicino**. || I'm the new **neighbour**.
ORNELLA [cool, formal]: Buongiorno. <short pause> Lei è americano? || Good morning. Are you American?

# CONFESSIONALE ben
BEN: Mi chiamo Ben. Sono americano. || My name is Ben. I'm American.

@grammar
# Essere: "to be"
...lesson in Markdown...
From the story: [[Io sono Ben.]]
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

**Scenes**
- `# SCENE location-id | time (optional) | character ids, comma-separated`
- `# CONFESSIONALE character-id`: a talking-head monologue, one speaker talking to the reader.
- Location ids come from `config/locations.json`. Character ids and names come from `config/voices.json`.

**Lines**: `SPEAKER [delivery]: Italian || English`
- One sentence (or short phrase) per line. Each line becomes one row of the parallel translation.
- `SPEAKER` is `NARRATOR` or a character name in capitals (`BEN`, `MAESTRA PAOLA`).
  Consecutive lines by the same speaker form one turn.
- `[delivery]` is optional: a short English note for the audio (`whispering`, `annoyed, fast`).
  It starts a new turn. Never put stage directions inside the Italian or English text.
- Audio tags go only in the Italian, and only these: `<laugh>` `<sigh>` `<cough>` `<gasp>`
  `<breath>` `<short pause>` `<long pause>`.
- `**bold**` marks focus items: vocabulary items (any listed form) and examples of the grammar
  focus. **Bold the English equivalent too, with the same number of bold spans in the same order.**
  A bold span that matches no vocabulary form counts as a grammar-focus example.

**Grammar lesson** (`@grammar` to the end of the file): Markdown. To quote the story, write the exact
Italian sentence in double brackets, `[[Io sono Ben.]]`, without bold. The converter replaces it with
the quote, its translation and its segment id. The quote must match a story line exactly
(ignoring bold and end punctuation).

Lines starting with `//` are comments.
