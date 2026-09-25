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
import threading
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
# Longest wait for one reply. OpenRouter keeps a slow request's connection alive with blank lines,
# so a socket timeout never fires; one request hung for 40 minutes (S1E2 batch, 2026-09-25).
REQUEST_DEADLINE = 600
# Preferred OpenRouter providers. The same model costs up to 3x more at some providers, and the
# chapter conversation is re-sent on every call, so a provider that caches it (DeepSeek's own: 2% of
# the input price for cached text) keeps a chapter at a few cents. Unpinned, the first batch paid
# $0.11–0.14 a chapter against $0.02–0.04 in the pilots.
PROVIDER_ORDER = {"deepseek/": ["deepseek", "deepinfra"]}


def _fetch_with_deadline(req, seconds):
    """urlopen + read + parse in a helper thread; raise TimeoutError if it takes longer than `seconds`."""
    result = {}

    def work():
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result["out"] = json.loads(resp.read())
        except BaseException as e:  # handed back to the caller
            result["err"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"no complete reply after {seconds}s")
    if "err" in result:
        raise result["err"]
    return result["out"]


def call_openrouter(model, effort, system, messages, reasoning_tokens=None):
    """One chat-completions request to OpenRouter. Returns (text, usage dict with 'cost' in USD)."""
    body = {
        "model": model,
        "max_tokens": 32000,
        "messages": [{"role": "system", "content": system}] + messages,
        "reasoning": ({"max_tokens": reasoning_tokens} if reasoning_tokens else
                      {"effort": {"xhigh": "high", "max": "high"}.get(effort, effort)}),
        "usage": {"include": True},
    }
    order = next((o for prefix, o in PROVIDER_ORDER.items() if model.startswith(prefix)), None)
    if order:
        body["provider"] = {"order": order, "allow_fallbacks": True}
    # A User-Agent is needed: Cloudflare rejects Python's default one (error 1010).
    headers = {"Content-Type": "application/json", "X-Title": "IMv4 Italian course",
               "User-Agent": "IMv4/1.0"}
    if os.environ.get("OPENROUTER_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OPENROUTER_API_KEY']}"
    data = json.dumps(body).encode()
    tries = 5
    for attempt in range(tries):
        req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
        try:
            out = _fetch_with_deadline(req, REQUEST_DEADLINE)
            if "error" in out or not out.get("choices"):
                raise RuntimeError(f"OpenRouter error in reply: {str(out.get('error', out))[:300]}")
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (408, 429, 500, 502, 503, 504) and attempt < tries - 1:
                print(f"  OpenRouter {e.code}; retrying")
                time.sleep(2 ** attempt * 10)
                continue
            raise RuntimeError(f"OpenRouter error {e.code}: {detail}")
        except Exception as e:  # dropped connection, cut-off body, bad JSON, deadline, error in reply
            if attempt < tries - 1:
                print(f"  {type(e).__name__}: {str(e)[:120]}; retrying")
                time.sleep(2 ** attempt * 5)
                continue
            raise
    choice = out["choices"][0]
    if choice.get("finish_reason") == "length":
        print("  warning: a reply hit max_tokens and may be cut off")
    return choice["message"]["content"] or "", out.get("usage", {})


# Scene asks as a multiple of the budget, per level, for models that don't undershoot like Claude.
# DeepSeek pilots (2026-09-25): 1.3x ran 15-20% over; 1.0x gave A1 6% under, B1 2.5% over.
ASK_FACTORS = {"deepseek/": {"A1": 1.15, "A2": 1.1, "B1": 1.0, "B2": 1.0}}


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
    ap.add_argument("--continuity-only", action="store_true",
                    help="only write the continuity entry (for a chapter fixed by hand and rebuilt)")
    ap.add_argument("--ask-factor", type=float, help="scene word ask as a multiple of its budget "
                    "(default 1.3, or per model from ASK_FACTORS)")
    args = ap.parse_args()

    pipe = Pipeline(args.chapter)
    if args.continuity_only:
        pipe.ask_continuity()
    else:
        pipe.start(force=args.force)
    per_level = next((f for prefix, f in ASK_FACTORS.items() if args.model.startswith(prefix)), {})
    pipe.ask_factor = args.ask_factor or per_level.get(pipe.plan["level"], pipe.ask_factor)
    openrouter = "/" in args.model
    client = None
    if not openrouter:
        import anthropic
        client = anthropic.Anthropic()
    messages = []

    print(f"{args.chapter}: writing with {args.model} via {'OpenRouter' if openrouter else 'Claude API'} "
          f"(effort {args.effort}, scene ask {pipe.ask_factor}x)")
    try:
        _loop(pipe, args, openrouter, client, messages)
    finally:  # report what was spent even if a request failed for good
        s = _spent
        print(f"{args.chapter}: {'done' if pipe.state['step'] == 'done' else 'stopped'} · {s['calls']} calls · "
              f"{s['out']} output tokens · {'cost' if openrouter else 'estimated cost'} ${s['cost']:.3f}")


_spent = {"calls": 0, "out": 0, "cost": 0.0}


def _loop(pipe, args, openrouter, client, messages):
    prompt = pipe.next_prompt()
    while prompt is not None:
        print(f"- {prompt.splitlines()[0][:70]}")
        if pipe.state["step"] == "continuity":
            messages = []  # the prompt carries the final story, so the long conversation isn't needed
        messages.append({"role": "user", "content": prompt})
        _spent["calls"] += 1
        if openrouter:
            # Outline, fixes and continuity entry are short, but DeepSeek has spent all 32k output
            # tokens thinking about an outline (S5E3) and a long fix list (S1E5), so their thinking
            # is capped.
            cap = 12000 if pipe.state["step"] in ("outline", "fix", "continuity") else None
            text, usage = call_openrouter(args.model, args.effort, pipe.system, messages, cap)
            messages.append({"role": "assistant", "content": text})
            _spent["cost"] += float(usage.get("cost") or 0)
            _spent["out"] += int(usage.get("completion_tokens") or 0)
        else:
            msg = call(client, args.model, args.effort, pipe.system, messages)
            messages.append({"role": "assistant", "content": msg.content})  # thinking blocks passed back unchanged
            _spent["cost"] += cost(args.model, msg.usage)
            _spent["out"] += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if b.type == "text")
        pipe.submit(text)
        prompt = pipe.next_prompt()


if __name__ == "__main__":
    main()
