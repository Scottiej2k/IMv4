# TTS format: Gemini 3.8 Flash TTS

`chapters/<id>/tts.json` is generated from `chapter.json`. It contains an ordered list of API requests
that a feeder script sends one at a time. The resulting WAV clips are then joined in order into the
chapter's audio.

> **Verification status:** the official docs page
> (<https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts>) couldn't be reached from the
> environment that wrote this spec. The request shape below comes from an open-source SDK that already
> ships Gemini 3.8 TTS support (Jellypod `speech-sdk`, v0.32.0), plus Google's migration notes. Before
> the first full audio run, check the items marked **⚠ verify** against the official page. Because
> `tts.json` is generated, a correction only means changing the build script, not the chapters.

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
