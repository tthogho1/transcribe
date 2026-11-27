"""
Answer prompts users can choose from, and admins can add.

Built-in prompts come from prompts.py and are read-only: they change only
with the code. Admins add their own prompts (e.g. an edited copy of a
built-in), which are saved as JSON files in a directory, so they survive
restarts when that directory is on persistent storage (/data on a Hugging
Face Space with storage enabled):

  <dir>/prompts/<id>.json   {"id", "title", "text", "updated_at"}
  <dir>/settings.json       {"default": "<id>"}
"""

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from services.chat.prompts import BUILTIN_ANSWER_PROMPTS

logger = logging.getLogger(__name__)

PROMPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_TITLE_CHARS = 60
MAX_TEXT_CHARS = 20000


@dataclass(frozen=True)
class Prompt:
    id: str
    title: str
    text: str
    builtin: bool  # one of BUILTIN_ANSWER_PROMPTS (read-only)


def default_store_dir() -> Path:
    """PROMPT_STORE_DIR, else /data/prompts (HF persistent storage), else
    instance/prompts in the project (local development; git-ignored)."""
    configured = os.getenv("PROMPT_STORE_DIR")
    if configured:
        return Path(configured)
    data = Path("/data")
    if data.is_dir() and os.access(data, os.W_OK):
        return data / "prompts"
    return Path(__file__).resolve().parents[3] / "instance" / "prompts"


def default_prompt_id(provider: str) -> str:
    """ANSWER_PROMPT, else the simple prompt for local models, else the full one."""
    return os.getenv("ANSWER_PROMPT") or ("simple" if provider == "ollama" else "full")


class PromptStore:
    """Built-in prompts plus the prompts admins saved in `directory`.

    Files are read on every call (they're tiny), so edits show up at once
    without a restart.
    """

    def __init__(self, directory: Path, fallback_default: str = "full"):
        self.directory = Path(directory)
        self.fallback_default = fallback_default
        self._lock = threading.Lock()

    # --- reading -------------------------------------------------------------

    def list(self) -> List[Prompt]:
        """Built-ins first (in their defined order), then the others by title."""
        builtins = [
            Prompt(pid, title, text, builtin=True)
            for pid, (title, text) in BUILTIN_ANSWER_PROMPTS.items()
        ]
        custom = [
            Prompt(pid, data["title"], data["text"], builtin=False)
            for pid, data in self._read_saved().items()
        ]
        return builtins + sorted(custom, key=lambda p: p.title)

    def get(self, prompt_id: Optional[str]) -> Optional[Prompt]:
        if not isinstance(prompt_id, str):
            return None
        return next((p for p in self.list() if p.id == prompt_id), None)

    @property
    def default_id(self) -> str:
        """The admin's choice if it still exists, else the configured fallback."""
        chosen = self._read_json(self._settings_path()).get("default")
        if chosen and self.get(chosen):
            return chosen
        return self.fallback_default if self.get(self.fallback_default) else "full"

    def resolve(self, prompt_id: Optional[str]) -> Prompt:
        """The requested prompt, or the default if it's missing or unknown."""
        return self.get(prompt_id) or self.get(self.default_id)

    # --- writing -------------------------------------------------------------

    def save(self, prompt_id: str, title: str, text: str) -> Prompt:
        """Create or replace an admin prompt. Raises ValueError on invalid
        input, including a built-in's id (built-ins are read-only)."""
        _validate(prompt_id, title, text)
        if prompt_id in BUILTIN_ANSWER_PROMPTS:
            raise ValueError(
                f"'{prompt_id}' is a built-in prompt and can't be edited; "
                "save your version under a new id"
            )
        record = {
            "id": prompt_id,
            "title": title.strip(),
            "text": text,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._write_json(self._prompt_path(prompt_id), record)
        logger.info(f"Saved prompt {prompt_id!r}")
        return self.get(prompt_id)

    def delete(self, prompt_id: str) -> None:
        """Delete an admin prompt. Raises KeyError if there is no such
        prompt (built-ins can't be deleted)."""
        if prompt_id in BUILTIN_ANSWER_PROMPTS or not PROMPT_ID_RE.match(prompt_id or ""):
            raise KeyError(prompt_id)
        path = self._prompt_path(prompt_id)
        with self._lock:
            if not path.exists():
                raise KeyError(prompt_id)
            path.unlink()
        logger.info(f"Deleted prompt {prompt_id!r}")

    def set_default(self, prompt_id: str) -> None:
        if not self.get(prompt_id):
            raise KeyError(prompt_id)
        with self._lock:
            self._write_json(self._settings_path(), {"default": prompt_id})

    # --- files ---------------------------------------------------------------

    def _prompt_path(self, prompt_id: str) -> Path:
        return self.directory / "prompts" / f"{prompt_id}.json"

    def _settings_path(self) -> Path:
        return self.directory / "settings.json"

    def _read_saved(self) -> Dict[str, Dict]:
        folder = self.directory / "prompts"
        if not folder.is_dir():
            return {}
        saved = {}
        for path in sorted(folder.glob("*.json")):
            pid = path.stem
            if pid in BUILTIN_ANSWER_PROMPTS:
                logger.warning(f"Ignoring {path}: built-in prompts can't be overridden")
                continue
            data = self._read_json(path)
            if PROMPT_ID_RE.match(pid) and isinstance(data.get("title"), str) and isinstance(data.get("text"), str):
                saved[pid] = data
            elif data:
                logger.warning(f"Ignoring malformed prompt file {path}")
        return saved

    @staticmethod
    def _read_json(path: Path) -> Dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.warning(f"Could not read {path}: {e}")
            return {}

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        """Write via a temp file + rename, so readers never see half a file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.chmod(tmp, 0o644)  # mkstemp creates 0600; keep it a normal readable file
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _validate(prompt_id: str, title: str, text: str) -> None:
    if not isinstance(prompt_id, str) or not PROMPT_ID_RE.match(prompt_id):
        raise ValueError(
            "id must be 1-40 characters: lowercase letters, digits, '-' or '_', "
            "starting with a letter or digit"
        )
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > MAX_TITLE_CHARS:
        raise ValueError(f"title must be 1-{MAX_TITLE_CHARS} characters")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"text must be 1-{MAX_TEXT_CHARS} characters")
