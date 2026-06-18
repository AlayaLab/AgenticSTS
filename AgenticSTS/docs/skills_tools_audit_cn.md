# Skills / Tools 中文审查清单

这份清单按“英文名 + 一句中文概括”整理，方便手动判断哪些该保留、降权或删除。

> **注 (2026-04-18)：** 下文提到的 `propose_prompt_edit` / `PromptPatch*` 等 prompt-evolution 相关条目已于 2026-04-18 删除——33/33 patches 全部 A/B 验证失败。详见 `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`。

说明：
- `source` 仅表示来源：`seed` 是初始手写种子，`discovered/evolved` 是运行中归纳出来的。
- `verified` 只是仓库当前标记，不代表它真的没问题。
- 这份文档先做“翻译和速查”，不替你做最终裁决。

## Query Tools

- `recall_encounter`：回忆以前打某个敌人的经验，总结什么打法有效、什么打法翻车。
- `[已删除] get_run_progress`：原本用于读取当前整局进度，概括血量变化、牌组演化、金币、遗物和关键决策。
- `[已删除] search_strategy`：原本用于从技能库和知识库里搜索相关策略建议。
- `read_guide`：按主题读取现成攻略，例如角色、战斗、构筑、路线。
- `assess_potion_value`：评估某瓶药是现在用更值，还是留给精英/Boss 更值。

## Decision Tools

- `combat_action`：逐步决定战斗中的下一张牌或结束回合。
- `combat_plan`：一次性规划完整战斗回合，包括出牌顺序和药水使用。
- `map_action`：决定下一步走哪一个地图节点。
- `rest_action`：决定营火要升级、回血、举重、挖掘等哪种操作。
- `event_action`：在事件界面里按选项索引做选择。
- `shop_action`：决定在商店买什么，或者直接离开。
- `card_reward_action`：在卡牌奖励里选一张牌，或者跳过。
- `card_select_action`：在升级/移除/附魔等界面里选择一张或多张牌。
- `hand_select_action`：在弃牌/消耗等手牌选择界面里选牌。
- `treasure_action`：在宝箱/宝物界面里决定拿还是跳过。
- `relic_select_action`：在多件遗物中选一件。
- `potion_action`：决定使用哪瓶药，或者不使用。

## Evolution / Authoring Tools

- `author_tool`：写一个新的计算型 Python 工具，供后续对局复用。
- `write_skill`：新建或更新一条自然语言策略 skill。
- `update_guide`：根据实战经验增补或修正攻略内容。
- `propose_prompt_edit`：提出 prompt 修改建议，交给人工审核。
- `get_performance_stats`：读取历史表现数据，例如胜率、平均层数、死因、工具使用统计。

## Skills

### Combat

- `3b91138f4a92` | Energy management - avoid dead turns | `source=evolved` `verified=True`
  避免空过回合：提醒结束回合前检查是否还有可行动作。
- `seed_core_combat` | Core Combat Principles | `source=seed` `verified=True`
  通用战斗总纲：读敌人意图、算总伤、优先斩杀、用满能量和药水。
- `3a779fc75027` | Multi-enemy combat: offense windows and kill priority | `source=evolved` `verified=True`
  多敌战要找输出窗口并明确集火顺序，不能只顾格挡。
- `ee53da7a8a40` | Terror Eel Weak timing and attack pattern | `source=evolved` `verified=False`
  总结 Terror Eel 的 Weak 时机和攻击节奏。
- `0ffe1b813bb0` | Smoggy skill-limit block priority | `source=evolved` `verified=False`
  遇到 Smoggy 限制 Skill 时，优先把有限的 Skill 出手留给最关键的防御/功能牌。
- `30c8d938f90c` | Corpse Slug Ravenous ramp danger | `source=evolved` `verified=False`
  提醒 Corpse Slug 的 Ravenous 会越拖越危险，要警惕成长失控。
- `14ff942a82bc` | Decimillipede Reattach mechanic | `source=evolved` `verified=False`
  说明 Decimillipede 的 Reattach 机制和对应打法。
- `7f75bd170026` | Play free cards before Calculated Gamble | `source=evolved` `verified=False`
  打 Calculated Gamble 前先把 0 费/免费牌打掉，减少白白丢价值。
- `c3748ab0a562` | Skittish enemies - avoid multi-hit and Shivs | `source=evolved` `verified=False`
  对 Skittish 敌人应避免多段攻击和 Shiv 这类低单次伤害打法。
- `8a2df2ee26b6` | Skulking Colony - Hardened Shell counter | `source=evolved` `verified=False`
  针对 Skulking Colony / Hardened Shell 机制给出克制思路。
- `82c38bdf57ff` | Early game survival priority | `source=evolved` `verified=True`
  前期先保命再谈贪收益，防止开局几层直接暴毙。
