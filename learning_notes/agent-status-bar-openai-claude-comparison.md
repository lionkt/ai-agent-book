# Agent 状态栏：OpenAI 与 Claude 的实现思路对比

> 文档核对时间：2026-08-10

## 1. 问题

OpenAI 和 Claude 是否已经把“Agent 状态栏”实现成一种标准协议？两边分别提供了哪些相关能力，又可以怎样实现一块供 Agent 使用的状态小黑板？

## 2. 核心结论

OpenAI 和 Anthropic 都没有定义跨厂商通用的 `agent_status` 消息类型，例如：

```json
{
  "type": "agent_status",
  "progress": "2/4",
  "next_step": "run tests"
}
```

行业目前收敛的是架构思路，而不是协议字段：

```text
运行时事件
  工具结果、任务更新、环境变化、资源计数
                    ↓
Harness 维护状态
  内存、文件、数据库、Session / Conversation
                    ↓
Harness 生成状态快照
  当前目标、进度、下一步、最近异常、剩余额度
                    ↓
把快照暴露给模型
  新消息、动态指令、Tool Result 或按需查询工具
```

因此要区分三个层级：

| 层级 | 主要职责 | 标准化程度 |
| --- | --- | --- |
| 模型 API | 传输消息、工具调用和工具结果 | 各厂商内部标准化 |
| Agent SDK | 维护 run、session、history、interruptions 等运行状态 | 各家实现不同 |
| Agent 产品 / Harness | Todo、进度、环境提醒、状态注入和 UI 展示 | 产品专用 |

“Agent 状态栏”主要属于第三层。API 和 SDK提供基础设施，Harness 决定具体记录什么、如何压缩，以及何时让模型看到。

## 3. OpenAI：提供通用状态原语，由应用完成状态暴露

### 3.1 API 层：Conversation State 不是 Agent Status

OpenAI Responses API 支持多种对话延续方式：

- 应用自己保存和重放 history；
- 使用 Session 保存持久上下文；
- 使用 Conversations API 的 `conversationId`；
- 使用 Responses API 的 `previousResponseId` 延续上一轮。

这些能力解决的是：

```text
下一次请求如何接着上一次请求继续
```

它们没有规定：

```text
当前任务进度应该有哪些字段
哪些状态必须展示给模型
状态快照应该以什么格式注入
```

也就是说，Conversation State 保存的是对话连续性，不等于已经替应用生成了 Agent 状态栏。

### 3.2 Agents SDK 层：Run State 用于续跑和恢复

OpenAI Agents SDK 的结果对象除了最终回答，还可以携带：

- 可重放的 history；
- 当前或最后负责执行的 Agent；
- 上一个 Response ID；
- pending approvals / interruptions；
- 可序列化并恢复的 run state；
- 更细粒度的工具、handoff、guardrail 和 usage 记录。

这些数据非常适合作为状态栏的原材料，但仍然不是模型自动可见的“HUD”。应用需要选出决策真正需要的部分，生成一份短快照，再把它加入下一次模型输入。

### 3.3 一种 OpenAI 风格的实现

应用首先在运行时维护结构化状态：

```python
runtime_state = {
    "goal": "修复登录超时问题",
    "completed_steps": 2,
    "total_steps": 4,
    "next_step": "运行回归测试",
    "last_error": "test_refresh_token failed",
    "remaining_tool_calls": 18,
}
```

Harness 在下一次调用模型之前，把它渲染为紧凑快照：

```xml
<agent_status>
  <goal>修复登录超时问题</goal>
  <progress>2/4</progress>
  <next_step>运行回归测试</next_step>
  <last_error>test_refresh_token failed</last_error>
  <remaining_tool_calls>18</remaining_tool_calls>
</agent_status>
```

然后根据状态的使用方式选择暴露通道：

```text
每轮都必须看见       → 作为下一次模型输入中的状态消息
只在模型需要时读取   → 暴露 get_runtime_status 工具
只影响某个工具调用   → 作为该工具的 Tool Result 或错误反馈
只供 Harness 使用    → 保留在本地 Run State，不发送给模型
```

