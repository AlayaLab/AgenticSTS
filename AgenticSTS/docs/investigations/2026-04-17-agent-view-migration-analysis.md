# agent_view 迁移价值调研

**日期**：2026-04-17
**问题**：CharTyr 上游 mod v0.5.3 引入的 `/state.agent_view` 并行视图对我们的 Python agent 值不值得扩大采用？
**结论预告**：**当前已是最优局部采用；扩大到 glossary 做 gap-backfill 是 B 档微增量；整体替换顶层字段（C 档大迁移）不值。**

---

## 0. 用户前提勘误

| 前提（来自调研 prompt） | 实际情况 | 影响 |
|---|---|---|
| "Pydantic 模型 extra="ignore" 静默丢掉了 agent_view" | `upstream_models.py:851` 已声明 `agent_view: AgentViewPayload \| None = None`，完整模型定义在 555-818 行 | 字段是 **First-class**，不被 ignore |
| "我们的 Python 客户端一直在用顶层字段" | 实际已有 **4 处 agent_view 消费点**（见 §1） | 不是零采用，是"局部采用" |
| KW_GLOSSARY "23 条手写" | 实际 20 条 | 小修正（不影响结论） |
| 上游 glossary "18 条中文" | 确认 18 条（见 §3.1 完整清单） | 前提正确 |

---

## 1. 当前 agent_view 已消费的 4 个点（grep 出来的事实）

| 位置 | 用途 | agent_view 字段 | 顶层能否替代 |
|---|---|---|---|
| `src/brain/conversation.py:1020-1060` | 战斗 prompt 的 `## Piles` 段：pile 大小 + 按关键词过滤后注入 draw/discard/exhaust 内容 | `av.combat.draw/.discard/.exhaust` | ❌ 顶层 `RawCombatPayload` 不含 draw/discard/exhaust 内容；MCP API 其余只给 pile size via 专用端点 |
| `src/agent/loop.py:3162-3178` | 记忆抽取时构造 enemy intent 文本：若顶层 `e.intents` 结构化列表为空（旧版 mod 兼容），fallback 到 `av_enemy.intent` 字符串 | `av.combat.enemies[].intent` (string) | 仅作为兼容 fallback，顶层 `intents[]` 是主源 |
| `src/memory/combat_delta.py:192-205` | 每次 action 的 state diff：比较 `pre_av.combat.exhaust` vs `post_av.combat.exhaust` 判断哪些卡被消耗 | `av.combat.exhaust[].line` | ❌ 顶层无 exhaust 内容 |
| `src/log/session_logger.py:195-201` | JSONL 结构化日志里记 pile size | `av.combat.{draw,discard,exhaust}` 长度 | ❌ 同上 |

**关键观察**：所有 4 处都在消费 **顶层 API 根本没有** 的字段（pile 内容 / exhaust 列表）。这是一次"只采用上游 API 盲区"的最小化策略。

**另一个关键观察**：第三方日志调研 agent 报告 "最近 5 个 JSONL 完全没有 agent_view 字段"，这是**误读**。session_logger 的 `data` dict 只把 agent_view 的 *pile 大小* 抽出来序列化（`draw_pile_size: 3`），没把整个 agent_view 子树 dump 进 JSONL。wire 层 agent_view 实际存在（否则 `gs.agent_view.combat.draw` 会 crash）。

---

## 2. C# 侧 agent_view 结构全貌（15 个 BuildAgent*Payload）

来源：`STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs`

### 2.1 场景 builder（全量）

