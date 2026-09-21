"""The AI provider: xAI Grok, bring your own key, one per agency.

Grok is reached through xAI's OpenAI-compatible API
(``https://api.x.ai/v1``). An agency stores one xAI key and each agent
picks a Grok model id (``grok-4.6``, ``grok-4.5``, ``grok-code-fast-1``, …).

The registry id stays ``openrouter`` so existing agencies, routes and
tests keep working; only the upstream host, label and models change.
The registry keeps its dict shape so a deployment can still swap the
base URL without touching the call sites.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, ProviderCredential
from ..security import decrypt_secret


PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {"label": "xAI Grok", "base_url": "https://api.x.ai/v1"},
    "xai": {"label": "xAI Grok", "base_url": "https://api.x.ai/v1"},
}
SUPPORTED = tuple(PROVIDERS)
DEFAULT_PROVIDER = "openrouter"


def base_url_for(provider: str) -> str:
    return PROVIDERS[provider]["base_url"]


def resolve_provider_credentials(db: Session, agency_id, provider: str) -> tuple[str, str] | None:
    """(base_url, api_key) for an agency's provider key, or None if unknown or unset."""
    if provider not in PROVIDERS:
        return None
    aliases = ("openrouter", "xai") if provider in ("openrouter", "xai") else (provider,)
    credential = db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.agency_id == agency_id,
            ProviderCredential.provider.in_(aliases),
        )
    )
    if not credential:
        return None
    return base_url_for(provider), decrypt_secret(credential.encrypted_api_key)


def resolve_agent_credentials(db: Session, agent: Agent) -> tuple[str, str] | None:
    """(base_url, api_key) for the agent's provider using the agency's stored key."""
    return resolve_provider_credentials(db, agent.agency_id, agent.provider)
