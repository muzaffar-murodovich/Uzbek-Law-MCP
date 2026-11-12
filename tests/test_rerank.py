from qonunshunos.search.rerank import blended_order, rerank_top


def test_blended_order_keeps_agreement_and_lifts_strong_scores():
    # Fused order 0, 1, 2, 3; the reranker likes item 3 best and item 0 second.
    order = blended_order([0.5, -1.0, -2.0, 3.0])
    assert order[:2] == [3, 0] or order[:2] == [0, 3]
    assert set(order) == {0, 1, 2, 3}
    # With equal scores the fused order stays.
    assert blended_order([1.0, 1.0, 1.0]) == [0, 1, 2]


def test_blended_order_without_fused_weight_follows_scores():
    assert blended_order([0.1, 0.9, 0.5], blend=0.0) == [1, 2, 0]


def test_rerank_top_from_environment(monkeypatch):
    monkeypatch.delenv("QONUNSHUNOS_RERANK_TOP", raising=False)
    assert rerank_top() == 20
    monkeypatch.setenv("QONUNSHUNOS_RERANK_TOP", "0")
    assert rerank_top() == 0
    monkeypatch.setenv("QONUNSHUNOS_RERANK_TOP", "30")
    assert rerank_top() == 30
