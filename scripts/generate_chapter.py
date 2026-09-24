#!/usr/bin/env python3
"""Generate a chapter with the Claude API, scene by scene (see scripts/pipeline.py).

The whole chapter is one conversation: outline → one turn per scene → grammar lesson →
at most one round of line fixes. The system prompt is cached, and so is the growing
conversation, so each turn pays full price only for its new text.

Requires:  pip install anthropic   and   ANTHROPIC_API_KEY in the environment.

Usage:
  python3 scripts/generate_chapter.py s01e01                        # default model: claude-sonnet-5
  python3 scripts/generate_chapter.py s01e01 --model claude-opus-5-5 --effort high
  python3 scripts/generate_chapter.py s01e01 --force                # start over
"""
import argparse
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import Pipeline  # noqa: E402

# Prices per million tokens (input, output), for the cost estimate printed at the end.
PRICES = {"claude-sonnet-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0),
          "claude-haiku-4-5": (1.0, 5.0)}


def call(client, model, effort, system, messages):
    kwargs = dict(
        model=model,
        max_tokens=32000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        cache_control={"type": "ephemeral"},  # also cache the growing conversation
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
        except anthropic.APIConnectionError:
            if attempt < 3:
                print("  connection error; retrying")
                time.sleep(2 ** attempt * 5)
            else:
                raise
    else:
        raise RuntimeError("gave up after retries")
    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined this request")
    if msg.stop_reason == "max_tokens":
        print("  warning: a reply hit max_tokens and may be cut off")
    return msg


def cost(model, usage):
    pin, pout = PRICES.get(model, (0, 0))
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (usage.input_tokens * pin + cached * pin * 0.1 + written * pin * 1.25 + usage.output_tokens * pout) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--force", action="store_true", help="discard any earlier run of this chapter")
    args = ap.parse_args()

    pipe = Pipeline(args.chapter)
    pipe.start(force=args.force)
    client = anthropic.Anthropic()
    messages, total, out_tokens = [], 0.0, 0

    print(f"{args.chapter}: writing with {args.model} (effort {args.effort})")
    prompt = pipe.next_prompt()
    while prompt is not None:
        print(f"- {prompt.splitlines()[0][:70]}")
        messages.append({"role": "user", "content": prompt})
        msg = call(client, args.model, args.effort, pipe.system, messages)
        messages.append({"role": "assistant", "content": msg.content})  # thinking blocks passed back unchanged
        total += cost(args.model, msg.usage)
        out_tokens += msg.usage.output_tokens
        pipe.submit("".join(b.text for b in msg.content if b.type == "text"))
        prompt = pipe.next_prompt()

    print(f"{args.chapter}: done · {len(messages) // 2} calls · {out_tokens} output tokens · "
          f"estimated cost ${total:.2f}")


if __name__ == "__main__":
    main()
