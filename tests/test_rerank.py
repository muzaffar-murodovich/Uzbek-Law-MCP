from nizom.search.rerank import DEFAULT_TOP, blended_order, rerank_top


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
    monkeypatch.delenv("NIZOM_RERANK_TOP", raising=False)
    monkeypatch.delenv("QONUNSHUNOS_RERANK_TOP", raising=False)
    assert rerank_top() == DEFAULT_TOP
    monkeypatch.setenv("NIZOM_RERANK_TOP", "0")
    assert rerank_top() == 0
    monkeypatch.setenv("NIZOM_RERANK_TOP", "12")
    assert rerank_top() == 12


def test_score_keeps_the_order_of_the_texts():
    from nizom.search.rerank import Reranker

    class Lengths(Reranker):
        def __init__(self) -> None:
            pass

        def _score(self, query, texts):
            return [float(len(t)) for t in texts]

    texts = ["ccc", "a", "bbbbb", "dd", "e" * 9]
    assert Lengths().score("q", texts, batch_size=2) == [3.0, 1.0, 5.0, 2.0, 9.0]
