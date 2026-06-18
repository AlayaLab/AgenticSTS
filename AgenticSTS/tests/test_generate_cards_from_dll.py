from __future__ import annotations

from pathlib import Path

from scripts.generate_cards_from_dll import (
    _render_description_template,
    parse_card_pools,
    parse_card_source,
)
from src.knowledge.card_lookup import CardLookup


def test_parse_scaling_attack_from_dll_source(tmp_path: Path) -> None:
    source = tmp_path / "Murder.cs"
    source.write_text(
        """
namespace MegaCrit.Sts2.Core.Models.Cards;

public sealed class Murder : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars => new DynamicVar[3]
    {
        new CalculationBaseVar(1m),
        new ExtraDamageVar(1m),
        new CalculatedDamageVar(ValueProp.Move).WithMultiplier(
            (CardModel card, Creature? _) =>
                CombatManager.Instance.History.Entries.OfType<CardDrawnEntry>().Count())
    };

    public Murder()
        : base(3, CardType.Attack, CardRarity.Rare, TargetType.AnyEnemy)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await DamageCmd.Attack(base.DynamicVars.CalculatedDamage).FromCard(this).Targeting(cardPlay.Target)
            .Execute(choiceContext);
    }

    protected override void OnUpgrade()
    {
        base.EnergyCost.UpgradeBy(-1);
    }
}
""",
        encoding="utf-8",
    )

    card = parse_card_source(source)

    assert card is not None
    assert card["id"] == "MURDER"
    assert card["cost"] == 3
    assert card["type"] == "Attack"
    assert card["rarity"] == "Rare"
    assert card["target"] == "AnyEnemy"
    assert card["vars"] == {"CalculationBase": 1, "ExtraDamage": 1, "CalculatedDamage": 2}
    assert card["damage"] == 1
    assert card["scaling"] == {"dimension": "cards_drawn_this_combat", "amount_per": 1}
    assert card["upgrade"] == {"cost": 2}


def test_parse_engine_support_card_from_dll_source(tmp_path: Path) -> None:
    source = tmp_path / "CorrosiveWave.cs"
    source.write_text(
        """
namespace MegaCrit.Sts2.Core.Models.Cards;

public sealed class CorrosiveWave : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars =>
        new DynamicVar("CorrosiveWave", 2m);

    public CorrosiveWave()
        : base(1, CardType.Skill, CardRarity.Rare, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await PowerCmd.Apply<CorrosiveWavePower>(
            base.Owner.Creature,
            base.DynamicVars["CorrosiveWave"].BaseValue,
            base.Owner.Creature,
            this);
    }

    protected override void OnUpgrade()
    {
        base.DynamicVars["CorrosiveWave"].UpgradeValueBy(1m);
    }
}
""",
        encoding="utf-8",
    )

    card = parse_card_source(source)

    assert card is not None
    assert card["vars"] == {"CorrosiveWave": 2}
    assert card["powers_applied"] == [{"power": "CorrosiveWave", "amount": 2}]
    assert card["upgrade"] == {"corrosivewave": "+1"}


def test_parse_card_pool_colors(tmp_path: Path) -> None:
    pools = tmp_path / "MegaCrit.Sts2.Core.Models.CardPools"
    pools.mkdir(parents=True)
    (pools / "SilentCardPool.cs").write_text(
        """
public sealed class SilentCardPool : CardPoolModel
{
    public override string Title => "silent";
    protected override CardModel[] GenerateAllCards()
    {
        return new CardModel[2]
        {
            ModelDb.Card<Murder>(),
            ModelDb.Card<CorrosiveWave>()
        };
    }
}
""",
        encoding="utf-8",
    )

    assert parse_card_pools(tmp_path) == {"Murder": "silent", "CorrosiveWave": "silent"}


