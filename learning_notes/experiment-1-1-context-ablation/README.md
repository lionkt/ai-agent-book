# 实验 1-1：上下文消融实验完整复盘

> 分析对象：2026-07-29 使用 Moonshot 直连 `kimi-k3` 完成的五组真实 API 运行  
> Canonical evidence：[`chapter1/context/validation/latest.json`](../../chapter1/context/validation/latest.json)  
> Evidence SHA-256：`1bd60e9548d7732820e6c8f73b565ee397b42c8d480f1ee2a120b6f81833913b`

## 1. 技术摘要

这次实验可靠地复现了三件事：

1. **没有工具定义，模型没有结构化行动接口。** `no_tool_calls` 组产生 0 次工具调用，最终拒绝编造汇率。
2. **没有工具结果，ReAct 从闭环退化为开环。** `no_tool_results` 组知道自己调用过什么，却看不到结果，于是重试并最终拒绝作答。
3. **没有任务内历史，模型每轮都从相同初态重新决策。** `no_history` 组连续五轮重复三次换汇，共 15 次工具调用，达到迭代上限仍未完成。

但实验没有复现书中关于历史思考过程的强结论：

> 删除历史 `reasoning_content` 后，Kimi K3 仍在 3 轮、4 次工具调用内得到正确总额 `$9,602,895.73` 和季度均值 `$2,400,723.93`。

直接原因不是“模型没有推理也能完成”，而是当前 treatment 只删除了**上一轮回传给下一轮的 reasoning 字段**：模型当前轮仍允许生成 reasoning，并在前两轮实际生成；`assistant.content`、历史工具调用、工具结果也全部保留。对这道浅层、结构化任务而言，这些字段已经构成下一步决策的充分状态，历史 rationale 没有提供不可替代的信息。

因此，当前证据支持的最强结论是：

> 上下文组件的价值取决于它是否承载当前决策所需、且无法从其他字段恢复的信息。工具定义给出动作接口，工具结果提供环境反馈，任务内历史保存已执行的动作与观察；历史 reasoning 在本任务中与这些结构化状态高度冗余。

当前实验**不能证明这是模型进化造成的**。它没有旧模型与新模型的 model swap，也只有一个任务、每组一次采样。模型进化是合理假设，不是本实验识别出的因果变量。

## 2. 实验要回答什么

书中 1.1.3“上下文：Agent 的眼睛”把单轮模型请求拆成五部分：

1. 系统提示词；
2. 工具定义；
3. 用户消息；
4. 模型回复，其中包含 `reasoning`、`content`、`tool_calls`；
5. 工具执行结果。

原始命题是：上下文决定模型在当前决策点能看到什么；逐一拿掉上下文组件，可以观察它对 Agent 行为的边际贡献。实验保留 system prompt，以完整上下文为 baseline，另外构造四个消融组。

这个问题在 ReAct 形式下可以写成：

$$
a_t \sim \pi_\theta(a_t \mid c_t), \qquad
c_t=(o_1,a_1,\ldots,o_{t-1},a_{t-1},o_t)
$$

模型参数 $\theta$ 固定；Harness 改变模型在第 $t$ 轮收到的 $c_t$。若移除某类信息后，行动、最终结果或执行成本稳定恶化，才说明该信息在这个任务分布上有边际价值。

这里要预先区分三个不同问题：

- **当前轮是否生成 reasoning**：模型在本轮做动作前是否产生思考 token。
- **历史 reasoning 是否回传**：上一轮已经生成的 reasoning 是否进入下一轮输入。
- **历史任务状态是否保留**：上一轮的 `content`、`tool_calls` 和 `tool results` 是否仍可见。

实验 1-1 的 `no_reasoning` 只改变第二项，并没有改变第一项。

## 3. 完整实验设计

### 3.1 实验单位与运行顺序

一个实验单位是一条完整的多币种任务轨迹，从初始用户请求开始，直到模型输出非空文本，或者达到 5 次模型迭代上限。

五组按代码中 `ContextMode` 的枚举顺序依次运行：

```text
full → no_history → no_reasoning → no_tool_calls → no_tool_results
```

