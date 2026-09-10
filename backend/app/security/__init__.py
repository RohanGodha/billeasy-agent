"""DPDP-focused PII shielding for Counter Copilot's free-text surfaces.

Exposed as `mask_pii`, applied at every boundary where user text reaches an LLM, the
knowledge base or persistence (see `app.api.chat` and `app.agent.graph`).
"""
from app.security.pii import mask_pii

__all__ = ["mask_pii"]
