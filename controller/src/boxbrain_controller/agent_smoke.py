from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .model_agents import (
    ModelAgentExecutionError,
    ModelAgentRuntimeUnavailable,
    ModelAgentService,
)
from .models import ProcessingRequest
from .processing_agents import ProcessingService
from .processing_store import ProcessingStore
from .settings import settings


async def _run(content: str) -> None:
    local_service = ProcessingService(
        ProcessingStore(settings.data_dir / "boxbrain.sqlite3")
    )
    model_service = ModelAgentService(
        local_service,
        enabled=settings.agent_runtime_enabled,
        model=settings.agent_model,
        max_output_tokens=settings.agent_max_output_tokens,
    )
    result = await model_service.process(
        ProcessingRequest(content=content, source="api")
    )
    print(
        json.dumps(
            {
                "id": str(result.id),
                "project": result.plan.project,
                "intent": result.plan.intent,
                "task_count": len(result.plan.tasks),
                "requires_approval": result.plan.requires_approval,
                "model": result.model,
                "provider_tokens": result.usage.total_tokens,
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one safe BoxBrain model-agent smoke test."
    )
    parser.add_argument(
        "content",
        nargs="?",
        default="Organize this BoxBrain note and propose the next build task.",
    )
    arguments = parser.parse_args()
    try:
        asyncio.run(_run(arguments.content))
    except (ModelAgentRuntimeUnavailable, ModelAgentExecutionError) as error:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "detail": str(error),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
