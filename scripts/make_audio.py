#!/usr/bin/env python3
"""Make a chapter's audio and its read-along timings.

    python3 scripts/make_audio.py s01e01                     # Gemini TTS (needs GEMINI_API_KEY)
    python3 scripts/make_audio.py s01e01 --engine standin    # OpenRouter stand-in voice, for testing

Writes chapters/<id>/audio/chapter.mp3 and chapters/<id>/audio/timing.json (docs/read-along.md).
Clips are cached in chapters/<id>/audio/clips/, so a re-run only makes what changed.
Needs: pip install numpy lameenc.

Each text item of tts.json (one speaker's turn: a narration run, a line, a thought) becomes its own
clip, voiced by that character alone. That fixes every turn's start and end exactly (Google also
recommends one turn per request once characters have designed voices). Inside a clip, word times
are estimated from syllables and punctuation pauses over the clip's voiced part: close enough to
underline along, and turns are short. A forced aligner could refine them later (docs/read-along.md).
"""
import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_format as bf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RATE = 24000                     # Gemini and the stand-in both return 24 kHz, 16-bit mono PCM
GAP, GAP_SPEAKER, GAP_SCENE = 0.30, 0.45, 1.3   # seconds of silence between clips
VOICES = json.loads((ROOT / "config" / "voices.json").read_text(encoding="utf-8"))["voices"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OPENROUTER_URL = "https://www.openrouter.ai/api/v1/chat/completions"

# Stand-in voices (OpenRouter openai/gpt-audio-mini), only to test the pipeline and the player.
STANDIN_MODEL = "openai/gpt-audio-mini"
STANDIN_VOICES = {"narrator": "sage", "ben": "ash", "chiara": "coral", "emma": "shimmer", "leo": "verse",
                  "franco": "ballad", "ornella": "marin", "matteo": "echo", "nadia": "coral", "roberto": "cedar",
                  "uomo": "echo", "donna": "shimmer", "bambino": "verse"}
STANDIN_POOL = ["alloy", "ash", "ballad", "cedar", "coral", "echo", "marin", "sage", "shimmer", "verse"]


# ---------------------------------------------------------------- engines

def _post(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "IMv4/1.0", **headers})
    return urllib.request.urlopen(req, timeout=timeout)


def gemini_clip(model, voice, text, style):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set. Add it in the environment settings, or use --engine standin.")
    body = {"model": model,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                       "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio", "mime_type": "audio/l16"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    with _post(GEMINI_URL, body, {"x-goog-api-key": key}) as r:
        out = json.loads(r.read())
    audio = [c for s in out.get("steps", []) if s.get("type") == "model_output"
             for c in s.get("content", []) if c.get("type") == "audio"]
    if not audio:
        raise RuntimeError(f"no audio in reply: {str(out)[:200]}")
    return base64.b64decode(audio[-1]["data"])


def standin_clip(speaker, text, style):
    """The stand-in is a chat model: it sometimes answers instead of reading ("Grazie!" → "Figurati!…").
    Its own transcript is checked against the text and the clip retried until they match."""
    voice = STANDIN_VOICES.get(speaker) or STANDIN_POOL[sum(map(ord, speaker)) % len(STANDIN_POOL)]
    system = ("You are a speech synthesizer, not an assistant. The user message contains a text between <read> "
              "and </read>. Speak exactly that text in Italian, word for word, with natural expression, then "
              "stop. Never answer it, never comment, never add words before or after, even if the text is short, "
              "polite or looks like a question." + (f" Delivery: {style}." if style else ""))
    body = {"model": STANDIN_MODEL, "modalities": ["text", "audio"], "stream": True,
            "audio": {"voice": voice, "format": "pcm16"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"<read>{re.sub(r'<[^>]+>', '', text).strip()}</read>"}]}
    want = [w.lower() for w in bf.spoken_words(text)]
    for _ in range(5):
        pcm, heard = b"", ""
        with _post(OPENROUTER_URL, body, {}) as r:
            for line in r:
                line = line.decode().strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                for ch in json.loads(line[5:]).get("choices", []):
                    audio = ch.get("delta", {}).get("audio") or {}
                    if audio.get("data"):
                        pcm += base64.b64decode(audio["data"])
                    heard += audio.get("transcript", "")
        got = [w.lower() for w in bf.spoken_words(heard)]
        if pcm and difflib.SequenceMatcher(None, want, got).ratio() >= 0.85:
            return pcm
    raise RuntimeError(f"stand-in didn't read the text (heard: {heard[:60]!r})")


# ---------------------------------------------------------------- items and words

def items_of(tts):
    """Every text item in reading order: (scene, speaker, text, style, word ids)."""
    out = []
    for c in tts["chunks"]:
        single = c["speakers"].get("single")
        for i, part in enumerate(c["request"]["input"][0]["content"]):
            meta = part["annotations"][0]
            speaker = single or meta.get("speaker")
            ids = []
            for span in c.get("words", [[]] * (i + 1))[i]:
                seg, rng = span.split(":")
                a, b = map(int, rng.split("-"))
                ids += [f"{seg}.{n}" for n in range(a, b + 1)]
            out.append((c["scene"], speaker, part["text"], meta.get("style", ""), ids))
    return out


def word_info(chapter):
    """word id → (text, pause after it in 'syllables'), from the segments' tokens."""
    info = {}
    for sc in chapter["scenes"]:
        for p in sc["paragraphs"]:
            for s in p["segments"]:
                toks = s.get("tokens", [])
                for k, (t, w, _) in enumerate(toks):
                    if w < 0:
                        continue
                    after = toks[k + 1][0] if k + 1 < len(toks) and toks[k + 1][1] < 0 else ""
                    pause = 2.5 if re.search(r"[.!?…]", after) else 1.2 if re.search(r"[,;:—–]", after) else 0.0
                    info[f"{s['id']}.{w}"] = (t, pause)
    return info


