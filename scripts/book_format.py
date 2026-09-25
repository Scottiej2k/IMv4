#!/usr/bin/env python3
"""The book format: prose lines with marked speech and thoughts (see docs/draft-format.md).

A story line is `Italian || English`. Inside the Italian:
    «Buongiorno!»{ben}            speech, voiced by ben
    «Piano...»{ben|whispering}    speech with a short English delivery note
    _Dov'è?_{ben}                 a thought, voiced by ben quietly, shown in italics
Everything else on the line is narration, read by the narrator. A blank line starts a paragraph.

split_voices() turns a line into the pieces the audio needs; book_text() gives the reader's text.
"""
import re

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
    """The line as a reader sees it: «speech» kept, speaker marks hidden, thoughts in *italics*."""
    def show(m):
        if m.group("speech") is not None:
            return f"«{m.group('speech')}»"
        return f"*{m.group('thought')}*"
    return MARK_RE.sub(show, italian)


def speakers(italian):
    return [m.group("sid") or m.group("tid") for m in MARK_RE.finditer(italian)]
