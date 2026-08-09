# Skill 与 Tool：上下文占用、前缀长度与 Prompt Cache

## 1. 核心结论

Skill 相比大量专用 Tool 的主要优势，不是“Tool 无法使用 Prompt Cache”，而是同时缓解了两个彼此独立的问题：

1. **前缀长度**：未被使用的能力不加载完整说明，减少上下文窗口占用和首次 prefill 成本。
2. **前缀变化**：需要动态选择能力时，不必回头增删位于 history 之前的 Tool schema，而可以把选中的 Skill 正文追加到会话历史。

必须区分：

```text
前缀很长 ≠ Prompt Cache 无法命中
前缀发生变化 → 从第一个变化 token 开始无法复用旧缓存
```

如果一组 Tool 从会话开始到结束始终固定，它们虽然占用很多上下文，但仍然可以稳定命中 Prompt Cache。

## 2. Tool 进入上下文的不是函数源码

通过原生 Function Calling 使用 Tool 时，模型看到的是调用契约：

```json
{
  "name": "search_web",
  "description": "搜索互联网",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string"}
    },
    "required": ["query"]
  }
}
```

模型看不到函数的完整实现：

```python
def search_web(query: str):
    # 网络请求、鉴权、重试和结果解析等实现
    ...
```

实现代码由 Agent Harness 在模型外部执行。因此，如果一项能力能够被可靠地封装成确定性函数，Tool 往往比 Skill 更节省 token，也更容易验证。

大量专用 Tool 的上下文成本来自每个 Tool 的 `name`、`description` 和参数 JSON Schema，而不是函数源码。单个 schema 可能不大，但几十或几百个 Tool 累积后仍会占用大量 token，并增加模型选择错误工具的概率。

## 3. Tool 和 Skill 分别向模型暴露什么

### 3.1 专用 Tool

一个专用 Tool 通常同时暴露：

- 它能做什么；
- 什么时候调用；
- 需要哪些结构化参数。

例如：

```text
create_presentation(title, source_file, theme, output_path)
```

真正的生成流程封装在 Tool 实现中，模型只负责选择工具并构造参数。

### 3.2 Skill

Skill 把信息拆成两层：

```text
Metadata：name + description
作用：路由——判断当前任务是否需要该 Skill

SKILL.md 正文：流程、约束、参考文件和脚本说明
作用：执行——告诉模型选中以后应该怎么做
```

模型仍然通过少量固定的通用工具完成实际操作，例如：

```text
read_file(path)
write_file(path, content)
execute_command(command)
activate_skill(name)
```

因此，Skill 的核心不是把函数实现换一种格式放进 Prompt，而是让需要 LLM 判断的领域流程按需进入上下文。

## 4. 前缀长度和前缀变化是两个问题

模型请求经过 Chat Template 序列化后，可以抽象为：

```text
[System Prompt]
[Tool Schemas]
[Conversation History]
[最新用户消息]
```

`tools` 在 API 中通常是独立字段，不一定真的是 system message；但在送入模型的 token 序列里，它们位于会话历史之前，属于静态前缀的一部分。

### 4.1 前缀很长

假设系统始终携带 100 个固定 Tool：

```text
第 1 轮：P = [System + 100 Tools] + [User 1]
第 2 轮：P = [System + 100 Tools] + [User 1 + Assistant 1 + User 2]
```

第二轮的开头与第一轮完全一致，因此能够命中缓存。问题在于：

- 第一轮需要计算很长的前缀；
- 这些 token 始终占据上下文窗口；
- Prompt Cache 可以减少重复计算，但不能释放上下文容量；
- 当前任务不需要的 Tool 仍然会干扰模型的工具选择。

### 4.2 前缀发生变化

为了减少上下文占用，框架可能针对任务动态选择 Tool：

```text
任务 A：[System][PPT Tools][History]
任务 B：[System][PDF Tools][History]
```

当 `PPT Tools` 被替换为 `PDF Tools` 时，前缀从工具定义的位置开始变化。Prompt Cache 按精确前缀匹配，因此只能复用第一个差异 token 之前的部分。

```text
[System]                 可以复用
[Tool Schema v2]         从这里开始不同
[后续全部 History]       需要重新计算
```