可以用概念伪代码表示：

```python
status_view = render_status(runtime_state)

next_input = [
    *conversation_history,
    {
        "role": "developer",
        "content": status_view,
    },
]
```

具体可用角色和 input item 结构应以所使用的 OpenAI API / SDK 版本为准；这里表达的是“把新状态追加到模型输入”的架构，而不是定义新的标准消息类型。

### 3.4 OpenAI 路线的特点

优点：

- 状态模型完全由应用定义，适合自定义工作流；
- history、session、conversation 和 run state 的持久化选择较丰富；
- 可以精确区分“只供代码使用的本地状态”和“需要模型看到的状态”。

代价：

- 开发者需要自己设计状态 schema、聚合逻辑和注入策略；
- Run State 并不会自动变成模型可见状态；
- 如果每轮塞入过多状态，会重新制造上下文膨胀和陈旧状态冲突。

## 4. Claude：API 提供动态注入通道，Claude Code 提供 Task 与 Hooks

### 4.1 Claude API：Mid-conversation System Message

Claude API 提供 mid-conversation system message：应用可以在会话进行到中途时，向 `messages` 末尾追加一条 `role: "system"` 的消息，而不必回头修改顶层 `system` 字段。

这非常适合作为状态栏的“主动暴露通道”。Anthropic 官方给出的适用状态包括：

- 文件系统发生变化；
- 用户切换了 auto-approve 等运行模式；
- 可用工具发生变化；
- session deadline 或剩余 token budget 发生变化。

概念上可以写成：

```json
{
  "role": "system",
  "content": "当前任务完成 2/4；下一步运行回归测试；剩余工具调用 18 次。"
}
```

它与修改顶层 system prompt 的区别是：

```text
修改顶层 system：改变请求开头，变动点之后的缓存无法复用
追加中途 system：旧历史保持不变，只计算新增状态消息
```

该能力是否可用与具体 Claude 模型和 API 版本有关，使用时必须检查官方支持矩阵。

### 4.2 Claude Code：Task 工具维护任务进度

Claude Code 提供结构化 Task 工具：

- `TaskCreate`：创建任务；
- `TaskUpdate`：更新任务状态、依赖和详细信息；
- `TaskGet`：读取某个任务；
- `TaskList`：读取完整任务列表。

Task 的常见状态包括：

```text
pending → in_progress → completed
```

这一层解决的是“小黑板的数据结构与更新协议”。它比让模型自由编辑 `TODO.md` 更容易校验，也更适合 UI 实时展示。

但 Task List 只覆盖状态栏的一部分：

```text
Task List：任务有哪些、分别做到哪里

完整 Agent Status：
任务进度 + 当前环境 + 最近异常 + 资源额度 + 权限 / 模式变化
```

### 4.3 Claude Code Hooks：把环境状态主动注入上下文

Claude Code Hooks 的 `additionalContext` 可以把一段运行时信息送进 Claude 的上下文。Claude Code 会把它包装成 system reminder，并插入 hook 触发的位置。

适合注入的信息包括：

- 当前 Git branch 或部署目标；
- 当前 feature flags；
- 刚刚运行的工具产生的环境变化；
- CI 结果；
- 当前目录的特殊规则。

一种典型流程是：

```text
PostToolUse Hook
        ↓
读取最新运行时状态
        ↓
返回 additionalContext
        ↓
Claude Code 插入 system reminder
        ↓
Claude 在下一次模型请求中看到最新状态
```

因此，Claude 路线已经提供了比较完整的组合：

```text
Task Tools             → 维护任务状态
Hooks                  → 监听运行时事件
additionalContext      → 向模型暴露状态
Terminal Status Area   → 向用户展示状态
```

这些仍然是 Claude Code / Claude Agent SDK 的产品约定，不是跨厂商 Agent Status 协议。

## 5. 简单对比

