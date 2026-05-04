from dataclasses import dataclass, field


@dataclass
class DeckHistoryEntry:
    name: str
    archetype: str
    colors: str
    score: int
    timestamp: str
    deck: list = field(default_factory=list)
    lands: list = field(default_factory=list)
    deck_qty: dict = field(default_factory=dict)
    land_qty: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
