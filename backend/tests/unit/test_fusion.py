"""Reciprocal rank fusion.

Cosine runs 0 to 1 and ts_rank_cd has no upper bound. Combining the scores means
inventing a conversion between them; combining the ranks does not.
"""

from uuid import UUID, uuid4

from ai.vectorstore.base import SearchHit
from ai.vectorstore.fusion import RRF_K, reciprocal_rank_fusion

DOC = uuid4()


def hit(chunk_id: UUID, score: float = 1.0) -> SearchHit:
    return SearchHit(chunk_id=chunk_id, document_id=DOC, content="x", score=score)


def test_no_rankings_produces_nothing() -> None:
    assert reciprocal_rank_fusion([]) == []


def test_a_single_ranking_keeps_its_order() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()

    fused = reciprocal_rank_fusion([[hit(a), hit(b), hit(c)]])

    assert [h.chunk_id for h in fused] == [a, b, c]


def test_a_result_in_both_rankings_outranks_one_in_either() -> None:
    both, vector_only, keyword_only = uuid4(), uuid4(), uuid4()

    fused = reciprocal_rank_fusion([[hit(vector_only), hit(both)], [hit(keyword_only), hit(both)]])

    assert fused[0].chunk_id == both


def test_scores_follow_the_formula() -> None:
    a, b = uuid4(), uuid4()

    fused = reciprocal_rank_fusion([[hit(a), hit(b)], [hit(b), hit(a)]])

    expected = 1 / (RRF_K + 1) + 1 / (RRF_K + 2)
    assert fused[0].score == expected
    assert fused[1].score == expected


def test_a_huge_score_does_not_beat_a_better_rank() -> None:
    """The point of rank fusion: the scales are not comparable."""
    loud, quiet = uuid4(), uuid4()

    fused = reciprocal_rank_fusion(
        [[hit(quiet, score=0.4), hit(loud, score=0.39)], [hit(loud, score=9999.0)]]
    )

    assert {h.chunk_id for h in fused} == {loud, quiet}
    assert fused[0].chunk_id == loud, "appearing in both lists should win"


def test_duplicates_are_merged_once() -> None:
    a = uuid4()

    fused = reciprocal_rank_fusion([[hit(a)], [hit(a)], [hit(a)]])

    assert len(fused) == 1


def test_the_limit_is_applied_after_fusing() -> None:
    hits = [hit(uuid4()) for _ in range(10)]

    assert len(reciprocal_rank_fusion([hits], limit=3)) == 3