每组创建一个新的 `ContextAwareAgent`，不会继承上一组的会话历史。组间没有随机化，也没有重复采样。

### 3.2 固定变量

| 变量 | 固定值 |
| --- | --- |
| Provider | Moonshot 直连 API，不经过 OpenRouter |
| Model | `kimi-k3` |
| Temperature | `1`；代码对 Kimi K3 强制使用 reasoning-safe temperature |
| `max_tokens` | 8192 / 模型调用 |
| 最大迭代 | 5 次模型调用 |
| System prompt | 五组相同 |
| User task | 五组相同 |
| 工具实现 | 五组相同；只有模型可见性发生变化 |
| 汇率环境 | 本地代码中的固定汇率表 |
| 正确答案判定 | 最终文本同时包含 `9602895.73` 与 `2400723.93` |

已验收运行环境：macOS arm64、Python 3.11.4、OpenAI Python SDK 1.97.1、Requests 2.32.5；仓库提交为 `4a7f37cf278bd15948c409f14533017c4c7fbc29`，但运行时 worktree 标记为 dirty，因此 commit 不能单独重建当时全部本地代码状态。

### 3.3 完整 system input

```text
You are an intelligent assistant with access to tools.

Your task is to solve the given problems using the available tools. Think step by step and use tools as needed.

Important: When you have gathered all necessary information and computed the final answer, clearly state "FINAL ANSWER:" followed by your answer.
```

注意：`no_reasoning` 组仍然保留了 `Think step by step`，所以它不是当前轮 NoThinking 实验。

### 3.4 完整 user input

```text
According to the company's quarterly revenue:
- Q1: 2.5 million USD
- Q2: 2.1 million EUR
- Q3: 1.8 million GBP
- Q4: 380 million JPY

Use the available currency-conversion and calculation tools to convert every
non-USD quarter to USD, then calculate the annual total and quarterly average.
Report both values rounded to two decimal places. Do not estimate exchange
rates yourself; use the tool observations.
```

### 3.5 模型可见的工具接口

除 `no_tool_calls` 外，模型都能看到四个 function tools：

| 工具 | 参数 | 返回作用 |
| --- | --- | --- |
| `parse_pdf` | `url: string` | 下载或读取 PDF 并提取文本；本任务不使用 |
| `convert_currency` | `amount: number`, `from_currency: string`, `to_currency: string` | 返回原金额、币种、转换值、汇率和时间戳 |
| `calculate` | `expression: string` | 计算受限数学表达式 |
| `code_interpreter` | `code: string` | 在受限 Python namespace 中执行聚合计算 |

