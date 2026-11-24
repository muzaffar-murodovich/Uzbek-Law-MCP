import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

from nizom.index.embed import DEFAULT_MODEL, MODELS, ensure_model, load_tokenizer


def test_load_tokenizer_drops_saved_padding_and_truncation(tmp_path):
    vocab = {"<pad>": 0, "<unk>": 1, "a": 2, "b": 3, "c": 4}
    saved = Tokenizer(models.WordLevel(vocab, unk_token="<unk>"))
    saved.pre_tokenizer = pre_tokenizers.Whitespace()
    # What transformers writes after fine-tuning: pad to the batch's longest, cut at 2.
    saved.enable_padding(pad_id=0, pad_token="<pad>")
    saved.enable_truncation(2)
    path = tmp_path / "tokenizer.json"
    saved.save(str(path))

    tokenizer = load_tokenizer(path, max_tokens=4)
    lengths = [len(e.ids) for e in tokenizer.encode_batch(["a", "a b c", "a b c a b"])]
    assert lengths == [1, 3, 4]


def test_local_model_is_never_downloaded(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("a local/ model must not be fetched from the Hub")

    monkeypatch.setattr("nizom.index.embed.httpx.stream", no_network)
    assert MODELS[DEFAULT_MODEL].repo.startswith("local/")
    with pytest.raises(RuntimeError, match="not on the Hub"):
        ensure_model(MODELS[DEFAULT_MODEL], tmp_path)
