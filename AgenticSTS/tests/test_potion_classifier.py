from src.knowledge.potion_classifier import classify_potion, format_potion_tag


class TestClassifyPotion:
    def test_strength_sustained(self):
        assert classify_potion("Strength Potion", "Gain 2 Strength.").timing == "sustained"

    def test_dexterity_sustained(self):
        assert classify_potion("Dexterity Potion", "Gain 2 Dexterity.").timing == "sustained"

    def test_regen_sustained(self):
        assert classify_potion("Regen Potion", "Gain 5 Regeneration.").timing == "sustained"

    def test_fire_instant(self):
        assert classify_potion("Fire Potion", "Deal 20 damage.").timing == "instant"

    def test_block_instant(self):
        assert classify_potion("Block Potion", "Gain 12 Block.").timing == "instant"

    def test_energy_instant(self):
        assert classify_potion("Energy Potion", "Gain 2 Energy.").timing == "instant"

    def test_unknown_defaults_instant(self):
        assert classify_potion("Mystery", "Something.").timing == "instant"


class TestFormatPotionTag:
    def test_sustained_monster(self):
        tag = format_potion_tag("sustained", "monster", floors_to_boss=5)
        assert "SUSTAINED" in tag
        assert "boss" in tag.lower()

    def test_sustained_boss(self):
        tag = format_potion_tag("sustained", "boss", floors_to_boss=0)
        assert "USE NOW" in tag or "OPTIMAL" in tag

    def test_instant(self):
        tag = format_potion_tag("instant", "monster", floors_to_boss=5)
        assert "INSTANT" in tag