- `37d9c291e5da` | Hardened Shell combat priority | `source=evolved` `verified=False`
  遇到 Hardened Shell 机制时，重新排序战斗中的行动优先级。
- `504247603131` | Hardened Shell attack priority | `source=evolved` `verified=False`
  遇到 Hardened Shell 敌人时，调整攻击顺序和集火目标。
- `93ce6f980b57` | No free turns at low HP | `source=evolved` `verified=False`
  低血时不能把敌人的“非攻击回合”浪费掉，必须更主动抢节奏。
- `f2fb67856934` | Multi-enemy attrition awareness | `source=evolved` `verified=False`
  多敌战要警惕拖回合带来的血量消耗会滚雪球。

### Boss / Elite

- `seed_core_boss_strategy` | Boss and Elite Fight Strategy | `source=seed` `verified=True`
  首领/精英战通用原则：药水该用就用，优先处理真正的赢点和致命机制。
- `684980744993` | Knowledge Demon boss - attack patterns and strategy | `source=evolved` `verified=False`
  总结 Knowledge Demon 的攻击模式和应对策略。
- `e33480cd1bdf` | Lagavulin Matriarch boss strategy - poison beats debuffs | `source=evolved` `verified=False`
  认为 Lagavulin Matriarch 更适合用毒推进，而不是单纯堆 debuff。
- `867a718c299b` | kin_priest_boss_kill_order | `source=evolved` `verified=False`
  给出 Kin Priest 战里的击杀顺序建议。

### Map / Routing

- `seed_core_map_routing` | Map Routing and Path Planning | `source=seed` `verified=True`
  通用路线规划：平衡商店、营火、事件、怪物和精英风险。
- `e3094ac36fa5` | Floor 1 elite avoidance without combat-ready deck | `source=discovered` `verified=True`
  第一层如果战斗力没成型，就别硬走精英路线。
- `deb3e89162fb` | Dead turn emergency - force combat skip or immediate removal | `source=discovered` `verified=False`
  如果牌组频繁空过，要立刻通过绕路或删牌止损。
- `5972b678902a` | Route deviation threshold - override plan when HP drops below 30% | `source=discovered` `verified=False`
  血量跌破 30% 时允许推翻原路线，优先保命。
- `60046234ec1b` | Hoard gold for curse removal when carrying Greed | `source=discovered` `verified=False`
  身上有 Greed 之类诅咒时，要留钱优先解除诅咒。
- `1d0c6186fa80` | Critical HP routing gate | `source=evolved` `verified=False`
  极低血量时开启保命路线门槛，停止贪收益节点。
- `dd3952891a2b` | Silent elite gate-check at map time | `source=evolved` `verified=True`
  Silent 在选精英路线前要先做一次战力门槛检查。
- `65d1f65510ef` | Reserve gold for card removal when routing through shops | `source=discovered` `verified=True`
  如果计划经过商店，就预留金币给删牌。
- `9ebf273d17c2` | Elite readiness gate - deck quality check before pathing | `source=evolved` `verified=False`
  走精英前除了看血量，还要看牌组质量是否达标。
- `21660cee7b4e` | Floor 1 combat readiness check | `source=discovered` `verified=False`
  第一层前几战/前几步路线前，先检查当前战斗准备度。
- `ccfdf7899579` | Elite path HP gate - Act 1 | `source=evolved` `verified=True`
  Act1 走精英路线时需要满足最低血量门槛。
- `319d480ad007` | Critical HP threshold - force rest or healing event | `source=discovered` `verified=False`
  血线过低时强制转向营火或治疗事件。
- `80c23aa063b6` | Post-elite HP assessment overrides route plan | `source=discovered` `verified=False`
  打完精英后如果血线崩了，应允许立刻改路线。
- `bdd21fe1221a` | Shop-before-rest routing when critically low HP | `source=discovered` `verified=False`
  极低血时如果商店能救局，有时应先去商店再去营火。

### Rest / Event

- `seed_core_rest_decision` | Rest Site and Event Decisions | `source=seed` `verified=True`
  营火默认升级，事件优先高价值收益，避免明显亏损和送命选项。
- `aff6c373d44f` | Prioritize card removal over marginal upgrades when deck has curses or excess basics | `source=discovered` `verified=True`
  有诅咒或基础牌太多时，删牌通常比小升级更值。
- `ce332360cf4c` | Cursed Pearl requires immediate playability verification | `source=discovered` `verified=True`
  遇到 Cursed Pearl 时要先确认当前构筑能否承受它的即时副作用。
- `912b82765338` | Silver Crucible event prioritization in early Act 1 | `source=discovered` `verified=True`
  Act1 前期遇到 Silver Crucible 事件时，建议提高优先级。
