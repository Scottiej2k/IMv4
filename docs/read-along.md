# Read-along: word highlighting while the audio plays

What the learner sees: while the chapter audio plays, each word is underlined as it is spoken, and
everything already played stays underlined. They can pause and later resume where they left off,
or choose **Play from here** on any sentence in the story or the side-by-side view.

Gemini 3.8 TTS returns audio only, with no word timings (checked against Google's docs,
2026-09-26). So timings come from a **forced aligner** run on the finished audio: given a clip and
the exact words spoken in it, it returns when each word starts and ends. This works well for
Italian (e.g. a wav2vec2 Italian CTC model through `torchaudio.functional.forced_align`, or
WhisperX), and because we give it the exact words, it doesn't have to recognise anything.

## What the content already provides

- **Word ids** (`chapter.json`): every segment has `tokens`, the sentence as shown, split into
  `[text, word index or -1, flags]` (`flags`: `b` bold, `i` italic thought). Word *i* of segment
  `s01e01-1-004` has the id `s01e01-1-004.i`. Words are letters or digits with inner apostrophes
  (*l'acqua*, *c'è* are one word; *14* is a word, spoken "quattordici"). Everything else (spaces,
  punctuation, « ») is shown but never timed. An app renders the tokens and puts the word id on
  each word.
- **Which words each audio request speaks** (`tts.json`): each chunk has `words`, one list per
  text item in its request, of spans like `"s01e01-1-010:0-3"` (words 0 to 3 of that segment).
  The aligner uses these to know exactly which displayed words each clip contains, in order.
- The build checks that every segment shows exactly the words its audio speaks, so highlighting
  can't drift (a warning names any segment that would).

## What the audio step will produce: `chapters/<id>/audio/`

- One clip per TTS chunk (raw 24 kHz PCM, `audio/l16`), and the joined chapter audio
  (`chapter.mp3` or similar), with 1.5 s of silence between scenes.
- `timing.json`, on the joined audio's clock:

```json
{
  "chapter": "s01e01",
  "audio": "chapter.mp3",
  "duration": 1834.2,
  "clips": [{"chunk": 0, "scene": 1, "start": 0.0, "end": 12.35}],
  "segments": {"s01e01-1-001": [0.00, 3.12]},
  "words": {"s01e01-1-001.0": [0.00, 0.21], "s01e01-1-001.1": [0.21, 0.58]}
}
```

`words` gives [start, end] in seconds for every word id; `segments` the span of each sentence (its
first word's start to its last word's end), which is where **Play from here** seeks.

## How an app uses it

- **Underline as it plays:** on each audio time update, underline every word whose start ≤ the
  current time. Keep the set of played words (per chapter, per learner) so that everything already
  heard stays underlined, even after jumping around.
- **Play from here:** tap a sentence → seek to `segments[id][0]` and play.
- **Resume:** save the current time (and the played set) when the learner pauses or leaves;
  offer "Resume" from that time next visit.

The review reader demonstrates this behaviour now with the browser's built-in Italian voice, which
reports word boundaries as it speaks. With real audio it switches to `timing.json`.

## How the audio is made now: `scripts/make_audio.py`

```
python3 scripts/make_audio.py s01e01                    # Gemini TTS: needs GEMINI_API_KEY
python3 scripts/make_audio.py s01e01 --engine standin   # OpenRouter stand-in voices, for testing
```

- Every text item of `tts.json` (one speaker's turn) becomes its own single-voice clip, so each
  turn's start and end in the chapter are exact. Clips are cached in `audio/clips/`.
- Inside a clip, word times are estimated: the voiced part (silence trimmed) is shared out by
  syllables, with pauses after commas and full stops. Turns are short, so the underline stays close;
  a forced aligner could refine it later, but its models can't be downloaded in this environment
  (huggingface.co and download.pytorch.org are blocked).
- The clips are joined with short gaps (longer between speakers and scenes) and encoded as a 32
  kbit/s mono MP3 (S1E1: 22 minutes, 5.4 MB). Needs `pip install numpy lameenc`.
- The stand-in (`openai/gpt-audio-mini`) is a chat model that sometimes answers instead of reading;
  each stand-in clip is checked against its own transcript and retried until it matches. Gemini
  TTS reads verbatim, so it doesn't need this.
- Audio files stay out of git (`chapters/*/audio/` is ignored); they're regenerated from `tts.json`.

The review reader uses `chapter.mp3` and `timing.json` when a chapter has them (S1E1 so far), and
the browser's voice otherwise.
