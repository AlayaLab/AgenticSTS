from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.loop import AgentLoop


@pytest.mark.asyncio
async def test_agent_loop_run_reloads_prompt_context_at_run_start() -> None:
    memory = MagicMock()
    memory.reload_prompt_context = MagicMock()

    with (
        patch.object(AgentLoop, "_init_knowledge", return_value=None),
        patch.object(AgentLoop, "_init_web_searcher", return_value=None),
        patch.object(AgentLoop, "_load_counter", return_value=0),
        patch.object(AgentLoop, "_init_skill_library", return_value=None),
        patch.object(AgentLoop, "_init_v2", return_value=None),
    ):
        loop = AgentLoop(
            client=MagicMock(),
            max_steps=0,
            use_llm=False,
            memory_manager=memory,
        )

    loop._safe_post_run = AsyncMock()
    loop._client.set_run_id = MagicMock()

    await loop.run()

    memory.reload_prompt_context.assert_called_once_with()
