"""GameKnowledge facade — unified access to all knowledge lookups."""

from __future__ import annotations

import logging
from pathlib import Path

from src.knowledge.act_lookup import ActLookup
from src.knowledge.card_lookup import CardLookup
from src.knowledge.enchantment_lookup import EnchantmentLookup
from src.knowledge.encounter_lookup import EncounterLookup
from src.knowledge.event_lookup import EventLookup
from src.knowledge.keyword_lookup import KeywordLookup
from src.knowledge.monster_lookup import MonsterLookup
from src.knowledge.potion_lookup import PotionLookup
from src.knowledge.relic_lookup import RelicLookup

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path("data/knowledge")


class GameKnowledge:
    """Singleton-style facade for all game knowledge lookups.

    Usage:
        kb = GameKnowledge()  # loads from data/knowledge/
        card = kb.cards.get("Strike")
        monster = kb.monsters.get("Chomper")
    """

    _instance: GameKnowledge | None = None

    def __init__(self, data_dir: Path | None = None) -> None:
        data_dir = data_dir or _DEFAULT_DATA_DIR
        self.cards = CardLookup(data_dir)
        self.monsters = MonsterLookup(data_dir)
        self.potions = PotionLookup(data_dir)
        self.events = EventLookup(data_dir)
        self.relics = RelicLookup(data_dir)
        self.encounters = EncounterLookup(data_dir)
        self.acts = ActLookup(data_dir)
        self.enchantments = EnchantmentLookup(data_dir)
        self.keywords = KeywordLookup(data_dir)
        logger.info(
            "GameKnowledge loaded: %d cards, %d monsters, %d potions, %d events, "
            "%d relics, %d encounters, %d acts, %d enchantments, %d keywords",
            self.cards.count, self.monsters.count,
            self.potions.count, self.events.count,
            self.relics.count, self.encounters.count,
            self.acts.count, self.enchantments.count, self.keywords.count,
        )

    @classmethod
    def get_instance(cls, data_dir: Path | None = None) -> GameKnowledge:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(data_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
