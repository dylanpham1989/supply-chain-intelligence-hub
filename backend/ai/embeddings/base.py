from typing import Protocol


class Embedder(Protocol):
    """Query and document vectors must come from the same model.

    Mixing models produces vectors that live in different spaces, and the
    failure looks like bad retrieval rather than an error.
    """

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def encode(self, texts: list[str]) -> list[list[float]]: ...

    async def encode_query(self, text: str) -> list[float]: ...
