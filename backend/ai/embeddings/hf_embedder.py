from typing import Any

import anyio

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

BATCH_SIZE = 32


class HuggingFaceEmbedder:
    """all-MiniLM-L6-v2 by default: 384 dimensions, cpu only, about 80 MB.

    Loaded once and kept. sentence-transformers is synchronous and cpu bound, so
    every call goes to a thread; running it inline would stall the event loop
    for every other request on the worker.
    """

    _model: Any = None

    def __init__(self, model_name: str | None = None, batch_size: int = BATCH_SIZE) -> None:
        self._model_name = model_name or settings.embedding_model
        self._batch_size = batch_size

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return settings.embedding_dim

    def _load(self) -> Any:
        if HuggingFaceEmbedder._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("embedder.loading", model=self._model_name)
            HuggingFaceEmbedder._model = SentenceTransformer(self._model_name, device="cpu")
            log.info("embedder.loaded", model=self._model_name)
        return HuggingFaceEmbedder._model

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            # Normalised, so cosine distance and inner product agree and the
            # pgvector index can use either.
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    async def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await anyio.to_thread.run_sync(self._encode_sync, texts)

    async def encode_query(self, text: str) -> list[float]:
        vectors = await self.encode([text])
        return vectors[0]

    async def warm(self) -> None:
        await anyio.to_thread.run_sync(self._load)


_embedder: HuggingFaceEmbedder | None = None


def get_embedder() -> HuggingFaceEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = HuggingFaceEmbedder()
    return _embedder
