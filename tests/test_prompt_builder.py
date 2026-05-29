import pytest
from src.ai.prompt_builder import _transpose_sample


def test_transpose_sample_basic():
    sample = [
        {"nome": "Alice", "idade": 30},
        {"nome": "Bob",   "idade": 25},
    ]
    result = _transpose_sample(sample)
    assert result == {"nome": ["Alice", "Bob"], "idade": [30, 25]}


def test_transpose_sample_empty():
    assert _transpose_sample([]) == {}


def test_transpose_sample_missing_keys():
    sample = [{"a": 1, "b": 2}, {"a": 3}]
    result = _transpose_sample(sample)
    assert result["a"] == [1, 3]
    assert result["b"] == [2]


def test_transpose_sample_preserves_row_order():
    sample = [
        {"col": "primeiro"},
        {"col": "segundo"},
        {"col": "terceiro"},
    ]
    result = _transpose_sample(sample)
    assert result["col"] == ["primeiro", "segundo", "terceiro"]
