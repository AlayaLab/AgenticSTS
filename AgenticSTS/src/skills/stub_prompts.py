"""Fill / update prompt assembly for Mode B seed stubs.

Builds the four-part prompt the LLM sees when filling a stub:
- Part A: role + scope + out-of-scope (system-prompt-like)
- Part B: evidence (combat replays or trajectories from selected runs)
- Part C: dimensions hint (from scaffold.dimensions_to_consider)
- Part D: output schema + format constraints

Update mode adds a leading "Existing Content" section so the LLM can refine
rather than start from scratch — but with explicit permission to rewrite
freely when new evidence contradicts old principles.

Critical methodology constraint: this prompt MUST NOT include the full text
of any expert seed skill. Topic-level hints (in scaffold.dimensions_to_consider)
are acceptable; specific tactics are not.

Spec: ``docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md``
"""

from __future__ import annotations


_SYSTEM_INTRO_TEMPLATE = """\
You are a strategy-skill author for an autonomous Slay the Spire 2 agent.
Your job is to write a GENERALIZED skill describing this character's
strategic principles for {state_type_cluster}.

A "skill" is the most general layer of agent knowledge:
- It describes principles applying to MOST decisions, not specific situations.
- Per-enemy mechanics belong in combat_guides (already exist).
- Per-card stats belong in card_memory (already exist).
- Per-mistake patches belong in fine-grained skills (already exist).
Your skill complements but DOES NOT duplicate these layers."""


_OUTPUT_SCHEMA_TEMPLATE = """\
Output JSON only:
{{
  "principles": [
    {{"text": "<imperative principle, one sentence>", "example": "<concrete example showing application>"}},
    ...
  ],
  "confidence": 0.5-0.9,
  "dimensions_covered": ["dim1", "dim2", ...],
  "evidence_basis": "<one-sentence justification citing run-history patterns>"
}}

Constraints:
- {structure}
- {voice}
- max_distinct_card_names: {max_cards}
- max_distinct_enemy_names: {max_enemies}
- DO NOT include specific HP thresholds or damage numbers (e.g. "Block 12 damage").
- DO NOT name cards or enemies that don't appear in your evidence.
- Token budget: {token_budget}"""


_UPDATE_REFERENCE_TEMPLATE = """\

## Existing Content (v{version})
{existing_content}

Refine this content based on new run data. If new evidence contradicts existing
principles, REPLACE rather than append. Avoid accreting low-confidence rules
from each run. Early-run content is expected to be coarse; rewrite freely as
evidence accumulates.
"""


def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items)


def _build_core(scaffold: dict, state_type_cluster: str, evidence: str) -> str:
    """Assemble the four core parts (no update reference)."""
    fc = scaffold.get("format_constraints", {})
    lg = scaffold.get("leakage_guard", {})

    part_a = _SYSTEM_INTRO_TEMPLATE.format(state_type_cluster=state_type_cluster)
    part_meta = "\n\n".join([
        f"Topic: {scaffold.get('topic', '')}",
        f"Scope: {scaffold.get('scope', '')}",
        "Out of scope:\n" + _format_bullets(scaffold.get("out_of_scope", [])),
    ])
    part_b = "## Evidence\n" + evidence
    part_c = (
        "## Cover these dimensions if your data supports them; "
        "skip if data is too thin:\n"
        + _format_bullets(scaffold.get("dimensions_to_consider", []))
    )
    part_d = _OUTPUT_SCHEMA_TEMPLATE.format(
        structure=fc.get("structure", "5-8 numbered principles + example each"),
        voice=fc.get("voice", "Imperative, second-person"),
        max_cards=lg.get("max_distinct_card_names", 8),
        max_enemies=lg.get("max_distinct_enemy_names", 3),
        token_budget=fc.get("token_budget", "300-700 tokens"),
    )

    return "\n\n".join([part_a, part_meta, part_b, part_c, part_d])


def build_fill_prompt(
    *,
    scaffold: dict,
    state_type_cluster: str,
    evidence: str,
) -> str:
    """Build the first-fill prompt (no existing content reference)."""
    return _build_core(scaffold, state_type_cluster, evidence)


def build_update_prompt(
    *,
    scaffold: dict,
    state_type_cluster: str,
    evidence: str,
    existing_content: str,
    existing_version: int,
) -> str:
    """Build the update prompt: core fill + existing content reference."""
    core = _build_core(scaffold, state_type_cluster, evidence)
    update_clause = _UPDATE_REFERENCE_TEMPLATE.format(
        version=existing_version,
        existing_content=existing_content,
    )
    return core + update_clause
