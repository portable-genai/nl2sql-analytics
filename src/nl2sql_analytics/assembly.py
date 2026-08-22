"""Wire the pure orchestrator to the profile-bound ports: the one place the two meet.

The domain :class:`AnalystService` takes its ports by constructor injection and knows nothing
about profiles or settings; the :class:`Container` binds ports by profile and knows nothing about
the orchestrator. This module joins them, so every surface (api, cli, agent, demo) builds the
service the same way and none reaches into the container port by port.
"""

from __future__ import annotations

from .config import Container, Settings, build_container
from .domain.analyst_service import AnalystService
from .semantic_config import load_semantic_layer


def analyst_service(container: Container) -> AnalystService:
    """Wire the orchestrator to an already-built container's ports and the certified layer."""
    layer = load_semantic_layer(container.settings)
    return AnalystService(
        layer=layer,
        guardrail=container.guardrail,
        dictionary=container.dictionary,
        llm=container.llm,
        certification=container.certification,
        query_engine=container.query_engine,
        audit=container.audit,
        tracer=container.tracer,
    )


def build_analyst(settings: Settings | None = None) -> tuple[Container, AnalystService]:
    """Return the profile-bound container and the orchestrator wired to its ports and layer."""
    container = build_container(settings or Settings.load())
    return container, analyst_service(container)
