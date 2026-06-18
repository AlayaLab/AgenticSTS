"""Replay a logged LLM call to test reproducibility.

Reads the saved fixture from tests/fixtures/replay_card_reward_3d469df1.json
and sends the same system prompt + messages + tools to the API N times,
comparing responses.

Usage:
    python -m scripts.replay_card_reward [--runs N] [--model MODEL]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def load_fixture() -> dict:
    path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "replay_card_reward_3d469df1.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def replay_once(fixture: dict, model_override: str | None = None, temperature: float | None = None) -> dict:
    """Send one API call matching the logged parameters. Returns parsed result."""
    import anthropic

    client = anthropic.Anthropic(
        api_key=config.LLM_API_KEY,
        base_url=config.ANTHROPIC_BASE_URL or None,
    )

    model = model_override or fixture["model"]
    system_prompt = fixture["system_prompt"]
    messages = fixture["messages"]
    tools = fixture["tools"]

    temp = temperature if temperature is not None else config.LLM_TEMPERATURE

    kwargs = {
        "model": model,
        "system": system_prompt,
        "messages": messages,
        "tools": tools,
        "max_tokens": config.LLM_MAX_TOKENS,
        "temperature": temp,
    }

    t0 = time.monotonic()

    # Use streaming if custom base URL (proxy compat, same as V2Backend)
    use_stream = bool(tools and config.ANTHROPIC_BASE_URL)
    if use_stream:
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
    else:
        response = client.messages.create(**kwargs)

    latency_ms = (time.monotonic() - t0) * 1000

    # Extract tool use
    tool_uses = []
    text_blocks = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_uses.append({
                "name": block.name,
                "input": block.input,
            })
        elif getattr(block, "type", None) == "text":
            text_blocks.append(block.text)

    result = {
        "model": model,
        "latency_ms": round(latency_ms, 1),
        "stop_reason": response.stop_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "tool_uses": tool_uses,
        "text_blocks": text_blocks,
    }

    return result


def extract_decision(result: dict) -> dict | None:
    """Extract the card_reward_action tool call from a result."""
    for tu in result["tool_uses"]:
        if tu["name"] == "card_reward_action":
            return tu["input"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Replay card reward LLM call")
    parser.add_argument("--runs", type=int, default=5, help="Number of replay runs")
    parser.add_argument("--model", type=str, default=None, help="Model override")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature override")
    args = parser.parse_args()

    fixture = load_fixture()
    temp = args.temperature if args.temperature is not None else config.LLM_TEMPERATURE
    print("=== Card Reward Replay Test ===")
    print(f"Model: {args.model or fixture['model']}")
    print(f"Runs: {args.runs}")
    print(f"Temperature: {temp}")
    print("Original response action: choose_reward_card, option_index=0 (Blade Dance)")
    print()

    results = []
    for i in range(args.runs):
        print(f"--- Run {i+1}/{args.runs} ---")
        try:
            result = replay_once(fixture, model_override=args.model, temperature=args.temperature)
            results.append(result)

            decision = extract_decision(result)
            if decision:
                action = decision.get("action", "?")
                idx = decision.get("option_index", "?")
                reasoning = decision.get("reasoning", "")[:200]
                note = decision.get("strategic_note", "")[:100]
                print(f"  Action: {action}, Index: {idx}")
                print(f"  Reasoning: {reasoning}...")
                print(f"  Note: {note}")
            else:
                # Maybe it called a query tool first
                for tu in result["tool_uses"]:
                    print(f"  Tool: {tu['name']}, input_keys: {list(tu['input'].keys())}")

            print(f"  Latency: {result['latency_ms']:.0f}ms, Tokens: {result['output_tokens']}")
            print(f"  Stop: {result['stop_reason']}")
            if result["text_blocks"]:
                for tb in result["text_blocks"]:
                    print(f"  Text: {tb[:200]}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"error": str(e)})
        print()

    # Summary
    print("=== Summary ===")
    choices = []
    for r in results:
        if "error" in r:
            choices.append("ERROR")
            continue
        d = extract_decision(r)
        if d:
            choices.append(f"option_{d.get('option_index', '?')}")
        else:
            # Query tool called first — not a direct decision
            tool_names = [tu["name"] for tu in r.get("tool_uses", [])]
            choices.append(f"query:{','.join(tool_names)}")

    print(f"Choices: {choices}")
    from collections import Counter
    counts = Counter(choices)
    print(f"Distribution: {dict(counts)}")
    total_valid = sum(1 for c in choices if c != "ERROR")
    if total_valid > 0:
        blade_dance = counts.get("option_0", 0)
        print(f"Blade Dance (option_0): {blade_dance}/{total_valid} = {blade_dance/total_valid*100:.0f}%")
        match_original = blade_dance == total_valid
        print(f"100% reproducible: {match_original}")


if __name__ == "__main__":
    main()
