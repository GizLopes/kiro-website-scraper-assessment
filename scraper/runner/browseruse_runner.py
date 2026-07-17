"""
BrowserUse Runner

Concrete runner that uses the `browser-use` library to drive a real
Chromium instance controlled by an LLM hosted on Amazon Bedrock.

Install:
    pip install "browser-use[aws]" boto3

Required AWS configuration:
    AWS_PROFILE
    AWS_DEFAULT_REGION
    BEDROCK_MODEL_ID

Configuration kwargs:
    llm_provider  (str)   : Must be "bedrock"
    model         (str)   : Bedrock model ID or inference profile ID
    headless      (bool)  : Run browser headless
    timeout       (int)   : Maximum seconds per run
    max_actions   (int)   : Maximum browser steps
    temperature   (float) : LLM temperature
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from .base_runner import BrowserAgentRunner, RunnerResult

import boto3
from botocore.config import Config
from browser_use.llm import ChatAWSBedrock

def _import_browser_use():
    try:
        from browser_use import Agent, BrowserProfile
        return Agent, BrowserProfile
    except ImportError as exc:
        raise ImportError(
            "The 'browser-use' package is required.\n"
            'Install it with: pip install "browser-use[aws]"'
        ) from exc

class ChatAWSBedrockExtendedTimeout(ChatAWSBedrock):
    """
    ChatAWSBedrock with an explicitly configured boto3 client.

    The browser-use version installed locally does not expose a client or
    botocore Config parameter, so the client creation must be overridden.
    """

    def _get_client(self):
        region = (
            self.aws_region
            or os.getenv("AWS_DEFAULT_REGION")
            or os.getenv("AWS_REGION")
            or "us-east-1"
        )

        profile_name = os.getenv("AWS_PROFILE")

        if profile_name:
            session = boto3.Session(
                profile_name=profile_name,
                region_name=region,
            )
        else:
            session = boto3.Session(region_name=region)

        return session.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                connect_timeout=60,
                read_timeout=3600,
                retries={
                    "mode": "standard",
                    "max_attempts": 3,
                },
            ),
        )

def _build_llm(provider: str, model: str, temperature: float):
    provider = provider.lower()

    if provider != "bedrock":
        raise ValueError(
            f"Unsupported LLM provider '{provider}'. Use 'bedrock'."
        )

    if not model:
        raise EnvironmentError(
            "No Bedrock model was provided. Set BEDROCK_MODEL_ID "
            "or pass --model."
        )

    region = (
        os.getenv("AWS_DEFAULT_REGION")
        or os.getenv("AWS_REGION")
        or "us-east-1"
    )

    print(f"[BEDROCK] Model: {model}")
    print(f"[BEDROCK] Region: {region}")
    print("[BEDROCK] Read timeout: 3600 seconds")

    return ChatAWSBedrockExtendedTimeout(
        model=model,
        aws_region=region,
        temperature=temperature,
        aws_sso_auth=bool(os.getenv("AWS_PROFILE")),
        max_tokens=4096,
    )

async def _run_async(self, prompt: str) -> str:
    Agent, BrowserProfile = _import_browser_use()

    if self._llm is None:
        self._llm = _build_llm(
            self._provider,
            self._model,
            self._temperature,
        )

    agent = Agent(
        task=prompt,
        llm=self._llm,
        use_vision=True,
        browser_profile=BrowserProfile(
            headless=self._headless,
        ),
    )

    try:
        result = await asyncio.wait_for(
            agent.run(max_steps=self._max_actions),
            timeout=self._timeout,
        )

        if hasattr(result, "final_result"):
            return str(result.final_result() or "")

        return str(result)

    finally:
        await _close_agent_browser(agent)


class BrowserUseRunner(BrowserAgentRunner):
    """
    Runs an extraction prompt using browser-use and Amazon Bedrock.

    Browser Use controls a Chromium browser while the Bedrock-hosted LLM
    decides which browser actions to execute.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self._provider = kwargs.get("llm_provider", "bedrock")

        self._model = (
            kwargs.get("model")
            or os.getenv("BEDROCK_MODEL_ID")
        )

        self._headless = bool(kwargs.get("headless", True))
        self._timeout = int(kwargs.get("timeout", 3600))
        self._max_actions = int(kwargs.get("max_actions", 200))
        self._temperature = float(kwargs.get("temperature", 0.0))
        self._llm = None

    def run(self, prompt: str, site: str) -> RunnerResult:
        start = time.monotonic()

        try:
            raw_text = asyncio.run(self._run_async(prompt))
            items = self._parse_json_response(raw_text)

            return RunnerResult(
                raw_items=items,
                site=site,
                duration_s=self._elapsed(start),
            )

        except Exception as exc:
            return RunnerResult(
                raw_items=[],
                site=site,
                duration_s=self._elapsed(start),
                error=str(exc),
            )

    async def _run_async(self, prompt: str) -> str:
        Agent, BrowserProfile = _import_browser_use()

        if self._llm is None:
            self._llm = _build_llm(
                self._provider,
                self._model,
                self._temperature,
            )

        agent = Agent(
            task=prompt,
            llm=self._llm,
            use_vision=True,
            browser_profile=BrowserProfile(
                headless=self._headless,
            ),
        )

        result = await asyncio.wait_for(
            agent.run(max_steps=self._max_actions),
            timeout=self._timeout,
        )

        if hasattr(result, "final_result"):
            return str(result.final_result() or "")

        return str(result)