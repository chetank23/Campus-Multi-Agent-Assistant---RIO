"""
agents/llm/provider_interface.py
--------------------------------
Provider-neutral LLM abstraction interface for RIO-MJP.
Establishes a pluggable architecture:
- Database query execution, authorization, result validation, and factual grounding
  remain strictly under deterministic application control.
- An LLM provider (when configured later) can supply natural-language intent recognition,
  entity extraction, follow-up resolution, and phrasing.
- If no external LLM is configured or available, the system uses the DeterministicLLMProvider
  operating 100% offline without network calls or API keys.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class IntentExtractionResult:
    """Structured intent and entity parsing result."""
    intent: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    is_ambiguous: bool = False
    clarification_question: Optional[str] = None
    extracted_entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FormattedResponseResult:
    """Structured natural language presentation."""
    content: str
    sources: List[str] = field(default_factory=list)
    confidence: float = 1.0


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract protocol for future LLM integration."""

    def is_available(self) -> bool:
        """Checks if the provider is configured and reachable."""
        ...

    def extract_intent_and_entities(
        self,
        message: str,
        role: str,
        conversation_history: List[Dict[str, Any]],
    ) -> IntentExtractionResult:
        """Parses user message into intent and approved tool call arguments."""
        ...

    def format_grounded_response(
        self,
        query: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Dict[str, Any],
        role: str,
        user_name: str,
    ) -> FormattedResponseResult:
        """Generates natural language response grounded strictly in tool_result."""
        ...


class BaseLLMProvider(abc.ABC):
    """Base abstract class for LLM providers."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        pass

    @abc.abstractmethod
    def extract_intent_and_entities(
        self,
        message: str,
        role: str,
        conversation_history: List[Dict[str, Any]],
    ) -> IntentExtractionResult:
        pass

    @abc.abstractmethod
    def format_grounded_response(
        self,
        query: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Dict[str, Any],
        role: str,
        user_name: str,
    ) -> FormattedResponseResult:
        pass

    def generate_chat_response(
        self,
        message: str,
        user: Any,
        db: Any,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generates real-time grounded conversational response."""
        return {
            "reply": "",
            "intent": "DETERMINISTIC_EXTRACTION",
            "selected_agent": None,
            "tool_calls": [],
            "sources": [],
            "success": False,
            "error": "Not implemented in base provider",
        }


class DeterministicLLMProvider(BaseLLMProvider):
    """
    Default deterministic, database-grounded engine.
    Always available, requires 0 API keys, 0 external network requests.
    Guarantees that database queries, authorization, and factual results
    are 100% evidence-backed.
    """

    def is_available(self) -> bool:
        return True

    def extract_intent_and_entities(
        self,
        message: str,
        role: str,
        conversation_history: List[Dict[str, Any]],
    ) -> IntentExtractionResult:
        # Handled by the deterministic intent catalog & context resolver
        return IntentExtractionResult(
            intent="DETERMINISTIC_EXTRACTION",
            confidence=1.0,
        )

    def format_grounded_response(
        self,
        query: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Dict[str, Any],
        role: str,
        user_name: str,
    ) -> FormattedResponseResult:
        # Handled by response_formatter
        return FormattedResponseResult(
            content="",
            sources=[],
            confidence=1.0,
        )


class LLMProviderRegistry:
    """Registry managing active and fallback LLM providers."""

    _active_provider: Optional[BaseLLMProvider] = None

    @classmethod
    def get_provider(cls) -> BaseLLMProvider:
        if cls._active_provider is not None:
            return cls._active_provider

        try:
            from agents.llm.nvidia_provider import NvidiaNemotronProvider
            nvidia = NvidiaNemotronProvider()
            if nvidia.is_available():
                return nvidia
        except Exception:
            pass

        return DeterministicLLMProvider()

    @classmethod
    def register_provider(cls, provider: Optional[BaseLLMProvider]) -> None:
        cls._active_provider = provider