| 方法 | 行号 | 主要字段 |
|---|---|---|
| `BuildAgentViewPayload` | 2991 | 顶层容器：version, screen, turn, actions, available_actions, glossary, + 所有子 builder |
| `BuildAgentCombatPayload` | 3048 | player(hp/block/energy/orbs) + hand[] + enemies[] + draw/discard/exhaust |
| `BuildAgentRunPayload` | 3094 | character, floor, hp, gold, deck[], relics[]（仅名字）, potions[], piles{} |
| `BuildAgentSelectionPayload` | 3149 | kind, prompt, cards[], selected_cards[], selectable_cards[], preview_cards[] |
| `BuildAgentCardsViewPayload` | 3173 | title + cards[] (Smith 升级列表) |
| `BuildAgentRewardPayload` | 3189 | pending_card_choice, rewards[], cards[], alternatives[] |
| `BuildAgentEventPayload` | 3220 | id, title, options[] (每个含 `line` 字符串) |
| `BuildAgentShopPayload` | 3242 | cards[] (含 `line` 合并价格) + relics[] + potions[] + remove{} |
| `BuildAgentRestPayload` | 3293 | options[] (index, line, enabled) |
| `BuildAgentMapPayload` | 3313 | current 字符串 + options[] |
| `BuildAgentCharacterSelectPayload` | 3331 | selected, embark, ascension, characters[] |
| `BuildAgentTimelinePayload` | 3353 | back, confirm, slots[] |
| `BuildAgentChestPayload` | 3373 | opened, claimed, relics[] |
| `BuildAgentModalPayload` | 3392 | type, confirm, dismiss, confirm_label |
| `BuildAgentGameOverPayload` | 3409 | victory, floor, character |
| `BuildAgentGlossary` | 3876 | Dictionary<string, string> keyword→中文定义 |

### 2.2 辅助 card builder

| 方法 | 行号 | 用途 |
|---|---|---|
| `BuildAgentHandCardPayload` | 3426 | 手牌详细：`i, line, type, playable, target, targets[], why, keywords[], mods[]` |
| `BuildAgentChoiceCardPayload` | 3450 | 选择/奖励卡（**无 mods**） |
| `BuildAgentPricedCardPayload` | 3473 | 商店卡（加价格 + afford） |
| `BuildAgentCardStacks` | 3499/3508/3517 | **按 name+upgraded+cost 聚合卡堆**（→ `"Defend×3"`） |
| `FormatCardLine` | 3575 | 统一 `名字[费]：规则文本` |
| `FormatOrbLine` | 3622 | `"{name} 被动{p}/激发{e}"`（中文） |
| `FormatPotionLine` | 3627 | `"{i}: {name}：{description}"` |

### 2.3 actions vs available_actions

GameStateService.cs:3024-3025 两个字段从 **同一** `BuildAvailableActionNames()` 返回值赋值，内容**完全一致**。`agent_view.actions` ≡ `agent_view.available_actions` ≡ 顶层 `available_actions`。没有"在复杂状态下可能有差异"这种事，用哪个都一样。

---

## 3. Glossary 对比（用户问题 Q1）

### 3.1 完整双向 diff

**我们有上游没有（9 条）**——Silent/Scholar 核心机制：

| 我们的 key | 语义 | 上游为什么没对应 |
|---|---|---|
| `sly` | 被卡效果弃牌时免费打出（Survivor/Acrobatics 专用） | 上游未定义 |
| `shiv` | 0 费 4 伤害 Attack + Exhaust（Silent 动态生成） | 未收录 |
| `scry` | 查看牌库顶 N 张 | 未收录 |
| `channel` | 充能球入槽（Scholar 核心） | 未收录（但上游有 `球位` 作为 C# 等价） |
| `replay` | N+1 次播放倍增效果（Silent Glam 附魔） | 未收录 |
| `artifact` | 否定 N 层 debuff（trap：上 debuff 前检查） | 未收录 |
| `intangible` | 伤害/HP损失降为 1 | 未收录 |
| `innate` | 开局必有 | 未收录 |
| `eternal` | 不可移除/变形 | 未收录 |

**上游有我们没有（7 条）**——边缘 debuff + Scholar 机制：

