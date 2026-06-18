"""English -> Simplified Chinese name lookup for STS2 entities.

Loads parallel `eng/*.json` and `zhs/*.json` localization tables (the same files
the game ships, mirrored at `data/knowledge/localization/{eng,zhs}/`) and joins
them by entry key (e.g. `STRIKE.title`). Used for two display-language tasks:

  1. Building a dynamic per-decision glossary the LLM uses to translate card /
     relic / potion / monster names in `reasoning_zh`.
  2. Replacing English entity names with Chinese names inside transition
     summary strings for stream-ui display.

Action names, JSON keys, and any structural / programmer-facing tokens are left
alone — those are API contract, not display text.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

# Order matters in the categories list: longer names first so substring
# replacement on summaries does not produce stale prefixes (e.g. "Strike" in
# "Strike+1" must not match before "Strike+1" itself).
_CATEGORIES = (
    ("cards", ".title"),
    ("relics", ".title"),
    ("potions", ".title"),
    ("monsters", ".name"),
    ("characters", ".title"),
    ("orbs", ".title"),
    ("powers", ".title"),
    ("enchantments", ".title"),
    ("afflictions", ".title"),
    ("events", ".title"),
)


def _default_eng_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge" / "localization" / "eng"


def _default_zhs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge" / "localization" / "zhs"


class LocaleTranslator:
    """Thread-safe en->zh name lookup, lazily loaded."""

    def __init__(self, eng_dir: Path | None = None, zhs_dir: Path | None = None) -> None:
        self._eng_dir = eng_dir or _default_eng_dir()
        self._zhs_dir = zhs_dir or _default_zhs_dir()
        self._lock = threading.Lock()
        self._loaded = False
        # category -> {english_name: chinese_name}
        self._maps: dict[str, dict[str, str]] = {}
        # Cached union of all categories for cross-category lookup, sorted by
        # descending name length for safe substring replacement.
        self._all_pairs_sorted: list[tuple[str, str]] = []
        # Cached regex that matches any English entity name (word-boundary aware
        # for ASCII names, longest-match-first via alternation order).
        self._name_re: re.Pattern[str] | None = None

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load()
            self._loaded = True

    def _load(self) -> None:
        for category, suffix in _CATEGORIES:
            eng_file = self._eng_dir / f"{category}.json"
            zhs_file = self._zhs_dir / f"{category}.json"
            if not eng_file.exists() or not zhs_file.exists():
                continue
            try:
                eng = json.loads(eng_file.read_text(encoding="utf-8"))
                zhs = json.loads(zhs_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            mapping: dict[str, str] = {}
            for key, en_value in eng.items():
                if not key.endswith(suffix):
                    continue
                if not isinstance(en_value, str) or not en_value.strip():
                    continue
                zh_value = zhs.get(key)
                if not isinstance(zh_value, str) or not zh_value.strip():
                    continue
                if en_value == zh_value:
                    # Identical -- entry not actually translated; skip to keep
                    # the glossary signal-only.
                    continue
                mapping[en_value] = zh_value
            if mapping:
                self._maps[category] = mapping

        # Build the sorted union (longest first) so substring replacement on a
        # summary handles overlapping names correctly (e.g. "Strike" inside
        # "Strike+1" -> replace longer first).
        union: dict[str, str] = {}
        for category_map in self._maps.values():
            for en, zh in category_map.items():
                union.setdefault(en, zh)
        self._all_pairs_sorted = sorted(
            union.items(), key=lambda kv: (-len(kv[0]), kv[0])
        )

        if union:
            # Word-boundary-aware regex. Names are escaped, joined longest-first
            # via alternation order. Word boundaries help skip false matches
            # like "Strike" inside "Striking".
            escaped = "|".join(re.escape(name) for name, _ in self._all_pairs_sorted)
            self._name_re = re.compile(rf"(?<![A-Za-z0-9])(?:{escaped})(?![A-Za-z0-9])")

    # ── Public API ──────────────────────────────────────────────

    # Trailing card-name decorations the mod's ResolveCardTitle appends, in
    # match order:
    #   "Strike+1"  -> base "Strike", suffix "+1"
    #   "Strike+"   -> base "Strike", suffix "+"
    #   "Strike*5"  -> base "Strike", suffix "*5" (pile-collapse marker)
    _SUFFIX_RE = re.compile(r"(\*\d+|\+\d+|\+)$")

    def to_chinese(self, english_name: str, category: str | None = None) -> str | None:
        """Look up the Simplified Chinese name for an English entity name.

        Handles trailing decorations the mod appends to upgraded cards
        (``Strike+``, ``Strike+1``) and pile-collapse copy markers
        (``Strike*5``) by stripping them, looking up the base name, and
        re-attaching the original suffix to the Chinese result. If
        `category` is provided, search only that category (e.g. "cards").
        Otherwise search all categories in priority order. Returns None if
        no match is found.
        """
        if not english_name:
            return None
        self._ensure_loaded()

        suffix = ""
        base_name = english_name
        m = self._SUFFIX_RE.search(english_name)
        if m:
            suffix = m.group(0)
            base_name = english_name[: m.start()]

        def _lookup(name: str) -> str | None:
            if category:
                return self._maps.get(category, {}).get(name)
            for cat, _ in _CATEGORIES:
                zh = self._maps.get(cat, {}).get(name)
                if zh is not None:
                    return zh
            return None

        # Try the full name first (handles names that legitimately end in "+"
        # or names overridden in a future locale file).
        zh = _lookup(english_name)
        if zh is not None:
            return zh
        if suffix:
            zh_base = _lookup(base_name)
            if zh_base is not None:
                return zh_base + suffix
        return None

    def category_pairs(self, category: str) -> dict[str, str]:
        """Return all (en_name, zh_name) pairs for a given category."""
        self._ensure_loaded()
        return self._maps.get(category, {})

    def find_glossary_in_text(self, text: str) -> dict[str, str]:
        """Scan `text` for any known English entity names, return en->zh pairs.

        Used to build a dynamic glossary for the LLM at decision time. False
        positives (substring of unrelated word) are filtered by a word-boundary
        regex; remaining false positives in the glossary are harmless because
        the LLM only consults entries it actually uses.
        """
        if not text:
            return {}
        self._ensure_loaded()
        if self._name_re is None:
            return {}
        found: dict[str, str] = {}
        for match in self._name_re.findall(text):
            if match in found:
                continue
            zh = None
            for cat, _ in _CATEGORIES:
                zh = self._maps.get(cat, {}).get(match)
                if zh is not None:
                    break
            if zh is not None:
                found[match] = zh
        return found

    # Common reasoning-phrase patterns emitted by deterministic (non-LLM)
    # decisions in src/agent/loop.py. Each entry is (compiled regex, zh
    # replacement). Replacement order is significant — more specific patterns
    # come first. After pattern translation, translate_summary() also runs to
    # catch any English entity names in the captured groups.
    _PHRASE_PATTERNS: list[tuple[re.Pattern[str], str]] = []

    @classmethod
    def _translate_node_inline(cls, raw: str) -> str:
        """Translate a node-type token used inline (`monster`, `elite`, `shop`...)."""
        token = raw.strip()
        return cls._STATE_LABELS.get(token, token)

    @classmethod
    def _build_phrase_patterns(cls) -> list[tuple[re.Pattern[str], str]]:
        if cls._PHRASE_PATTERNS:
            return cls._PHRASE_PATTERNS
        # `_DASH` matches optional whitespace + dash (em-dash or hyphen) + optional
        # whitespace, used between phrase head and tail.
        _DASH = r"\s*[—\-]+\s*"
        # `_RT` translates reward-type keywords appearing inside "Claim X:" patterns.
        _RT = {
            "gold": "金币", "relic": "遗物", "potion": "药水",
            "card": "卡牌", "key": "钥匙",
        }

        def _claim_repl(m: "re.Match[str]") -> str:
            rt_label = _RT.get(m.group(1).lower(), m.group(1))
            return f"获得 {rt_label}：{m.group(2)}"

        raw_pairs: list[tuple[str, "str | callable"]] = [
            # Most-specific first
            (r"^Stuck recovery:\s*(.+)$", r"卡顿恢复：\1"),
            (r"^Skill eval:\s*(.+)$", r"技能评估：\1"),
            (r"^Shop plan complete" + _DASH + r"leaving$",
             r"商店计划完成 — 离开"),
            (r"^Shop plan: nothing to buy" + _DASH + r"(.+)$",
             r"商店计划：无可购买 — \1"),
            (r"^Shop plan unrecoverable after retry" + _DASH + r"leaving shop$",
             r"商店计划重试后仍无法恢复 — 离开商店"),
            (r"^Plan: end turn" + _DASH + r"(.+)$", r"计划:结束回合 — \1"),
            (r"^Plan: use potion\s+(.+)$", r"计划：使用药水 \1"),
            (r"^Plan:\s*(.+)$", r"计划：\1"),
            (r"^Claim ([A-Za-z_]+):\s*(.+)$", _claim_repl),
            (r"^Claim ([A-Za-z_]+)$",
             lambda m: f"获得 {_RT.get(m.group(1).lower(), m.group(1))}"),
            (r"^Claim:\s*(.+)$", r"获得：\1"),
            (r"^Forced potion discard:\s*(.+)$", r"强制丢弃药水:\1"),
            (r"^Crystal Sphere: reveal (.+) with the active divination\.?$",
             r"水晶球：使用激活占卜揭示 \1。"),
            (r"^Crystal Sphere: switch tool via (.+)\.?$",
             r"水晶球：通过 \1 切换工具。"),
            (r"^Crystal Sphere:\s*(.+)$", r"水晶球：\1"),
            # Path / option patterns — translate node_type (e.g. monster → 怪物)
            (r"^Only path:\s*(.+)$",
             lambda m: f"唯一路径：{cls._translate_node_inline(m.group(1))}"),
            (r"^Only option:\s*(.+)$",
             lambda m: f"唯一选项：{cls._translate_node_inline(m.group(1))}"),
            (r"^Random path:\s*(.+)$",
             lambda m: f"随机路径：{cls._translate_node_inline(m.group(1))}"),
            (r"^Random:\s*play\s+(.+)$",
             lambda m: f"随机：打出 {m.group(1)}"),
            # Reward / card-reward heuristics (often heuristic, not LLM-driven)
            (r"^Open card reward$", r"打开卡牌奖励"),
            (r"^Collect all rewards and proceed$", r"领取所有奖励并前进"),
            (r"^Safe fallback: skip card reward$", r"安全回退：跳过卡牌奖励"),
            (r"^Skip card reward$", r"跳过卡牌奖励"),
            (r"^Fallback pick:\s*(.+)$", r"回退选择：\1"),
            # Event
            (r"^Event: no options, proceed$", r"事件：无可选项，前进"),
            (r"^Event:\s*(.+)$", r"事件：\1"),
            # Rest
            (r"^Proceed from rest$", r"从休息站前进"),
            (r"^Rest:\s*(.+)$", r"休息站：\1"),
            # Shop
            (r"^Close shop inventory to leave$", r"关闭商店物品栏以离开"),
            (r"^Skip shop$", r"跳过商店"),
            (r"^Shop plan: discard\s+(.+)$", r"商店计划：丢弃 \1"),
            (r"^Shop plan \[(\d+)/(\d+)\]:\s*(.+)$",
             r"商店计划 [\1/\2]：\3"),
            # Hand-select / card-select
            (r"^Confirm optional hand selection without choosing a card$",
             r"确认可选手牌选择，不选择任何牌"),
            (r"^Confirm hand selection \((\d+)/(\d+)\)$",
             r"确认手牌选择 (\1/\2)"),
            (r"^Confirm selection after payload-less card_select refresh$",
             r"载荷为空的牌选刷新后确认选择"),
            (r"^Confirm current pack selection$", r"确认当前包的选择"),
            (r"^Confirm selection \((\d+)/(\d+)\)$",
             r"确认选择 (\1/\2)"),
            (r"^Cancel selection$", r"取消选择"),
            (r"^Select\s+(.+?)\s*\+\s*confirm \((\d+) cards? done\)$",
             r"选择 \1 + 确认（\2张完成）"),
            (r"^Select\s+(.+?)\s*\((\d+)/(\d+)\)$",
             r"选择 \1（\2/\3）"),
            # Treasure / relic
            (r"^Open chest$", r"打开宝箱"),
            (r"^Proceed from treasure$", r"从宝箱前进"),
            (r"^Select relic:\s*(.+)$", r"选择遗物：\1"),
            (r"^Skip relic$", r"跳过遗物"),
            # Combat fallbacks
            (r"^Plan partially complete, remaining cards unplayable$",
             r"计划部分完成，剩余牌无法打出"),
            # Standalone short phrases
            (r"^All rewards claimed, proceed$", r"已领取所有奖励，前进"),
            (r"^Event finished, proceed$", r"事件结束，前进"),
            (r"^Auto-proceed from rest \(option already used\)$",
             r"自动从休息站前进（休息选项已使用）"),
            (r"^Leave shop after closing inventory$", r"关闭物品栏后离开商店"),
            (r"^No playable cards, end turn$", r"无可打出的牌，结束回合"),
            (r"^No alive enemies, no-target replan exhausted" + _DASH + r"end turn$",
             r"无存活敌人，无目标重计划已耗尽 — 结束回合"),
            (r"^Plan complete, end turn$", r"计划完成，结束回合"),
        ]
        cls._PHRASE_PATTERNS = [
            (re.compile(p, re.IGNORECASE), repl) for p, repl in raw_pairs
        ]
        return cls._PHRASE_PATTERNS

    def translate_reasoning(self, reasoning: str) -> str:
        """Translate a deterministic English reasoning string to Chinese.

        Used for non-LLM decisions emitted by the agent loop (claim reward,
        stuck recovery, only-path, etc.) when STS2_DISPLAY_LANGUAGE=zh and the
        LLM did not produce a `reasoning_zh`. Two passes:

          1. Pattern-translate known English phrase templates to Chinese.
          2. Replace English entity names (cards/relics/potions/monsters)
             inside the result via translate_summary's regex.

        Strings with no matching pattern are still passed through pass 2 so
        bare entity names get translated (e.g. ``"Akabeko"`` -> ``"赤牛"``).
        """
        if not reasoning:
            return reasoning
        text = reasoning
        for regex, replacement in self._build_phrase_patterns():
            new_text, n = regex.subn(replacement, text)
            if n:
                text = new_text
                break
        return self.translate_summary(text)

    # Structural-label patterns specific to gs.summary() output. Two passes:
    #   1. Bracketed state labels: [combat], [monster/Act 1 Boss], etc.
    #   2. Field abbreviations: HP:n/m, E:n, Hand:n, G:n, F<n>, vs, dmg.
    # Bracketed labels include the slash-form composite ("combat/Act 1 Boss")
    # so each side is translated independently.
    _STATE_LABELS: dict[str, str] = {
        "combat": "战斗",
        "monster": "怪物",
        "elite": "精英",
        "boss": "Boss",
        "map": "地图",
        "event": "事件",
        "shop": "商店",
        "rest_site": "休息站",
        "treasure": "宝箱",
        "card_select": "选牌",
        "card_reward": "卡牌奖励",
        "combat_rewards": "战斗奖励",
        "relic_select": "选择遗物",
        "hand_select": "选择手牌",
        "cards_view": "查看牌组",
        "menu": "主菜单",
        "character_select": "角色选择",
        "timeline": "时间轴",
        "epoch_inspect": "时代查看",
        "game_over": "游戏结束",
        "victory": "胜利",
    }

    # Phase transitions emitted by GameStateMachine. The values land in the
    # `type` field of monitor `transition` events.
    _TRANSITION_LABELS: dict[str, str] = {
        "combat_start": "进入战斗",
        "combat_end": "战斗结束",
        "floor_change": "进入新楼层",
        "act_change": "进入新章节",
        "phase_change": "阶段转换",
        "run_end": "本局结束",
        "none": "",
    }

    # Plan-item action types — used by stream-ui's combat-plan renderer so
    # the UI does not need its own Chinese vocabulary.
    _PLAN_ITEM_TYPE_LABELS: dict[str, str] = {
        "card": "卡牌",
        "potion": "药水",
        "relic": "遗物",
    }

    def translate_transition_type(self, transition_type: str) -> str:
        """Return the Chinese label for a phase-transition type, or '' if unknown."""
        return self._TRANSITION_LABELS.get(transition_type, "")

    def translate_state_type(self, state_type: str) -> str:
        """Return the Chinese label for a game state_type, or '' if unknown."""
        return self._STATE_LABELS.get(state_type, "")

    def translate_plan_item_type(self, item_type: str) -> str:
        """Return the Chinese label for a plan-item action type, or '' if unknown."""
        return self._PLAN_ITEM_TYPE_LABELS.get(item_type, "")

    _ENCOUNTER_LABEL_PATTERNS: list[tuple[str, str]] = [
        (r"\bAct (\d+) Boss\b", r"第\1幕Boss"),
        (r"\bAct (\d+) Elite\b", r"第\1幕精英"),
        (r"\bAct (\d+) Monster\b", r"第\1幕怪物"),
    ]

    def _translate_state_token(self, token: str) -> str:
        """Translate a token like `combat/Act 1 Boss` -> `战斗/第1幕Boss`."""
        parts = token.split("/")
        translated = []
        for part in parts:
            p = part.strip()
            zh = self._STATE_LABELS.get(p)
            if zh is not None:
                translated.append(zh)
                continue
            new_part = part
            for pattern, repl in self._ENCOUNTER_LABEL_PATTERNS:
                new_part = re.sub(pattern, repl, new_part)
            translated.append(new_part)
        return "/".join(translated)

    def translate_summary(self, summary: str) -> str:
        """Translate `summary` (output of GameState.summary()) into Chinese.

        Three passes:
          1. Bracketed state labels: `[combat/Act 1 Boss]` -> `[战斗/第1幕Boss]`.
          2. Field abbreviations: F<n>, HP:a/b, E:n, Hand:n, G:n, vs, dmg.
          3. English entity names (cards/relics/potions/monsters/characters/...)
             via the eng->zhs map.

        Used for transition log lines like
        `[combat/Act 1 Boss] F8 The Silent | HP:60/72 E:3 Hand:5 | vs [Jaw Worm(35 8dmg)]`
        becoming
        `[战斗/第1幕Boss] 第8层 静默猎手 | 血量:60/72 能量:3 手牌:5 | 对战 [颚虫(35 8伤害)]`.
        """
        if not summary:
            return summary
        self._ensure_loaded()

        # Pass 1: bracketed state token, e.g. "[combat/Act 1 Boss]"
        text = re.sub(
            r"\[([^\[\]]+)\]",
            lambda m: f"[{self._translate_state_token(m.group(1))}]",
            summary,
        )

        # Pass 2: field abbreviations. Order matters — translate longest first.
        text = re.sub(r"\bHP:(\d+)/(\d+)", r"血量:\1/\2", text)
        text = re.sub(r"\bMaxHP:(\d+)", r"最大血量:\1", text)
        text = re.sub(r"\bE:(\d+)", r"能量:\1", text)
        text = re.sub(r"\bHand:(\d+)", r"手牌:\1", text)
        text = re.sub(r"\bG:(\d+)", r"金币:\1", text)
        text = re.sub(r"\bF(\d+)\b", r"第\1层", text)
        text = re.sub(r"\bvs\b", "对战", text)
        text = re.sub(r"(\d+)dmg\b", r"\1伤害", text)

        # Pass 3: entity names — only run if we have any maps loaded.
        if self._name_re is not None:
            def _repl(m: re.Match[str]) -> str:
                en = m.group(0)
                for cat, _ in _CATEGORIES:
                    zh = self._maps.get(cat, {}).get(en)
                    if zh is not None:
                        return zh
                return en
            text = self._name_re.sub(_repl, text)

        return text

    # ─────────────────── Inline display markup ───────────────────
    #
    # `apply_inline_markup` wraps known enemy names and keyword-like terms with
    # short BBCode-ish tags so the stream-ui can color them at render time:
    #
    #   [e]Jaw Worm[/e]      → enemy (red)
    #   [k]Block[/k]         → keyword (cyan)
    #
    # Used on display-only fields (`text`, decoded reasoning_zh) so the canonical
    # `reasoning` stays clean for memory + skills + multi-turn LLM context.

    _MARKUP_INLINE_RES: tuple[re.Pattern[str], ...] | None = None

    # Hand-curated keyword set: powers + common card mechanics. Both English and
    # Chinese forms are wrapped. Names that overlap with other categories
    # (e.g. "Burn") are still safe — the regex uses word boundaries.
    _KEYWORD_EN = (
        "Strength", "Dexterity", "Vulnerable", "Weak", "Frail", "Poison",
        "Block", "Energy", "Damage", "Burn", "Wound", "Slimed",
        "Bleed", "Confusion", "Curse", "Status",
        "Retain", "Innate", "Ethereal", "Exhaust", "Unplayable",
        "Artifact", "Plated Armor", "Metallicize", "Thorns", "Intangible",
        "Dexterity Down", "Strength Down",
    )
    _KEYWORD_ZH = (
        "力量", "敏捷", "易伤", "虚弱", "虚弱", "中毒",
        "格挡", "能量", "伤害",
        "保留", "固有", "虚无", "消耗", "无法打出",
        "神器", "钢铁意志", "金属化", "荆棘", "无形",
    )

    @classmethod
    def _build_inline_markup_res(cls) -> tuple[re.Pattern[str], ...]:
        """Build (enemy_regex, keyword_regex). Cached after first call."""
        if cls._MARKUP_INLINE_RES is not None:
            return cls._MARKUP_INLINE_RES

        # Enemy names: from monsters category, both English and Chinese.
        # Built lazily — initialised when called from an instance, but the
        # regex is cached at class level for thread safety.
        cls._MARKUP_INLINE_RES = (re.compile(r"(?!x)x"), re.compile(r"(?!x)x"))
        return cls._MARKUP_INLINE_RES

    def _enemy_names(self) -> set[str]:
        """All known enemy names (English + Chinese counterparts)."""
        self._ensure_loaded()
        names: set[str] = set()
        for en, zh in self._maps.get("monsters", {}).items():
            if en:
                names.add(en)
            if zh:
                names.add(zh)
        return names

    def _card_names(self) -> set[str]:
        """All known card names plus their upgraded "+" forms (English + Chinese)."""
        self._ensure_loaded()
        names: set[str] = set()
        for en, zh in self._maps.get("cards", {}).items():
            if en:
                names.add(en)
                names.add(en + "+")
            if zh:
                names.add(zh)
                names.add(zh + "+")
        return names

    def _relic_names(self) -> set[str]:
        """All known relic names (English + Chinese counterparts)."""
        self._ensure_loaded()
        names: set[str] = set()
        for en, zh in self._maps.get("relics", {}).items():
            if en:
                names.add(en)
            if zh:
                names.add(zh)
        return names

    def _keyword_names(self) -> set[str]:
        """All known gameplay-keyword names (English + Chinese)."""
        names: set[str] = set(self._KEYWORD_EN)
        names.update(self._KEYWORD_ZH)
        # Augment with any power/affliction/enchantment translations loaded from
        # the locale data — they read as keywords in reasoning text too.
        self._ensure_loaded()
        for cat in ("powers", "afflictions", "enchantments"):
            for en, zh in self._maps.get(cat, {}).items():
                if en:
                    names.add(en)
                if zh:
                    names.add(zh)
        return names

    def _build_markup_regex(self, names: set[str]) -> re.Pattern[str] | None:
        """Compile a longest-first alternation regex with word boundaries."""
        cleaned = sorted({n for n in names if n}, key=lambda s: (-len(s), s))
        if not cleaned:
            return None
        escaped = "|".join(re.escape(n) for n in cleaned)
        # Word-boundary trick that works for both ASCII and CJK: don't match
        # if the surrounding char is alphanumeric. CJK falls through fine.
        return re.compile(rf"(?<![A-Za-z0-9])(?:{escaped})(?![A-Za-z0-9])")

    # CJK-character detector — used by apply_inline_markup to decide whether
    # to also translate an embedded English entity name to Chinese inline.
    _CJK_RE = re.compile(r"[一-鿿]")

    def apply_inline_markup(self, text: str) -> str:
        """Wrap enemy / card / keyword names with short BBCode-ish tags.

        Tags emitted (consumed by stream-ui's renderer):
          [e]…[/e]    — enemy (red)
          [c]…[/c]    — card (color depends on `+` suffix at render time)
          [r]…[/r]    — relic (teal)
          [k]…[/k]    — keyword / power / status (cyan)

        Order: enemies first (most specific), then cards (so card names that
        happen to also be powers — e.g. "Demon Form" — get the card tint),
        then relics, then keywords. Each pass skips matches already inside a
        tagged span so we don't nest tags.

        When the surrounding text is Chinese (any CJK character present), an
        embedded English entity name (e.g. ``Toxic``, ``Pocketwatch``) is
        translated to its Chinese counterpart via the eng->zhs map before
        being wrapped. This patches the common case where the LLM emits a
        Chinese narrative but leaves a few entity names in English.
        """
        if not text:
            return text

        has_cjk = bool(self._CJK_RE.search(text))

        def _maybe_localize(name: str) -> str:
            if not has_cjk:
                return name
            zh = self.to_chinese(name)
            return zh if zh else name

        def _wrap_outside_existing(
            text_in: str, regex: re.Pattern[str], tag: str,
        ) -> str:
            def _wrap(m: re.Match[str]) -> str:
                start = m.start()
                if start >= 1 and text_in[start - 1] == "]":
                    return m.group(0)
                back = text_in.rfind("[", 0, start)
                if back != -1:
                    close = text_in.find("]", back, start)
                    if close == -1:
                        return m.group(0)
                return f"[{tag}]{_maybe_localize(m.group(0))}[/{tag}]"
            return regex.sub(_wrap, text_in)

        enemy_re = self._build_markup_regex(self._enemy_names())
        if enemy_re is not None:
            text = enemy_re.sub(
                lambda m: f"[e]{_maybe_localize(m.group(0))}[/e]", text,
            )

        card_re = self._build_markup_regex(self._card_names())
        if card_re is not None:
            text = _wrap_outside_existing(text, card_re, "c")

        relic_re = self._build_markup_regex(self._relic_names())
        if relic_re is not None:
            text = _wrap_outside_existing(text, relic_re, "r")

        kw_re = self._build_markup_regex(self._keyword_names())
        if kw_re is not None:
            text = _wrap_outside_existing(text, kw_re, "k")

        return text


# ── Module-level singleton ───────────────────────────────────────

_singleton: LocaleTranslator | None = None
_singleton_lock = threading.Lock()


def get_translator() -> LocaleTranslator:
    """Return the process-wide LocaleTranslator (lazy-loaded on first call)."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = LocaleTranslator()
    return _singleton
