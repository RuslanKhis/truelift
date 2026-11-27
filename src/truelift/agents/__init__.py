"""The agents and their model gateway (G11; D7). Every LLM call goes through ``gateway``.

Nothing here imports ``google.adk`` at package import: the policy modules (keys, redaction,
payload, gateway) are importable and testable without the SDK, and the API app does not load
ADK to serve the setup routes. The ADK model wrapper loads on first use (``gated_model``).
"""
