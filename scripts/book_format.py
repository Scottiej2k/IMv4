#!/usr/bin/env python3
"""The book format: prose lines with marked speech and thoughts (see docs/draft-format.md).

A story line is `Italian || English`. Inside the Italian:
    «Buongiorno!»{ben}            speech, voiced by ben
    «Piano...»{ben|whispering}    speech with a short English delivery note
    _Dov'è?_{ben}                 a thought, voiced by ben quietly, shown in italics
Everything else on the line is narration, read by the narrator. A blank line starts a paragraph.

split_voices() turns a line into the pieces the audio needs; book_text() gives the reader's text.
In stored text, thoughts are `_…_` on both sides (so a single `*` never clashes with `**bold**`).
"""
import re

STORY_RE = re.compile(r"^(?P<it>.+?)\s*\|\|\s*(?P<en>.+?)\s*$")
LONE_STAR_RE = re.compile(r"(?<!\*)\*(?!\*)")

MARK_RE = re.compile(r"«(?P<speech>.+?)»\{(?P<sid>[a-z][a-z-]*)(?:\|(?P<sd>[^}]*))?\}"
                     r"|_(?P<thought>.+?)_\{(?P<tid>[a-z][a-z-]*)(?:\|(?P<td>[^}]*))?\}")
THOUGHT_STYLE = "thinking to themself, quiet and close"


def split_voices(italian):
    """[(speaker, text, style)] in reading order; narration has speaker 'narrator'."""
    pieces, pos = [], 0
    for m in MARK_RE.finditer(italian):
        before = italian[pos:m.start()].strip(" ,")
        if before:
            pieces.append(("narrator", before, ""))
        if m.group("speech") is not None:
            pieces.append((m.group("sid"), m.group("speech").strip(), (m.group("sd") or "").strip()))
        else:
            style = ", ".join(s for s in (THOUGHT_STYLE, (m.group("td") or "").strip()) if s)
            pieces.append((m.group("tid"), m.group("thought").strip(), style))
        pos = m.end()
    rest = italian[pos:].strip(" ,")
    if rest:
        pieces.append(("narrator", rest, ""))
    return pieces


def book_text(italian):
    """The line as a reader sees it: «speech» kept, speaker marks hidden, thoughts as _italics_."""
    def show(m):
        if m.group("speech") is not None:
            return f"«{m.group('speech')}»"
        return f"_{m.group('thought')}_"
    return MARK_RE.sub(show, italian)


def english_text(english):
    """The English with thoughts as _italics_ (writers use *…*, also as ***bold start** … *)."""
    english = re.sub(r"(?<!\S)\*\*\*(?=\S)", "_**", english)
    english = re.sub(r"(?<=\S)\*\*\*(?!\w)", "**_", english)
    return LONE_STAR_RE.sub("_", english)


def voiced_share(pieces):
    """Characters' words / all words in a line's pieces (for the dialogue share)."""
    total = sum(len(t.split()) for _, t, _ in pieces)
    spoken = sum(len(t.split()) for w, t, _ in pieces if w != "narrator")
    return spoken, total


def speakers(italian):
    return [m.group("sid") or m.group("tid") for m in MARK_RE.finditer(italian)]
