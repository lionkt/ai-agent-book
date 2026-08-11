# 实验 1-1 报告：来源与审计说明

这份文件保存主报告背后的来源映射、结构决策和证据边界。主报告只呈现影响理解与结论的内容。

## 1. 报告定位

- 受众：技术读者。
- 目标：完整复盘实验设计、真实输入输出、五组结果、因果解释、书稿命题边界与下一轮实验设计。
- 交付面：仓库原生 Markdown。用户指定输出到 `learning_notes/`，因此没有生成通用 HTML 或外部站点。
- 时间范围：以 2026-07-29 accepted run 为结果源；2026-08-11 的失败重跑只用于说明当前复现状态。
- 比较基准：同一任务、同一模型和 Harness 下的 `full` 组。

## 2. Canonical evidence

| 来源 | 作用 | 完整性检查 |
| --- | --- | --- |
| `chapter1/context/validation/latest.json` | 五组真实 API request/response、工具结果、usage、context contract、聚合结论 | SHA-256 `1bd60e9548d7732820e6c8f73b565ee397b42c8d480f1ee2a120b6f81833913b` |
| `chapter1/context/validation/real_20260729T153329Z/evidence.json` | accepted run 的不可变目录副本 | 与 `latest.json` SHA-256 相同 |
| `chapter1/EXPERIMENT_LEDGER.md:7-10` | 仓库级验收状态及 negative result 说明 | 与 evidence 的 `analysis` 一致 |
| `chapter1/context/README.md:250-304, 740-783` | 运行命令、五组观察和结果语义 | 只作说明，数字以 evidence 为准 |

排除项：

- `validation/real_20260811T153240Z/`：沙箱网络隔离导致连接失败，0 token。
- `validation/real_20260811T153302Z/`：Moonshot 余额不足导致 HTTP 429，0 token。

两次运行均没有模型推理，不能作为行为实验样本。

## 3. 实现来源

| 文件与行号 | 用于核验什么 |
| --- | --- |
| `chapter1/context/run_experiment_1_1.py:28-52` | canonical task、expected numbers、provider credentials |
| `chapter1/context/run_experiment_1_1.py:116-233` | 每个 treatment 的实际 payload contract |
| `chapter1/context/run_experiment_1_1.py:236-288` | correctness、completion、重复调用等指标 |
| `chapter1/context/run_experiment_1_1.py:291-363` | token 聚合、行为主张与实验验收条件 |
| `chapter1/context/run_experiment_1_1.py:371-459` | 运行顺序、固定参数、产物与 `latest` 更新行为 |
| `chapter1/context/agent.py:25-39` | Kimi K3 temperature 与五种 context mode |
| `chapter1/context/agent.py:131-230` | 固定汇率表与换汇算法 |
| `chapter1/context/agent.py:239-365` | calculator 与 code interpreter 行为 |
| `chapter1/context/agent.py:424-515` | system prompt 与完整工具 schema |
| `chapter1/context/agent.py:518-535` | `no_reasoning` 只删除历史 `reasoning_content` |
| `chapter1/context/agent.py:644-676` | `no_history` 每轮只保留 system+user |
| `chapter1/context/agent.py:685-940` | ReAct loop、终止语义、tool result 隐藏方式 |

## 4. 书稿来源矩阵

### 第一章：实验命题和 ReAct 基线

| 文件与行号 | 主报告中的作用 | 适用边界 |
| --- | --- | --- |
| `book/chapter1.md:13-29` | Model–Harness–Environment 边界 | 隐藏结果改变的是模型观察，不是环境执行 |
| `book/chapter1.md:109-135` | 内部思考、模型即 Agent、模型能力演进 | 说明 model evolution 有机制基础，但不是当前实验变量 |
| `book/chapter1.md:137-160` | 1.1.3 的精确边界、五类上下文和实验原始主张 | system prompt 未消融；强结论需逐句核验 |
| `book/chapter1.md:161-215` | ReAct 轨迹和 3 轮/4 工具的预期 baseline | 工具结果和 code output 已是高密度状态 |
| `book/chapter1.md:220-228` | Kimi K3 的原生工具决策能力 | 只能支持模型能力假设，不能证明本次 negative result 的来源 |
| `book/chapter1.md:246-280` | 实验属于 Harness 上下文投影变化 | 不要把 Harness treatment 误写成参数更新 |

### 第二章：充分上下文、reasoning 协议和状态压缩