| 上游 key | 上游定义（中译英） | 我们是否需要 |
|---|---|---|
| `眩晕` (Stun) | "通常是无法主动打出的状态牌" | ⚠️ Silent 受影响时有用，我们可以补 |
| `灼伤` (Burn) | "会在手中或结算时带来额外伤害" | ⚠️ Regent 核心 debuff，**应该补** |
| `虚空` (Void) | "在抽到时消耗能量或妨碍出牌" | ⚠️ Silent 遇 Time Eater 时会吃，**应该补** |
| `力量流失` (StrengthDown) | "临时降低力量" | 我们已经用 `strength` 的 trap 提示 cover |
| `集中` (Focus) | "强化充能球被动与激发" | Scholar 核心，**应该补** |
| `附魔` / `灌注` (Enchantment / Infusion) | 词条/附着层 | 系统性概念，`mods` 字段附带 |
| `临时` (Temporary) | "在回合结束或打出后离开" | 边缘词 |

**11 条重叠**：block/weak/vulnerable/poison/strength/dexterity/frail/retain/exhaust/unplayable/ethereal 双方都有。

### 3.2 关键质量差异

| 维度 | 我们（KW_GLOSSARY） | agent_view.glossary |
|---|---|---|
| 条数 | 20（手写英文） | 18（手写中文）+ dynamic mods 扫描 |
| 深度 | 含 **trap 提示**：`"End-of-turn auto-discard does NOT trigger Sly"`, `"Check enemy Artifact before applying debuffs"`, `"Game-changing effect"` | 仅定义一句话 |
| 语言 | 英文（我们的 prompt 全英文） | 中文（**prompt 若注入会语种混杂**） |
| 筛选 | 扫 `card rules_text` 后交集（KW_GLOSSARY > _dll_mechanics） | C# 侧 `GetGlossaryMatches()` 扫 rules_text + card.mods + ascension descs + selection prompt，18 条上限 |
| Fallback | `_dll_mechanics` 自动从 DLL 扫（含所有 keywords.json 的定义） | 无（固定 18 条） |

**我们的 Tier 2 fallback (`_dll_mechanics`) 是关键优势**：运行时从 `data/knowledge/upstream/mechanics_dll.json` 加载游戏 DLL 扫出的**所有**关键词机制（不止 18 条），当 KW_GLOSSARY 未覆盖时自动补。上游 glossary 是硬编码固定集合，没有这一层动态能力。

### 3.3 Token 成本

粗估（每个词平均 80-120 字符）：
- 我们的 20 条 trigger 时平均注入 **~3-6 条**（手牌通常只触 Block/Weak/Vulnerable/Exhaust 等）≈ 400-700 chars
- agent_view.glossary 同场景 subset ≈ 3-6 条中文 ≈ 250-400 chars
- 如果全量注入两者叠加 ≈ 2000+ chars = 额外 500 tokens

**省不下多少**。agent_view 的"context-aware"我们已经做到（按 rules_text 扫描）。

### 3.4 结论（glossary 维度）

双方各自独占 ~9 / ~7 条。上游的 `灼伤/虚空/集中` 是**我们应该补的 Regent/Scholar 盲区**，但不是必须通过 agent_view 补——直接手写加 3 条 KW_GLOSSARY 条目成本最低（1 行代码/词）。上游中文定义塞进英文 prompt 不如自己翻译。

---

## 4. Combat payload 对比（用户问题 Q2）

### 4.1 字段级映射

