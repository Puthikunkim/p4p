from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from vcore.core import schema as vschema
from vcore.core.models import Rule

log = logging.getLogger(__name__)

_RULE_GLOB = ("*.yaml", "*.yml", "*.json")


@dataclass
class RuleLoadError:
    path: str
    reason: str


class RuleRegistry:
    """Loads and hot-reloads declarative rule files from a directory.

    Each file is validated against the Rule Grammar contract independently —
    a bad file is skipped and recorded as an error; all other rules are
    unaffected.
    """

    def __init__(self, rules_dir: Path) -> None:
        self._rules_dir = Path(rules_dir)
        self._rules: dict[str, Rule] = {}
        self._path_to_id: dict[Path, str] = {}
        self._errors: list[RuleLoadError] = []
        self._observer: Any = None  # watchdog Observer; Any avoids mypy valid-type issue
        self._lock = threading.RLock()  # guards _rules and _path_to_id (watchdog vs. API thread)

    # ── public interface ──────────────────────────────────────────────────────

    def load_all(self) -> None:
        """Load every rule file in rules_dir. Safe to call multiple times."""
        self._errors.clear()
        for glob in _RULE_GLOB:
            for path in self._rules_dir.glob(glob):
                self._load_file(path)

    def start_watching(
        self,
        on_change: Callable[[], Coroutine[Any, Any, None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Start a watchdog observer; call *on_change* coroutine on any change."""
        handler = _ChangeHandler(self, on_change, loop)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._rules_dir), recursive=False)
        self._observer.start()
        log.info("registry: watching %s", self._rules_dir)

    def stop_watching(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    @property
    def rules(self) -> dict[str, Rule]:
        with self._lock:
            return dict(self._rules)

    @property
    def errors(self) -> list[RuleLoadError]:
        with self._lock:
            return list(self._errors)

    # ── internal ──────────────────────────────────────────────────────────────

    def _load_file(self, path: Path) -> None:
        try:
            text = path.read_text()
            raw: dict[str, Any] = yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else __import__("json").loads(text)
            vschema.validate(raw, "rule_grammar")
            rule = Rule.model_validate(raw)
        except Exception as exc:
            with self._lock:
                self._errors = [e for e in self._errors if e.path != str(path)]
                self._errors.append(RuleLoadError(path=str(path), reason=str(exc)))
            log.warning("registry: skipped %s — %s", path.name, exc)
            return

        with self._lock:
            old_id = self._path_to_id.pop(path, None)
            if old_id and old_id != rule.id:
                self._rules.pop(old_id, None)
            self._errors = [e for e in self._errors if e.path != str(path)]
            self._rules[rule.id] = rule
            self._path_to_id[path] = rule.id
        log.info("registry: loaded rule %r from %s", rule.id, path.name)

    def _remove_file(self, path: Path) -> None:
        with self._lock:
            rule_id = self._path_to_id.pop(path, None)
            if rule_id:
                self._rules.pop(rule_id, None)
        if rule_id:
            log.info("registry: removed rule %r (file deleted)", rule_id)


class _ChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        registry: RuleRegistry,
        on_change: Callable[[], Coroutine[Any, Any, None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._registry = registry
        self._on_change = on_change
        self._loop = loop

    def _is_rule_file(self, path: str) -> bool:
        return Path(path).suffix in (".yaml", ".yml", ".json")

    def _dispatch_change(self, path: str, *, deleted: bool = False) -> None:
        p = Path(path)
        if deleted:
            self._registry._remove_file(p)
        else:
            self._registry._load_file(p)
        asyncio.run_coroutine_threadsafe(self._on_change(), self._loop)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_rule_file(str(event.src_path)):
            self._dispatch_change(str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_rule_file(str(event.src_path)):
            self._dispatch_change(str(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_rule_file(str(event.src_path)):
            self._dispatch_change(str(event.src_path), deleted=True)
