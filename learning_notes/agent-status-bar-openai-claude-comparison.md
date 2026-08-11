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

## 7. 状态栏更新：每轮替换与持久追加

### 7.1 问题

状态栏会随着任务推进不断变化。上一轮 TODO 还剩两项，下一轮可能只剩一项；工具调用计数、错误状态和资源预算也会更新。旧状态如何被新状态替代，主要有两种实现：

- 每轮替换旧状态栏；
- 保留旧状态栏，持久追加新状态。

二者交换的是两类成本：

```text
每轮替换：缓存重算成本
持久追加：上下文膨胀和状态歧义成本
```

### 7.2 实现一：每轮替换

假设第 N 轮输入为：

```text
[稳定历史 H]
[状态栏 S1]
```

模型随后生成回复并调用工具，历史变成：

```text
[稳定历史 H]
[状态栏 S1]
[Assistant A1]
[Tool Result T1]
```

下一轮产生新状态 `S2` 时，Harness 删除 `S1`，然后把 `S2` 追加到末尾：

```text
旧：[H][S1][A1][T1]
新：[H]    [A1][T1][S2]
```

虽然 `A1` 和 `T1` 的内容没有变化，但其前面的 `S1` 被删除了。从 `S1` 所在位置开始，新旧 token 前缀不再相同，因此 Prompt Cache 只能复用 `[H]`，`[A1][T1][S2]` 需要重新计算。

由于状态栏通常位于轨迹后部，这不会破坏最前面的 System Prompt、工具定义和早期历史，失效范围通常只有最近一轮或几轮。

这种方式的收益是：

- 上下文始终只有一份最新状态；
- 不存在新旧状态冲突；
- 状态栏的 Token 占用有上限；
- 模型不必判断哪条状态仍然有效。

代价是：

- 每次替换都会使旧状态栏之后的缓存失效；
- 最近的 Assistant 输出和工具结果可能需要重新 prefill；
- 长任务中反复替换，会持续产生局部 cache miss。

### 7.3 实现二：持久追加

持久追加不删除 `S1`，而是直接在轨迹末尾增加 `S2`：

```text
[稳定历史 H]
[状态栏 S1]
[Assistant A1]
[Tool Result T1]
[状态栏 S2]
```

旧内容没有被修改，新请求只是向后追加。因此原有前缀保持一致，可以最大限度复用缓存。

这种方式的收益是：

- 会话保持 append-only；
- 最符合 KV Cache 的前缀匹配机制；
- 不会因为更新状态而主动使已有前缀失效；
- 适合长时间、多轮运行的 Agent Loop。

代价是：

- `S1`、`S2`、`S3` 会持续占用上下文；
- 新旧状态可能互相矛盾；
- 模型必须识别“最新状态覆盖旧状态”；
- 缓存只能减少 prefill 成本，旧 Token 仍占用上下文窗口；
- 最终仍需要压缩或清理，而清理会形成一次新的缓存断点。

持久追加时，最好显式标注版本和覆盖关系：

```xml
<agent_status version="12">
  Latest authoritative state.
  This supersedes all earlier agent_status blocks.
</agent_status>
```

### 7.4 如何选择

| 场景 | 更适合的实现 |
| --- | --- |
| 不能容忍新旧状态歧义 | 每轮替换 |
| 单条状态消息很大 | 每轮替换 |
| 任务较短、更新次数少 | 每轮替换 |
| 长时间运行、状态频繁更新 | 持久追加 |
| 最近一轮输出很长，重新计算代价高 | 持久追加 |
| 状态很短，例如计数器、当前步骤 | 持久追加 |

真正决定替换成本的，不是完整 History 的总长度，而是：

1. 旧状态栏后面有多少内容会因替换而失去缓存；
2. 这种替换在整个任务中会重复多少次。

如果状态栏每轮更新，它通常靠近轨迹末尾，单次替换损失可能不大；但长任务中重复几百次，累计代价仍然可能很高。

### 7.5 实际系统通常采用混合方案

生产系统不必永久坚持其中一种方式。更常见的做法是：

```text
持续追加短状态或状态增量
            ↓
累积到长度或轮数阈值
            ↓
生成一份最新完整快照
            ↓
压缩旧状态，接受一次局部 cache miss
```

也就是使用持久追加优化日常更新，再通过周期性的 checkpoint 或 compaction 控制上下文膨胀。

