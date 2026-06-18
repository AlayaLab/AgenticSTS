import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIG
# dev script — adjust paths for your environment if needed.
# Default: <repo-root>/logs (resolved relative to this file).
# ═══════════════════════════════════════════════════════════════
LOG_DIR = str(Path(__file__).resolve().parents[1] / "logs")
REPORT_DIR = os.path.join(LOG_DIR, "reports")

# Use 5 most recent run files
all_log_files = sorted(
    [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR)
     if f.startswith("run_") and f.endswith(".jsonl")],
    key=os.path.getmtime, reverse=True
)
SPECIFIC_FILES = all_log_files[:5]

# ═══════════════════════════════════════════════════════════════
# TRANSLATION DICTIONARIES (Chinese game terms)
# ═══════════════════════════════════════════════════════════════

CARD_NAME_CN = {
    "strike": "打击", "defend": "防御", "survivor": "幸存者",
    "neutralize": "中和", "backstab": "背刺", "acrobatics": "杂技",
    "adrenaline": "肾上腺素", "accuracy": "精准", "afterimage": "残像",
    "assassinate": "暗杀", "backflip": "后空翻", "blade dance": "刀刃之舞",
    "blade of ink": "墨刃", "blur": "模糊", "bouncing flask": "弹跳瓶",
    "bullet time": "子弹时间", "burst": "爆发", "calculated gamble": "计算下注",
    "cloak and dagger": "披风与匕首", "corrosive wave": "腐蚀波",
    "dagger spray": "匕首飞射", "dagger throw": "匕首投掷",
    "dash": "冲刺", "deadly poison": "致命毒药", "deflect": "偏折",
    "dodge and roll": "闪避翻滚", "envenom": "淬毒",
    "escape plan": "逃脱计划", "expertise": "专业知识",
    "finisher": "终结技", "flechettes": "飞镖", "flick-flack": "连续空翻",
    "footwork": "步法", "grand finale": "大终结", "hand trick": "手法",
    "haze": "迷雾", "hidden daggers": "隐秘匕首",
    "infinite blades": "无尽刀刃", "knife trap": "刀刃陷阱",
    "leading strike": "先手打击", "leg sweep": "扫腿",
    "malaise": "萎靡", "master planner": "规划大师",
    "memento mori": "死亡提醒", "mirage": "海市蜃楼",
    "murder": "谋杀", "nightmare": "噩梦",
    "noxious fumes": "毒雾", "outbreak": "爆发",
    "phantom blades": "幻影刃", "piercing wail": "穿刺哀嚎",
    "pinpoint": "精确瞄准", "poisoned stab": "淬毒刺击",
    "pounce": "猛扑", "predator": "掠食者",
    "prepared": "早有准备", "reflex": "本能反应",
    "restlessness": "坐立不安", "ricochet": "弹射",
    "serpent form": "蛇形", "skewer": "串刺",
    "slice": "切割", "snakebite": "蛇咬",
    "storm of steel": "钢铁风暴", "strangle": "绞杀",
    "sucker punch": "偷袭", "tactician": "战术大师",
    "the hunt": "猎杀", "tools of the trade": "行业工具",
    "untouchable": "触不可及", "up my sleeve": "袖中暗器",
    "well-laid plans": "周密计划", "wraith form": "幽灵形态",
    "shiv": "小刀", "anticipate": "预判",
    "expose": "暴露", "fan of knives": "刀扇",
    "lethality": "致命", "fight me!": "放马过来!",
    "speedster": "疾行者", "shadowmeld": "融入暗影",
    "shadow step": "暗影步", "tracking": "追踪",
    "abrasive": "磨蚀", "accelerant": "催化剂",
    "bubble bubble": "泡泡", "echoing slash": "回荡斩",
    "flanking": "侧击", "sneaky": "鬼祟",
    "suppress": "镇压", "precise cut": "精准切割",
}

