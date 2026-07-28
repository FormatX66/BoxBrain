"""Backward-compatible imports for pre-0.6 edge-agent clients."""

from boxbrain.agent import agent_state, recommendations


controller_state = agent_state

__all__ = ["agent_state", "controller_state", "recommendations"]