- `9dc88474a37c` | Enchantment priority - frequently played cards over situational | `source=discovered` `verified=True`
  附魔优先常打的核心牌，不要浪费在偶发牌上。
- `76d7121b60b3` | Fresnel Lens value in early Act 1 | `source=discovered` `verified=False`
  评估 Fresnel Lens 在 Act1 前期的收益是否足够高。
- `611511668f0d` | Bulk removal priority order: curses > strikes > excess defends | `source=discovered` `verified=False`
  大批量删牌时优先顺序为诅咒、Strike、再到多余 Defend。
- `761733c63bf7` | Act 1 HP conservation before boss | `source=evolved` `verified=False`
  Act1 进 Boss 前应尽量节省血量，避免为小利多掉血。
- `5678c93ed219` | Minimum deck size for forced discard events | `source=discovered` `verified=True`
  遇到强制弃/删牌事件时，牌组太薄会伤筋动骨，要注意最低厚度。
- `ec404b4d311e` | Heal before boss - HP threshold | `source=evolved` `verified=True`
  给出 Boss 前该不该回血的血量阈值。
- `b4c1efaf2a0a` | Upgrade for energy relief before damage scaling when cursed | `source=discovered` `verified=False`
  身上有诅咒时，先做减费/顺能量升级，再谈伤害成长。
- `47b325a3d3c1` | Max HP trade events require HP recovery plan | `source=discovered` `verified=True`
  用最大生命换收益前，必须先有后续回血方案。
- `9162c00a8b7d` | Lava Rock validation - combat capability | `source=discovered` `verified=False`
  拿 Lava Rock 一类收益前，要先确认当前战斗能力是否足够支撑。

### Deck Building

- `cdbecaa27d2c` | Defensive scaling beats raw block when HP is low and facing multi-fight gauntlet | `source=discovered` `verified=True`
  低血连续作战时，长期防御成长往往比单回合格挡更重要。
- `b2ae00c12b4a` | Pre-boss deck discipline: stop adding cards near boss floors | `source=evolved` `verified=False`
  进 Boss 前几层严控加牌，避免把关键牌稀释。
- `fa0f4266aad7` | Shop removal priority and deck bloat threshold | `source=discovered` `verified=False`
  规定商店删牌优先级，并给出“牌组过胖”的警戒线。
- `04fd38c1b13c` | The Insatiable boss preparation | `source=evolved` `verified=True`
  围绕 The Insatiable 的专门备战建议，包括选牌和资源规划。
- `77b98f7346c7` | Multiple consecutive dead turns signals run-ending trajectory | `source=discovered` `verified=True`
  如果连续多个回合空过，说明牌组结构已经接近崩盘，需要马上纠偏。
- `808eac6f0a7d` | Act 1 Silent minimum damage deck building | `source=evolved` `verified=False`
  Silent 在 Act1 必须保证最低伤害密度，否则会被普通战拖死。
- `a5ec50f4d514` | Card removal without card addition starves the deck of playable cards | `source=discovered` `verified=False`
  只删牌不补强会让牌组缺少可打牌，可能把牌组削到不能运转。
- `bd8703326f77` | Silent Act 1 deck building - escape basics trap | `source=evolved` `verified=False`
  Silent 在 Act1 要尽快摆脱基础牌过多的状态。
- `4cf85e014650` | Dual-purpose cards fix multiple gaps efficiently | `source=discovered` `verified=True`
  能同时补多个短板的牌，通常比纯单功能牌更高效。
- `a4696421feda` | Energy-efficient cards when energy-starved | `source=discovered` `verified=True`
  能量紧张时优先考虑高能效、低费、减费或回能牌。
- `359f2d99e15f` | Poison deck HP efficiency - block gaps kill runs | `source=discovered` `verified=False`
  毒流如果防御断档，哪怕输出够也会因为血线效率太差而翻车。
- `d25cdced1378` | Power Potion priority for scaling-dependent builds | `source=discovered` `verified=False`
  依赖成长的构筑应提高 Power Potion 的优先级。
- `b0cce1478739` | Footwork timing - take before boss when defense is weak | `source=discovered` `verified=False`
  如果防御偏弱，Boss 前应更积极拿 Footwork。
- `158e54450c2a` | Silent poison build requires draw engine support | `source=discovered` `verified=False`
  Silent 毒流需要抽牌/循环引擎支撑，不然启动太慢。
- `353b780717dd` | Win condition density check before Act 2 | `source=discovered` `verified=False`
  进 Act2 前要检查“赢法组件”的密度是否足够。
- `seed_core_deck_building` | Deck Building Across the Run | `source=seed` `verified=True`
  全程构筑总纲：平衡伤害、防御、抽牌、能量，同时控制牌组体积。