KEYWORD_CN = [
    (r"Deal (\d+) damage to ALL enemies (\d+) times", r"对所有敌人造成\1伤害×\2次"),
    (r"Deal (\d+) damage to ALL enemies twice", r"对所有敌人造成\1伤害×2次"),
    (r"Deal (\d+) damage to ALL enemies", r"对所有敌人造成\1伤害"),
    (r"Deal (\d+) damage to a random enemy (\d+) times", r"对随机敌人造成\1伤害×\2次"),
    (r"Deal (\d+) damage (\d+) times", r"造成\1伤害×\2次"),
    (r"Deal (\d+) damage twice", r"造成\1伤害×2次"),
    (r"Deal (\d+) damage", r"造成\1伤害"),
    (r"Gain (\d+) Block", r"获得\1格挡"),
    (r"Draw (\d+) cards?", r"抽\1张牌"),
    (r"Apply (\d+) Poison to ALL enemies", r"对所有敌人施加\1层毒"),
    (r"Apply (\d+) Poison", r"施加\1层毒"),
    (r"Apply (\d+) Weak", r"施加\1层虚弱"),
    (r"Apply (\d+) Vulnerable", r"施加\1层易伤"),
    (r"Discard (\d+) cards?", r"丢弃\1张牌"),
    (r"Add (\d+) Shivs? into your Hand", r"添加\1张小刀到手牌"),
    (r"Gain (\d+) Strength", r"获得\1力量"),
    (r"Gain (\d+) Dexterity", r"获得\1敏捷"),
    (r"Gain (\d+) energy", r"获得\1点能量"),
    (r"\bExhaust\b\.?", "消耗"),
    (r"\bSly\b\.?", "奇巧(弃牌免费打出)"),
    (r"\bRetain\b\.?", "保留(跨回合)"),
    (r"\bInnate\b\.?", "固有(起手必摸)"),
    (r"\bEthereal\b\.?", "虚无(不打就消耗)"),
    (r"ALL enemies", "所有敌人"),
    (r"to a random enemy", "对随机敌人"),
    (r"(\d+) times", r"\1次"),
    (r"\btwice\b", "两次"),
    (r"If your Hand is empty", "如果手牌为空"),
    (r"\bthis turn\b", "本回合"),
    (r"\bnext turn\b", "下回合"),
    (r"\beach turn\b", "每回合"),
    (r"At the start of your turn", "回合开始时"),
    (r"At the end of your turn", "回合结束时"),
    (r"If Fatal", "若击杀"),
    (r"Costs? (\d+) less", r"费用减\1"),
    (r"\bfor each\b", "每个"),
    (r"\bper copy\b", "每张"),
    (r"\bPoison\b", "毒"),
    (r"\bBlock\b", "格挡"),
    (r"\bStrength\b", "力量"),
    (r"\bDexterity\b", "敏捷"),
    (r"\bWeak\b", "虚弱"),
    (r"\bVulnerable\b", "易伤"),
    (r"\bIntangible\b", "无形"),
    (r"\benemy\b", "敌人"),
    (r"\bHand\b", "手牌"),
    (r"\bdiscard\b", "弃牌"),
    (r"\bdraw\b", "抽牌"),
    (r"\bupgrade\b", "升级"),
    (r"\bpower\b", "异能"),
    (r"\bskill\b", "技能"),
    (r"\battack\b", "攻击"),
]

def translate_card_name(name):
    base = name.rstrip("+").strip().lower()
    cn = CARD_NAME_CN.get(base, "")
    suffix = "+" if name.endswith("+") else ""
    if cn:
        return "{}({}){}" .format(name.rstrip("+"), cn, suffix)
    return name

def translate_rules_text(text):
    if not text:
        return ""
    cn = text
    for pattern, replacement in KEYWORD_CN:
        cn = re.sub(pattern, replacement, cn, flags=re.IGNORECASE)
    if cn != text:
        return "{}\n      → 中文: {}".format(text, cn)
    return text

# ═══════════════════════════════════════════════════════════════
# DATA EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_section(prompt, header):
    marker = "## {}".format(header)
    idx = prompt.find(marker)
    if idx < 0:
        return ""
    end = prompt.find("\n## ", idx + len(marker))
    return prompt[idx:end].strip() if end > 0 else prompt[idx:idx+1000].strip()

def get_deck_summary(deck):
    names = []
    for c in deck:
        n = c["name"]
        if c.get("upgraded"):
            n += "+"
        names.append(n)
    counter = Counter(names)
    parts = []
    for name, cnt in sorted(counter.items()):
        cn = translate_card_name(name)
        parts.append("{}x{}".format(cn, cnt) if cnt > 1 else cn)
    return ", ".join(parts)

