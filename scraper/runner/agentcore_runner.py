"""
AgentCore Runner

Concrete runner that uses the AWS BedrockAgentCore (or Bedrock Converse API)
to drive a browser agent in the cloud.

NOTE:
    This runner calls the Bedrock *Converse* API directly (text-in / text-out).
    It sends the extraction prompt as a user message and expects a JSON array
    back. For full agentic browser control via AWS, swap _call_bedrock() for
    the BedrockAgentCore invoke_agent() call once you have an AgentCore agent
    deployed and an agentId / agentAliasId.
"""
from __future__ import annotations

import os
import time
from typing import Any

from .base_runner import BrowserAgentRunner, RunnerResult

# ── Lazy import (boto3 is optional) ───────────────────────────────────────────

def _get_bedrock_client(region: str):
    """Return a boto3 bedrock-runtime client, raising a clear error if boto3 is absent."""
    try:
        import boto3  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "The 'boto3' package is required for AgentCoreRunner.\n"
            "Install it with:  pip install boto3"
        ) from exc
    return boto3.client("bedrock-runtime", region_name=region)


class AgentCoreRunner(BrowserAgentRunner):
    """
    Calls the AWS Bedrock Converse API with the extraction prompt and parses
    the JSON array from the model's text response.

    This provides a cloud-native path for extraction without requiring a local
    browser binary. For pure agentic browsing, replace _call_bedrock() with
    the BedrockAgentCore invoke_agent() once an agent is provisioned.
    """

    # Default Bedrock model — Claude Sonnet 4.6 via cross-region inference
    _DEFAULT_MODEL = "anthropic.claude-sonnet-4-6"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model_id   = kwargs.get("model_id") or os.getenv(
            "BEDROCK_MODEL_ID", self._DEFAULT_MODEL
        )
        self._region     = kwargs.get("region") or os.getenv(
            "AWS_DEFAULT_REGION", "us-east-1"
        )
        self._max_tokens = int(kwargs.get("max_tokens", 8192))
        self._temperature = float(kwargs.get("temperature", 0.0))
        self._timeout    = int(kwargs.get("timeout", 600))
        self._client     = None  # built lazily on first run

    # ── BrowserAgentRunner contract ───────────────────────────────────────

    def run(self, prompt: str, site: str) -> RunnerResult:
        start = time.monotonic()
        try:
            raw_text = self._call_bedrock(prompt)
            items    = self._parse_json_response(raw_text)
            return RunnerResult(
                raw_items=items,
                site=site,
                duration_s=self._elapsed(start),
            )
        except Exception as exc:  # noqa: BLE001
            return RunnerResult(
                raw_items=[],
                site=site,
                duration_s=self._elapsed(start),
                error=str(exc),
            )

    def close(self) -> None:
        """Boto3 clients don't need explicit teardown; kept for interface parity."""
        self._client = None

    # ── Internal ──────────────────────────────────────────────────────────

    def _call_bedrock(self, prompt: str) -> str:
        """
        Send the prompt to Bedrock Converse API and return the raw text response.

        The Converse API is model-agnostic and handles the correct request
        format for each provider (Anthropic, Amazon, etc.) automatically.
        """
        if self._client is None:
            self._client = _get_bedrock_client(self._region)

        response = self._client.converse(
            modelId=self._model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": self._max_tokens,
                "temperature": self._temperature,
            },
        )

        # Converse response shape: output.message.content[0].text
        try:
            return response["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Bedrock Converse response structure: {exc}\n"
                f"Full response keys: {list(response.keys())}"
            ) from exc

    # ── Repr ──────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"AgentCoreRunner(model={self._model_id!r}, "
            f"region={self._region!r}, "
            f"max_tokens={self._max_tokens})"
        )
