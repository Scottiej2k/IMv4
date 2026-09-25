#!/usr/bin/env python3
"""Generate a chapter scene by scene (see scripts/pipeline.py) with the Claude API or OpenRouter.

The whole chapter is one conversation: outline → one turn per scene → grammar lesson →
at most one round of line fixes. The system prompt is cached, and so is the growing
conversation, so each turn pays full price only for its new text.

Claude models (claude-…): pip install anthropic, and ANTHROPIC_API_KEY in the environment.
OpenRouter models (any slug with a '/', e.g. openai/gpt-6-luna): no packages needed. The key comes
from OPENROUTER_API_KEY if set; otherwise the request is sent without one, for environments whose
proxy adds the Authorization header for openrouter.ai.

Usage:
  python3 scripts/generate_chapter.py s01e01 --model openai/gpt-6-luna
  python3 scripts/generate_chapter.py s01e01                        # default model: claude-sonnet-5
  python3 scripts/generate_chapter.py s01e01 --model claude-opus-5-5 --effort high
  python3 scripts/generate_chapter.py s01e01 --force                # start over
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import Pipeline  # noqa: E402

# Prices per million tokens (input, output), for the cost estimate printed at the end.
PRICES = {"claude-sonnet-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0),
          "claude-haiku-4-5": (1.0, 5.0)}


def call(client, model, effort, system, messages):
    import anthropic
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


OPENROUTER_URL = "https://www.openrouter.ai/api/v1/chat/completions"  


def call_openrouter(model, effort, system, messages):
    """One chat-completions request to OpenRouter. Returns (text, usage dict with 'cost' in USD)."""
    body = {
        "model": model,
        "max_tokens": 32000,
        "messages": [{"role": "system", "content": system}] + messages,
        "reasoning": {"effort": {"xhigh": "high", "max": "high"}.get(effort, effort)},
        "usage": {"include": True},
    }
    # A User-Agent is needed: Cloudflare rejects Python's default one (error 1010).
    headers = {"Content-Type": "application/json", "X-Title": "IMv4 Italian course",
               "User-Agent": "IMv4/1.0"}
    if os.environ.get("OPENROUTER_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OPENROUTER_API_KEY']}"
    data = json.dumps(body).encode()
    for attempt in range(4):
        req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                out = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                print(f"  OpenRouter {e.code}; retrying")
                time.sleep(2 ** attempt * 10)
                continue
            raise RuntimeError(f"OpenRouter error {e.code}: {detail}")
        except urllib.error.URLError:
            if attempt < 3:
                print("  connection error; retrying")
                time.sleep(2 ** attempt * 5)
                continue
            raise
    if "error" in out:
        raise RuntimeError(f"OpenRouter error: {out['error']}")
    choice = out["choices"][0]
    if choice.get("finish_reason") == "length":
        print("  warning: a reply hit max_tokens and may be cut off")
    return choice["message"]["content"] or "", out.get("usage", {})


# Scene asks as a multiple of the budget, for models that don't undershoot like Claude does.
# DeepSeek wrote 15-20% over the target at 1.3x (pilots, 2026-09-25).
ASK_FACTORS = {"deepseek/": 1.0}


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
    ap.add_argument("--ask-factor", type=float, help="scene word ask as a multiple of its budget "
                    "(default 1.3, or per model from ASK_FACTORS)")
    args = ap.parse_args()

    pipe = Pipeline(args.chapter)
    pipe.start(force=args.force)
    pipe.ask_factor = args.ask_factor or next(
        (f for prefix, f in ASK_FACTORS.items() if args.model.startswith(prefix)), pipe.ask_factor)
    openrouter = "/" in args.model
    client = None
    if not openrouter:
        import anthropic
        client = anthropic.Anthropic()
    messages, total, out_tokens = [], 0.0, 0

    print(f"{args.chapter}: writing with {args.model} via {'OpenRouter' if openrouter else 'Claude API'} "
          f"(effort {args.effort}, scene ask {pipe.ask_factor}x)")
    prompt = pipe.next_prompt()
    while prompt is not None:
        print(f"- {prompt.splitlines()[0][:70]}")
        messages.append({"role": "user", "content": prompt})
        if openrouter:
            # The outline is short, but at medium effort DeepSeek spent all 32k output tokens
            # thinking about it (twice, on S5E3). Low effort keeps it to a normal reply.
            effort = "low" if pipe.state["step"] == "outline" else args.effort
            text, usage = call_openrouter(args.model, effort, pipe.system, messages)
            messages.append({"role": "assistant", "content": text})
            total += float(usage.get("cost") or 0)
            out_tokens += int(usage.get("completion_tokens") or 0)
        else:
            msg = call(client, args.model, args.effort, pipe.system, messages)
            messages.append({"role": "assistant", "content": msg.content})  # thinking blocks passed back unchanged
            total += cost(args.model, msg.usage)
            out_tokens += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
        pipe.submit(text)
        prompt = pipe.next_prompt()

    print(f"{args.chapter}: done · {len(messages) // 2} calls · {out_tokens} output tokens · "
          f"{'cost' if openrouter else 'estimated cost'} ${total:.3f}")


if __name__ == "__main__":
    main()
