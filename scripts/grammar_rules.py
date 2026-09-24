#!/usr/bin/env python3
"""Grammar-ceiling checker: finds word forms of structures a chapter hasn't taught yet.

Each rule belongs to the curriculum concept that introduces it. For a chapter earlier than
that concept, any match in the Italian text is flagged. The patterns are deliberately
concrete (actual word forms) and err on the side of flagging: a flag means "check this line",
and a false positive is simply left unchanged.

Usage: python3 scripts/grammar_rules.py s05e03      # lint chapters/s05e03/draft.txt
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PART = (r"(?:\w+(?:ato|ata|ati|ate|uto|uta|uti|ute|ito|ita|iti|ite)|fatto|fatta|fatti|detto|detta|visto|vista|"
        r"visti|preso|presa|presi|messo|messa|scritto|letto|aperto|chiuso|rotto|chiesto|risposto|perso|persa|"
        r"bevuto|stato|stata|stati|state|nato|nata|morto|morta|rimasto|rimasta|successo|venuto|venuta|scelto|"
        r"deciso|vinto|speso|corso|pianto|riso|sceso|spento|acceso|offerto|sofferto|mosso|messi)")
AVERE = r"(?:ho|hai|ha|abbiamo|avete|hanno)"
ESSERE = r"(?:sono|sei|è|siamo|siete)"
MOTION = (r"(?:andat[oaie]|venut[oaie]|arrivat[oaie]|partit[oaie]|uscit[oaie]|entrat[oaie]|tornat[oaie]|"
          r"stat[oaie]|nat[oaie]|mort[oaie]|rimast[oaie]|successo|caduto|caduta|cresciut[oaie]|diventat[oaie])")
IMP_SUBJ = (r"(?:fossi|fosse|fossimo|foste|fossero|avessi|avesse|avessimo|aveste|avessero|facessi|facesse|"
            r"dessi|desse|stessi|stesse|dicessi|dicesse|bevessi|\w{2,}(?:assi|asse|assimo|assero|essi|esse|"
            r"essimo|essero|issi|isse|issimo|issero))")
# Common words that look like imperfect-subjunctive forms but aren't.
IMP_SUBJ_FALSE = {"passi", "bassi", "grassi", "classi", "sassi", "tassi", "interesse", "interessi", "processi",
                  "successi", "stessi", "messi", "spessi", "adesso", "promesse", "compromessi", "espressi",
                  "lessi", "ossessi", "possessi", "stesse", "esse", "fissi", "missi", "dissi", "misi", "risse",
                  "abbassi", "incassi", "passassi", "massi", "rossi", "grosse", "mosse", "fesse", "presse",
                  "sassi", "collassi", "eccessi", "accessi", "progressi", "congressi", "permessi", "premesse",
                  "scommesse", "rimesse", "classe", "casse", "tasse", "masse", "tosse", "grasse", "basse", "rosse", "adesso", "tesse", "tessi", "badesse", "principesse", "contesse", "duchesse",
                  "professoresse", "dottoresse", "studentesse", "poetesse", "campionesse", "ostesse", "hostesse"}

RULES = [
    {"concept": "g-pp-avere", "what": "passato prossimo (avere + participle)",
     "examples": "ho mangiato, abbiamo visto, hai fatto",
     "re": rf"\b{AVERE}\s+(?:già\s+|appena\s+|mai\s+|sempre\s+)?{PART}\b"},
    {"concept": "g-pp-essere", "what": "passato prossimo (essere + participle)",
     "examples": "sono andato, è arrivata, siamo stati",
     "re": rf"\b{ESSERE}\s+(?:già\s+|appena\s+)?{MOTION}\b"},
    {"concept": "g-imperfetto-forms", "what": "imperfetto",
     "examples": "era, c'era, avevo, facevo, andava, stavamo",
     "re": r"\b(?:ero|eri|era|eravamo|eravate|erano|c'era|c'erano|avevo|avevi|aveva|avevamo|avevate|avevano|"
           r"facevo|faceva|facevano|dicevo|diceva|stavo|stava|stavano|andavo|andava|andavano|volevo|voleva|"
           r"potevo|poteva|dovevo|doveva|sapevo|sapeva|pensavo|pensava|sembrava|\w{3,}(?:avamo|avate|avano|"
           r"evamo|evate|evano|ivamo|ivate|ivano))\b"},
    {"concept": "g-conditional-polite", "what": "conditional (beyond the fixed phrase 'vorrei')",
     "examples": "potresti, sarebbe, mi piacerebbe, dovresti",
     "re": r"\b(?:sarei|saresti|sarebbe|saremmo|sareste|sarebbero|avrei|avresti|avrebbe|avremmo|avreste|"
           r"avrebbero|vorresti|vorrebbe|vorremmo|vorreste|vorrebbero|potrei|potresti|potrebbe|potremmo|"
           r"potreste|potrebbero|dovrei|dovresti|dovrebbe|dovremmo|dovreste|dovrebbero|piacerebbe|"
           r"\w{3,}(?:erei|eresti|erebbe|eremmo|ereste|erebbero|irei|iresti|irebbe|iremmo|ireste|irebbero))\b"},
    {"concept": "g-futuro-semplice", "what": "futuro semplice",
     "examples": "sarò, avrà, andremo, parlerai, farà",
     "re": r"\b(?:sarò|sarai|sarà|saremo|sarete|saranno|avrò|avrai|avrà|avremo|avrete|avranno|andrò|andrà|"
           r"farò|farà|faremo|verrò|verrà|potrò|potrà|dovrò|dovrà|vorrò|vorrà|\w{3,}(?:erò|erai|erà|eremo|erete|"
           r"eranno|irò|irai|irà|iremo|irete|iranno))\b"},
    {"concept": "g-condizionale-passato", "what": "condizionale passato",
     "examples": "avrei dovuto, sarebbe stato, avresti fatto",
     "re": rf"\b(?:avrei|avresti|avrebbe|avremmo|avreste|avrebbero|sarei|saresti|sarebbe|saremmo|sareste|"
           rf"sarebbero)\s+(?:voluto|dovuto|potuto|{PART})\b"},
    {"concept": "g-trapassato-prossimo", "what": "trapassato prossimo",
     "examples": "avevo già mangiato, era partita, avevano deciso",
     "re": rf"\b(?:avevo|avevi|aveva|avevamo|avevate|avevano)\s+(?:già\s+|appena\s+|mai\s+)?{PART}\b|"
           rf"\b(?:ero|eri|era|eravamo|eravate|erano)\s+(?:già\s+|appena\s+)?{MOTION}\b"},
    {"concept": "g-congiuntivo-presente", "what": "congiuntivo presente",
     "examples": "penso che sia, credo che abbia, voglio che tu vada",
     "re": r"\bche\s+(?:\w+\s+)?(?:sia|siano|abbia|abbiano|vada|vadano|faccia|facciano|possa|possano|debba|"
           r"debbano|voglia|vogliano|sappia|sappiano|venga|vengano|stia|stiano|dia|diano)\b"},
    {"concept": "g-congiuntivo-emotion", "what": "subjunctive after emotions",
     "examples": "ho paura che dica, sono contento che venga, mi dispiace che sia",
     "re": r"\b(?:paura|contento|contenta|contenti|felice|felici|triste|dispiace|temo|teme|temono|"
           r"sorpreso|sorpresa|preoccupato|preoccupata)\s+che\b"},
    {"concept": "g-congiuntivo-passato", "what": "congiuntivo passato",
     "examples": "penso che abbia visto, credo che sia partita",
     "re": rf"\b(?:abbia|abbiano|sia|siano)\s+(?:già\s+)?(?:{PART}|{MOTION})\b"},
    {"concept": "g-congiuntivo-imperfetto", "what": "congiuntivo imperfetto",
     "examples": "se fossi, volevo che tu venissi, magari avessi",
     "re": rf"\b{IMP_SUBJ}\b", "exclude": IMP_SUBJ_FALSE},
    {"concept": "g-periodo-ipotetico-2", "what": "hypothetical 'se' + imperfect subjunctive",
     "examples": "se fossi in te, se avessi tempo, se potessi",
     "re": r"\bse\s+(?:\w+\s+){0,2}(?:fossi|fosse|fossimo|foste|fossero|avessi|avesse|potessi|potesse|"
           r"\w{2,}(?:assi|asse|essi|esse|issi|isse))\b"},
    {"concept": "g-congiuntivo-trapassato", "what": "congiuntivo trapassato",
     "examples": "se avessi saputo, pensavo che fosse già partito",
     "re": rf"\b(?:avessi|avesse|avessimo|aveste|avessero|fossi|fosse|fossimo|foste|fossero)\s+(?:già\s+)?"
           rf"(?:{PART}|{MOTION})\b"},
    {"concept": "g-passato-remoto-regular", "what": "passato remoto",
     "examples": "fu, ebbe, disse, parlò, andarono, nacque",
     "re": r"\b(?:fu|furono|ebbe|ebbero|fece|fecero|disse|dissero|venne|vennero|vide|videro|nacque|nacquero|"
           r"morì|prese|presero|mise|misero|scrisse|scrissero|rispose|decise|\w{3,}(?:arono|erono|irono)|"
           r"\w{2,}[^rn\W]ò)\b",
     "exclude": {"però", "può", "ciò", "perciò", "cioè", "falò", "comò", "oblò", "rococò", "bordò", "domino"}},
]


def load_order():
    order = {}
    for p in sorted((ROOT / "curriculum" / "seasons").glob("s*.json")):
        for ch in json.loads(p.read_text(encoding="utf-8"))["chapters"]:
            order[ch["grammar"]["id"]] = ch["id"]
    return order


def active_rules(chapter_id):
    """Rules for structures not yet taught at this chapter."""
    order = load_order()
    out = []
    for r in RULES:
        intro = order.get(r["concept"])
        if intro and chapter_id < intro:
            out.append(dict(r, intro=intro))
    return out


def lint_text(text, rules):
    hits = []
    clean = re.sub(r"\*\*|<[^>]+>", "", text)
    for r in rules:
        for m in re.finditer(r["re"], clean, re.I):
            word = m.group(0)
            if word.lower() in r.get("exclude", set()) or word.lower() == "vorrei":
                continue
            hits.append((r, word))
    return hits


def lint_draft(chapter_id, draft_text):
    """Return [(draft line number, line, [(rule, matched text)])] for the Italian side of story lines."""
    rules = active_rules(chapter_id)
    results = []
    in_grammar = False
    for n, line in enumerate(draft_text.splitlines(), start=1):
        if line.strip().lower().startswith("@grammar"):
            in_grammar = True
        if in_grammar or "||" not in line or ":" not in line:
            continue
        italian = line.split(":", 1)[1].split("||", 1)[0]
        hits = lint_text(italian, rules)
        if hits:
            results.append((n, line.strip(), hits))
    return results


def forbidden_forms_text(chapter_id):
    """Concrete 'don't use yet' list for the writer's brief."""
    lines = []
    for r in active_rules(chapter_id):
        lines.append(f"- {r['what']} (taught in {r['intro']}): e.g. *{r['examples']}*")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    cid = sys.argv[1]
    draft = ROOT / "chapters" / cid / "draft.txt"
    results = lint_draft(cid, draft.read_text(encoding="utf-8"))
    for n, line, hits in results:
        what = "; ".join(f"{r['what']} ('{w}', taught {r['intro']})" for r, w in hits)
        print(f"line {n}: {what}\n    {line}")
    print(f"{len(results)} line(s) flagged")


if __name__ == "__main__":
    main()
