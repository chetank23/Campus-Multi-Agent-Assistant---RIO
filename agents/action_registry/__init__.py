"""
agents/action_registry package
------------------------------
Authoritative action registry for RIO Campus Assistant.
"""

from agents.action_registry.schemas import ActionDefinition, ActionParameter
from agents.action_registry.registry import ActionRegistry, action_registry

__all__ = [
    "ActionDefinition",
    "ActionParameter",
    "ActionRegistry",
    "action_registry",
]
