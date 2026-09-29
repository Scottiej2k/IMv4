#!/usr/bin/env python3
"""Leo audition: his real lines read by several voices in several child-voice styles.

    python3 scripts/leo_audition.py     # writes audition/leo/ (git-ignored): clips + leo.json

Gemini's prebuilt voices are all adult, so a child sound comes from the voice's pitch plus the style
prompt. The owner's pick goes into config/voices.json (leo: voice + style).
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audition as au  # noqa: E402

OUT = au.OUT / "leo"
PACE = au.LEVEL_STYLE
STYLES = [
    {"id": "now", "name": "Current style", "style": "8-year-old boy, high and bright child's voice, curious, " + PACE},
    {"id": "small", "name": "Small child",
     "style": "a small 7-year-old child, very high-pitched, light and squeaky, genuinely childlike, "
              "not an adult imitating a child, " + PACE},
    {"id": "cheeky", "name": "Cheeky kid",
     "style": "a cheeky, excited little boy, high-pitched and breathless, a kid's playful energy, "
              "clearly a young child and not a woman, " + PACE},
    {"id": "boy", "name": "Young boy, not a woman",
     "style": "young boy aged 8, pre-pubescent, high thin boyish voice, no adult female tone, "
              "innocent and curious, " + PACE},
]
VOICES = ["Leda", "Zephyr", "Laomedeia", "Puck", "Sadachbia", "Autonoe", "Achird"]


def main():
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    lines = au.lines_for("leo")
    jobs, takes = [], []
    for v in VOICES:
        for s in STYLES:
            files = [f"clips/{v}-{s['id']}-{i}.mp3" for i in range(len(lines))]
            takes.append({"voice": v, "descr": au.DESCR.get(v, ""), "style": s["id"], "files": files})
            for i, ln in enumerate(lines):
                jobs.append((OUT / files[i], v, ln["it"], s["style"]))

    def run(job):
        path, voice, text, style = job
        if not path.exists():
            path.write_bytes(au.mp3(au.speak(voice, text, style)))

    print(f"{len(jobs)} clips with {au.MODEL}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run, jobs))
    (OUT / "leo.json").write_text(json.dumps({"model": au.MODEL, "current": "Leda", "lines": lines,
                                              "styles": STYLES, "takes": takes},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(au.ROOT)}/")


if __name__ == "__main__":
    main()
