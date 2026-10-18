"""
agents/scheduling_agent/__init__.py
-----------------------------------
Package for RIO-MJP Scheduling Agent.
"""

from agents.scheduling_agent.agent import run_scheduling_agent
from agents.scheduling_agent.proposal_store import proposal_store, SchedulingProposal

__all__ = ["run_scheduling_agent", "proposal_store", "SchedulingProposal"]