| 文件与行号 | 主报告中的作用 | 适用边界 |
| --- | --- | --- |
| `book/chapter2.md:31-37` | $a_t\sim\pi(a_t\mid c_t)$；API 无状态；Harness 重建充分 $c_t$ | 完整原文可由充分摘要替代，但关键语义不可丢 |
| `book/chapter2.md:45-56` | 四类 message role + 顶层 tools 对应五类上下文 | API 结构分类，不等于五个正交因子 |
| `book/chapter2.md:95-245` | 工具调用、Harness 执行、结果回传的闭环 | tool call 与 tool result 必须关联 |
| `book/chapter2.md:303-368` | 消融要作用于下一轮实际 messages | max iteration 是 Harness 截断机制 |
| `book/chapter2.md:481-503` | 不同模型的历史 CoT 回传策略不同 | 协议要求与任务收益不能互相推出 |
| `book/chapter2.md:804-869` | 状态栏将隐式轨迹提炼成显式状态 | 状态摘要必须准确，且是有损投影 |
| `book/chapter2.md:945-982` | 结构化总结可能比原始历史更易使用 | 压缩可能删除未预料但重要的语义 |
| `book/chapter2.md:1034-1055` | 压缩应保留决策、约束和验证状态 | reasoning 中的排除理由可能属于高价值信息 |

### 其他高度相关章节

| 文件与行号 | 主报告中的作用 | 适用边界 |
| --- | --- | --- |
| `book/chapter3.md:3-19` | 区分任务内 history 与跨会话 user memory | `no_history` 不测试长期用户记忆 |
| `book/chapter4.md:67-81` | 工具 schema 让模型知道何时、如何调用 | 新式 tool search 可按需加载 schema |
| `book/chapter4.md:265-269` | 执行—验证—反馈闭环 | 直接解释 hidden tool results 的开环退化 |
| `book/chapter6.md:13-19` | Harness ablation 与 model swap 的区别 | 判断模型进化必须增加 model swap |
| `book/chapter6.md:102-116` | outcome 与 trajectory 双重评估 | 最终答对不能替代过程审计 |
| `book/chapter6.md:646-658` | 单次运行仅筛方向，多 seed、配对分析 | 当前结果不能给出稳定效果量 |
| `book/chapter6.md:743-747` | 随模型演进定期重做消融、发现特性债务 | 只支持未来实验必要性，不支持当前因果结论 |
| `book/chapter7.md:195-201` | 当前轮思考 token 是语言动作 | 与历史 reasoning replay 不同 |
| `book/chapter7.md:365-380` | 简单任务 NoThinking 可相当，困难任务才显优势 | AdaptThink 是当前轮 thinking treatment，不是本实验 treatment |
| `book/chapter10.md:403` | 结构化 handoff 可不传全量中间思考 | 多 Agent 旁证，不能当作本实验直接证据 |

## 5. 技术报告结构映射

| 技术报告要求 | 主报告位置 |
| --- | --- |
| 标题 | 文档标题 |
| 技术摘要 | 第 1 节 |
| 关键发现和精确证据 | 第 4 节五组总表与逐组分析 |
| 范围、数据、指标定义 | 第 2、3 节 |
| 实验设计与方法 | 第 3 节 |
| 不确定性、局限与 robustness | 第 7、8 节 |
| 建议下一步 | 第 9 节 |
| 进一步问题 | 第 9 节的 H1–H3 与困难任务设计 |

## 6. 可视化决策

没有生成图表，原因不是缺少数值，而是当前数据不支持有意义的统计视觉：

- 每组 $n=1$；
- 正确完成、grounded refusal、迭代上限截断是不同类型的 outcome；
- token 和延迟受随机生成长度影响，不能作为稳定 effect size；
- 五组 treatment 也不是完全正交。

因此使用精确结果表和 role-vector/轨迹序列。它们更适合审计单次 Agent run，也不会暗示不存在的置信度。

## 7. 生成物一致性

`extract_evidence.py` 只读取 canonical evidence，并确定性生成：

- `results.json`
- `turn-traces.md`

检查命令：

```bash
.venv/bin/python \
  learning_notes/experiment-1-1-context-ablation/extract_evidence.py \
  --check
```

主报告中的表格数字应同时满足：

1. 与 `results.json` 一致；
2. 与 canonical evidence 的 `arms[].behavior`、`api_turns[].response.usage` 一致；
3. 五组 token 加总与 `analysis.usage` 一致。
