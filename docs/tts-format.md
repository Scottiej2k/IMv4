# TTS format: Gemini 3.8 Flash TTS

`chapters/<id>/tts.json` is generated from `chapter.json`. It contains an ordered list of API requests
that a feeder script sends one at a time. The resulting WAV clips are then joined in order into the
chapter's audio.

> **Verification status (2026-09-25):** checked against Google's page
> <https://ai.google.dev/gemini-api/docs/speech-generation>. Confirmed: the request shape; speaker
> labels can be any names (e.g. character names); a single-voice request's `speech_config` is an array
> (`[{"voice": "Kore"}]`); multi-speaker requests take at most 2 prebuilt voices, and every turn must
> name its `speaker`. Findings that change how we build requests (to apply with the book format):
>
> - **Keep `style` short or empty.** Google: long persona text in `style` is "the most common cause of
>   voice drift", and age, gender, accent and names must not go in `style`. Build each character once
>   as a voice (Voice design `voice_...`, or an Italian voice from the Extended Voice Library,
>   `GET /v1beta/voices`) and use `style` only for per-line delivery ("proud", "whispering",
>   "speaking slowly"). Designed or replicated voices can't be combined in one multi-speaker request:
>   synthesize each turn separately with those.
> - **More vocal tags** (English tags even for Italian text): `<laugh>` `<chuckle>` `<giggle>` `<sigh>`
>   `<gasp>` `<groan>` `<tsk>` `<phew>`/`<pff>` `<yawn>` `<cough>` `<breath>` `<whispers>` `<cry>`
>   `<sob>` `<snort>` `<throat-clearing>` `<short pause>` `<long pause>` and more. Human sounds only,
>   no sound effects.
> - **Backchannels:** a listener's short reaction inside another speaker's turn, in pipes:
>   `"Ho tre frasi |mm| e sono pronto."`
> - **Emphasis:** capitalised words are stressed; commas, `--` and `...` make natural hesitations.
> - **Output** is WAV with a 44-byte header by default. To join clips, request
>   `{"type": "audio", "mime_type": "audio/l16"}` (raw 24 kHz PCM) or strip each header.
> - `gemini-3.8-flash-lite-tts` is the cheaper bulk model; `gemini-3.8-flash-tts` for best acting.

## Model facts the format is built around

| Fact | Consequence for us |
|---|---|
| Model ids `gemini-3.8-flash-tts` (top quality) and `gemini-3.8-flash-lite-tts` (cheaper) | We default to `gemini-3.8-flash-tts` |
| Uses the **Interactions API** (`POST /v1beta/interactions`) | Requests are stored in that shape |
| Input text is read **verbatim**. Stage directions in the text get spoken aloud | Delivery notes go in `speech_metadata.style`, never in the text |
| Point-in-time vocal events are **inline angle-bracket tags**: `<laugh>` `<sigh>` `<cough>` `<gasp>` `<breath>` `<short pause>` `<long pause>` | Only these tags are allowed in `chapter.json` (**⚠ verify** whether the official list is longer) |
| Native multi-speaker dialogue takes **exactly 2 prebuilt voices** per request | Ensemble scenes are split into chunks of at most 2 voices, and the narrator counts as a voice |
| Conservative text budget: **≤ 5,000 characters** per request, **≤ ~2,500** for dialogue | The chunker packs turns up to these limits |
| Google doesn't guarantee the same voice sounds identical across requests | Every character always gets the same prebuilt voice (`config/voices.json`), and consistent `style` wording helps |
| Output is WAV / 24 kHz 16-bit mono PCM | Clips are joined without resampling |

## Chunking rules

1. Walk the turns in story order.
2. Start a new chunk when adding the next turn would:
   - bring in a **third distinct voice**, or
   - go over **2,500 characters** (dialogue chunk) or **4,500** (single-voice chunk), or
   - cross a **scene boundary**. A `<long pause>` is added between scenes by the joining step, not in the text.
3. A chunk with 2 voices is sent as a **conversational** request. A chunk with 1 voice is sent as a
   **single-speaker** request.
4. Every turn in a conversational request carries a `speaker` in its `speech_metadata`, matching one of
   the two configured speakers.

Chunks never split a turn. A turn longer than the limit is split at segment boundaries.

## Level-based delivery

Each level adds a base style in front of every turn's own `style`:

| Level | Base style |
|---|---|
| A1 | `speaking slowly and very clearly, standard Italian pronunciation` |
| A2 | `speaking a little slower than normal, clearly` |
| B1 | `natural conversational pace` |
| B2 | `natural pace` (none added) |

A turn's final style is `"<level base>; <character default from voices.json>; <turn style>"`.
If a character has a `style_by_level` entry for the chapter's level (Ben's accent fades as the
series goes on), it is added after the character default.

## `tts.json` shape

```json
{
  "chapter": "s01e01",
  "model": "gemini-3.8-flash-tts",
  "chunks": [
    {
      "index": 0,
      "scene": 1,
      "turn_ids": ["s01e01-1-001", "s01e01-1-002"],
      "request": { "...": "body POSTed as-is to /v1beta/interactions" }
    }
  ]
}
```

### Conversational chunk (2 voices)

```json
{
  "model": "gemini-3.8-flash-tts",
  "input": [
    {
      "type": "user_input",
      "content": [
        {
          "type": "text",
          "text": "Buongiorno! Tu sei il nuovo vicino?",
          "annotations": [
            { "type": "speech_metadata", "speaker": "Speaker1",
              "style": "speaking slowly and very clearly, standard Italian pronunciation; warm, curious" }
          ]
        },
        {
          "type": "text",
          "text": "Sì, sono io. <laugh> Mi chiamo Tom.",
          "annotations": [
            { "type": "speech_metadata", "speaker": "Speaker2",
              "style": "speaking slowly and very clearly, standard Italian pronunciation; shy, light American accent" }
          ]
        }
      ]
    }
  ],
  "response_format": { "type": "audio" },
  "generation_config": {
    "speech_config": {
      "mode": "conversational",
      "speakers": [
        { "speaker": "Speaker1", "voice": "Kore" },
        { "speaker": "Speaker2", "voice": "Puck" }
      ]
    }
  }
}
```

Speaker labels are `Speaker1` / `Speaker2` inside each request, following the SDK. The mapping back to
character ids is kept in the chunk's `turn_ids`. (**⚠ verify** whether character names can be used as
labels instead.)

### Single-speaker chunk (narration, monologue)

```json
{
  "model": "gemini-3.8-flash-tts",
  "input": [
    {
      "type": "user_input",
      "content": [
        {
          "type": "text",
          "text": "È sabato mattina nel quartiere. Il sole entra dalla finestra della cucina.",
          "annotations": [
            { "type": "speech_metadata",
              "style": "speaking slowly and very clearly, standard Italian pronunciation; calm, friendly storyteller" }
          ]
        }
      ]
    }
  ],
  "response_format": { "type": "audio" },
  "generation_config": {
    "speech_config": [ { "voice": "Charon" } ]
  }
}
```

(**⚠ verify** that the single-speaker `speech_config` really is an array, as the SDK sends it.)

## `config/voices.json`

This is the only place voices are assigned. It covers each character's prebuilt voice, a default
style (age, temperament, accent where the story calls for one), and the narrator. Voices are chosen
when the cast is final (world-bible phase). No two characters who often share a scene get similar voices.

## Out of scope for now

- Custom or cloned voices (the model supports them, but they don't work in native dialogue requests).
- Word-level timestamps for karaoke-style highlighting in the app (possible later with forced
  alignment, since segment ids already map text to clips).
