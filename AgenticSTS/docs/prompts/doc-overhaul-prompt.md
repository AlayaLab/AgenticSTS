# Documentation Overhaul Prompt

Use this as the initial message in a new Claude Code Sonnet session.

---

## Prompt (copy below this line)

```
我需要你帮我重构项目文档。当前 CLAUDE.md 有 63KB/655行/~21K tokens，远超 Claude Code 有效阅读的 10K token 上限。Memory 文件也有 48KB。文档内容严重过时（最后大更新在 3/28，之后新增了 24 个模块未记录）。

## 目标

将 CLAUDE.md 从 655 行压缩到 ~200 行（目标 <8K tokens），让 Claude Code 每次会话都能有效读取全部项目上下文。

## 执行计划

### Phase 1: 审计当前文档 vs 实际代码

1. 读取 `CLAUDE.md` 全文，逐节标记：
   - KEEP: 仍然准确且有用的内容
   - UPDATE: 内容过时需要更新（对照实际代码）
   - ARCHIVE: 历史信息，移到归档文件
   - DELETE: 重复或无用

2. 扫描以下目录，找出未记录的新模块：
   - `src/brain/` (新增: decision_parser.py, enemy_pattern_injector.py, plan_verifier.py, proxy_compat.py, state_snapshot_store.py, cache_diagnostics.py)
   - `src/brain/prompts/` (新增: _card_clarifications.py, _keyword_fmt.py)
   - `src/knowledge/` (新增: act_lookup.py, enchantment_lookup.py, encounter_lookup.py, keyword_lookup.py, relic_lookup.py)
   - `src/memory/` (新增: card_memory_extractor.py, card_memory_store.py, hint_sanitizer.py, situation.py)
   - `src/skills/` (新增: cohort_discovery.py, cohort_utils.py, combat_quality.py, dedup.py, evidence.py, hypothesis_store.py)
   - `src/skills/seeds/` (新增: silent_a10_guide.json, silent_card_notes.json)

3. 对每个新模块，读取文件头部和关键函数，写一行描述

### Phase 2: 重构 CLAUDE.md 为索引结构

新结构（目标 ~200 行）:

```
# AgenticSTS
一句话描述 + 目标

## Quick Reference
- Entry point, config, how to run (10 lines)

## Architecture (索引式)
src/ 目录树，每个文件一行描述（当前的 Architecture 段保留但更新）
- 新模块补进去
- 删除已不存在的文件

## Key Decisions (精简到 ~30 行)
只保留影响日常开发的决策：
- Model routing（哪个 tier 用哪个 model）
- Tool architecture（6 gameplay tools, dynamic tools via preprocessor）
- Prompt caching strategy
- Combat conversation pattern
- Strategic thread mechanism
删除：已实现细节、proxy workaround 历史、具体 bug 修复记录

## Current State
- 当前工作重点 / 未完成 TODO（只列 active items）
- 已知限制

## Conventions
从 Important Patterns 精简，只保留编码时需要知道的约定
```

归档到 `docs/archive/`:
- `docs/archive/bugs-fixed.md` — 当前 Bugs Fixed 全段
- `docs/archive/development-phases.md` — 当前 Development Phases 全段
- `docs/archive/detailed-technical-decisions.md` — Key Technical Decisions 的详细版本

### Phase 3: 清理 Memory 文件

1. 删除过时的 memory 文件:
   - `project_phase2_status.md` (3/13, 内容已过时)
   - `feedback_v2_testing.md` (3/21, V2 早期测试记录已无用)
   - `feedback_v2_bugs.md` (3/27, 旧 bug 列表已在 git 中)

2. 合并/更新:
   - `project_architecture.md` + `project_v2_architecture.md` → 合并为一个当前架构 memory
   - `project_self_evolution_plan.md` → 更新为当前 evolution 状态
   - `project_monitor_dashboard.md` → 检查是否还准确
   - `project_token_optimization.md` → 已完成的优化可以删除

3. 新增 memory（如果在代码中发现重要的非显而易见的信息）:
   - 记录新增的 cohort-based skill discovery 系统
   - 记录 scoped strategic notes 机制
   - 记录 enemy pattern injection

4. 更新 MEMORY.md 索引

### Phase 4: 验证

1. 字数检查: CLAUDE.md 必须 < 200 行
2. 准确性: 每个文件描述对照实际代码验证
3. 完整性: 所有 src/ 下的 .py 文件都在 Architecture 中有一行描述
4. Memory 总量: 所有 memory 文件合计 < 30KB

## 工作方式

- 先读代码，后写文档（不要凭记忆写）
- 用 `grep` 和 `read` 验证每个描述
- 归档时保留原文不修改
- 新 CLAUDE.md 每行都要对应实际代码
- 用中文写 memory 描述（项目涉及中文游戏）
- CLAUDE.md 保持英文（因为是代码项目文档）

## 不要做

- 不要重写代码
- 不要改动 src/ 下任何文件
- 不要创建新的 .md 文件（除了 docs/archive/ 下的归档）
- 不要删除 CLAUDE.md 中的 Running 段（保留可执行信息）
```
