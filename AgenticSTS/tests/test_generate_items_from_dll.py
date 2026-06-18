from __future__ import annotations

from pathlib import Path

from scripts.generate_items_from_dll import generate_potions, generate_relics


def test_generate_relics_from_dll_source_and_flat_localization(tmp_path: Path) -> None:
    relic_dir = tmp_path / "MegaCrit.Sts2.Core.Models.Relics"
    pool_dir = tmp_path / "MegaCrit.Sts2.Core.Models.RelicPools"
    loc_dir = tmp_path / "loc"
    relic_dir.mkdir(parents=True)
    pool_dir.mkdir(parents=True)
    loc_dir.mkdir()
    (relic_dir / "Vajra.cs").write_text(
        """
public sealed class Vajra : RelicModel
{
    public override RelicRarity Rarity => RelicRarity.Common;
    protected override IEnumerable<DynamicVar> CanonicalVars =>
        new PowerVar<StrengthPower>(1m);
    public override async Task AfterRoomEntered(AbstractRoom room)
    {
        await PowerCmd.Apply<StrengthPower>(
            base.Owner.Creature, base.DynamicVars.Strength.BaseValue, base.Owner.Creature, null);
    }
}
""",
        encoding="utf-8",
    )
    (pool_dir / "SharedRelicPool.cs").write_text(
        "class SharedRelicPool { object x = ModelDb.Relic<Vajra>(); }",
        encoding="utf-8",
    )
    loc = loc_dir / "relics.json"
    loc.write_text(
        '{"VAJRA.title":"Vajra","VAJRA.description":"Start each combat with [blue]{StrengthPower}[/blue] [gold]Strength[/gold]."}',
        encoding="utf-8",
    )

    relic = generate_relics(tmp_path, loc)[0]

    assert relic["id"] == "VAJRA"
    assert relic["name"] == "Vajra"
    assert relic["rarity"] == "Common"
    assert relic["pool"] == "shared"
    assert relic["vars"] == {"StrengthPower": 1}
    assert relic["powers_applied"] == [{"power": "Strength", "amount": 1}]
    assert relic["description"] == "Start each combat with [blue]1[/blue] [gold]Strength[/gold]."


def test_generate_potions_from_dll_source_and_flat_localization(tmp_path: Path) -> None:
    potion_dir = tmp_path / "MegaCrit.Sts2.Core.Models.Potions"
    pool_dir = tmp_path / "MegaCrit.Sts2.Core.Models.PotionPools"
    loc_dir = tmp_path / "loc"
    potion_dir.mkdir(parents=True)
    pool_dir.mkdir(parents=True)
    loc_dir.mkdir()
    (potion_dir / "DexterityPotion.cs").write_text(
        """
public sealed class DexterityPotion : PotionModel
{
    public override PotionRarity Rarity => PotionRarity.Common;
    public override PotionUsage Usage => PotionUsage.CombatOnly;
    public override TargetType TargetType => TargetType.AnyPlayer;
    protected override IEnumerable<DynamicVar> CanonicalVars =>
        new PowerVar<DexterityPower>(2m);
    protected override async Task OnUse(PlayerChoiceContext choiceContext, Creature? target)
    {
        await PowerCmd.Apply<DexterityPower>(target, base.DynamicVars.Dexterity.BaseValue, base.Owner.Creature, null);
    }
}
""",
        encoding="utf-8",
    )
    (pool_dir / "SharedPotionPool.cs").write_text(
        "class SharedPotionPool { object x = ModelDb.Potion<DexterityPotion>(); }",
        encoding="utf-8",
    )
    loc = loc_dir / "potions.json"
    loc.write_text(
        '{"DEXTERITY_POTION.title":"Dexterity Potion","DEXTERITY_POTION.description":"Gain [blue]{DexterityPower}[/blue] [gold]Dexterity[/gold]."}',
        encoding="utf-8",
    )

    potion = generate_potions(tmp_path, loc)[0]

    assert potion["id"] == "DEXTERITY_POTION"
    assert potion["name"] == "Dexterity Potion"
    assert potion["rarity"] == "Common"
    assert potion["usage"] == "CombatOnly"
    assert potion["target"] == "AnyPlayer"
    assert potion["pool"] == "shared"
    assert potion["vars"] == {"DexterityPower": 2}
    assert potion["powers_applied"] == [{"power": "Dexterity", "amount": 2}]
    assert potion["description"] == "Gain [blue]2[/blue] [gold]Dexterity[/gold]."
