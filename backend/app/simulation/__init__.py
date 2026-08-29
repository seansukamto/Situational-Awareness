"""Authoritative simulation domain and Game Master."""

from .game_master import GAME_MASTER_RULES, GAME_MASTER_RULES_VERSION, GameMaster
from .scenarios import build_demo_store, get_scenario

__all__ = [
    "GAME_MASTER_RULES",
    "GAME_MASTER_RULES_VERSION",
    "GameMaster",
    "build_demo_store",
    "get_scenario",
]