这来自因果注意力：后面的 token 会关注前面的 Tool schema；前面的 token 发生变化，后续 token 的隐藏状态和 K/V 也可能随之变化。

这里的“缓存失效”不一定表示旧缓存被物理删除，而是新请求无法继续匹配和复用旧缓存。

## 5. 三种能力加载方案

| 方案 | 上下文占用 | 前缀稳定性 | 主要代价 |
| --- | ---: | ---: | --- |
| 所有专用 Tool 固定放在前缀 | 高 | 高 | 首次 prefill 大、长期占用窗口、工具竞争 |
| 每轮选择相关 Tool 并修改前缀 | 低 | 低 | 工具集合变化时产生 cache miss |
| Skill：短目录常驻，正文按需追加 | 较低 | 较高 | 依赖 Skill 路由和模型遵循长流程的能力 |

不存在“Tool 天生破坏缓存、Skill 天生不破坏缓存”的结论。真正的区别是能力变化发生在哪里：

```text
动态 Tool：变化发生在 history 之前的 tools 字段
Skill：变化主要作为新内容追加在 history 末尾
```

## 6. Skill 如何保持已有前缀不变

以常见的渐进式披露实现为例，会话启动时只加载 Skill 目录：

```text
[System Prompt]
[固定通用工具]
[Skill Metadata List]
[用户任务]
```

模型根据 `description` 选中 PPTX Skill 后，运行时加载完整正文：

```text
[System Prompt]
[固定通用工具]
[Skill Metadata List]
[用户任务]
[Skill 调用]
[PPTX SKILL.md 正文]    ← 追加的新内容
[模型后续操作]
```

原来的 token 序列没有被改写，因此原有前缀可以继续复用。完整 Skill 正文第一次进入上下文时仍需要计算；之后只要它在历史中的内容和位置不变，也可以成为后续请求的缓存前缀。

Skill 并没有消除 token 成本，而是把成本从：

```text
所有任务都提前承担全部能力说明
```

变成：

```text
每个任务只承担实际激活的能力说明
```

## 7. 为什么不能只在 History 里声明 Tool 已更新

可以追加一条文字说明：

```text
search_web 现在新增了 top_k 参数。
```

这种做法不会改写前缀，但它通常只是在语义上通知模型，并没有修改 API 的原生 Tool schema。如果 `tools` 字段仍然是旧版本，模型生成的新参数可能被 SDK、API 或 Harness 的 schema 校验拒绝。

此外，新旧定义会同时留在上下文中：

```text
前面：search_web(query)
后面：search_web(query, top_k)
```

模型需要自行推断后面的说明覆盖前面的定义。连续更新后，冲突和上下文垃圾会不断累积。

要在不改写旧前缀的前提下真正注册新 Tool，需要满足以下条件之一：

1. API 原生支持在对话中间追加 Tool schema，例如 Tool Search / deferred loading；
2. 使用固定的通用执行器，由 Harness 在模型外部解析和校验动态能力；
3. 不把动态能力表示成原生 Tool，而是表示成按需加载的 Skill 指令。

## 8. Tool 与 Skill 的选择边界

### 更适合 Tool

- 输入和输出契约可以明确表达；
- 执行过程可以由确定性程序完成；
- 需要严格参数校验、权限控制和稳定行为；
- 模型只需要决定“调不调用”和“传什么参数”。

### 更适合 Skill

- 执行过程包含大量依赖语境的判断；
- 流程会引用操作规范、示例、模板和脚本；
- 很难用一个固定函数完整封装；
- 单次任务只使用庞大能力库中的少数能力。

二者通常组合使用：

```text
Skill 决定流程和判断原则
Tool 提供确定性的外部操作
```

例如，PPTX Skill 负责页面规划、视觉原则和验收流程；文件读取、图片处理、脚本执行和文件写入仍由 Tool 完成。

## 9. 最终心智模型

```text
Tool：把能力封装进模型外部的程序，只向模型暴露固定接口。

Skill：把需要模型理解和遵循的操作手册模块化，先暴露短目录，选中后再加载全文。
```

Prompt Cache 关心的是“旧 token 前缀是否逐字不变”，而不是内容属于 Tool 还是 Skill：

```text
内容很多但固定：能缓存，但占窗口。
内容很少但经常改：频繁 cache miss。
内容按需追加：已有前缀不变，只计算新增部分。
```
