import asyncio
from types import SimpleNamespace

from src.agent.loop import AgentLoop


def test_handle_card_select_confirms_without_selection_payload() -> None:
    agent = object.__new__(AgentLoop)
    agent._card_select_selected = {0}
    agent._card_select_target = 2

    executed: list[tuple[dict, dict]] = []

    async def fake_execute(action: dict, **kwargs) -> None:
        executed.append((action, kwargs))

    def fake_reset() -> None:
        agent._card_select_selected.clear()
        agent._card_select_target = 0

    agent._execute = fake_execute
    agent._reset_card_select_tracking = fake_reset

    gs = SimpleNamespace(
        selection=None,
        available_actions=["confirm_selection", "use_potion", "discard_potion"],
        run=SimpleNamespace(floor=45),
        state_type="card_select",
    )

    decision = asyncio.run(agent._handle_card_select(gs))

    assert decision is not None
    assert decision.action == {"action": "confirm_selection"}
    assert executed == [({"action": "confirm_selection"}, {"delta_source": "confirm"})]
    assert agent._card_select_selected == set()
    assert agent._card_select_target == 0
