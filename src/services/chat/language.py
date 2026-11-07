"""Decide whether a question is Japanese (the language of the search index)."""

import re

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException

# langdetect is probabilistic; seed it so the same text always gets the same answer.
DetectorFactory.seed = 0

# Hiragana, katakana (incl. half-width) and CJK ideographs.
_JAPANESE_SCRIPT_RE = re.compile(r"[぀-ヿㇰ-ㇿ㐀-䶿一-鿿ｦ-ﾟ]")


def detect_language(text: str) -> str:
    """A langdetect code for `text`, or "unknown" if it can't tell
    (empty text, or only digits/punctuation/emoji)."""
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def is_japanese_query(text: str) -> bool:
    """True if the user's query should be handled as Japanese.

    Any kana or kanji counts as Japanese: langdetect often labels short
    kanji-only queries (e.g. "東京駅") as Chinese or Korean. Text it can't
    classify (e.g. "2024") also defaults to Japanese, the index's language.
    """
    if _JAPANESE_SCRIPT_RE.search(text):
        return True
    return detect_language(text) in ("ja", "unknown")