| 我们的 prompt 字段 | 来源 formatter / 顶层 | agent_view.combat 对应 | 迁移能否替代 |
|---|---|---|---|
| Player HP/Block/Energy 一行 | 顶层 `combat.player.current_hp/max_hp/block/energy/stars` 手拼 | `player.hp="35/50"` + `block, energy, stars` | ✅ 可简化（小收益） |
| Orbs（Scholar） | 顶层结构化 `orbs[]` + 自己格式化 | `player.orbs[]` 已格式化字符串（中文） | ⚠️ 语种不匹配 |
| Player powers | 顶层 `combat.player.powers[].{name, amount}` | **缺失**（agent_view 不给） | ❌ 不能迁移 |
| Hand card 一行 | 顶层 `combat.hand[]` 经 `hand_select` prompt 组装 | `hand[].line + type + playable + targets[] + keywords[] + mods[] + why` | ⚠️ 细节（见下） |
| 敌人意图伤害计算 | **`_intent_fmt.compute_total_incoming()`**（CLAUDE.md "唯一真源"） | `enemies[].intent` 字符串如 `"Attack 7x1 (7)"` | ❌ **硬阻断** |
| 敌人 powers | 顶层 `enemies[].powers[]` | **缺失** | ❌ 不能迁移 |
| Piles 段 | `_pile_fmt.format_pile_compact` + 我们 2 周前已接入的 `av.combat.draw/discard/exhaust` | 已在用 | ✅ **已迁移** |
| hand[i].target_previews（每目标伤害） | 顶层 `hand[].target_previews[]` | **缺失** | ❌ 不能迁移 |
| hand[i].{damage, block, hits, total_damage} | 顶层数值字段 | 被折叠进 `line` 字符串 | ❌ 不能做计算 |
| hand[i].unplayable_reason | 顶层显式字段 | `hand[].why` 等价 | ✅ 可替代（几乎相同） |
| Keyword glossary trigger | `_keyword_fmt.format_keyword_glossary(rules_texts)` | 顶层 `agent_view.glossary` dict | ⚠️ 见 §3 |

### 4.2 agent_view.combat 的硬损失（我们需要但它没有）

这些字段**顶层有但 agent_view 完全丢掉**，是阻断整体迁移的关键：

1. **`enemies[].intents[]` 结构化数组**（damage, hits, total_damage, intent_type）→ 退化为字符串 intent
   - `compute_total_incoming()` 依赖此做总入伤计算 → 不能重建
   - `format_poison_hint()` 依赖此做"中毒后剩余 HP"计算 → 不能重建
   - `hand_select.py` 和 `potion.py` 的幸存决策直接用这个
2. **`enemies[].powers[]`**（debuff 层数、persist turns）→ 完全丢失
   - 诸如"敌人 Artifact 3 层，别上 debuff"这类判断无法做
3. **`player.powers[]`**（玩家身上的 buff/debuff）→ 完全丢失
   - Weak/Vulnerable/Frail 状态下的攻防倍率修正
4. **`hand[].target_previews[]`**（每个合法目标的预期伤害）→ 完全丢失
   - 多目标卡（AOE 预期 vs 单点）选 target 关键
5. **`hand[].{damage,block,hits,total_damage}`**（结构化数值）→ 折叠到 `line` 文本
   - 我们 prompt 里直接显示 `Strike (1): 6 damage` 是从数值字段拼的，改用 `line` 要回去解析字符串

**判决：combat 核心 payload 整体迁移 ≈ 自残**。

### 4.3 可简化的 formatter（假设全迁移）

| formatter | 能省多少 | 代价 |
|---|---|---|
| `_pile_fmt.py` | 已在用 agent_view，再迁入无增量 | — |
| `_target_fmt.py` (22 行) | 可删 | 微不足道 |
| `_deck_fmt.strip_bbcode` (30 行) | 理论可删（如果 agent_view.line 已清洗）| 丢 strip_bbcode 通用能力 |
| `_intent_fmt.py` (183 行) | **不能删** | compute_total_incoming 唯一真源 |
| `_card_clarifications.py` (77 行) | **不能删** | 手写 bug-fix 知识（Speedster/Ricochet/Accuracy）agent_view 无法提供 |
| `_relic_fmt.py` (282 行) | **不能删** | 41 条 context-aware 战略提示，agent_view 只给名字 |
| `_keyword_fmt.py` (110 行) | 可部分替代但语种/深度损失 | 见 §3.4 |

**总计可删减**：~50-100 行（target_fmt + strip_bbcode）。**不能删的核心知识**：~650+ 行。ROI 极差。

---

## 5. 实际日志样本对比（用户问题 Q5）

来源：日志调研 agent 抽样 `run_20260417_115929_998c77b9.jsonl`（2551 combat snapshots + 176 reward + 198 event + 73 shop）。

