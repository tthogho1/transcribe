"""Tests for services/chat/prompt_store.py."""

import json

import pytest

from services.chat.prompt_store import PromptStore, default_prompt_id, default_store_dir
from services.chat.prompts import ANSWER_SYSTEM_PROMPT, SIMPLE_ANSWER_SYSTEM_PROMPT


@pytest.fixture
def store(tmp_path):
    return PromptStore(tmp_path, fallback_default="full")


def test_builtins_are_listed_first(store):
    prompts = store.list()
    assert [p.id for p in prompts] == ["full", "simple"]
    assert prompts[0].text == ANSWER_SYSTEM_PROMPT
    assert prompts[1].text == SIMPLE_ANSWER_SYSTEM_PROMPT
    assert all(p.builtin for p in prompts)


def test_nothing_is_written_until_something_is_saved(store, tmp_path):
    store.list(), store.resolve("full"), store.default_id
    assert list(tmp_path.iterdir()) == []


def test_save_adds_a_prompt_after_the_builtins(store, tmp_path):
    store.save("casual", "カジュアル", "やさしく答える。")

    assert [p.id for p in store.list()] == ["full", "simple", "casual"]
    saved = json.loads((tmp_path / "prompts" / "casual.json").read_text(encoding="utf-8"))
    assert (saved["title"], saved["text"]) == ("カジュアル", "やさしく答える。")
    assert "updated_at" in saved


def test_saved_prompts_survive_a_new_store_instance(store, tmp_path):
    store.save("casual", "カジュアル", "やさしく答える。")
    assert PromptStore(tmp_path).get("casual").text == "やさしく答える。"


@pytest.mark.parametrize("prompt_id", ["full", "simple"])
def test_builtins_cannot_be_saved_over(store, tmp_path, prompt_id):
    with pytest.raises(ValueError, match="built-in"):
        store.save(prompt_id, "改", "新しい本文")
    assert store.get(prompt_id).text != "新しい本文"
    assert not (tmp_path / "prompts").exists()


def test_a_leftover_override_file_is_ignored(store, tmp_path):
    folder = tmp_path / "prompts"
    folder.mkdir()
    (folder / "full.json").write_text('{"title": "改", "text": "上書き"}', encoding="utf-8")
    assert store.get("full").text == ANSWER_SYSTEM_PROMPT


def test_edited_copy_of_a_builtin_is_a_new_prompt(store):
    store.save("full-copy", "通常（コピー）", ANSWER_SYSTEM_PROMPT + "\n- 追加ルール")
    assert store.get("full").text == ANSWER_SYSTEM_PROMPT
    assert store.get("full-copy").text.endswith("追加ルール")
    assert not store.get("full-copy").builtin


def test_delete_custom_prompt(store):
    store.save("casual", "カジュアル", "本文")
    store.delete("casual")
    assert store.get("casual") is None


@pytest.mark.parametrize("prompt_id", ["full", "simple", "missing", "../etc/passwd", ""])
def test_delete_without_a_saved_file_is_a_key_error(store, prompt_id):
    with pytest.raises(KeyError):
        store.delete(prompt_id)


@pytest.mark.parametrize("prompt_id, title, text", [
    ("Bad-Caps", "t", "x"),
    ("../escape", "t", "x"),
    ("a" * 41, "t", "x"),
    ("-leading", "t", "x"),
    ("ok", "", "x"),
    ("ok", "   ", "x"),
    ("ok", "t" * 61, "x"),
    ("ok", "t", "   "),
    ("ok", "t", "x" * 20001),
    ("ok", None, "x"),
    ("ok", "t", None),
])
def test_invalid_input_is_rejected(store, tmp_path, prompt_id, title, text):
    with pytest.raises(ValueError):
        store.save(prompt_id, title, text)
    assert not (tmp_path / "prompts").exists() or not any((tmp_path / "prompts").iterdir())


def test_default_follows_the_admin_choice_while_it_exists(store):
    assert store.default_id == "full"
    store.save("casual", "カジュアル", "本文")
    store.set_default("casual")
    assert store.default_id == "casual"

    store.delete("casual")
    assert store.default_id == "full"  # back to the fallback


def test_set_default_to_unknown_prompt_fails(store):
    with pytest.raises(KeyError):
        store.set_default("missing")


def test_fallback_default_is_used_when_valid(tmp_path):
    assert PromptStore(tmp_path, fallback_default="simple").default_id == "simple"
    assert PromptStore(tmp_path, fallback_default="missing").default_id == "full"


@pytest.mark.parametrize("requested, expected", [("simple", "simple"), ("missing", "full"), (None, "full"), (5, "full")])
def test_resolve_falls_back_to_the_default(store, requested, expected):
    assert store.resolve(requested).id == expected


def test_malformed_files_are_ignored(store, tmp_path):
    folder = tmp_path / "prompts"
    folder.mkdir()
    (folder / "broken.json").write_text("{not json", encoding="utf-8")
    (folder / "nofields.json").write_text('{"title": 1}', encoding="utf-8")
    (folder / "Upper.json").write_text('{"title": "t", "text": "x"}', encoding="utf-8")
    assert [p.id for p in store.list()] == ["full", "simple"]


def test_no_temp_files_are_left_behind(store, tmp_path):
    store.save("casual", "カジュアル", "本文")
    store.set_default("casual")
    leftovers = [p.name for p in tmp_path.rglob("*") if p.name.endswith(".tmp")]
    assert leftovers == []


# --- defaults from the environment ------------------------------------------

def test_default_prompt_depends_on_provider(monkeypatch):
    monkeypatch.delenv("ANSWER_PROMPT", raising=False)
    assert default_prompt_id("openai") == "full"
    assert default_prompt_id("ollama") == "simple"
    monkeypatch.setenv("ANSWER_PROMPT", "casual")
    assert default_prompt_id("ollama") == "casual"


def test_store_dir_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMPT_STORE_DIR", str(tmp_path / "x"))
    assert default_store_dir() == tmp_path / "x"


def test_store_dir_defaults_to_project_instance_folder(monkeypatch):
    monkeypatch.delenv("PROMPT_STORE_DIR", raising=False)
    directory = default_store_dir()
    assert directory.parts[-2:] == ("instance", "prompts") or str(directory) == "/data/prompts"