def extract_run_data(fpath):
    with open(fpath, encoding="utf-8", errors="replace") as f:
        events = []
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not events:
        return None

    run_id = events[0].get("run_id", os.path.basename(fpath).replace("run_","").replace(".jsonl",""))

    run_end = next((e for e in events if e.get("event") == "run_end"), None)
    character = ""
    victory = None
    final_floor = 0

    for e in events:
        if e.get("event") == "state":
            if e.get("floor", 0) > final_floor:
                final_floor = e["floor"]
        if e.get("event") == "run_start":
            character = e.get("character", "")

    if run_end:
        victory = run_end.get("victory", None)
        final_floor = run_end.get("floor", final_floor)

    states = [e for e in events if e.get("event") == "state"
              and e.get("state_type") in ("card_reward", "shop")]
    decisions_map = {d["step"]: d for d in events if d.get("event") == "decision"}
    llm_calls = [e for e in events if e.get("event") == "llm_call"]

    results = []
    for s in states:
        step = s["step"]
        ts = s.get("ts", 0)
        dec = decisions_map.get(step)
        call = next((lc for lc in llm_calls if lc.get("ts", 0) > ts and lc.get("ts", 0) - ts < 60), None)

        results.append({
            "run_id": run_id,
            "step": step,
            "floor": s.get("floor", 0),
            "state_type": s.get("state_type"),
            "hp": s.get("hp", 0),
            "hp_max": s.get("hp_max", 0),
            "gold": s.get("player", {}).get("gold", 0),
            "deck_size": s.get("deck_size", 0),
            "deck": s.get("deck", []),
            "decision": dec,
            "llm_call": call,
            "state": s,
        })

    return {
        "run_id": run_id,
        "character": character,
        "victory": victory,
        "final_floor": final_floor,
        "entries": results,
    }

# ═══════════════════════════════════════════════════════════════
# REPORT FORMATTING
# ═══════════════════════════════════════════════════════════════

ACTION_CN = {
    "choose_reward_card": "✅ 选择卡牌",
    "skip_reward_cards": "⏭️ 跳过",
    "skip_card_reward": "⏭️ 跳过",
    "buy_card": "🛒 购买卡牌",
    "buy_relic": "🛒 购买圣物",
    "buy_potion": "🛒 购买药水",
    "remove_card": "🗑️ 移除卡牌",
    "close_shop_inventory": "🚶 关闭商店",
    "proceed": "🚶 离开",
    "open_shop_inventory": "📂 打开商店",
}

