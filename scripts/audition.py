#!/usr/bin/env python3
"""Voice audition: each main character's real lines read by a few candidate Gemini voices.

    python3 scripts/audition.py            # writes audition/ (git-ignored): clips + audition.json

The audition page (audition/index.html) plays them and stores the owner's picks; the picks then go
into config/voices.json. Uses Gemini 3.8 Flash TTS through OpenRouter (no Google key needed).
"""
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lameenc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chapter as bc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "audition"
MODEL = "google/gemini-3.8-flash-tts"
URL = "https://www.openrouter.ai/api/v1/audio/speech"
LEVEL_STYLE = bc.VOICES["level_styles"]["A1"]
ACCENT = "speaking Italian with a noticeable American accent"

# Google's one-word description of each prebuilt voice (ai.google.dev speech-generation docs).
DESCR = {"Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative", "Kore": "Firm", "Fenrir": "Excitable",
         "Leda": "Youthful", "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going", "Autonoe": "Bright",
         "Enceladus": "Breathy", "Iapetus": "Clear", "Umbriel": "Easy-going", "Algieba": "Smooth",
         "Despina": "Smooth", "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
         "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm", "Schedar": "Even", "Gacrux": "Mature",
         "Pulcherrima": "Forward", "Achird": "Friendly", "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle",
         "Sadachbia": "Lively", "Sadaltager": "Knowledgeable", "Sulafat": "Warm"}

# Candidates per character: the current voice first, then alternatives of a fitting sound.
CANDIDATES = {
    "narrator": ["Sulafat", "Charon", "Achernar", "Sadaltager"],
    "ben": ["Puck", "Fenrir", "Achird"],
    "chiara": ["Kore", "Zephyr", "Callirrhoe"],
    "emma": ["Leda", "Autonoe", "Laomedeia"],
    "leo": ["Laomedeia", "Leda", "Zephyr"],
    "franco": ["Algenib", "Enceladus", "Rasalgethi"],
    "ornella": ["Gacrux", "Vindemiatrix", "Pulcherrima"],
    "matteo": ["Sadachbia", "Puck", "Umbriel"],
    "nadia": ["Despina", "Erinome", "Aoede"],
    "roberto": ["Alnilam", "Orus", "Iapetus"],
}


def lines_for(who, n=2):
    """The character's clearest real lines from the written chapters (8–22 words, no sound tags)."""
    found = []
    for folder in sorted((ROOT / "chapters").glob("s01e0*")):
        ch = json.loads((folder / "chapter.json").read_text(encoding="utf-8"))
        for _, block, seg in bc.segments(ch):
            for sp, text, _ in bc.voice_pieces(block, seg):
                plain = bc.spoken_text(text).strip("«» ")
                if sp == who and 8 <= len(plain.split()) <= 22 and "<" not in plain:
                    found.append({"it": plain, "en": re.sub(r"\*\*|_", "", seg["en"]), "id": seg["id"]})
    found.sort(key=lambda x: -len(x["it"]))
    picks, seen = [], set()
    for f in found:  # varied: not two from the same chapter
        if f["id"][:6] not in seen:
            picks.append(f)
            seen.add(f["id"][:6])
        if len(picks) == n:
            break
    return picks


def speak(voice, text, style):
    body = {"model": MODEL, "input": text, "voice": voice, "response_format": "pcm",
            "provider": {"options": {"google-ai-studio": {"speech_metadata": {"style": style}}}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "IMv4/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise


def mp3(pcm):
    enc = lameenc.Encoder()
    enc.set_bit_rate(48)
    enc.set_in_sample_rate(24000)
    enc.set_channels(1)
    enc.set_quality(2)
    return enc.encode(pcm) + enc.flush()


def main():
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    jobs, cast = [], []
    for who, voices in CANDIDATES.items():
        v = bc.VOICES["voices"][who]
        lines = lines_for(who)
        if who == "narrator":
            lines = lines[:1] + lines_for("narrator", 3)[1:2]
        entry = {"id": who, "name": v.get("name", who), "about": v.get("style", ""), "current": v["voice"],
                 "lines": lines, "takes": []}
        variants = [("", "")] + ([(ACCENT, "with American-accent style")] if who == "ben" else [])
        for voice in voices:
            for extra, label in variants:
                style = ", ".join(s for s in (LEVEL_STYLE, extra) if s)
                take = {"voice": voice, "descr": DESCR.get(voice, ""), "label": label,
                        "files": [f"clips/{who}-{voice}{'-accent' if extra else ''}-{i}.mp3" for i in range(len(lines))]}
                entry["takes"].append(take)
                for i, line in enumerate(lines):
                    jobs.append((OUT / take["files"][i], voice, line["it"], style))
        cast.append(entry)

    def run(job):
        path, voice, text, style = job
        if not path.exists():
            path.write_bytes(mp3(speak(voice, text, style)))

    print(f"{len(jobs)} clips with {MODEL}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run, jobs))
    (OUT / "audition.json").write_text(json.dumps({"model": MODEL, "style": LEVEL_STYLE, "cast": cast},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}/ ({sum(1 for _ in (OUT / 'clips').iterdir())} clips)")


if __name__ == "__main__":
    main()
