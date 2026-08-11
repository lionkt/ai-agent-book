#!/usr/bin/env python3
"""Extract an auditable, human-readable view of Experiment 1-1 evidence.

The canonical artifact is intentionally not copied into ``learning_notes``.
This script keeps the notes reproducible while leaving the signed evidence in
``chapter1/context/validation`` as the single source of truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_INPUT = REPO_ROOT / "chapter1/context/validation/latest.json"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def fenced_json(value: Any) -> str:
    # Four backticks remain valid even when a model message contains a normal
    # three-backtick Markdown fence.
    return f"````json\n{json_text(value)}\n````"


def source_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def response_message(turn: dict[str, Any]) -> dict[str, Any]:
    choices = turn.get("response", {}).get("choices") or []
    return (choices[0].get("message") or {}) if choices else {}


def response_finish_reason(turn: dict[str, Any]) -> str | None:
    choices = turn.get("response", {}).get("choices") or []
    return choices[0].get("finish_reason") if choices else None


def arm_usage(arm: dict[str, Any]) -> dict[str, int]:
    usage: Counter[str] = Counter()
    for turn in arm.get("api_turns", []):
        current = turn.get("response", {}).get("usage") or {}
        prompt = int(current.get("prompt_tokens") or current.get("input_tokens") or 0)
        completion = int(
            current.get("completion_tokens") or current.get("output_tokens") or 0
        )
        prompt_details = current.get("prompt_tokens_details") or current.get(
            "input_tokens_details"
        ) or {}
        completion_details = current.get("completion_tokens_details") or current.get(
            "output_tokens_details"
        ) or {}
        usage["prompt_tokens"] += prompt
        usage["completion_tokens"] += completion
        usage["total_tokens"] += int(current.get("total_tokens") or prompt + completion)
        usage["cached_prompt_tokens"] += int(prompt_details.get("cached_tokens") or 0)
        usage["reasoning_tokens"] += int(completion_details.get("reasoning_tokens") or 0)
    return dict(usage)


def normalized_arm(arm: dict[str, Any]) -> dict[str, Any]:
    behavior = arm.get("behavior", {})
    completed = bool(arm.get("completed", arm.get("success", False)))
    task_success = bool(
        arm.get("task_success", behavior.get("canonical_answer_correct", False))
    )
    signatures = arm.get("tool_call_signatures", [])
    repeated = arm.get("repeated_tool_calls")
    if repeated is None:
        repeated = len(signatures) - len(set(signatures))
    return {
        "mode": arm.get("mode"),
        "completed": completed,
        "canonical_answer_correct": task_success,
        "iterations": arm.get("iterations", 0),
        "elapsed_seconds": arm.get("elapsed_seconds"),
        "tool_action_count": len(arm.get("tool_calls", [])),
        "repeated_tool_actions": repeated,
        "hit_iteration_ceiling": bool(behavior.get("hit_iteration_ceiling", False)),
        "final_answer": arm.get("final_answer"),
        "tool_call_sequence": [
            {
                "tool_name": call.get("tool_name"),
                "arguments": call.get("arguments"),
                "result": call.get("result"),
            }
            for call in arm.get("tool_calls", [])
        ],
        "request_role_vectors": arm.get("context_contract", {}).get("request_roles", []),
        "context_contract": arm.get("context_contract", {}),
        "usage": arm_usage(arm),
    }


def build_results(evidence: dict[str, Any], source: Path, digest: str) -> str:
    result = {
        "generated_from": {
            "path": source_label(source),
            "sha256": digest,
            "schema_version": evidence.get("schema_version"),
            "created_at": evidence.get("created_at"),
        },
        "run": {
            "experiment_id": evidence.get("experiment_id"),
            "evidence_mode": evidence.get("evidence_mode"),
            "canonical_source": evidence.get("canonical_source"),
            "command": evidence.get("command"),
            "host": evidence.get("host"),
            "dependencies": evidence.get("dependencies"),
            "repository": evidence.get("repository"),
            "expected_numbers": evidence.get("expected_numbers"),
        },
        "metric_definitions": {
            "completed": (
                "A non-empty terminal text response was observed; this is not correctness."
            ),
            "canonical_answer_correct": (
                "The final answer contains both canonical numeric strings after removing commas, "
                "dollar signs, and spaces."
            ),
            "repeated_tool_actions": (
                "Total tool calls minus unique (tool name, canonical JSON arguments) signatures."
            ),
            "context_contract": (
                "Checks the payload actually sent to the provider, not only the CLI flag."
            ),
        },
        "arms": [normalized_arm(arm) for arm in evidence.get("arms", [])],
        "analysis": evidence.get("analysis", {}),
    }
    return json_text(result) + "\n"


def build_traces(evidence: dict[str, Any], source: Path, digest: str) -> str:
    arms = evidence.get("arms", [])
    if not arms or not arms[0].get("api_turns"):
        raise ValueError("Evidence has no API turns")

    first_request = arms[0]["api_turns"][0]["request"]
    shared_messages = first_request.get("messages", [])
    shared_system = next((m for m in shared_messages if m.get("role") == "system"), None)
    shared_user = next((m for m in shared_messages if m.get("role") == "user"), None)
    shared_tools = first_request.get("tools", [])

    lines = [
        "# 实验 1-1：完整逐轮输入输出",
        "",
        "> 这是从已验收 evidence 自动生成的审计视图，不是人工重构的示例。",
        "> `request.messages`、模型 `response.message`、usage、工具参数和工具执行结果均保留原值；",
        "> 完整 HTTP 响应封套、时间戳和 provider 元数据仍以 canonical evidence 为准。",
        "",
        "## 证据身份",
        "",
        f"- 来源：`{source_label(source)}`",
        f"- SHA-256：`{digest}`",
        f"- 运行时间：`{evidence.get('created_at')}`",
        f"- 模型：`{arms[0].get('provider')} / {arms[0].get('model')}`",
        "",
        "## 所有实验组共享的静态输入",
        "",
        "### System message",
        "",
        fenced_json(shared_system),
        "",
        "### User message",
        "",
        fenced_json(shared_user),
        "",
        "### 完整工具定义",
        "",
        fenced_json(shared_tools),
        "",
        "后文每轮若标记“共享工具定义”，指的就是上面这份完全相同的 `tools` 数组；",
        "`no_tool_calls` 组则不发送 `tools` 和 `tool_choice`。",
        "",
    ]

    for arm in arms:
        mode = arm.get("mode")
        lines.extend(
            [
                f"## `{mode}`",
                "",
                "### 实际上下文契约",
                "",
                fenced_json(arm.get("context_contract", {})),
                "",
            ]
        )
        tool_cursor = 0
        executed_calls = arm.get("tool_calls", [])
        for turn in arm.get("api_turns", []):
            iteration = turn.get("iteration")
            request = turn.get("request", {})
            response = turn.get("response", {})
            message = response_message(turn)
            model_calls = message.get("tool_calls") or []
            request_meta = {
                key: request.get(key)
                for key in ("model", "temperature", "max_tokens", "tool_choice", "thinking")
                if key in request
            }
            request_meta["tools"] = (
                "shared_tool_definitions" if request.get("tools") else "absent"
            )
            response_meta = {
                "id": response.get("id"),
                "model": response.get("model"),
                "finish_reason": response_finish_reason(turn),
            }
            lines.extend(
                [
                    f"### 第 {iteration} 轮",
                    "",
                    "#### 模型输入：请求参数",
                    "",
                    fenced_json(request_meta),
                    "",
                    "#### 模型输入：`messages`",
                    "",
                    fenced_json(request.get("messages", [])),
                    "",
                    "#### 模型输出：响应元数据",
                    "",
                    fenced_json(response_meta),
                    "",
                    "#### 模型输出：`assistant` message",
                    "",
                    fenced_json(message),
                    "",
                    "#### 本轮 token usage",
                    "",
                    fenced_json(response.get("usage") or {}),
                    "",
                ]
            )
            if model_calls:
                count = len(model_calls)
                tool_slice = executed_calls[tool_cursor : tool_cursor + count]
                tool_cursor += count
                lines.extend(
                    [
                        "#### Harness 执行工具后的真实结果",
                        "",
                        fenced_json(
                            [
                                {
                                    "tool_name": call.get("tool_name"),
                                    "arguments": call.get("arguments"),
                                    "result": call.get("result"),
                                }
                                for call in tool_slice
                            ]
                        ),
                        "",
                    ]
                )

        if tool_cursor != len(executed_calls):
            raise ValueError(
                f"{mode}: traced {tool_cursor} tool calls but evidence has "
                f"{len(executed_calls)}"
            )

        lines.extend(
            [
                "### 该组终局",
                "",
                fenced_json(normalized_arm(arm)),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        return path.exists() and path.read_text(encoding="utf-8") == content
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source = args.input.resolve()
    raw = source.read_bytes()
    evidence = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        args.output_dir / "results.json": build_results(evidence, source, digest),
        args.output_dir / "turn-traces.md": build_traces(evidence, source, digest),
    }
    failed = []
    for path, content in outputs.items():
        if not write_or_check(path, content, args.check):
            failed.append(path)

    if failed:
        for path in failed:
            print(f"out of date: {path}")
        return 1
    for path in outputs:
        print(f"{'verified' if args.check else 'wrote'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
