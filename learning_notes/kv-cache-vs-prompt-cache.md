# KV Cache 与 Prompt Cache

## 一句话结论

Prompt Cache 不是一套独立于 KV Cache 的底层算法，而是推理服务层围绕 KV Cache 增加的跨请求复用机制。

应用层负责构造稳定的 prompt 前缀；服务端负责保存、匹配和复用这些前缀对应的 KV 状态。

## 核心区别

| 维度 | KV Cache | Prompt Cache |
|---|---|---|
| 复用范围 | 一次推理请求内部 | 多次 API 请求之间 |
| 主要优化阶段 | Decode：逐 token 生成 | Prefill：处理输入 prompt |
| 缓存内容 | 每层、每个历史 token 的 K/V 张量 | 相同 prompt 前缀对应的 K/V 张量 |
| 实现位置 | 模型推理引擎 | API 服务端或推理服务层 |
| 主要收益 | 避免生成每个 token 时重算全部历史 | 避免每次请求都重新计算相同前缀 |
| 典型指标 | Decode latency、tokens/s | Cached tokens、TTFT、缓存输入费用 |

两者并不是完全平行的概念。Prompt Cache 复用的底层计算产物通常就是 KV Cache，区别主要在缓存的生命周期和作用范围。

## 从一次请求到跨请求

假设一次 Agent 调用的输入是：

```text
请求 1：
[System][Tools][User]
```

模型在 prefill 阶段为这些 token 计算出每一层的 K/V；开始生成回复后，KV Cache 支撑逐 token decode。

下一轮 Agent 会重新发送完整上下文：

```text
请求 2：
[System][Tools][User][Assistant][Tool Result]
```

如果没有 Prompt Cache，请求 2 需要重新计算所有输入 token。

如果命中 Prompt Cache：

1. 服务端识别出 `[System][Tools][User]` 是相同前缀；
2. 加载请求 1 已经计算好的 KV 状态；
3. 只对新增的 `[Assistant][Tool Result]` 做 prefill；
4. 生成新回复时，继续使用请求内的 KV Cache。

## Prompt Cache 解决的结构性问题

LLM API 在逻辑上通常是无状态的：每次请求必须重新提交完整上下文。

Agent 的上下文却具有明显的追加结构：

```text
C₁ = 静态前缀 + 第 1 轮轨迹
C₂ = C₁ + 第 2 轮轨迹
C₃ = C₂ + 第 3 轮轨迹
```

如果服务端不保留计算状态，每一轮都需要重新处理前面已经算过的内容。

Prompt Cache 在不改变无状态 API 接口的前提下，让服务端在物理执行上变成增量计算：

```text
逻辑接口：每轮提交完整上下文
物理计算：复用旧前缀，只计算新增后缀
```

这才是 Prompt Cache 最本质的价值。

## Prompt Cache 的价值

### 1. 降低首 token 延迟

长 prompt 的时间主要消耗在 prefill。命中缓存后，服务端只需处理未命中的后缀，因此 TTFT 通常会下降。

### 2. 降低重复计算和输入成本

System Prompt、工具定义以及历史轨迹会在 Agent 的多次调用中反复发送。缓存命中可以避免重复计算；部分服务商也会对 cached input tokens 使用更低价格。

### 3. 支撑长轨迹 Agent

Agent 经常需要几十轮模型调用。轨迹越长，每轮从头执行 prefill 的浪费越明显。Prompt Cache 将上下文的追加结构转化为增量计算，使长任务的延迟和成本更可控。

### 4. 让上下文布局成为架构决策

为了提高命中率，prompt 应当组织为：

```text
[长期稳定内容][会话稳定内容][历史轨迹][本轮动态内容]
```

典型原则：

- System Prompt 和工具定义保持稳定；
- 工具定义顺序保持稳定；
- 时间戳、余额、运行状态等动态信息放到末尾；
- 尽量追加消息，不修改已有前缀；
- 对话压缩应考虑修改位置以及缓存失效范围。

## “缓存静态 prompt”的准确含义

Prompt Cache 通常不是缓存 prompt 文本本身，而是缓存该 token 前缀经过模型计算后得到的 K/V 张量。

“静态”也不是某种特殊标记，而是指连续请求中的 token 前缀保持一致。已经发生且不再修改的历史对话，同样可以成为下一轮的稳定前缀。

缓存匹配通常要求 token 级一致，而不是语义一致：

```text
Current time: 10:30:01
Current time: 10:30:02
```

两段内容语义非常接近，但从时间戳位置开始 token 已经不同，因此该位置之后的缓存通常不能复用。

## Prompt Cache 不解决什么

Prompt Cache 通常不会：

- 减少上下文实际包含的 token 数；
- 消除新输出 token 的 decode 计算；
- 消除长上下文带来的显存和注意力读取开销；
- 直接返回之前的最终答案。

最后一种属于 Response Cache：

```text
Prompt Cache：相同前缀 → 复用中间 K/V 状态 → 继续推理
Response Cache：相同请求 → 直接返回之前的最终结果
```

## 应用层与推理服务层的职责

应用层负责：

- 构造稳定的 token 前缀；
- 避免在前缀中插入无关动态信息；
- 保持消息和工具定义的顺序、格式稳定；
- 监控 cached tokens、TTFT 和成本。

推理服务层负责：

- 对 prompt 前缀进行匹配；
- 存储和加载对应的 KV 状态；
- 管理缓存分块、有效期和淘汰；
- 执行实际的增量 prefill。

因此，更准确的表述是：

> Prompt Cache 是基于 KV Cache 可复用性的推理服务层工程机制；应用层通过缓存友好的上下文设计，提高它的命中率。

## 阅读本实验代码时的注意点

是否命中缓存只取决于服务端最终看到的 token 序列，而不取决于客户端是否复用了同一个 Python `messages` 对象。

重新创建列表：

```python
messages = rebuild_messages()
```

只要重建后的内容、顺序和序列化结果完全一致，仍然可能命中 Prompt Cache。

真正导致缓存失效的是：

- System Prompt 中加入变化的时间戳；
- 动态修改用户信息；
- 调整工具定义顺序；
- 删除或重写历史消息；
- 改变消息序列化格式。

因此，实验中的关键变量应当是“发送给模型的 token 前缀是否发生变化”，而不是“Python 列表是否被重新创建”。
