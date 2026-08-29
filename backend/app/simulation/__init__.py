"""Authoritative simulation domain and Game Master."""

from .game_master import GameMaster
from .scenarios import build_demo_store, get_scenario

__all__ = ["GameMaster", "build_demo_store", "get_scenario"]