def test_render_description_template_with_current_dll_vars() -> None:
    rendered = _render_description_template(
        "Deal {Damage:diff()} damage.\n"
        "Add {Shivs:diff()} [gold]{Shivs:plural:Shiv|Shivs}[/gold] into your Hand.",
        {"Damage": 3, "Shivs": 2},
    )

    assert rendered == "Deal 3 damage.\nAdd 2 [gold]Shivs[/gold] into your Hand."


def test_generated_card_includes_upgraded_state(tmp_path: Path) -> None:
    source = tmp_path / "CloakAndDagger.cs"
    source.write_text(
        """
namespace MegaCrit.Sts2.Core.Models.Cards;

public sealed class CloakAndDagger : CardModel
{
    protected override IEnumerable<DynamicVar> CanonicalVars => new DynamicVar[2]
    {
        new BlockVar(6m),
        new CardsVar(1)
    };

    public CloakAndDagger()
        : base(1, CardType.Skill, CardRarity.Common, TargetType.Self)
    {
    }

    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        await CreatureCmd.GainBlock(base.Owner.Creature, base.DynamicVars.Block, cardPlay);
    }

    protected override void OnUpgrade()
    {
        base.DynamicVars.Cards.UpgradeValueBy(1m);
    }
}
""",
        encoding="utf-8",
    )
    card = parse_card_source(source)
    assert card is not None

    from scripts.generate_cards_from_dll import merge_display_fields

    merged = merge_display_fields(
        card,
        {
            "id": "CLOAK_AND_DAGGER",
            "name": "Cloak and Dagger",
            "description_raw": (
                "Gain {Block:diff()} [gold]Block[/gold].\n"
                "Add {Cards:diff()} [gold]{Cards:plural:Shiv|Shivs}[/gold] into your Hand."
            ),
        },
    )

    assert merged["description"] == "Gain 6 [gold]Block[/gold].\nAdd 1 [gold]Shiv[/gold] into your Hand."
    assert merged["upgraded_vars"] == {"Block": 6, "Cards": 2}
    assert merged["upgraded_description"] == (
        "Gain 6 [gold]Block[/gold].\nAdd 2 [gold]Shivs[/gold] into your Hand."
    )


def test_parse_multiplayer_constraint_from_dll_source(tmp_path: Path) -> None:
    source = tmp_path / "Flanking.cs"
    source.write_text(
        """
namespace MegaCrit.Sts2.Core.Models.Cards;

public sealed class Flanking : CardModel
{
    public override CardMultiplayerConstraint MultiplayerConstraint =>
        CardMultiplayerConstraint.MultiplayerOnly;

    public Flanking()
        : base(2, CardType.Skill, CardRarity.Uncommon, TargetType.AnyEnemy)
    {
    }
}
""",
        encoding="utf-8",
    )

    card = parse_card_source(source)

    assert card is not None
    assert card["multiplayer_constraint"] == "MultiplayerOnly"


def test_card_lookup_indexes_json_only_cards(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "cards_dll.json").write_text(
        """[
          {
            "id": "DEFEND_SILENT",
            "name": "Defend",
            "description": "Gain 5 [gold]Block[/gold].",
            "description_raw": "Gain {Block:diff()} [gold]Block[/gold].",
            "rules_text": "Gain 5 [gold]Block[/gold].",
            "cost": 1,
            "type": "Skill",
            "rarity": "Basic",
            "target": "Self",
            "vars": {"Block": 5},
            "upgrade": {"block": "+3"},
            "upgraded_cost": 1,
            "upgraded_vars": {"Block": 8},
            "upgraded_description": "Gain 8 [gold]Block[/gold].",
            "upgraded_rules_text": "Gain 8 [gold]Block[/gold]."
          }
        ]""",
        encoding="utf-8",
    )

    lookup = CardLookup(tmp_path)
    card = lookup.get("Defend")

    assert card is not None
    assert card.name == "Defend"
    assert card.description == "Gain 5 [gold]Block[/gold]."
    assert card.base_cost == 1
    assert card.base_vars == (("Block", 5),)
    assert lookup.get_upgrade_preview("Defend") == (None, "Gain 8 Block.", [])
