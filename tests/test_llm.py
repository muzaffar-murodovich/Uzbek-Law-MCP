import pytest

from qonunshunos import llm
from qonunshunos.llm import BudgetExhausted, Ledger, LLMError, OpenAIChat, tier_of


def test_unknown_model_is_refused():
    assert tier_of("gpt-5.4") == "big"
    assert tier_of("gpt-5.4-mini") == "small"
    with pytest.raises(LLMError):
        tier_of("gpt-image-1")


def test_keys_are_skipped_once_their_free_tokens_are_used(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY_2", "k2")
    monkeypatch.setenv("OPENAI_API_KEY_3", "k3")
    monkeypatch.setenv("OPENAI_API_KEY", "k1")
    monkeypatch.setattr(llm, "LEDGER", tmp_path / "usage.json")
    monkeypatch.setattr(llm, "load_dotenv", lambda: None)
    chat = OpenAIChat("gpt-5.4")
    chat.ledger = Ledger(tmp_path / "usage.json")
    assert chat._pick_key() == ("OPENAI_API_KEY_2", "k2")  # second account first
    chat.ledger.add("OPENAI_API_KEY_2", "big", 239_000)
    assert chat._pick_key() == ("OPENAI_API_KEY_3", "k3")
    chat.ledger.add("OPENAI_API_KEY_3", "big", 240_000)
    assert chat._pick_key() == ("OPENAI_API_KEY", "k1")
    chat.ledger.add("OPENAI_API_KEY", "big", 250_000)
    with pytest.raises(BudgetExhausted):
        chat._pick_key()
    chat.allow_paid = True  # explicitly allowed: the least used account pays
    assert chat._pick_key() == ("OPENAI_API_KEY_2", "k2")
