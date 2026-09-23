from typing import ClassVar

from arq.connections import RedisSettings

from ai.embeddings.hf_embedder import get_embedder
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from worker.tasks import embed_document, process_document

log = get_logger(__name__)

JOB_TIMEOUT_S = 300
MAX_TRIES = 3


async def startup(ctx: dict[str, object]) -> None:
    configure_logging(env=settings.env, level="DEBUG" if settings.debug else "INFO")
    # Loading the model takes a few seconds. Paying that at startup keeps it out
    # of the first job's latency, and the startup probe covers the wait.
    await get_embedder().warm()
    log.info("worker.startup", env=settings.env, embedding_model=settings.embedding_model)


async def shutdown(ctx: dict[str, object]) -> None:
    log.info("worker.shutdown")


class WorkerSettings:
    functions: ClassVar[list[object]] = [process_document, embed_document]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = JOB_TIMEOUT_S
    max_tries = MAX_TRIES
    # Parsing holds a whole document in memory, so concurrency is bounded well
    # below what the event loop could otherwise run.
    max_jobs = 4
    retry_jobs = True
    keep_result = 3600