def syllables(word):
    if word.isdigit():
        return 2 * len(word)
    return max(1, len(re.findall(r"[aeiouàèéìíòóùú]+", word.lower())))


def voiced_bounds(pcm):
    """(start, end) in seconds of the voiced part of a clip (leading/trailing silence trimmed)."""
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    frame = RATE // 50  # 20 ms
    n = len(x) // frame
    if n == 0:
        return 0.0, len(x) / RATE
    rms = np.sqrt((x[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    loud = np.where(rms > max(200.0, 0.08 * np.percentile(rms, 95)))[0]
    if len(loud) == 0:
        return 0.0, len(x) / RATE
    return loud[0] * frame / RATE, (loud[-1] + 1) * frame / RATE


def time_words(ids, info, start, end):
    """Spread the words over [start, end] by syllables, leaving punctuation pauses after words."""
    weights = [(syllables(info[i][0]) if i in info else 1, info[i][1] if i in info else 0.0) for i in ids]
    total = sum(w + p for w, p in weights) or 1
    per = (end - start) / total
    out, t = {}, start
    for i, (w, p) in zip(ids, weights):
        out[i] = [round(t, 3), round(t + w * per, 3)]
        t += (w + p) * per
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--engine", choices=["gemini", "standin"], default="gemini")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--bitrate", type=int, default=32, help="MP3 kbit/s (speech: 32 is plenty)")
    args = ap.parse_args()

    folder = ROOT / "chapters" / args.chapter
    chapter = json.loads((folder / "chapter.json").read_text(encoding="utf-8"))
    tts = json.loads((folder / "tts.json").read_text(encoding="utf-8"))
    items = items_of(tts)
    clips_dir = folder / "audio" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    def clip_path(n, item):
        _, sp, text, style, _ = item
        voice = VOICES.get(sp, {}).get("voice", "") if args.engine == "gemini" else STANDIN_VOICES.get(sp, "")
        h = hashlib.sha1(f"{args.engine}|{tts['model']}|{sp}|{voice}|{style}|{text}".encode()).hexdigest()[:12]
        return clips_dir / f"{n:04d}-{h}.pcm"

    done, lock, t0 = [0], threading.Lock(), time.time()

    def make(n):
        item = items[n]
        path = clip_path(n, item)
        if path.exists() and path.stat().st_size > 0:
            return
        _, sp, text, style, _ = item
        for attempt in range(4):
            try:
                if args.engine == "gemini":
                    pcm = gemini_clip(tts["model"], VOICES[sp]["voice"], text, style)
                else:
                    pcm = standin_clip(sp, text, style)
                break
            except SystemExit:
                raise
            except Exception as e:
                if attempt == 3:
                    raise RuntimeError(f"item {n} ({sp}: {text[:40]}): {e}")
                time.sleep(2 ** attempt * 3)
        path.write_bytes(pcm)
        with lock:
            done[0] += 1
            if done[0] % 50 == 0:
                print(f"  {done[0]} clips made ({time.time() - t0:.0f}s)", flush=True)

    todo = [n for n in range(len(items)) if not clip_path(n, items[n]).exists()]
    print(f"{args.chapter}: {len(items)} clips, {len(todo)} to make with {args.engine}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(make, todo))

    # Join the clips (voiced part only, with our own gaps) and time every word.
    info = word_info(chapter)
    pcm_out, t, words, clips, prev = [], 0.0, {}, [], None
    for n, item in enumerate(items):
        scene, sp, _, _, ids = item
        raw = clip_path(n, item).read_bytes()
        a, b = voiced_bounds(raw)
        body = raw[int(a * RATE) * 2: int(b * RATE) * 2]
        if prev is not None:
            gap = GAP_SCENE if scene != prev[0] else GAP_SPEAKER if sp != prev[1] else GAP
            pcm_out.append(b"\0\0" * int(gap * RATE))
            t += gap
        dur = len(body) / 2 / RATE
        words.update(time_words(ids, info, t, t + dur))
        clips.append({"item": n, "scene": scene, "speaker": sp, "start": round(t, 3), "end": round(t + dur, 3)})
        pcm_out.append(body)
        t += dur
        prev = (scene, sp)
    segments = {}
    for wid, (s, e) in words.items():
        seg = wid.rsplit(".", 1)[0]
        cur = segments.get(seg)
        segments[seg] = [min(s, cur[0]), max(e, cur[1])] if cur else [s, e]

    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(args.bitrate)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    mp3 = enc.encode(b"".join(pcm_out)) + enc.flush()
    (folder / "audio" / "chapter.mp3").write_bytes(mp3)
    timing = {"chapter": args.chapter, "audio": "chapter.mp3", "engine": args.engine,
              "voices": "stand-in (OpenRouter gpt-audio-mini)" if args.engine == "standin" else tts["model"],
              "duration": round(t, 3), "clips": clips, "segments": segments, "words": words}
    (folder / "audio" / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8")
    shown = sum(1 for sc in chapter["scenes"] for p in sc["paragraphs"] for s in p["segments"]
                for tok in s.get("tokens", []) if tok[1] >= 0)
    print(f"{args.chapter}: {t / 60:.1f} min of audio, {len(mp3) / 1e6:.1f} MB mp3, "
          f"{len(words)}/{shown} words timed → chapters/{args.chapter}/audio/")


if __name__ == "__main__":
    main()
