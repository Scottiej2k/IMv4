#!/usr/bin/env python3
"""Generate a chapter draft with the Claude API, then convert and build it.

One streamed request per chapter: the system prompt (writer instructions + draft format +
world bible) is identical for every chapter and cached; the chapter brief is the user message.
If the draft has hard errors, one follow-up request asks for corrected lines only.

Requires:  pip install anthropic   and   ANTHROPIC_API_KEY in the environment.

Usage:
  python3 scripts/generate_chapter.py s01e01                     # default model: claude-sonnet-5
  python3 scripts/generate_chapter.py s01e01 --model claude-opus-5-5 --effort high
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_brief  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Prices per million tokens (input, output), for the cost estimate printed at the end.
PRICES = {"claude-sonnet-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0),
          "claude-haiku-4-5": (1.0, 5.0)}


def call(client, model, effort, system, messages):
    kwargs = dict(
        model=model,
        max_tokens=64000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    if model != "claude-haiku-4-5":
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}
    for attempt in range(4):
        try:
            with client.messages.stream(**kwargs) as stream:
                for _ in stream.text_stream:
                    pass
                msg = stream.get_final_message()
            break
        except anthropic.RateLimitError as e:
            wait = int(e.response.headers.get("retry-after", "30"))
            print(f"  rate limited; retrying in {wait}s")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt < 3:
                print(f"  server error {e.status_code}; retrying")
                time.sleep(2 ** attempt * 5)
            else:
                raise
    else:
        raise RuntimeError("gave up after retries")
    if msg.stop_reason == "max_tokens":
        print("  warning: output hit max_tokens; the draft may be cut off")
    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return text, msg.usage


def cost(model, usage):
    pin, pout = PRICES.get(model, (0, 0))
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (usage.input_tokens * pin + cached * pin * 0.1 + written * pin * 1.25 + usage.output_tokens * pout) / 1e6


def convert(cid):
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "convert_draft.py"), cid],
                         capture_output=True, text=True)
    print(res.stdout.rstrip())
    return res.returncode == 0, res.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    args = ap.parse_args()

    cid = args.chapter
    folder = ROOT / "chapters" / cid
    folder.mkdir(parents=True, exist_ok=True)
    system, brief = make_brief.system_prompt(), make_brief.chapter_brief(cid)
    client = anthropic.Anthropic()

    print(f"{cid}: generating with {args.model} (effort {args.effort})…")
    messages = [{"role": "user", "content": brief}]
    draft, usage = call(client, args.model, args.effort, system, messages)
    total = cost(args.model, usage)
    (folder / "draft.txt").write_text(draft + "\n", encoding="utf-8")

    ok, report = convert(cid)
    if not ok and "ERROR" in report:
        print(f"{cid}: asking for one round of fixes…")
        errors = "\n".join(l.strip() for l in report.splitlines() if "ERROR" in l)
        messages += [{"role": "assistant", "content": draft},
                     {"role": "user", "content": "The converter reported these errors:\n\n" + errors +
                      "\n\nReturn the complete corrected draft (same format, nothing else). Change only what "
                      "is needed to fix these errors."}]
        draft, usage2 = call(client, args.model, args.effort, system, messages)
        total += cost(args.model, usage2)
        (folder / "draft.txt").write_text(draft + "\n", encoding="utf-8")
        ok, _ = convert(cid)

    print(f"{cid}: {'done' if ok else 'needs attention'} · estimated cost ${total:.2f} · "
          f"output tokens {usage.output_tokens}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
