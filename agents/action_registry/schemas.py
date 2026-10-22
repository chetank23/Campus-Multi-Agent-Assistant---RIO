"""
agents/action_registry/schemas.py
---------------------------------
Typed schemas for discoverable, authoritative assistant action definitions.
PROJECT_SPECIFICATION.md and REAL-TIME AI OPERATIONS CAPABILITY contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ActionParameter(BaseModel):
    """Metadata describing a parameter required or accepted by an action."""
    name: str
    param_type: str  # e.g., "int", "str", "date", "time", "dict"
    description: str
    required: bool = True
    default: Optional[Any] = None


class ActionDefinition(BaseModel):
    """
    Authoritative typed definition of an assistant-executable capability.
    Enforces strict role boundaries, backend service delegation, and confirmation rules.
    """
    name: str
    category: Literal["READ", "WRITE"]
    purpose: str
    parameters: List[ActionParameter] = Field(default_factory=list)
    permitted_roles: List[str]  # e.g., ["ADMIN"], ["FACULTY", "STUDENT", "ADMIN"]
    authoritative_service: str
    validation_rules: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    expected_result: str
    failure_conditions: List[str] = Field(default_factory=list)