**重要免责**：JSONL 只记了**经我们代码处理过**的字段（见 session_logger.py）。agent_view 原始 wire 格式不在 JSONL 里，但 `av.combat.draw_pile_size` 能写进 JSONL 说明 wire 上 agent_view 存在（否则 None access 会爆）。

### 5.1 战斗样本

顶层敌人 intent（结构化，真实数据）：
```json
{"type": "Attack", "label": "7", "damage": 7, "hits": 1, "total_damage": 7}
{"type": "Buff",   "label": null, "damage": null, "hits": null, "total_damage": null}
```

agent_view 对应（推测，按 C# 格式化规则）：
```
intent: "Attack 7x1 (7)"  或  "Attack 7"
intent: "Buff"  或  "Ritual"（具体名）
```

**差异**：`Buff` 字符串丢掉了具体 buff 名（Ritual vs Metallicize vs Inflame），顶层 `enemies[].powers` 或 `move_id` 才有这种差别。agent_view 的 `intent` 是 UI 图标文案级别的简写。

### 5.2 商店样本

顶层（~5.2 KB/shop state）：结构化 `{name, price, enough_gold, category, is_stocked, rules_text}`
agent_view（预估 ~1.8 KB）：`{i, line: "Skewer (71G) [Character]", affordable: true, stocked: true, keywords: []}`

agent_view 把 rules_text 折叠进 line 丢了（或塞进 line 尾巴）。**商店决策本身需要 rules_text 评估协同**（`_card_clarifications` 触发依赖 name 匹配，不受影响；但 LLM 评估 Skewer 值不值 71G 需要知道 "Deal 7 damage X times"）。

### 5.3 事件样本

顶层带 BBCode 和未解析模板变量：`"Gain [blue]{SmallChestGold}[/blue] [gold]Gold[/gold]."`

agent_view event.options[].line 是清洗过的 summary（按 C# `FormatEventOptionLine` 行 3638）。

**这里 agent_view 有小价值**：省掉我们一次 strip_bbcode 处理。但 `{SmallChestGold}` 变量的实际数值 C# 侧 `FormatEventOptionLine` 会不会解析？需要实测。（调研 agent 推测"已解析"但未验证，此处存疑。）

### 5.4 卡牌奖励样本

顶层只有 `{name, rules_text}`。agent_view 加了 `keywords[], mods[]`（标记升级态）。

**这里 agent_view 有明确价值**：我们 Python 侧目前**分辨不了 Base vs Upgraded** 版本（只看到相同 name）。`mods` 字段（如 `["Upgraded"]`）是盲区补全。

→ 但！`RawRewardCardOptionPayload.upgraded` 字段早在 v0.5.2 就已在顶层（`upstream_models.py:518`）。是我们的卡牌奖励 prompt 没有注入 upgraded 标记。**这个问题不需要 agent_view 就能修**。

---

## 6. 迁移成本评估（用户问题 Q4）

### 假设迁移到 B 档（glossary gap-backfill）

**改动**：
1. `_keyword_fmt.py`：在 KW_GLOSSARY 和 _dll_mechanics 之后增第 3 层——扫 `gs.agent_view.glossary`，补进翻译后的 `灼伤/虚空/集中/眩晕` 等 **我们未覆盖** 的词。
2. 硬编码中英文 map 做翻译（因为我们的 prompt 是英文）。
3. 每次 format_keyword_glossary 多一个可选参数 agent_view。

**收益**：pcm 补上 3-4 个 Regent/Scholar 盲区。
**成本**：~40 行代码 + 3-5 条手写中英翻译。
**风险**：翻译漂移、覆盖优先级设计。

### 假设迁移到 C 档（combat/shop/reward 某个子系统整体替换）

**改动**：
- 新增 `src/state/agent_view_view.py` 适配层
- 改写 `src/brain/conversation.py`（600+ 行 combat prompt 构造）
- 改写 `src/brain/prompts/shop.py`, `reward.py`, `event.py`
- Pydantic 模型层面写 fallback 逻辑（agent_view 可用时优先）

