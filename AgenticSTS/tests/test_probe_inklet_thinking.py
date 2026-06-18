from __future__ import annotations

from types import SimpleNamespace

from scripts.probe_inklet_thinking import apply_system_profile, build_stats


def test_apply_system_profile_is_idempotent():
    system = "You are a careful agent."

    updated = apply_system_profile(system, "think_before_tool")
    updated_twice = apply_system_profile(updated, "think_before_tool")

    assert updated == updated_twice
    assert "Before any tool call" in updated


def test_build_stats_counts_signature_delta_and_text_chars():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="abc"),
            SimpleNamespace(type="text", text="hello"),
            SimpleNamespace(type="tool_use", name="combat_plan"),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )
    events = [
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="thinking"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="thinking_delta", thinking="abc"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="signature_delta", signature="sig_123"),
        ),
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="text"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="hello"),
        ),
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"x":1}'),
        ),
    ]

    stats = build_stats(
        mode="adaptive",
        effort="high",
        system_profile="think_before_tool",
        run_index=1,
        response=response,
        events=events,
    )

    assert stats.block_types == ["thinking", "text", "tool_use"]
    assert stats.thinking_chars == 3
    assert stats.text_chars == 5
    assert stats.raw_thinking_delta_chars == 3
    assert stats.raw_signature_delta_count == 1
    assert stats.raw_tool_json_chars == 7
    assert stats.raw_has_signature_delta is True