| 维度 | OpenAI | Claude / Claude Code |
| --- | --- | --- |
| 是否有统一 `agent_status` 类型 | 没有 | 没有 |
| 对话延续 | history、Session、Conversation、previous response | Messages history、session / transcript 等产品机制 |
| 运行状态原语 | result、history、interruptions、resumable state | Task Tools、transcript、hooks 等 |
| 状态存储 | 应用内存、Session、Conversation、数据库 | Task state、session transcript、文件或应用自定义存储 |
| 主动暴露给模型 | 应用把快照加入下一次 input / instructions / tool result | mid-conversation system message 或 Hook `additionalContext` |
| 按需读取 | 自定义 `get_runtime_status` Tool | `TaskList` / `TaskGet` 或自定义 Tool |
| UI 展示 | 取决于 Codex、ChatKit或应用自身 | Claude Code 内置 Task / status area 更直接 |
| 自定义自由度 | 高，偏基础设施和应用编排 | API 也可自定义；Claude Code 提供较多开箱即用组件 |
| 主要风险 | 本地状态没有正确暴露给模型 | Task 状态与注入状态可能不同步或变陈旧 |

可以把两条路线概括为：

```text
OpenAI：
提供 conversation/run state 和续跑基础设施，应用决定怎样生成并注入 HUD。

Claude：
Claude API 提供更直接的中途系统状态注入通道；
Claude Code 再提供 Task、Hooks 和 UI，形成产品级状态追踪。
```

这个区别不是绝对的。两家都允许开发者自行维护状态和追加上下文，差别主要在于当前公开 API / SDK 提供了多少开箱即用的状态管理组件。

## 6. 一个跨厂商的最小实现

不依赖特定厂商时，可以自行定义一个小型状态对象：

```python
from dataclasses import dataclass


@dataclass
class AgentStatus:
    goal: str
    completed_steps: int
    total_steps: int
    next_step: str | None
    last_error: str | None
    remaining_tool_calls: int
```

每次工具执行后更新状态：

```text
tool result
    ↓
reducer 更新 AgentStatus
    ↓
只保留当前快照，不在对象中堆积完整日志
```

调用模型前再决定如何暴露：

```python
def render_status(status: AgentStatus) -> str:
    return f"""<agent_status>
<goal>{status.goal}</goal>
<progress>{status.completed_steps}/{status.total_steps}</progress>
<next_step>{status.next_step or 'none'}</next_step>
<last_error>{status.last_error or 'none'}</last_error>
<remaining_tool_calls>{status.remaining_tool_calls}</remaining_tool_calls>
</agent_status>"""
```

跨厂商实现时应遵守四条原则：

1. **状态对象与展示视图分离**：内部可以很详细，给模型的快照必须短。
2. **只展示决策需要的信息**：日志和证据留在外部存储，需要时再查。
3. **区分推送与拉取**：必须每轮知道的主动注入，其余通过 Tool 按需查询。
4. **只追加，不回写旧历史**：状态变化时追加新快照，避免改写已经缓存的前缀。

需要注意第四条的代价：append-only 会让旧状态留在 history。长期任务需要通过 compaction、状态替换边界或重新开 session 清理陈旧快照，不能无限追加。

## 7. 最终心智模型

```text
模型 API：提供运输通道
Agent SDK：维护运行与续跑状态
Agent Harness：把状态整理成 HUD 并决定何时暴露
```

OpenAI 和 Claude 已经分别提供了实现 Agent 状态栏所需的大部分原语，但目前不存在共同的标准协议。真正跨厂商、可复用的部分，是下面这条数据流：

```text
事件 → 状态存储 → 状态归约 → 当前快照 → 模型上下文
```

相关概念笔记：

- [Agent 状态栏：不是文件系统，而是状态暴露机制](agent-status-bar-as-state-exposure.md)

## 8. 官方资料

### OpenAI

- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [Agents SDK: Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents)
- [Agents SDK: Results and state](https://developers.openai.com/api/docs/guides/agents/results)

### Anthropic

- [Mid-conversation system messages and tool changes](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)
- [Claude Code tools reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)