def format_decision_entry(idx, entry):
    lines = []
    st = entry["state_type"]
    st_cn = "卡牌奖励" if st == "card_reward" else "商店"
    dec = entry.get("decision") or {}
    action = dec.get("action", {}) if isinstance(dec.get("action"), dict) else {}
    call = entry.get("llm_call") or {}
    prompt = call.get("prompt", "")

    lines.append("")
    lines.append("### [{}] Floor {} — {}".format(idx, entry["floor"], st_cn))
    lines.append("**状态**: HP {}/{} | 金币 {}g | 卡组 {}张".format(
        entry["hp"], entry["hp_max"], entry["gold"], entry["deck_size"]))

    deck_str = get_deck_summary(entry["deck"])
    if len(deck_str) > 180:
        deck_str = deck_str[:177] + "..."
    lines.append("**卡组**: {}".format(deck_str))

    s = entry["state"]
    if st == "card_reward":
        options = s.get("card_reward_details", {}).get("card_options", [])
        lines.append("**候选卡牌**:")
        for c in options:
            cn_name = translate_card_name(c["name"])
            cn_rules = translate_rules_text(c.get("rules_text", ""))
            lines.append("  [{}] {}".format(c["index"], cn_name))
            if cn_rules:
                lines.append("      {}".format(cn_rules))
    elif st == "shop":
        sd = s.get("shop_details", {})
        cards = sd.get("cards", [])
        relics = sd.get("relics", [])
        potions = sd.get("potions", [])
        if cards:
            lines.append("**商店卡牌**:")
            for c in cards:
                sym = "✓" if c.get("enough_gold") else "✗"
                cn_name = translate_card_name(c["name"])
                cn_rules = translate_rules_text(c.get("rules_text", ""))
                lines.append("  {} {} ({}g)".format(sym, cn_name, c.get("price","?")))
                if cn_rules:
                    lines.append("      {}".format(cn_rules))
        if relics:
            lines.append("**商店圣物**:")
            for r in relics:
                sym = "✓" if r.get("enough_gold") else "✗"
                lines.append("  {} {} ({}g)".format(sym, r.get("name","?"), r.get("price","?")))
        if potions:
            lines.append("**商店药水**:")
            for p in potions:
                sym = "✓" if p.get("enough_gold") else "✗"
                lines.append("  {} {} ({}g)".format(sym, p.get("name","?"), p.get("price","?")))
        removal = sd.get("card_removal", {})
        if removal and removal.get("price"):
            enough = "✓" if removal.get("enough_gold") else "✗"
            lines.append("**移除卡牌**: {} {}g".format(enough, removal["price"]))

    # Injected memory
    injected_parts = []
    card_insights = extract_section(prompt, "Card-Specific Insights")
    if card_insights:
        injected_parts.append("  📚 {}".format(card_insights[:700]))
    skills = extract_section(prompt, "Expert Knowledge") or extract_section(prompt, "Strategy Skills")
    if skills:
        injected_parts.append("  🎯 {}".format(skills[:350]))
    thread = extract_section(prompt, "Strategic Thread")
    if thread:
        injected_parts.append("  🧵 {}".format(thread[:450]))
    guide = extract_section(prompt, "Guide")
    if guide:
        injected_parts.append("  📖 {}".format(guide[:250]))

    if injected_parts:
        lines.append("")
        lines.append("**注入的记忆/评价** (影响Agent决策的上下文):")
        lines.extend(injected_parts)

    # Decision
    act_type = action.get("action", "")
    act_cn = ACTION_CN.get(act_type, act_type)

    lines.append("")
    if act_type == "choose_reward_card":
        idx_chosen = action.get("option_index", "?")
        options = s.get("card_reward_details", {}).get("card_options", [])
        chosen_name = "?"
        if isinstance(idx_chosen, int) and idx_chosen < len(options):
            chosen_name = translate_card_name(options[idx_chosen]["name"])
        lines.append("**选择**: ✅ [{}] {}".format(idx_chosen, chosen_name))
    elif act_type == "buy_card":
        cards_shop = s.get("shop_details", {}).get("cards", [])
        idx_chosen = action.get("card_index", action.get("option_index", "?"))
        if isinstance(idx_chosen, int) and idx_chosen < len(cards_shop):
            c = cards_shop[idx_chosen]
            lines.append("**选择**: 🛒 购买 {} ({}g)".format(translate_card_name(c["name"]), c.get("price","?")))
        else:
            lines.append("**选择**: {}".format(act_cn))
    elif act_type == "buy_relic":
        rels = s.get("shop_details", {}).get("relics", [])
        idx_chosen = action.get("relic_index", action.get("option_index", "?"))
        if isinstance(idx_chosen, int) and idx_chosen < len(rels):
            r = rels[idx_chosen]
            lines.append("**选择**: 🛒 购买圣物 {} ({}g)".format(r["name"], r.get("price","?")))
        else:
            lines.append("**选择**: {}".format(act_cn))
    elif act_type == "remove_card":
        lines.append("**选择**: 🗑️ 移除卡牌")
    else:
        lines.append("**选择**: {}".format(act_cn if act_cn else "(无记录)"))

    sn = action.get("strategic_note", "")
    if sn:
        lines.append("**战略Note**: {}".format(str(sn)[:200]))

    reasoning = (dec.get("reasoning", "") or "")[:350]
    if reasoning:
        lines.append("**推理**: {}".format(reasoning))

    thinking = (call.get("thinking_text", "") or "")[:350]
    if thinking:
        lines.append("**Think**: {}".format(thinking))

    model_name = call.get("model", "?")
    tier = call.get("tier", "?")
    tokens = call.get("tokens", "?")
    latency = call.get("latency_ms", "?")
    lines.append("**模型**: {} | {} | {} tokens | {}ms".format(model_name, tier, tokens, latency))

    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

print("处理最近5个log文件:")
for f in SPECIFIC_FILES:
    print("  {}".format(os.path.basename(f)))

