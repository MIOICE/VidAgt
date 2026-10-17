import math

from app.agents.retrieval import _cosine, _tokens


def test_cosine_similarity() -> None:
    assert math.isclose(_cosine([1.0, 0.0], [1.0, 0.0]), 1.0)
    assert math.isclose(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
    assert _cosine([], []) == 0.0


def test_tokenizer_supports_chinese_bigrams_and_english_words() -> None:
    tokens = _tokens("讲解 Python 二叉树遍历")
    assert "python" in tokens
    assert "二叉" in tokens
    assert "遍历" in tokens

