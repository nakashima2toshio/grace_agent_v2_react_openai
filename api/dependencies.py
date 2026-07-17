"""Application-scoped service dependencies."""

import os

from services.agent_support_run_store import RedisAgentSupportRunStore
from services.agent_support_service import AgentSupportService


def _create_service() -> AgentSupportService:
    if os.getenv("AGENT_SUPPORT_STORE", "memory").lower() == "redis":
        store = RedisAgentSupportRunStore.from_url(
            os.getenv("AGENT_SUPPORT_REDIS_URL", "redis://localhost:6379/2"),
            os.getenv("AGENT_SUPPORT_REDIS_NAMESPACE", "grace:agent_support:v1"),
        )
        return AgentSupportService(store=store)
    return AgentSupportService()


agent_support_service = _create_service()


def get_agent_support_service() -> AgentSupportService:
    return agent_support_service
