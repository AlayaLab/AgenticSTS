from __future__ import annotations

from src.brain.cache_diagnostics import compute_cache_prefix_hash


def test_prefix_hash_ignores_tail_after_system_breakpoint() -> None:
    system = [{
        "type": "text",
        "text": "system",
        "cache_control": {"type": "ephemeral"},
    }]
    messages_a = [
        {"role": "user", "content": "first prompt"},
        {"role": "assistant", "content": "tail a"},
    ]
    messages_b = [
        {"role": "user", "content": "different prompt"},
        {"role": "assistant", "content": "tail b"},
    ]

    hash_a = compute_cache_prefix_hash(tools=None, system=system, messages=messages_a)
    hash_b = compute_cache_prefix_hash(tools=None, system=system, messages=messages_b)

    assert hash_a
    assert hash_a == hash_b


def test_prefix_hash_tracks_first_message_breakpoint_only() -> None:
    system = [{"type": "text", "text": "system"}]
    first = {
        "role": "user",
        "content": [{
            "type": "text",
            "text": "combat start",
            "cache_control": {"type": "ephemeral"},
        }],
    }
    changed_first = {
        "role": "user",
        "content": [{
            "type": "text",
            "text": "different combat start",
            "cache_control": {"type": "ephemeral"},
        }],
    }

    hash_a = compute_cache_prefix_hash(
        tools=None,
        system=system,
        messages=[first, {"role": "assistant", "content": "round 1"}],
    )
    hash_b = compute_cache_prefix_hash(
        tools=None,
        system=system,
        messages=[first, {"role": "assistant", "content": "round 2"}],
    )
    hash_c = compute_cache_prefix_hash(
        tools=None,
        system=system,
        messages=[changed_first, {"role": "assistant", "content": "round 2"}],
    )

    assert hash_a
    assert hash_a == hash_b
    assert hash_a != hash_c


def test_prefix_hash_extends_through_tool_result_breakpoint() -> None:
    system = [{"type": "text", "text": "system"}]
    messages_a = [
        {"role": "user", "content": "combat start"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "read_guide", "input": {"topic": "boss"}}
            ],
        },
        {"role": "user", "content": [{
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "Use poison.",
            "cache_control": {"type": "ephemeral"},
        }]},
        {"role": "assistant", "content": "tail a"},
    ]
    messages_b = [
        {"role": "user", "content": "combat start"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "read_guide", "input": {"topic": "boss"}}
            ],
        },
        {"role": "user", "content": [{
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "Use poison.",
            "cache_control": {"type": "ephemeral"},
        }]},
        {"role": "assistant", "content": "tail b"},
    ]
    messages_c = [
        {"role": "user", "content": "combat start"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "read_guide",
                    "input": {"topic": "elites"},
                }
            ],
        },
        {"role": "user", "content": [{
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "Use poison.",
            "cache_control": {"type": "ephemeral"},
        }]},
        {"role": "assistant", "content": "tail b"},
    ]

    hash_a = compute_cache_prefix_hash(tools=None, system=system, messages=messages_a)
    hash_b = compute_cache_prefix_hash(tools=None, system=system, messages=messages_b)
    hash_c = compute_cache_prefix_hash(tools=None, system=system, messages=messages_c)

    assert hash_a
    assert hash_a == hash_b
    assert hash_a != hash_c
