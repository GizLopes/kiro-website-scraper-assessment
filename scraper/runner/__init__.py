from .base_runner import BrowserAgentRunner, RunnerResult
from .mock_runner import MockRunner

__all__ = ["BrowserAgentRunner", "RunnerResult", "MockRunner"]

# BrowserUseRunner and AgentCoreRunner are imported lazily to avoid
# hard dependencies on optional packages (browser-use, boto3).
def get_runner(name: str) -> type:
    """
    Factory that returns a runner class by name.
    Supported names: "mock", "browseruse", "agentcore"
    """
    name = name.lower().strip()
    if name == "mock":
        return MockRunner
    if name == "browseruse":
        from .browseruse_runner import BrowserUseRunner
        return BrowserUseRunner
    if name == "agentcore":
        from .agentcore_runner import AgentCoreRunner
        return AgentCoreRunner
    raise ValueError(
        f"Unknown runner '{name}'. Choose from: mock, browseruse, agentcore"
    )
