"""
Base runner interface

All concrete runners must inherit BrowserAgentRunner and implement run().
The pipeline (main.py) only talks to this interface, making it trivial to
swap BrowserUse → AgentCore → any future runtime without touching the rest
of the codebase.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunnerResult:
    """
    Container for the output of a single runner execution.

    Attributes:
        raw_items   : List of raw dicts as returned / parsed from the LLM.
        site        : Site identifier used for this run.
        duration_s  : Wall-clock seconds the run took.
        error       : Non-None if the run failed entirely.
        llm_tokens  : Approximate token count if the runtime exposes it.
    """
    raw_items: List[Dict[str, Any]] = field(default_factory=list)
    site: str = ""
    duration_s: float = 0.0
    error: Optional[str] = None
    llm_tokens: Optional[int] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def __repr__(self) -> str:
        status = "ok" if self.success else f"error={self.error!r}"
        return (
            f"RunnerResult(site={self.site!r}, items={len(self.raw_items)}, "
            f"duration={self.duration_s:.1f}s, {status})"
        )


class BrowserAgentRunner(ABC):
    """
    Abstract base class for all browser-agent runners.

    Subclasses must implement:
        run(prompt, site) -> RunnerResult

    They may optionally override:
        close()           — release browser / session resources
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Accept arbitrary keyword arguments so subclass configs
        (model name, timeout, API keys…) can be passed uniformly.
        """
        self._config: Dict[str, Any] = kwargs

    # ── Contract ──────────────────────────────────────────────────────────

    @abstractmethod
    def run(self, prompt: str, site: str) -> RunnerResult:
        """
        Send `prompt` to the LLM browser agent and return a RunnerResult
        whose raw_items is a list of dicts (one per product).

        Implementations must:
        - Set result.site to the `site` argument.
        - Set result.duration_s to elapsed wall-clock time.
        - On total failure, return a RunnerResult with error set (do not raise).
        - Parse the LLM response into a Python list[dict] via _parse_json_response().
        """

    def close(self) -> None:
        """Release any browser session or network resources. No-op by default."""

    # ── Context manager support ───────────────────────────────────────────

    def __enter__(self) -> "BrowserAgentRunner":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Shared utilities ──────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(text: str) -> List[Dict[str, Any]]:
        """
        Extract a JSON array from the LLM's raw text response.

        Handles common LLM formatting artefacts:
        - Markdown code fences (```json ... ```)
        - Leading / trailing prose before / after the array
        - Single object responses (wrapped into a list automatically)

        Returns an empty list if parsing fails entirely.
        """
        if not text:
            return []

        # 1) Strip markdown fences
        text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```\s*$", "", text, flags=re.IGNORECASE).strip()

        # 2) Find the outermost [ ... ] or { ... }
        array_match = re.search(r"(\[.*\])", text, re.DOTALL)
        if array_match:
            candidate = array_match.group(1)
        else:
            # Maybe the LLM returned a single object
            obj_match = re.search(r"(\{.*\})", text, re.DOTALL)
            if obj_match:
                candidate = f"[{obj_match.group(1)}]"
            else:
                return []

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            # Last resort: try to fix truncated JSON
            try:
                parsed = json.loads(_attempt_json_repair(candidate))
            except Exception:
                return []

        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
        return []

    @staticmethod
    def _elapsed(start: float) -> float:
        return round(time.monotonic() - start, 2)


def _attempt_json_repair(text: str) -> str:
    """
    Very basic JSON repair: close unclosed brackets/braces.
    Only intended as a last-resort fallback.
    """
    stack = []
    pairs = {"{": "}", "[": "]"}
    closing = set(pairs.values())

    for ch in text:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closing:
            if stack and stack[-1] == ch:
                stack.pop()

    return text + "".join(reversed(stack))