**收益**：
- 可能删 50-100 行 formatter 代码
- Pile 段已在用，无增量
- hand.keywords 自动化（省掉 `_keyword_fmt` 一次扫描 cost）

**成本**：
- ~1500 行代码改动 + 适配层 + fallback
- 回归测试覆盖面：所有 A6-A10 runs 要重跑
- 丢失 _intent_fmt 结构化计算 → 必须把 agent_view.intent 反向解析回 damage/hits；我们自己造字符串解析器比用 C# 结构化字段倒退
- 丢失 _card_clarifications 注入时机（因为 agent_view 不给单卡结构化 index 来 hook）
- 丢失 _relic_fmt 的 41 条 synergy 注入时机（agent_view.run.relics 只有 name 数组）

**判决**：C 档是**用更简单的文本换结构化数据，用架构整齐换 agent 决策质量**。我们当前 A6 稳定跑赢上游 baseline 的根本原因就是这些 Python 侧独占知识层；为了架构对齐把它们吞掉是本末倒置。

### 假设迁移到 A 档（保持现状）

**改动**：0（或只做小 tweaks）。
**收益**：维持现有决策质量和独占知识层。
**成本**：继续维护双视图消费代码（`gs.agent_view` 的 4 处调用点）。
**风险**：上游 mod 大版本升级时 agent_view schema 变动需跟进（但只影响 4 处调用点）。

---

## 7. 三选一推荐

### **A+ / B（二者合并）**——保持现状 + 选择性 glossary gap-backfill

具体落地：

1. **不触动**：conversation.py combat prompt、shop/reward/event/rest/map 所有顶层字段消费、_intent_fmt、_card_clarifications、_relic_fmt、_deck_fmt。这些是我们跑赢上游的核心。

2. **继续使用**：当前 4 个 agent_view 消费点（pile 注入、intent fallback、exhaust diff、pile size logging）。这些是顶层 API 盲区的唯一解。

3. **可选增量（~40 行）**：给 `_keyword_fmt.py` 补 **3-4 条手写英文 KW_GLOSSARY 条目**（`burn`, `void`, `focus`, `stun`），参考上游中文 + 我们自己的 trap 提示风格写成英文。**不走 agent_view.glossary 运行时注入路径**——直接扩充 KW_GLOSSARY 就行。

4. **可选修复（~5 行）**：卡牌奖励 prompt 注入 `RawRewardCardOptionPayload.upgraded` 字段，显示 `Strike+` vs `Strike`。这是与 agent_view 无关的独立 bug。

### 为什么不是 B（只引入 agent_view.glossary）

agent_view.glossary 中文 + 硬 18 条上限 + 只扫 rules_text 的限制，不如 **我们现有 `KW_GLOSSARY + _dll_mechanics` 双层结构 + 英文 + trap 提示**。补上游有我们没有的 4 条，手写一条 20 行代码就能搞定，没必要引入新的运行时依赖和语种转换逻辑。

### 为什么不是 C（整体或子系统迁移）

- combat payload 丢失 `intents[]` / `powers[]` / `target_previews[]` — 伤害计算唯一真源不能丢
- shop/reward 丢失 rules_text 结构化 — 评估协同的信息源不能丢
- _card_clarifications / _relic_fmt 的手写知识层 agent_view 无等价 — 我们跑赢上游的核心
- 代码改动 1500+ 行换 50-100 行 formatter 删除 — ROI 负

### 为什么不是纯 A

上游中文 glossary 里的 `灼伤/虚空/集中` 确实是我们 Regent/Scholar 盲区。即使不采用 agent_view 机制，这个信息差也得补（直接扩 KW_GLOSSARY，最廉价路径）。

---

## 8. 实施路径（推荐方案落地）

### 步骤 1：扩充 KW_GLOSSARY（~30 分钟）

