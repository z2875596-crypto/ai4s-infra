"""Tool executor — validates, sandboxes, executes tools with full error handling."""

from __future__ import annotations

import time
from typing import Any

from ai4s.common.exceptions import ToolExecutionError
from ai4s.common.logging import get_logger
from ai4s.agent_runtime.tools.registry import ToolDefinition, ToolRegistry
from ai4s.agent_runtime.tools.sandbox import ExecutionSandbox, SandboxResult

logger = get_logger(__name__)


class ToolExecutor:
    """Safely executes tools via sandbox with input validation and chaining.

    Usage::

        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="run_python", description="Execute Python code",
            parameters={"type": "object", "properties": {"code": {"type": "string"}},
                        "required": ["code"]},
            handler=None, category="code",
        ))

        executor = ToolExecutor(registry, sandbox=ExecutionSandbox("gvisor"))
        result = await executor.execute("run_python", {"code": "print(1+1)"})
        # Or chain multiple calls:
        results = await executor.execute_chain([
            {"tool": "query_db", "arguments": {"sql": "SELECT ..."}},
            {"tool": "run_python", "arguments": {"code": "..."}},
        ])
    """

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: ExecutionSandbox | None = None,
        max_chain_depth: int = 10,
        result_cache_size: int = 1000,
    ) -> None:
        self._registry = registry
        self._sandbox = sandbox or ExecutionSandbox()
        self._max_chain_depth = max_chain_depth
        self._result_cache: dict[str, dict[str, Any]] = {}

    # -- single execution ---------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_sec: int | None = None,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        tool = self._registry.get(tool_name)
        if not tool:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")

        # Check cache
        cache_key = f"{tool_name}:{hash(frozenset(arguments.items()))}"
        if not bypass_cache and cache_key in self._result_cache:
            logger.debug("Cache hit for tool=%s", tool_name)
            return self._result_cache[cache_key]

        # Validate
        self._validate_arguments(tool, arguments)

        timeout = timeout_sec or tool.timeout_sec
        started = time.monotonic()

        try:
            if tool.requires_sandbox:
                command = self._build_sandbox_command(tool, arguments)
                sandbox_result = await self._sandbox.run(
                    command=command,
                    timeout_sec=timeout,
                    env=arguments.get("_env", {}),
                    memory_limit_mb=arguments.get("_memory_mb", 512),
                )
                result = {
                    "stdout": sandbox_result.stdout,
                    "stderr": sandbox_result.stderr,
                    "exit_code": sandbox_result.exit_code,
                    "artifacts": sandbox_result.artifacts,
                }
            else:
                result = await tool.handler(**arguments)

        except ToolExecutionError:
            raise
        except Exception as exc:
            logger.error("Tool '%s' execution failed: %s", tool_name, exc)
            raise ToolExecutionError(f"Tool '{tool_name}' failed: {exc}") from exc

        elapsed = round(time.monotonic() - started, 3)
        output = {
            "tool": tool_name,
            "result": result,
            "elapsed_sec": elapsed,
            "cached": False,
        }

        # Cache result (up to _max_cache_size entries if configured)
        max_size = getattr(self, '_max_cache_size', 0)
        if max_size == 0 or len(self._result_cache) < max_size:
            self._result_cache[cache_key] = output

        logger.info("Tool %s completed in %.3fs (exit=%s)",
                     tool_name, elapsed, result.get("exit_code", "N/A"))
        return output

    # -- chain execution ----------------------------------------------------

    async def execute_chain(
        self,
        steps: list[dict[str, Any]],
        stop_on_error: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a chain of tool calls.

        Each step: {"tool": "tool_name", "arguments": {...}}
        Output from previous steps is merged into arguments via $_prev.

        Example::
            steps = [
                {"tool": "read_file", "arguments": {"path": "/data/input.csv"}},
                {"tool": "run_python", "arguments": {"code": "...process $_prev.stdout..."}},
            ]
        """
        if len(steps) > self._max_chain_depth:
            raise ToolExecutionError(f"Chain depth {len(steps)} exceeds max {self._max_chain_depth}")

        results: list[dict[str, Any]] = []
        ctx: dict[str, Any] = {}

        for i, step in enumerate(steps):
            args = {**step.get("arguments", {})}
            args["_context"] = ctx

            try:
                result = await self.execute(step["tool"], args)
                results.append(result)
                ctx = {**ctx, **result.get("result", {})}
            except ToolExecutionError:
                if stop_on_error:
                    raise
                results.append({"tool": step["tool"], "error": "failed", "step": i})
                break

        return results

    # -- validation ---------------------------------------------------------

    def _validate_arguments(self, tool: ToolDefinition, args: dict[str, Any]) -> None:
        params = tool.parameters
        required = params.get("required", [])
        properties = params.get("properties", {})

        for param in required:
            if param not in args:
                raise ToolExecutionError(
                    f"Tool '{tool.name}' missing required parameter: '{param}'"
                )

        # Type-check against JSON Schema properties
        for param, value in args.items():
            if param in properties:
                prop = properties[param]
                expected_type = prop.get("type")
                if expected_type == "string" and not isinstance(value, str):
                    raise ToolExecutionError(
                        f"Tool '{tool.name}' param '{param}': expected string, got {type(value).__name__}"
                    )
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    raise ToolExecutionError(
                        f"Tool '{tool.name}' param '{param}': expected number, got {type(value).__name__}"
                    )
                elif expected_type == "integer" and not isinstance(value, int):
                    raise ToolExecutionError(
                        f"Tool '{tool.name}' param '{param}': expected integer, got {type(value).__name__}"
                    )
                elif expected_type == "boolean" and not isinstance(value, bool):
                    raise ToolExecutionError(
                        f"Tool '{tool.name}' param '{param}': expected boolean, got {type(value).__name__}"
                    )

    @staticmethod
    def _build_sandbox_command(tool: ToolDefinition, args: dict[str, Any]) -> list[str]:
        clean_args = {k: v for k, v in args.items() if not k.startswith("_")}
        return ["python3", "-m", f"ai4s.agent_runtime.tools.builtins.{tool.name}"] + [
            f"--{k}={v}" for k, v in clean_args.items()
        ]