完整 JSON Schema 见 [`turn-traces.md`](turn-traces.md#完整工具定义)。

### 3.6 工具环境与期望 output

`convert_currency` 的描述写的是“current exchange rates”，但实现并不访问实时汇率服务，而是使用固定表：

```python
USD = 1.00
EUR = 0.92
GBP = 0.79
JPY = 149.50
```

算法先将源货币除以该币种的表值转换成 USD，再乘目标币种表值；每笔换汇先四舍五入到两位小数：

| 季度 | 计算 | USD 结果 |
| --- | --- | ---: |
| Q1 | 已经是 USD | 2,500,000.00 |
| Q2 | `2,100,000 / 0.92` | 2,282,608.70 |
| Q3 | `1,800,000 / 0.79` | 2,278,481.01 |
| Q4 | `380,000,000 / 149.50` | 2,541,806.02 |

因此：

```text
Annual total     = 2,500,000.00 + 2,282,608.70 + 2,278,481.01 + 2,541,806.02
                 = 9,602,895.73 USD

Quarterly average = 9,602,895.73 / 4
                  = 2,400,723.9325
                  = 2,400,723.93 USD
```

这说明实验测的是**模型能否正确利用结构化工具轨迹**，不是汇率检索能力，也不是复杂数学推理能力。

### 3.7 五组 treatment 的精确定义

下表描述的是第二轮以后真正发送给 provider 的请求，而不是 CLI 标签的字面含义：

| 组别 | 实际改动 | 仍然保留什么 | 真正测试的问题 |
| --- | --- | --- | --- |
| `full` | 无 | system、user、tools、历史 reasoning/content/tool calls/tool results | 完整 ReAct baseline |
| `no_history` | 每轮请求重置为 `system + user` | 工具定义仍在；模型本轮仍可 reasoning 和发起工具调用 | 没有任何任务内轨迹时，模型能否推进状态 |
| `no_reasoning` | assistant message 写入历史前删除 `reasoning_content` | 普通 content、tool calls、tool results 全保留；模型本轮仍可生成 reasoning | 历史 CoT transcript 的边际价值 |
| `no_tool_calls` | 请求不发送 `tools` 和 `tool_choice` | system、user；底层 Python 工具实现仍存在但模型不可调用 | 没有模型可见动作接口时能否完成 |
| `no_tool_results` | 工具真实执行，但回传给模型的 content 被替换为 `[Tool result hidden due to context mode]` | tool call、tool_call_id、assistant content/reasoning、工具定义 | 看得见动作但看不见观察时能否闭环 |

两个设计边界必须显式记录：

1. `no_history` 一次删除 reasoning、content、tool calls 和 tool results，不是与其他组正交的单字段消融；“历史”本身就是其他动态字段的容器。
2. `no_tool_results` 不是让观察静默消失，而是提供了一条非常显眼的新观察“结果被隐藏”。模型因此能够诊断 Harness 限制，并选择重试或拒答。

### 3.8 指标与验收口径

| 指标 | 定义 | 为什么需要 |
| --- | --- | --- |
| `completed` | 收到非空终局文本 | 区分循环是否自然停止，但不等于答对 |
| `canonical_answer_correct` | 终局包含两个预期数字 | 验证最终 outcome |
| `iterations` | 模型 API 调用轮数 | 衡量路径长度 |
| `tool_action_count` | Harness 实际执行的工具调用数 | 衡量行动成本 |
| `repeated_tool_actions` | 总调用数减去唯一“工具名+规范化参数”签名数 | 识别重复行动 |
| `hit_iteration_ceiling` | 未完成且已用满 5 轮 | 区分自然终止与 Harness 截断 |
| context contract | 检查实际 request payload 是否满足 treatment | 防止“只改标签、没改真实输入” |
| token usage | prompt、completion、cached、reasoning token | 衡量模型成本；本证据不含货币价格 |

旧 evidence 中的 `success` 表示“出现终局文本”，不是任务正确。报告统一将它归一为 `completed`，正确性只看 canonical numeric rubric。

## 4. 五组结果

### 4.1 总表

| 组别 | 完成 | 数值正确 | 迭代 | 工具调用 | 重复调用 | 总 token | reasoning token | 耗时 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full` | 是 | **是** | 3 | 4 | 0 | 4,421 | 228 | 46.61 s |
| `no_history` | 否 | 否 | 5 | 15 | 12 | 5,016 | 582 | 64.27 s |
| `no_reasoning` | 是 | **是** | 3 | 4 | 0 | 4,831 | 248 | 39.61 s |
| `no_tool_calls` | 是，拒答 | 否 | 1 | 0 | 0 | 2,829 | 2,111 | 94.72 s |
| `no_tool_results` | 是，拒答 | 否 | 5 | 7 | 3 | 14,773 | 4,062 | 191.33 s |

五组一共消耗 31,870 tokens，其中 prompt 20,599、completion 11,271、cached prompt 11,776、reasoning 7,231。证据没有保存对应价格表，不能严谨换算货币成本。

这里不画柱状图：每组只有一次运行，且“正确性、拒答、被迭代上限截断”是异质终局。把单点 token 或耗时画成效果量会制造统计稳定性的错觉，精确表格更合适。

### 4.2 `full`：完整闭环按预期完成

轨迹与书中 ReAct 示例一致：

```text
Turn 1: 3 × convert_currency
Turn 2: 1 × code_interpreter
Turn 3: final answer
```

三个换汇 tool results 向第二轮提供数值观察；代码解释器又把四个季度的数值压缩为总额和均值。第三轮不再需要重新计算，只需要读取工具结果并组织最终回答。

最终 output：

```text
Annual total: $9,602,895.73 USD
Quarterly average: $2,400,723.93 USD
```

这组同时通过了三项 payload 检查：每轮存在工具定义；第二轮以后同时存在 assistant 和 tool 历史；上一轮 reasoning 被保留。

### 4.3 `no_history`：相同输入诱导相同动作

五轮实际 request role vector 都是：

```text
[system, user]
```

模型无法看到上一轮发出的三个换汇请求，也看不到三个已经返回的 USD 数值。对它而言，每一轮都是第一次接到任务，于是五次重复：

```text
EUR → USD
GBP → USD
JPY → USD
```

结果是 15 次工具调用，其中 12 次是重复调用；5 轮耗尽后没有终局答案。

因果链不是“模型忘性大”，而是 Harness 每轮主动把状态重置为同一个 $c_0$：

```text
相同 system + 相同 user + 相同 tools
                  ↓
          相近的首步决策
                  ↓
工具虽然执行，但结果不进入下一轮输入
                  ↓
             再做首步
```

严格来说，实验只观察到“在 5 轮上限内持续重复”，不能从有限轨迹证明数学意义上的无限循环。

### 4.4 `no_tool_calls`：动作集合被拿掉，安全拒答

请求不含 `tools` 和 `tool_choice`，所以模型没有可发出的结构化换汇动作。它仍然理解任务，也知道不能凭空估算汇率；经过较长的当前轮 reasoning 后，输出：

```text
The annual total and quarterly average cannot be numerically computed because
no currency-conversion tool observations ... are available ...
```

这是**任务失败但行为合理**：

- outcome 角度：没有给出目标数字；
- 安全性角度：遵守“不得估算汇率”，没有幻觉数字；
- 能力边界角度：工具 Python 函数仍存在，但没有进入模型的动作空间，等价于模型无法使用。

因此，这组支持“工具定义决定 Agent 可调用的动作接口”，不支持更宽泛的“模型失去相关知识”。新式 tool search 还可能只常驻一个检索入口、按需加载完整 schema；本结果不能外推为“所有完整工具 schema 必须启动时常驻”。

### 4.5 `no_tool_results`：有行动、无观察，闭环退化

真实工具仍然执行并产生正确值，但模型只看到：

```text
[Tool result hidden due to context mode]
```

逐轮行为是：

1. 并行调用三次换汇；
2. 发现结果隐藏，单独重试 EUR；
3. 再重试 GBP 和 JPY；
4. 用 `calculate("2500000 + 0")` 测试是不是所有工具输出都不可见；
5. 确认系统性隐藏后，拒绝编造结果。

共 7 次工具调用、3 次重复调用，总 token 是 baseline 的约 3.34 倍，耗时约 4.11 倍。这个倍率只描述本次轨迹，不能当作期望效果量。

这一组很好地分开了 Environment 和 Context：Environment 中的工具确实完成了计算；失败发生在 Harness 没把观察暴露给 Model。循环因此不是完全“无反馈”——模型获得了“反馈被隐藏”这条元反馈——但没有获得推进任务所需的数值反馈。

### 4.6 `no_reasoning`：删掉的是历史草稿，不是本轮推理

实际 context contract 是：

```text
provider_generated_reasoning     = true
reasoning_removed_from_history   = true
tool_and_result_history_retained = true
```

三轮仍然完成了与 baseline 相同的状态转移：

```text
Turn 1 response:
  新生成 reasoning
  content = “I'll convert ... These are independent conversions ...”
  3 × convert_currency

Turn 2 input:
  没有 Turn 1 reasoning
  仍有 Turn 1 content + tool_calls + 3 个精确 tool results

Turn 2 response:
  重新生成 reasoning
  content = “All conversions complete. Now let me calculate ...”
  1 × code_interpreter

Turn 3 input:
  没有历史 reasoning
  仍有全部结构化行动、观察和普通计划文本

Turn 3 response:
  正确总额与平均值
```

为什么历史 reasoning 没有边际作用？因为下一步所需信息已经存在于其他字段：

| 下一步需要知道什么 | 可恢复来源 |
| --- | --- |
| 三笔换汇是否已执行 | 历史 `tool_calls` |
| 换汇后的精确 USD 数值 | 三条 `tool` results |
| 当前阶段是“换汇完成，开始汇总” | `assistant.content` |
| 总额和平均值 | `code_interpreter` result |
| 如何选择下一动作 | 模型本轮新生成的 reasoning |

用信息论语言表达：这次单条轨迹与“在给定行动、观察和普通 content 后，历史 reasoning 对下一动作的条件信息接近冗余”一致；但单次样本无法估计真正的条件互信息，更不能证明它在其他任务上为零。

`no_reasoning` 的总 token 反而比 baseline 高约 9.3%，reasoning token 也略高。不能据此说“删除历史 reasoning 更贵”或“更便宜”：Kimi K3 使用 temperature 1，每组只有一次随机生成，两条轨迹的措辞和推理长度并不配对。

## 5. 与书中上下文的对照

### 5.1 1.1.3“上下文：Agent 的眼睛”

书中 [1.1.3](../../book/chapter1.md#上下文agent-的眼睛) 的基础框架被实验支持：Model 只能基于 Harness 暴露的上下文做决策；工具定义、历史行动和工具观察改变了模型可用的信息与动作。

但其中两句需要收窄：

- “思考过程一旦被剥离，前后决策就开始互相矛盾”在这次已验收运行中没有复现。
- “缺失任何一个上下文组件，Agent 的决策能力都会严重退化”被 `no_reasoning` 组直接否定，至少不能作为跨任务、跨模型的无条件命题。

更稳健的表述是：

> 缺失决定下一步行动所需、且无法从其他字段恢复的语义，会使 Agent 退化；字段名本身并不天然不可替代。

### 5.2 ReAct：关键是 observation 回到下一轮

书中 [ReAct 循环](../../book/chapter1.md#react-循环) 将轨迹写成“思考 → 行动 → 观察 → 再思考”。本实验最强的结果不是“所有历史都要保留”，而是：

```text
行动必须产生真实反馈，反馈必须进入下一次决策上下文。
```

`no_history` 丢掉行动和观察；`no_tool_results` 保留行动却丢掉任务数据。两者都无法推进状态。完整组与 `no_reasoning` 组都保留行动和观察，所以都能完成。

### 5.3 第二章：模型需要的是信息充分的 $c_t$

[上下文工程](../../book/chapter2.md#上下文决定-agent-能力上限的关键) 从 ReAct 定义出发，指出 API 本身无状态，Harness 必须在每一轮重建“足够的” $c_t$；同时允许摘要和压缩，只要求不能丢掉决定下一步的信息。

这给出了比“原始字段全部不可替代”更本质的判据：

- 工具结果是当前任务的 observation，不能无损恢复，所以删除后失败；
- 任务内历史整体记录已经采取的 action 和得到的 observation；`no_history` 证明这组状态不能整体删除，但由于它联合删除 `content`、`tool_calls` 和 `tool results`，本实验没有识别历史 `tool_calls` 单独的边际贡献；
- 历史 reasoning 在本任务中可以从行动、观察、普通 content 和当前轮重算中恢复，所以删除后不失败。

### 5.4 不同模型对历史 CoT 的协议并不统一

第二章 [Chat Template](../../book/chapter2.md#从-api-消息到模型-tokenchat-template) 明确指出，不同模型家族对历史思维链有不同训练分布和回传协议：有的模型曾要求剥离历史 `reasoning_content`，有的模型要求原样回传，Claude thinking block 也有自己的边界。

因此要区分：

- API 是否接受或要求历史 reasoning；
- 模型是否在当前轮生成 reasoning；
- 某个任务是否从历史 reasoning 中获得可测收益。

这是三个不同的事实，不能由其中一个推出另外两个。

### 5.5 状态栏和上下文压缩提供了同一条反例

第二章 [Agent 状态栏](../../book/chapter2.md#agent-状态栏通过元信息增强-agent-轨迹管理) 和 [上下文压缩](../../book/chapter2.md#上下文压缩策略) 都主张：与其让模型反复扫描原始轨迹，不如把任务所需状态提炼成高密度、可直接读取的表示。

这与 `no_reasoning` 的结果一致：

- 三条换汇结果是确定性、结构化 observation；
- code interpreter 输出是对四个季度的进一步确定性压缩；
- 后续模型只需读取这些显式状态，不需要保留完整思考草稿。

但书中也给出边界：状态摘要是有损投影；如果后续问题涉及摘要未覆盖的维度，删除原始上下文会导致断崖式退化。历史 reasoning 可能承载的“被排除假设、长期计划、约束理由”正属于容易在压缩中丢失的信息。

### 5.6 第七章：NoThinking 与删除历史 reasoning 不是一回事

第七章将思考 token 描述为不直接改变环境、但可能改善动作质量的语言动作；[AdaptThink 实验](../../book/chapter7.md#实验-7-10-adaptthink学会-何时不思考) 又显示，简单问题上 NoThinking 可能相当甚至更好，困难问题上 Thinking 优势才显现。

实验 1-1 没有测试这件事。Kimi K3 当前轮仍可生成 reasoning，且前两轮确实生成；它只是不在下一轮看到旧 reasoning。因此本结果不能推出“思考无用”，只能推出“这道题没有显示出保存跨轮思考草稿的收益”。

### 5.7 第六章：要判断模型进化，必须做 model swap

[Agent 评估](../../book/chapter6.md) 明确区分两种方法：

- Harness 消融：固定模型，关闭某个 Harness 组件；
- Model swap：固定 Harness，只更换模型。

当前实验属于前者。它没有时间维度或模型版本维度，所以无法回答“新模型是否比旧模型更不依赖历史 reasoning”。第六章同时提醒，单次运行只能筛选方向；稳定结论至少需要多个随机种子和配对比较。

## 6. 书中主张的证据判定

| 书中或常见主张 | 当前判定 | 证据边界 |
| --- | --- | --- |
| 完整 baseline 能以 3 轮、4 次工具调用完成 | **支持** | 单次 Kimi K3 真实运行 |
| 工具定义是结构化行动能力的基础 | **支持** | 无工具定义时 0 tool calls；不外推为 schema 必须全部常驻 |
| 工具结果闭合反馈循环 | **支持** | 隐藏结果后重复调用且无法得到数字 |
| 任务内历史保存进度、避免重做 | **支持** | 每轮只见 system+user 时重复三次换汇 |
| 删除历史 reasoning 会导致决策矛盾 | **未支持** | `no_reasoning` 仍正确完成 |
| 当前轮 reasoning 对复杂动作可能有帮助 | **未测试** | 当前轮 thinking 没有关闭 |
| system prompt 不可或缺 | **未测试** | 原设计主动排除 system 消融 |
| 缺失任何一个原始字段都会严重退化 | **需要收窄** | 字段可能语义冗余；真正要求是决策状态充分 |
| 模型进化使历史 reasoning 不再必要 | **无法判断** | 缺旧/新模型 swap，缺多次采样 |
| 完整原始历史永远优于摘要 | **不成立为普遍命题** | 书中状态栏、压缩和多 Agent handoff 都允许充分状态替代原始轨迹 |

## 7. 为什么现在不能归因于“模型进化”

模型进化是有机制基础的假设：预训练和 RL 后训练可能让模型更擅长分解任务、从工具轨迹恢复当前状态，并内化工具选择策略。书中也提出，应定期重跑消融，以发现随着模型演进而产生的“特性债务”。

但当前数据缺少识别这个因果所需的对照：

```text
当前数据：固定 Kimi K3，改变历史上下文
需要的数据：固定 Harness 和任务，对比旧模型与新模型
```

至少存在四个竞争解释：

1. **任务太简单**：三次独立换汇加一次求和，不需要长程 rationale。
2. **结构化状态已经充分**：工具调用和结果准确记录了“做过什么、得到什么”。
3. **普通 content 泄漏了计划**：即使删掉 reasoning，仍保留“换汇完成，接下来求和”。
4. **模型能力较强**：Kimi K3 能在需要时从现有轨迹重新生成所需推理。

只有第 4 项属于模型进化；当前五臂实验无法把它与前三项分开。

## 8. 有效性威胁与不能下的结论

### 8.1 内部效度

- **每组只有一次采样。** Temperature 为 1，没有固定随机种子；不能估计均值、方差或显著性。
- **组间顺序固定。** 没有随机化执行次序；服务端负载、缓存和限流可能影响耗时与 token 行为。
- **消融不正交。** `no_history` 同时删除多种动态消息；不能把它与单字段 treatment 当作独立因子比较。
- **treatment 可见。** `[Tool result hidden due to context mode]` 明示实验状态，会改变模型策略。
- **普通 content 保留。** `no_reasoning` 仍存在自然语言计划通道，所以不能估计“所有自然语言中间状态”的作用。
- **当前轮 thinking 保留。** system prompt 还显式要求 step-by-step。
- **工具结果高度充分。** code interpreter 直接返回目标数字，降低了对历史规划的依赖。
- **运行 worktree dirty。** Evidence 能证明请求与响应，但仅凭记录的 commit 无法完全重建运行源码。

### 8.2 测量效度

- **`completed` 不等于成功。** 两个拒答组都有终局文本，但任务不正确。
- **正确性 verifier 很窄。** 只检查两个数字字符串，没有验证币种、推导、每季度值或是否真的根据工具结果得出。
- **“无限循环”没有被证明。** `no_history` 只是在五轮上限内持续重复；`no_tool_results` 第五轮主动拒答。
- **重复调用指标只比较完全相同参数。** 语义等价但格式略不同的调用不会计为重复。
- **成本缺失。** Token 有记录，货币价格没有记录。

### 8.3 外部效度

- 只有一个多币种任务、一个 provider、一个模型标识和一次运行。
- `kimi-k3` 不是不可变 checkpoint 标识；同名服务端模型可能随时间更新。
- 历史 reasoning 的协议和训练分布高度模型相关，不能直接外推到 DeepSeek、Claude、OpenAI 或本地开源模型。
- 工具所谓“current exchange rates”实际是固定表，不能外推到真实外部 API 的延迟、错误和数据漂移。
- 当前任务的决策状态几乎完全包含在工具结果里，不能代表需要保留排除理由、长期承诺或隐含约束的任务。

### 8.4 本实验不能证明

- 不能证明 reasoning 对 Agent 无用；
- 不能证明 Kimi K3 因“进化”而不需要历史 reasoning；
- 不能证明任何缺失工具结果的系统都会无限循环；
- 不能证明完整原始上下文总是最优；
- 不能证明 system prompt 的边际贡献；
- 不能用单次 token/耗时差异做成本结论。

## 9. 下一轮实验：真正检验 reasoning 与模型进化

### 9.1 先把两个变量正交化

构造 $2\times2$ treatment：

| 当前轮 Thinking | 历史 reasoning 回传 | 要回答的问题 |
| --- | --- | --- |
| 开 | 开 | 完整 reasoning baseline |
| 开 | 关 | 当前实验真正实现的 treatment |
| 关 | 开 | 通常不成立：没有新 reasoning 可回传；可作为协议检查 |
| 关 | 关 | 真正的 NoThinking 路径 |

若 provider 不能稳定控制当前轮 thinking，应改用能够固定 checkpoint、thinking mode 和 seed 的本地模型；否则 treatment 与模型端协议混在一起。

另加一组：删除历史 reasoning 和普通 `assistant.content`，但保留 `tool_calls`、`tool_call_id` 与 `tool results`。这能检验当前正确结果是否来自 content 中的计划泄漏。

### 9.2 用 model swap 识别模型进化

固定同一份 Harness、tool schema、工具实现、任务集、iteration budget 和 verifier，只替换模型：

```text
旧/弱模型 × reasoning history on/off
新/强模型 × reasoning history on/off
```

真正对应“模型进化”的量是交互项：

```text
新模型在关闭 reasoning history 后的降幅
减去
旧模型在关闭 reasoning history 后的降幅
```

如果新模型的降幅稳定更小，才能说新模型更能从行动/观察恢复状态，降低了对历史 reasoning 的依赖。仅仅看到新模型在关闭组答对，不够。

### 9.3 增加能让 reasoning 承载独特状态的任务

当前算术题不是检验历史 rationale 的强任务。更有区分度的设计是：

1. 第一轮比较 A/B/C 三个方案；
2. 因一条不会出现在工具结果中的隐含约束排除 A；
3. 后续工具只返回新数据，使 A 在表面指标上重新变优；
4. 检查模型是否记得最初排除 A 的理由。

还应覆盖：

- 工具返回冲突信息，需要保留“为什么信任某一来源”；
- 一次工具失败后要记住已排除的修复假设；
- 长程计划中存在延迟约束和不可逆动作；
- 中途压缩成结构化 status，再与 raw history、全删除比较。

### 9.4 采样与指标

探索阶段每个 cell 至少运行 3–5 次；要做稳定的二元成功率比较，应根据预期差异做功效分析，通常需要明显更多任务和重复。任务级别采用配对顺序或 paired bootstrap/McNemar 分析。

同时报告：

- 最终正确率；
- grounded refusal 与幻觉率；
- 完成率、迭代数、重复工具调用；
- 违反历史约束的比例；
- prompt/completion/reasoning/cached tokens；
- p50/p95 延迟与实际费用；
- context contract 是否逐轮成立。

预注册三个假设：

- H1：当前多币种任务中，关闭历史 reasoning 不降低正确率；
- H2：需要保存不可恢复决策理由的任务中，关闭历史 reasoning 会降低正确率；
- H3：新模型相对旧模型的 reasoning-history ablation 降幅更小。

## 10. 复现与审计

### 10.1 原实验入口

```bash
cd chapter1/context
../../.venv/bin/python run_experiment_1_1.py \
  --provider kimi \
  --model kimi-k3 \
  --max-iterations 5
```

需要有效的 `MOONSHOT_API_KEY`。运行器会保存 credential-free request/response、context contract、SHA-256 和聚合分析。

注意：当前运行器即使实验未验收也会覆盖 `validation/latest.json`。重跑前应保存 accepted artifact，或修改运行器为“只有验收通过才更新 latest”。2026-08-11 的现场重跑因 Moonshot 账户余额不足返回 429，所有组均为 0 token；该失败不属于本报告结果，`latest.json` 已恢复为 2026-07-29 的 accepted evidence。

### 10.2 本目录的证据产物

- [`results.json`](results.json)：从 canonical evidence 归一化出的机器可读结果、工具序列、指标定义和 token usage。
- [`turn-traces.md`](turn-traces.md)：五组每一轮实际 `messages`、请求参数、模型 `assistant` 输出、reasoning、工具参数、工具结果和 usage。
- [`extract_evidence.py`](extract_evidence.py)：确定性生成上面两个文件。
- [`source-notes.md`](source-notes.md)：书稿依据、报告结构映射和证据边界。

重新生成：

```bash
.venv/bin/python \
  learning_notes/experiment-1-1-context-ablation/extract_evidence.py
```

检查生成物是否与当前 canonical evidence 一致：

```bash
.venv/bin/python \
  learning_notes/experiment-1-1-context-ablation/extract_evidence.py \
  --check
```

## 11. 最终结论

实验 1-1 真正展示的不是“上下文越完整越好”，而是 **Agent 的下一步决策需要一个信息充分的状态表示**：

```text
工具定义       → 告诉模型可以做什么
历史 tool calls → 告诉模型已经做过什么
工具结果       → 告诉模型环境发生了什么
reasoning      → 在其他字段不足时，保存为什么这样做、排除了什么、接下来要坚持什么
```

工具定义和工具结果在对应消融中显示出不可替代的作用；任务内历史作为一个整体也负责保存进度，但本设计不能分辨其中 `content`、`tool_calls` 与 `tool results` 各自的独立贡献。历史 reasoning 没有显示额外收益，因为工具轨迹、结果和普通 content 已经覆盖了下一步所需状态。换到长程、分支、反事实或隐含约束任务，reasoning 可能重新变得关键。

所以本次 negative result 不应被解释成“思考无用”，也不应直接包装成“模型进化”。更准确的认识是：

> 判断一段上下文是否有价值，不看它叫 reasoning、history 还是 status；要看删除后，模型是否还拥有决定下一步所需的充分信息。