相关原文：[《深入理解 AI Agent》第 2.6.4 节](../book/chapter2.md#状态更新的两种实现与缓存代价)。

## 8. 2.6.2 的构成分类与 2.6.5 的实现技术

### 8.1 两节采用了不同的分类维度

2.6.2 和 2.6.5 可以对应，但不是严格的一一映射：

- 2.6.2 按“信息是什么”分类；
- 2.6.5 按“具体怎样实现和暴露”分类。

因此，同一种实现可能同时承载多类状态，一类状态也可能通过不同位置暴露。

| 2.6.5 的技术 | 对应 2.6.2 分类 | 对应程度 |
| --- | --- | --- |
| TODO 列表 | 任务规划 | 完全对应 |
| 时间戳跟踪 | 事件的侧信道信息 | 完全对应 |
| 工具调用计数器 | 事件侧信道 + 环境状态摘要 | 跨两个分类 |
| 系统状态感知 | 环境当前状态的观察摘要 | 完全对应 |
| 详细错误信息 | 结构化工具观察，接近事件侧信道 | 不能完全对应 |

### 8.2 TODO 列表：任务规划

TODO 列表直接表达任务结构和执行进度：

```text
目标
├── Task A: completed
├── Task B: in_progress
└── Task C: pending
```

它让模型知道当前执行到哪里、还有哪些任务没有完成，对应 2.6.2 的“任务规划”。

### 8.3 时间戳：事件侧信道

时间戳不改变事件本身，只给事件增加时序元数据：

```text
原始结果：
payment succeeded

增加侧信道：
[2026-08-12 10:30:00] payment succeeded
```

因此它完全符合“事件的侧信道信息”的定义。

### 8.4 工具调用计数器：横跨两类状态

如果调用序号附加在单次工具结果上：

```text
Tool call #3 for 'read_file'
```

它属于事件侧信道。

如果 Harness 在状态栏中做全局汇总：

```text
TOOL COUNTS:
read_file=3
write_file=1
```

它又属于环境当前状态的观察摘要。因此工具计数器体现的是多对多关系：

```text
单次调用序号 → 事件级侧信道
全局调用统计 → Agent 当前状态
```

### 8.5 系统状态感知：环境状态摘要

例如：

```text
cwd=/workspace/project
os=Linux
shell=zsh
python=3.12
```

这些信息由 Harness 从运行环境读取并聚合成当前快照，对应“环境当前状态的观察摘要”。

### 8.6 详细错误信息：原分类的边界

详细错误通常包括：

```json
{
  "error_type": "FileNotFoundError",
  "arguments": {"path": "a.txt"},
  "stack": "...",
  "suggestion": "Check the current directory"
}
```

它既不是任务规划，也不是稳定的全局环境状态，而是在增强某一次工具执行产生的观察：

- `error_type`、参数和调用栈属于结构化事件信息；
- `suggestion` 是 Harness 派生出的决策辅助；
- 整体更适合称为 **structured tool feedback** 或 **observation enrichment**。

可以把它宽泛地归入事件侧信道，但这也说明 2.6.2 的三类不能完整覆盖 2.6.5。

### 8.7 更完整的信息分类

如果重新整理，可以把运行时元信息分成四类：

```text
Agent 运行时元信息
├── 任务状态
│   └── TODO List
├── 事件元数据
│   ├── 时间戳
│   └── 单次工具调用序号
├── 结构化执行反馈
│   └── 详细错误信息
└── 全局运行环境状态
    ├── 工具调用汇总
    ├── cwd / OS / Shell
    └── 资源与预算
```

还需要区分两种暴露位置：

```text
事件旁边的信息 → event-level annotation
上下文末尾的快照 → global status view
```

如果严格把状态栏定义为上下文末尾的全局快照，那么 TODO、系统状态和调用汇总属于状态栏；时间戳、单次调用序号和详细错误属于事件级上下文增强。

书中采用的是广义定义：只要是 Harness 主动向模型暴露的运行时元信息，都归入“Agent 状态栏”机制。这个定义便于组织工程实践，但实现时仍应区分事件注解和全局状态快照。

相关原文：[2.6.2 状态栏的构成](../book/chapter2.md#agent-状态栏的构成)与[实验 2-9：几种好用的 Agent 状态栏技术](../book/chapter2.md#agent-状态栏通过元信息增强-agent-轨迹管理)。

## 9. 最终心智模型

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
- [Context Engineering 的本质及其与 ICL 的关系](context-engineering-and-icl.md)

## 10. 官方资料

### OpenAI

- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [Agents SDK: Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents)
- [Agents SDK: Results and state](https://developers.openai.com/api/docs/guides/agents/results)

### Anthropic

- [Mid-conversation system messages and tool changes](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)
- [Claude Code tools reference](https://code.claude.com/docs/en/tools-reference)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
