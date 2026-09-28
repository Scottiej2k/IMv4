#!/usr/bin/env python3
"""Narrator audition: one real narration passage read by several voices at several paces.

    python3 scripts/narrator_audition.py     # writes audition/narrator/ (git-ignored): clips + narrator.json

The page audition/narrator.html plays them and stores the owner's pick. The pick then goes into
config/voices.json (voice) and level_styles / the narrator's style (pace and delivery).
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audition as au  # noqa: E402

OUT = au.OUT / "narrator"
PASSAGE = {
    "it": ("È lunedì sera. Franco è nella sua casa al numero nove. La cucina è piccola e silenziosa. "
           "Sul tavolo ci sono i pomodori dell'orto. Franco guarda fuori. Dalla finestra vede la strada. "
           "Vede la casa numero quattordici. Le luci sono accese. C'è il vicino nuovo con la sua famiglia. "
           "Franco beve un bicchiere d'acqua."),
    "en": ("It's Monday evening. Franco is in his house at number nine. The kitchen is small and quiet. "
           "On the table are the tomatoes from the garden. Franco looks out. From the window he sees the "
           "street. He sees house number fourteen. The lights are on. There's the new neighbour with his "
           "family. Franco drinks a glass of water."),
    "from": "Chapter 1, scene 4",
}
# Pace/delivery settings, from the current one (slowest) to a natural audiobook read.
STYLES = [
    {"id": "now", "name": "Current setting", "style": au.LEVEL_STYLE},
    {"id": "clear", "name": "Clear, a little quicker",
     "style": "speaking clearly at a calm, unhurried pace, standard Italian pronunciation, smooth and natural"},
    {"id": "story", "name": "Storyteller",
     "style": "warm audiobook narrator, clear standard Italian, relaxed natural pace, "
              "sentences flow into each other, gently expressive"},
]
VOICES = ["Charon", "Algieba", "Iapetus", "Sadaltager", "Achird", "Schedar"]


def main():
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    jobs, takes = [], []
    for v in VOICES:
        for s in STYLES:
            f = f"clips/{v}-{s['id']}.mp3"
            takes.append({"voice": v, "descr": au.DESCR.get(v, ""), "style": s["id"], "file": f})
            jobs.append((OUT / f, v, s["style"]))

    def run(job):
        path, voice, style = job
        if not path.exists():
            path.write_bytes(au.mp3(au.speak(voice, PASSAGE["it"], style)))

    print(f"{len(jobs)} clips with {au.MODEL}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(run, jobs))
    (OUT / "narrator.json").write_text(json.dumps({"model": au.MODEL, "current": "Charon", "passage": PASSAGE,
                                                    "styles": STYLES, "takes": takes},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(au.ROOT)}/")


if __name__ == "__main__":
    main()
