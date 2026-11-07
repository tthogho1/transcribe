"""Tests for services/chat/language.py."""

import pytest

from services.chat.language import detect_language, is_japanese_query


@pytest.mark.parametrize("query", ["東京駅", "誉", "人工知能", "駅そば", "好きな食べ物は何", "ｶﾚｰ"])
def test_japanese_script_is_japanese(query):
    # langdetect alone labels e.g. "東京駅" as ko and "誉" as zh-cn
    assert is_japanese_query(query) is True


@pytest.mark.parametrize("query", ["2024", "？", "!!!", ""])
def test_unclassifiable_query_defaults_to_japanese(query):
    assert is_japanese_query(query) is True


def test_english_query_is_not_japanese():
    assert is_japanese_query("What did you eat at the station?") is False


def test_detect_language_never_raises():
    assert detect_language("2024") == "unknown"
