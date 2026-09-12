"""Adapter: recording AI runs. Satisfies ports.AiRunRecorder."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.ai_run_recorder import AiRunRecord
from app.infrastructure.database.models import AiRunModel
from app.observability.logging import get_logger

_logger = get_logger(__name__)


class SqlAlchemyAiRunRecorder:
    """Persists one row per LLM call."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, run: AiRunRecord) -> None:
        """Store the run, and never let a telemetry failure break the request.

        Losing an observability row is annoying. Failing a user's request
        because an observability row could not be written is worse.
        """
        try:
            async with self._session_factory() as session:
                session.add(
                    AiRunModel(
                        id=uuid4(),
                        feature=run.feature,
                        provider=run.provider,
                        model=run.model,
                        prompt_version=run.prompt_version,
                        status=run.status,
                        error=run.error,
                        latency_ms=run.latency_ms,
                        input_tokens=run.input_tokens,
                        output_tokens=run.output_tokens,
                        estimated_cost_usd=run.estimated_cost_usd,
                        output=dict(run.output),
                        lead_id=run.lead_id,
                        correlation_id=run.correlation_id,
                        created_at=run.created_at,
                    )
                )
                await session.commit()
        except Exception:
            _logger.exception("ai_run_record_failed", feature=run.feature)
