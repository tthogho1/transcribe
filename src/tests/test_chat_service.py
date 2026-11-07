"""
Tests for services/chat/service.py and services/chat/generator.py.

Components are passed in as fakes, so nothing connects to OpenAI, Zilliz or
Google Translate.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.chat.generator as generator_module
from models.conversation_chunk import SearchResult
from services.chat.generator import AnswerGenerator, GeneratedAnswer, trim_history
from services.chat.service import ChatService, QueryAnalysis


def _result(file_name="abc123.json", text="駅そばの話", title="Video"):
    return SearchResult(
        text=text, speaker="A", timestamp="00:01", file_name=file_name,
        score=0.9, similarity=0.9, search_type="hybrid", title=title,
    )


def _openai_response(content, total_tokens=5000):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=total_tokens),
    )


class FakeOpenAI:
    """Replies to answer calls from `answers` and to follow-up checks with `rewrite`."""

    def __init__(self, answers=(), rewrite=None):
        self.answers = list(answers)
        self.rewrite = rewrite
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "response_format" in kwargs:
            if isinstance(self.rewrite, Exception):
                raise self.rewrite
            return _openai_response(json.dumps(self.rewrite))
        reply = self.answers.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _openai_response(reply)

    def answer_calls(self):
        return [c for c in self.calls if "response_format" not in c]


def refuse_translation(*args, **kwargs):
    raise AssertionError("test tried to call Google Translate")


@pytest.fixture(autouse=True)
def no_network_translation(monkeypatch):
    monkeypatch.setattr(generator_module, "GoogleTranslator", MagicMock(side_effect=refuse_translation))


@pytest.fixture
def make_service():
    def make(results=None, openai=None, translate=refuse_translation):
        vectorizer = MagicMock()
        vectorizer.search_passages.return_value = [_result()] if results is None else results
        openai = openai or FakeOpenAI(answers=["答え"])
        return ChatService(
            vectorizer=vectorizer,
            generator=AnswerGenerator(client=openai),
            translator=SimpleNamespace(translate=translate),
        )
    return make


HISTORY = [{"role": "user", "content": "駅そばの話は？"}, {"role": "assistant", "content": "おいしかった"}]


# --- language ---------------------------------------------------------------

def test_kanji_only_query_is_answered_in_japanese(make_service):
    openai = FakeOpenAI(answers=["答え"])
    response = make_service(openai=openai).process_chat_query("東京駅")

    assert response.answer == "答え"
    system_prompt = openai.answer_calls()[0]["messages"][0]["content"]
    assert system_prompt.endswith("- Answer in Japanese")


def test_digit_only_query_does_not_error(make_service):
    assert make_service().process_chat_query("2024").answer == "答え"


def test_english_query_is_searched_in_japanese_and_answered_in_english(make_service, monkeypatch):
    translated_back = MagicMock(return_value="English answer")
    monkeypatch.setattr(
        generator_module, "GoogleTranslator",
        MagicMock(return_value=SimpleNamespace(translate=translated_back)),
    )
    openai = FakeOpenAI(answers=["日本語の答え"])
    service = make_service(openai=openai, translate=lambda text: "駅そばについて")

    response = service.process_chat_query("What about the station soba?")

    service.vectorizer.search_passages.assert_called_once_with("駅そばについて", limit=5)
    assert openai.answer_calls()[0]["messages"][0]["content"].endswith("- Answer in English")
    assert response.answer == "English answer"
    assert response.query == "What about the station soba?"


# --- follow-up detection ----------------------------------------------------

def test_follow_up_is_searched_with_rewritten_query_and_answered_with_history(make_service):
    openai = FakeOpenAI(answers=["続き"], rewrite={"is_follow_up": True, "standalone_query": " 駅そばの詳細 "})
    service = make_service(openai=openai)

    service.process_chat_query("もっと詳しく", HISTORY)

    service.vectorizer.search_passages.assert_called_once_with("駅そばの詳細", limit=5)
    messages = openai.answer_calls()[0]["messages"]
    assert messages[1:3] == HISTORY


def test_new_topic_is_answered_without_history(make_service):
    openai = FakeOpenAI(answers=["別の話"], rewrite={"is_follow_up": False, "standalone_query": "無視"})
    service = make_service(openai=openai)

    service.process_chat_query("ほまれって何？", HISTORY)

    service.vectorizer.search_passages.assert_called_once_with("ほまれって何？", limit=5)
    assert [m["role"] for m in openai.answer_calls()[0]["messages"]] == ["system", "user"]


def test_no_history_skips_the_follow_up_check(make_service):
    openai = FakeOpenAI(answers=["答え"])
    make_service(openai=openai).process_chat_query("駅そば")
    assert len(openai.calls) == 1  # the answer only


@pytest.mark.parametrize("rewrite", [RuntimeError("down"), {"is_follow_up": "yes"}, ["not", "a", "dict"]])
def test_failed_follow_up_check_keeps_history_and_query(make_service, rewrite):
    service = make_service(openai=FakeOpenAI(rewrite=rewrite))
    assert service.analyze_query("それは？", HISTORY) == QueryAnalysis(True, "それは？")


def test_blank_rewrite_falls_back_to_the_question(make_service):
    service = make_service(openai=FakeOpenAI(rewrite={"is_follow_up": True, "standalone_query": "  "}))
    assert service.analyze_query("それは？", HISTORY) == QueryAnalysis(True, "それは？")


# --- errors -----------------------------------------------------------------

@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_openai_answer_becomes_error_message(make_service, content):
    service = make_service(openai=FakeOpenAI(answers=[content]))

    response = service.process_chat_query("質問")

    assert response.error is True
    assert response.answer == "申し訳ございませんが、回答の生成中にエラーが発生しました。"
    assert response.sources  # the search results are still shown


def test_empty_answer_raises_in_the_generator():
    generator = AnswerGenerator(client=FakeOpenAI(answers=[None]))
    with pytest.raises(ValueError):
        generator.generate("質問", [_result()], [], answer_in_english=False)


def test_search_failure_is_a_processing_error_without_generating(make_service):
    openai = FakeOpenAI()
    service = make_service(openai=openai)
    service.vectorizer.search_passages.side_effect = ConnectionError("zilliz down")

    response = service.process_chat_query("駅そば")

    assert response.error is True
    assert response.answer == "申し訳ございませんが、処理中にエラーが発生しました。"
    assert response.sources == []
    assert openai.calls == []


def test_error_messages_follow_the_question_language(make_service, monkeypatch):
    service = make_service(openai=FakeOpenAI(answers=[RuntimeError("down")]), translate=lambda t: "駅そば")
    response = service.process_chat_query("What happened there?")
    assert response.answer == "Sorry, an error occurred while generating the response."


# --- generator details ------------------------------------------------------

def test_context_too_long_retries_with_shorter_history():
    long_history = [{"role": r, "content": "あ" * 1000} for r in ["user", "assistant"] * 8]
    openai = FakeOpenAI(answers=[RuntimeError("This model's maximum context length is 8192"), "再試行"])

    answer = AnswerGenerator(client=openai).generate("質問", [_result()], long_history, False)

    assert answer.text == "再試行"
    first, retry = openai.answer_calls()
    assert len(retry["messages"]) < len(first["messages"])


def test_other_openai_errors_are_not_retried():
    openai = FakeOpenAI(answers=[RuntimeError("rate limited"), "unused"])
    with pytest.raises(RuntimeError, match="rate limited"):
        AnswerGenerator(client=openai).generate("質問", [_result()], [], False)
    assert len(openai.answer_calls()) == 1


def test_answer_reports_total_tokens():
    answer = AnswerGenerator(client=FakeOpenAI(answers=["答え"])).generate("質問", [], [], False)
    assert answer == GeneratedAnswer("答え", 5000)


def test_trim_history_keeps_recent_messages_within_budget():
    history = [{"role": "system", "content": "x"}] + [
        {"role": "user", "content": f"{i}" * 400} for i in range(10)
    ]
    trimmed = trim_history(history, max_turns=6, max_tokens=250)
    assert [m["content"][0] for m in trimmed] == ["8", "9"]  # system dropped; budget leaves 2


# --- response ---------------------------------------------------------------

def test_related_videos_are_deduplicated_with_title_fallback(make_service):
    results = [
        _result("vidA_transcription.json", title="A"),
        _result("vidB.json", title=""),
        _result("vidA_transcription.json", title="A"),
    ]
    response = make_service(results=results).process_chat_query("駅そば")

    assert response.related_videos == [
        {"video_id": "vidA", "title": "A", "url": "https://www.youtube.com/watch?v=vidA"},
        {"video_id": "vidB", "title": "vidB", "url": "https://www.youtube.com/watch?v=vidB"},
    ]
    assert sorted(response.file_names) == ["vidA_transcription.json", "vidB.json"]
