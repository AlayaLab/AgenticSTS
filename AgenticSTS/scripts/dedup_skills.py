"""Skills deduplication analysis and cleanup script."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402

with paths.skills_file().open() as f:
    skills = json.load(f)

# ============================================================
# DELETION PLAN — each entry: (index, reason)
# ============================================================
deletions = []

# --- COMBAT: Silent poison/shiv TOOL DISPATCH redundancy (14 skills -> keep [68]) ---
poison_tool_dupes = [36, 40, 46, 49, 51, 53, 55, 57, 60, 63, 65, 70, 71, 114]
for i in poison_tool_dupes:
    deletions.append((i, "duplicate: Silent poison tool dispatch (keep [68] merged)"))

# --- COMBAT: multi_enemy_attrition_calc_v4 TOOL DISPATCH (7 -> merge into [50]) ---
attrition_tool_dupes = [47, 48, 59, 62, 64, 67, 72]
for i in attrition_tool_dupes:
    deletions.append((i, "duplicate: multi-enemy attrition tool dispatch (merged into [50])"))

# --- COMBAT: Multi-enemy offense duplicates ---
deletions.append((32, "duplicate: anti-turtling (merged into [31] offense windows)"))
deletions.append((69, "duplicate: Silent multi-enemy offense (merged into [31])"))
deletions.append((50, "duplicate: multi-enemy offense (merged into [31])"))

# --- COMBAT: Summoner focus duplicates ---
deletions.append((77, "duplicate: generic summoner focus (merged into [80])"))
deletions.append((82, "duplicate: summoner focus (identical to [77], merged into [80])"))
deletions.append((73, "duplicate: Louse Progenitor (merged into [80] which has same enemy trigger)"))

# --- COMBAT: Living Fog duplicates ---
deletions.append((81, "duplicate: Living Fog (merged into [109])"))
deletions.append((88, "duplicate: Living Fog Smoggy (merged into [109])"))

# --- COMBAT: Block/defensive priority duplicates ---
deletions.append((10, "duplicate: low HP multi-enemy (merged into [38])"))
deletions.append((78, "duplicate: block mandate (merged into [83] defensive priority)"))
deletions.append((94, "duplicate: no powers facing lethal (merged into [83])"))

# --- COMBAT: dead turn overlap ---
deletions.append((12, "duplicate: dead turn combat (covered by [0] energy management)"))

# --- COMBAT: merge [108] into [107] (both Knowledge Demon) ---
deletions.append((108, "duplicate: boss powers-first (merged into [107] Sloth)"))

# --- COMBAT: low-value ---
deletions.append((1, "low value: potion targeting (usage=0, niche)"))

# --- DECK_BUILDING: Silent archetype commitment (5 -> 1) ---
for i in [54, 56, 58, 61]:
    deletions.append((i, "duplicate: Silent archetype (merged into [52])"))

# --- DECK_BUILDING: Energy curve / playability ---
for i in [13, 86, 92]:
    deletions.append((i, "duplicate: energy curve / playability (merged into [17])"))

# --- DECK_BUILDING: Dead turn response ---
deletions.append((18, "duplicate: dead turn deck (merged into [14])"))
deletions.append((93, "duplicate: dead turn metric (merged into [14])"))

# --- DECK_BUILDING: Card removal priority ---
deletions.append((112, "duplicate: deck bloat (merged into [42])"))

# --- DECK_BUILDING: Early card selection ---
deletions.append((35, "duplicate: shop energy priority (merged into [26])"))
deletions.append((74, "duplicate: energy solution (merged into [26])"))

# --- DECK_BUILDING: Silent win condition ---
deletions.append((100, "duplicate: Silent win condition (merged into [102])"))

# --- DECK_BUILDING: Greed curse ---
deletions.append((22, "duplicate: playability after curse (merged into [21])"))

# --- DECK_BUILDING: additional merges ---
deletions.append((27, "duplicate: 0-cost energy fix (merged into [17] energy curve)"))
deletions.append((30, "duplicate: critical HP block (merged into combat [38])"))
deletions.append((103, "duplicate: card rewards over gold (merged into [4] seed)"))
deletions.append((104, "duplicate: poison 3+ sources (merged into [52] archetype)"))
deletions.append((34, "duplicate: Silent 2-cost cap (merged into [17] energy curve)"))
deletions.append((9, "duplicate: quest cards (merged into [4] seed)"))
deletions.append((99, "duplicate: strong cards basics-heavy (merged into [4] seed)"))

# --- EVENT ---
deletions.append((85, "duplicate: Silver Crucible (same as [23])"))
deletions.append((89, "duplicate: event HP tool dispatch (merged into [110])"))
deletions.append((115, "duplicate: Silent event HP (merged into [110])"))
deletions.append((111, "duplicate: forced discard (merged into [113])"))
deletions.append((75, "duplicate: floor 1 event (merged into [23])"))
deletions.append((41, "low value: draw-reduction curses (niche, usage=0)"))

# --- REST ---
deletions.append((11, "duplicate: Act 3 heal (merged into [96])"))
deletions.append((19, "duplicate: dead turn surgery (covered by [14] deck_building)"))

# --- MAP ---
deletions.append((16, "duplicate: first combat path (merged into [15])"))
deletions.append((98, "duplicate: Silent elite readiness (merged into [15])"))

# ============================================================
# REPORT
# ============================================================
del_indices = set(d[0] for d in deletions)
kept = [s for i, s in enumerate(skills) if i not in del_indices]

before_src = Counter(s['source'] for s in skills)
after_src = Counter(s['source'] for s in kept)
before_cat = Counter(s['category'] for s in skills)
after_cat = Counter(s['category'] for s in kept)

print("=" * 80)
print("SKILLS CLEANUP REPORT")
print("=" * 80)
print(f"\nBefore: {len(skills)} skills ({before_src['seed']} seed, {before_src['discovered']} discovered, {before_src['evolved']} evolved)")
print(f"After:  {len(kept)} skills ({after_src.get('seed',0)} seed, {after_src.get('discovered',0)} discovered, {after_src.get('evolved',0)} evolved)")
print(f"Deleted: {len(del_indices)}")

print("\n--- Category breakdown ---")
print(f"{'Category':<15} {'Before':>6} {'After':>6} {'Deleted':>7}")
for cat in sorted(set(list(before_cat.keys()) + list(after_cat.keys()))):
    b = before_cat.get(cat, 0)
    a = after_cat.get(cat, 0)
    print(f"{cat:<15} {b:>6} {a:>6} {b-a:>7}")

print("\n--- Deletions by type ---")
reasons = Counter()
for _, reason in deletions:
    tag = reason.split(":")[0].strip()
    reasons[tag] += 1
for r, c in reasons.most_common():
    print(f"  {r}: {c}")

print(f"\n{'='*80}")
print("DELETED SKILLS (by category)")
print("=" * 80)
sorted_dels = sorted(deletions, key=lambda x: (skills[x[0]]['category'], x[0]))
cur_cat = None
for i, reason in sorted_dels:
    s = skills[i]
    if s['category'] != cur_cat:
        cur_cat = s['category']
        print(f"\n  {cur_cat.upper()}:")
    print(f"    [{i:3d}] {s['source']:<10} conf={s['confidence']:.3f} usage={s['usage_count']:>3} | {s['name'][:55]}")
    print(f"          -> {reason}")

print(f"\n{'='*80}")
print("KEPT SKILLS (final list)")
print("=" * 80)
for cat in ['boss', 'combat', 'deck_building', 'event', 'map', 'rest']:
    cat_kept = [(i, s) for i, s in enumerate(skills) if s['category'] == cat and i not in del_indices]
    print(f"\n  {cat.upper()} ({len(cat_kept)} skills):")
    for i, s in cat_kept:
        merge_targets = [d[0] for d in deletions if f"[{i}]" in d[1] or f" {i}]" in d[1] or f"[{i} " in d[1]]
        flag = f" [MERGE from {merge_targets}]" if merge_targets else ""
        print(f"    [{i:3d}] {s['source']:<10} conf={s['confidence']:.3f} usage={s['usage_count']:>3} | {s['name'][:55]}{flag}")
