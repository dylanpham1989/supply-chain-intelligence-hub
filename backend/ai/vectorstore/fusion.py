from collections import defaultdict
from collections.abc import Sequence

from ai.vectorstore.base import SearchHit

# The constant damps the influence of the top few ranks. 60 is the value from
# the original paper and behaves well without tuning.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchHit]], *, k: int = RRF_K, limit: int | None = None
) -> list[SearchHit]:
    """Merge result lists by position rather than by score.

    Cosine similarity runs 0 to 1 and ts_rank_cd has no upper bound, so adding
    or averaging them means inventing a conversion. Ranks need no such thing,
    which is why this is the usual way to combine the two.
    """
    scores: dict[str, float] = defaultdict(float)
    seen: dict[str, SearchHit] = {}

    for ranking in rankings:
        for position, hit in enumerate(ranking, start=1):
            key = str(hit.chunk_id)
            scores[key] += 1.0 / (k + position)
            seen.setdefault(key, hit)

    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    fused = [
        SearchHit(
            chunk_id=seen[key].chunk_id,
            document_id=seen[key].document_id,
            content=seen[key].content,
            score=score,
            metadata=seen[key].metadata,
        )
        for key, score in ordered
    ]
    return fused[:limit] if limit else fused