all_runs = []
for fpath in SPECIFIC_FILES:
    try:
        run_data = extract_run_data(fpath)
        if run_data and run_data["entries"]:
            all_runs.append(run_data)
            print("  {} → {}个卡牌/商店决策".format(run_data["run_id"], len(run_data["entries"])))
        elif run_data:
            print("  {} → 无卡牌/商店决策".format(run_data["run_id"]))
    except Exception as ex:
        import traceback
        print("  ERROR {}: {}".format(fpath, ex))
        traceback.print_exc()

if not all_runs:
    print("没有找到卡牌奖励或商店决策")
    exit()

# Build report
report_lines = []
report_lines.append("# STS2 Agent 卡牌奖励/商店决策分析报告")
report_lines.append("生成时间: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
report_lines.append("分析最近5个Run")
report_lines.append("")

total_rewards = 0
total_shop = 0
total_skips = 0
all_picked = []
all_skipped_candidates = []

for run_data in all_runs:
    entries = run_data["entries"]
    cr = [e for e in entries if e["state_type"] == "card_reward"]
    sh = [e for e in entries if e["state_type"] == "shop"]
    skips = [e for e in cr
             if (e.get("decision") or {}).get("action", {}) and
             isinstance((e.get("decision") or {}).get("action"), dict) and
             (e.get("decision") or {})["action"].get("action") in ("skip_reward_cards", "skip_card_reward")]

    total_rewards += len(cr)
    total_shop += len(sh)
    total_skips += len(skips)

    result_cn = "胜利🏆" if run_data["victory"] else ("失败💀" if run_data["victory"] is False else "未知❓")
    report_lines.append("")
    report_lines.append("=" * 60)
    report_lines.append("## Run: {}".format(run_data["run_id"]))
    report_lines.append("角色: {} | 结果: {} | 最终层数: {}".format(
        run_data["character"] or "未知", result_cn, run_data["final_floor"]))
    report_lines.append("卡牌奖励: {}次 | 商店: {}次 | 跳过: {}/{}".format(
        len(cr), len(sh), len(skips), len(cr)))
    report_lines.append("=" * 60)

    for i, entry in enumerate(entries, 1):
        report_lines.append(format_decision_entry(i, entry))

        dec = entry.get("decision") or {}
        action = dec.get("action", {}) if isinstance(dec.get("action"), dict) else {}
        act_type = action.get("action", "")
        if act_type == "choose_reward_card":
            idx_chosen = action.get("option_index")
            options = entry["state"].get("card_reward_details", {}).get("card_options", [])
            if isinstance(idx_chosen, int) and idx_chosen < len(options):
                all_picked.append(options[idx_chosen]["name"])
        elif act_type in ("skip_reward_cards", "skip_card_reward"):
            for c in entry["state"].get("card_reward_details", {}).get("card_options", []):
                all_skipped_candidates.append(c["name"])

# Summary
report_lines.append("")
report_lines.append("")
report_lines.append("=" * 60)
report_lines.append("## 总结统计")
report_lines.append("=" * 60)
report_lines.append("总Run数: {}".format(len(all_runs)))
report_lines.append("总卡牌奖励: {} | 跳过: {} ({}%)".format(
    total_rewards, total_skips, total_skips * 100 // max(total_rewards, 1)))
report_lines.append("总商店决策: {}".format(total_shop))
if all_picked:
    top_picked = Counter(all_picked).most_common(5)
    report_lines.append("最常选择的卡: {}".format(
        ", ".join("{}({}次)".format(translate_card_name(n), c) for n, c in top_picked)))
if all_skipped_candidates:
    top_skipped = Counter(all_skipped_candidates).most_common(5)
    report_lines.append("跳过时候选卡: {}".format(
        ", ".join("{}({}次)".format(translate_card_name(n), c) for n, c in top_skipped)))

# Write output
os.makedirs(REPORT_DIR, exist_ok=True)
date_str = datetime.now().strftime("%Y-%m-%d")
existing = [f for f in os.listdir(REPORT_DIR) if f.startswith("card_shop_{}_".format(date_str))]
seq = len(existing) + 1
filename = "card_shop_{}_{:03d}.txt".format(date_str, seq)
out_path = os.path.join(REPORT_DIR, filename)

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

total_decisions = total_rewards + total_shop
print("\n报告已生成: {}".format(out_path))
print("{}个Run, {}条决策 ({}卡牌奖励 + {}商店)".format(
    len(all_runs), total_decisions, total_rewards, total_shop))