在 `src/brain/prompts/_keyword_fmt.py` KW_GLOSSARY dict 加：

```python
"burn": "Burn: Non-playable status card. When drawn, typically deals damage at end of turn or on interaction. Remove via exhaust effects.",
"void": "Void: Non-playable status card. Drains energy/disrupts flow when drawn. Exhaust or ethereal synergies help.",
"focus": "Focus: Increases Orb passive and evoke values (Scholar core stat). Scales orb-based damage and block.",
"stun": "Stun: Status card that cannot be played. Clogs hand — consider exhaust synergies.",
```

同时考虑加 `strength_down`（我们现有 `strength` trap 提示已部分覆盖，低优）。

### 步骤 2：card_reward upgraded 标记（~10 分钟）

在 `src/brain/prompts/reward.py` 或 wherever 构造 card option list 的地方，把 `RawRewardCardOptionPayload.upgraded` 字段加进显示名：`Strike+` 而非 `Strike`（当 upgraded=true）。

### 步骤 3：回归验证（~1 小时）

- 跑 `python -m scripts.run_agent --steps 500 --ascension 0`（A0 单次 Silent）
- 检查日志里有没有 `Keyword Glossary` 段多出 burn/void/focus 等条目（场景：打 Regent/Scholar 卡组的战斗）
- 检查 card_reward prompt 里 Upgraded 卡的 name 是否带 `+`

### 步骤 4（可选）：记忆层 agent_view 迁移

`combat_delta.py` 和 `loop.py` 的 agent_view 消费已经是最优形式。不需要改。

### 风险

- 扩充 KW_GLOSSARY 不会破坏现有行为（累加触发，不覆盖）
- 上游 mod v0.5.3 后的 schema 变化：如果 `AgentViewPayload` 字段改名，会影响现有 4 个消费点。**缓解**：Pydantic `extra="ignore"` 会自动兼容新字段；重命名时在 4 处调用点各加一层 `getattr()` fallback。
- 中文→英文翻译漂移：人工写 + review，不走自动化路径。

### 测试计划

- 新增 `tests/brain/test_keyword_fmt.py` 用例：
  - 输入含 `"Burn deals X damage"` 的 rules_text，断言输出 `"Burn:"` 开头的条目
  - 输入不含关键词的 rules_text，断言 burn/void/focus 不触发
- 现有 `tests/brain/` 的 prompt snapshot 测试跑一遍确保无回归

---

## 9. 附录：已在用的 agent_view 字段清单（4 处）

| 字段路径 | 消费者 | 用途 | 顶层等价物 |
|---|---|---|---|
| `agent_view.combat.draw[]` | `conversation.py:1041,1046`, `session_logger.py:199` | 战斗 prompt Piles 段 + pile_size 记录 | **无** |
| `agent_view.combat.discard[]` | `conversation.py:1042,1050`, `session_logger.py:200` | 同上 | **无** |
| `agent_view.combat.exhaust[]` | `conversation.py:1043,1054`, `session_logger.py:201`, `combat_delta.py:198-205` | Piles 段 + pile_size + pre/post exhaust diff 判断 card_play 消耗了哪些卡 | **无** |
| `agent_view.combat.enemies[].intent` | `loop.py:3176` | 旧版 mod 兼容 fallback，当 `e.intents[]` 空时显示 `"Attack 7x1"` 字符串 | `intents[]` 列表（主源） |

**总计引入成本**：~30 行代码（已完成），零回归，覆盖顶层 API 盲区。这次 §7 的推荐方案 A+/B 保持此 4 处不动。

---

## 10. 最后一句

上游 agent_view 是面向"只读上游 API 的通用 LLM agent"的架构合理化产物，优化方向是 token 压缩 + 文本可读性。**我们是半自研 agent，手写知识层和结构化数值计算是核心竞争力**。借用 agent_view 盲区字段（pile / exhaust diff）是应该的、已经做了；把 agent_view 作为主 payload 去替换顶层是技术债交换——交出质量去换整齐。不换。
