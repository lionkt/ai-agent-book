# 从 \(h_D\) 的计算到 KV Cache

## 1. 核心流程

对于输入：

```text
A = 法国
B = 的
C = 首都
D = 是
```

Decoder-only Transformer 的计算主线是：

```text
A-D 的 embedding
        ↓
D 用 Q_D 查询 A-D 的 K
        ↓
根据 attention 权重读取 A-D 的 V
        ↓
得到 Attention Output O_D
        ↓
经过输出投影、残差和 MLP
        ↓
得到 h_D
        ↓
LM Head 将 h_D 映射到词表概率
        ↓
预测 E = 巴黎
```

其中：

- \(V_D\)：D 自身提供给 Attention 的内容；
- \(O_D\)：D 从 A-D 聚合到的上下文；
- \(h_D\)：D 经过完整 Transformer Block 加工后的状态。

三者不能混用。

## 2. 变量的直观理解与准确定义

| 变量 | 直观类比 | 准确定义 |
| --- | --- | --- |
| \(h_i^0\) | token 的初始资料卡 | token embedding 加位置编码 |
| \(W_Q\) | 查询需求提取器 | 将 hidden state 投影到 Query 空间的参数 |
| \(Q_i\) | 当前 token 发出的搜索请求 | \(h_iW_Q\) |
| \(W_K\) | 检索标签生成器 | 将 hidden state 投影到 Key 空间的参数 |
| \(K_i\) | token 的检索标签 | \(h_iW_K\) |
| \(W_V\) | 正文内容提取器 | 将 hidden state 投影到 Value 空间的参数 |
| \(V_i\) | token 被选中后提供的内容 | \(h_iW_V\) |
| \(score_{ij}\) | Query 与资料标签的匹配度 | \(Q_iK_j^T/\sqrt{d_k}\) |
| \(\alpha_{ij}\) | 分配给资料 \(j\) 的阅读预算 | score 经过 Softmax |
| \(O_i\) | 从上下文读取到的笔记 | \(\sum_j\alpha_{ij}V_j\) |
| \(h_i^l\) | 第 \(l\) 层加工后的工作状态 | Attention、残差、MLP 的输出 |

## 3. \(h_D\) 的 Running Example

构造一个极简 Transformer：

- 只有一层；
- 只有一个 Attention Head；
- 向量维度为 2；
- 忽略 LayerNorm、MLP 和 \(W_O\)；
- 保留 Self-Attention 和残差连接。

假设两个维度分别表示：

```text
第一维：法国相关线索
第二维：首都/答案槽相关线索
```

这是便于手算的人工设定。真实模型的单个维度通常没有固定的人类语义。

### 3.1 初始表示

\[
h_A^0=[2,0],\quad
h_B^0=[0,0],\quad
h_C^0=[0,2],\quad
h_D^0=[0,1]
\]

| Token | 初始表示 |
| --- | --- |
| 法国 | \([2,0]\) |
| 的 | \([0,0]\) |
| 首都 | \([0,2]\) |
| 是 | \([0,1]\) |

### 3.2 计算 \(Q_D\)

令：

\[
W_Q=
\begin{bmatrix}
1&0\\
1&1
\end{bmatrix}
\]

则：

\[
Q_D=h_D^0W_Q
=[0,1]W_Q
=[1,1]
\]

直观上，D 发出的查询是：

```text
我需要知道：
1. 当前讨论哪个实体？
2. 当前涉及什么关系？
```

### 3.3 计算 A-D 的 K/V

为了简化，令：

\[
W_K=W_V=I
\]

所以：

\[
K_i=V_i=h_i^0
\]

| Token | \(K_i\) | \(V_i\) |
| --- | --- | --- |
| A | \([2,0]\) | \([2,0]\) |
| B | \([0,0]\) | \([0,0]\) |
| C | \([0,2]\) | \([0,2]\) |
| D | \([0,1]\) | \([0,1]\) |

真实 Transformer 中 \(W_K\) 和 \(W_V\) 是不同的学习参数，K/V 通常不会相同。

### 3.4 计算相关性

\[
score_{D,j}
=
\frac{Q_DK_j^T}{\sqrt2}
\]

得到：

\[
scores_D=[1.414,\ 0,\ 1.414,\ 0.707]
\]

经过 Softmax：

\[
\alpha_D=[0.365,\ 0.089,\ 0.365,\ 0.180]
\]

| Token | Attention 权重 |
| --- | ---: |
| 法国 | 0.365 |
| 的 | 0.089 |
| 首都 | 0.365 |
| 是 | 0.180 |

### 3.5 加权聚合 Value

\[
O_D
=
0.365V_A+
0.089V_B+
0.365V_C+
0.180V_D
\]

逐项计算：

\[
0.365V_A=[0.730,0]
\]

\[
0.089V_B=[0,0]
\]

\[
0.365V_C=[0,0.730]
\]

\[
0.180V_D=[0,0.180]
\]

相加：

\[
O_D=[0.730,0.910]
\]

\(O_D\) 是 D 从 A-D 中读取到的上下文，不是 \(V_D\)。

### 3.6 残差连接

极简模型中：

\[
h_D^1=h_D^0+O_D
\]

因此：

\[
h_D^1=[0,1]+[0.730,0.910]
\]

得到：

\[
\boxed{h_D^1=[0.730,1.910]}
\]

它同时保留了：

- D 原本的“答案槽”状态；
- 从 A 读取的“法国”信息；
- 从 C 读取的“首都”信息。

真实 Transformer 会继续经过 MLP，并重复多层：

```text
h_D⁰
 ↓ 第一层读取 A-D
h_D¹
 ↓ 第二层基于新状态再次读取 A-D
h_D²
 ↓
...
 ↓
h_Dᴸ
```

最终的 \(h_D^L\) 是面向 next-token prediction 的上下文状态。它可以近似理解为 A-D 的语义压缩，但不是无损摘要，只保留模型认为对后续计算有用的信息。

## 4. 从 \(h_D\) 预测 E

最终状态经过 LM Head：

\[
logits_D=W_{\text{vocab}}h_D^L
\]

其中 \(W_{\text{vocab}}\) 为词表中的每个 token 计算一个分数：

```text
巴黎：8.2
北京：2.1
伦敦：1.4
……
```

Softmax 后得到：

\[
P(x_{D+1}=v\mid A,B,C,D)
\]

采样得到：

```text
E = 巴黎
```

此时 E 只是一个离散 token ID。模型处理 A-D 时没有计算过 \(Q_E,K_E,V_E,h_E\)。

如果还要继续预测 F，就必须把 E 送回 Transformer：

```text
[A,B,C,D] → h_D → 预测 E
[A,B,C,D,E] → h_E → 预测 F
```

## 5. KV Cache 在哪里发挥作用

需要严格区分：

```text
Self-Attention：规定当前位置如何使用历史 K/V
KV Cache：规定历史 K/V 是重新计算，还是直接复用
```

### 5.1 Prefill 阶段

首次处理 A-D 时，每层都会计算：

```text
K_A-D
V_A-D
```

这些 K/V 一方面参与构造 A-D 的 hidden state，另一方面被保存在显存中：

```text
Layer 1 cache: K_A-D¹, V_A-D¹
Layer 2 cache: K_A-D², V_A-D²
...
Layer L cache: K_A-Dᴸ, V_A-Dᴸ
```

第一次计算 \(h_D\) 时，A-D 的 K/V 是刚计算的，还没有发生历史复用。

### 5.2 Decode 阶段

E 被预测出来后，为了构造 \(h_E\)，每一层只计算：

\[
Q_E,\quad K_E,\quad V_E
\]

然后读取缓存的历史 K：

\[
scores_E
=
\frac{
Q_E[K_A,K_B,K_C,K_D,K_E]^T
}{
\sqrt{d_k}
}
\]

K cache 用于决定 E 应该读取谁。

再根据 Attention 权重读取缓存的 V：

\[
O_E
=
\alpha_{E,A}V_A+
\alpha_{E,B}V_B+
\alpha_{E,C}V_C+
\alpha_{E,D}V_D+
\alpha_{E,E}V_E
\]

V cache 用于决定 E 实际读出什么。

计算完成后，把新产生的 K/V 追加进 cache：

```text
旧 cache：K_A-D, V_A-D
新增：    K_E, V_E
新 cache：K_A-E, V_A-E
```

下一步预测 F 时继续复用。

## 6. 有无 KV Cache 的区别

### 无 KV Cache

构造 \(h_E\) 时重新输入：

```text
[A,B,C,D,E]
```

重新计算 A-E 在每一层的 Q/K/V 和 hidden state。

### 有 KV Cache

构造 \(h_E\) 时输入：

```text
E + A-D 的历史 KV
```

只计算 E 的 Q/K/V，直接读取 A-D 的缓存。

| 项目 | 无 Cache | 有 Cache |
| --- | --- | --- |
| A-D 的 K/V | 重新计算 | 从显存读取 |
| E 的 Q/K/V | 计算 | 计算 |
| E 是否读取 A-D | 是 | 是 |
| E 的最终结果 | 相同 | 相同 |
| 单步 Attention 计算量 | 约 \(O(n^2)\) | 约 \(O(n)\) |
| 额外显存 | 少 | 随上下文长度增长 |

KV cache 优化的是重复计算，不会切断新 token 对历史上下文的依赖。

## 7. KV Cache 的直观理解

可以把历史 token 想成一组已经处理好的资料：

```text
K：每份资料的检索标签
V：每份资料中可取出的内容
Q：当前 token 发出的搜索请求
```

没有 cache：

> 每来一个新 token，都重新阅读全部历史资料，并重新制作所有检索标签和内容摘要。

有 cache：

> 历史资料的检索标签 K 和内容 V 已经做好并放在显存中。新 token 只需生成自己的 Q，然后查询这些历史 K/V。

因此，KV cache 可以理解为：

> 对历史 token 在每一层 Attention 中产生的“可检索索引 K”和“可读取内容 V”进行 memoization。

它不是长期记忆，也不是对话的语义摘要，而是一次生成过程中临时保存的中间张量。

## 8. 为什么缓存 K/V，不缓存 Q 和 Attention 权重

历史 Q 不需要缓存，因为：

```text
Q_D 只在构造 h_D 时使用
未来构造 h_E 时，需要的是 Q_E
```

历史 K/V 会被所有未来 token 反复读取，所以值得缓存。

Attention 权重也不能直接缓存，因为不同新 token 有不同的 Q：

\[
Q_EK_A^T\neq Q_FK_A^T
\]

因此，每个新 token 都必须重新计算自己与历史 K 的 score 和 Attention 权重。

## 9. 最终总结

构造当前位置 \(i\) 的 hidden state：

\[
Q_i
\rightarrow
K_{1:i}
\rightarrow
\alpha_i
\rightarrow
V_{1:i}
\rightarrow
O_i
\rightarrow
h_i
\]

KV cache 的作用：

```text
不缓存：
每一步重新计算历史 K/V

缓存：
历史 K/V 只计算一次；
未来 token 继续读取，但不再重新计算
```

最关键的区分是：

> Self-Attention 决定“如何读取历史”，KV Cache 决定“读取历史时是否需要重新制作 K/V”。

## 10. Prefill 的准确含义

Decoder-only Transformer 的推理可以分成两个阶段：

```text
输入 Prompt
    ↓
Prefill：处理全部输入 token
    ↓
生成第一个输出 token
    ↓
Decode：逐个生成后续 token
```

假设输入 prompt 为：

\[
x_1,x_2,\ldots,x_N
\]

Prefill 会在因果掩码约束下，对这 \(N\) 个 token 执行完整的 Transformer 前向计算。

在每一层中，模型都会计算：

\[
Q_{1:N},\quad K_{1:N},\quad V_{1:N}
\]

并进一步得到每个位置的 hidden state。计算结束后：

1. 保留所有输入 token 的 \(K/V\)，形成 KV Cache；
2. 使用最后一个位置的 hidden state \(h_N\) 计算 logits；
3. 从 logits 中采样第一个输出 token。

因此，“Prefill”可以理解为：

> 在自回归生成开始前，先处理完整输入，并把后续 Decode 所需的 KV Cache 填充好。

Prefill 阶段虽然可以并行处理多个输入 token，但并不意味着没有计算成本。每个位置仍然要通过多层 Attention 和 MLP；长 prompt 的 Prefill 往往是首 token 延迟的重要来源。

## 11. 冷启动时的 Prefill

假设这是某段 prompt 第一次被模型服务处理：

```text
Prompt：x₁, x₂, ..., xₙ
```

在输出第一个 token 前，服务端没有这些 token 对应的历史 K/V，因此必须执行：

```text
完整 Prompt
    ↓
计算 x₁ 到 xₙ 的所有层 K/V
    ↓
得到 hₙ
    ↓
生成第一个输出 token
```

此时，普通 KV Cache 还不能减少 Prefill 计算，因为缓存尚不存在。

更准确地说：

> 在冷启动 Prefill 中，KV Cache 是计算的产物，而不是可以复用的输入。

KV Cache 会从后续 Decode 开始发挥作用：生成下一个 token 时，模型可以读取刚刚建立的 Prompt KV Cache，而不必重新计算输入 prompt。

## 12. Prompt Cache 命中时的 Prefill

假设新的 API 请求包含 \(N\) 个输入 token，其中前 \(M\) 个 token 与之前的请求完全相同：

```text
[x₁ ... xₘ][xₘ₊₁ ... xₙ]
  相同前缀       新增后缀
```

如果服务端保存了相同前缀对应的 KV Cache，就可以执行：

```text
前 M 个 token：加载已有 KV
后 N-M 个 token：执行新的 Prefill
```

也就是：

\[
\text{完整 Prefill}(N)
\quad\longrightarrow\quad
\text{加载缓存}(M)+\text{Prefill}(N-M)
\]

随后，模型使用完整上下文对应的状态生成第一个输出 token。

因此，Prompt Cache 并不是绕过 Prefill，而是缩小本次请求实际需要执行 Prefill 的范围。

### 冷启动与缓存命中对比

| 情况 | 前缀 KV 是否存在 | 本次需要计算的部分 | KV Cache 的角色 |
| --- | --- | --- | --- |
| 冷启动 | 不存在 | 完整 prompt | Prefill 的产物 |
| Prompt Cache 命中 | 已存在相同前缀 KV | 未命中的后缀 | Prefill 的输入 |
| Decode | 已有完整历史 KV | 当前新增 token | 每一步读取并追加 |

## 13. Prompt Cache 如何影响 TTFT

首 token 延迟可以粗略分解为：

\[
T_{\text{TTFT}}
=
T_{\text{排队}}
+
T_{\text{缓存查找与加载}}
+
T_{\text{未命中部分 Prefill}}
+
T_{\text{首 token 计算}}
+
T_{\text{网络传输}}
\]

冷启动时：

\[
T_{\text{未命中部分 Prefill}}
=
T_{\text{完整 Prompt Prefill}}
\]

缓存命中时：

\[
T_{\text{未命中部分 Prefill}}
=
T_{\text{新增后缀 Prefill}}
\]

因此，Prompt Cache 主要减少的是重复的前缀 Prefill，并不能消除：

- 缓存查找和 KV 加载；
- 未命中后缀的计算；
- 第一个输出 token 的 logits 计算与采样；
- 排队和网络延迟。

某些推理引擎还可能需要重新计算最后一个 token 或最后一个缓存块。因此，即使 prompt 完整命中，TTFT 也不会降低到零。

## 14. 最终区分

```text
请求内 KV Cache：
Prefill 创建 KV
Decode 复用 KV

跨请求 Prompt Cache：
之前请求创建 KV
当前请求的 Prefill 复用 KV
```

所以，“第一个 token 输出前的 Prefill 无法被 cache 优化”只在冷启动时成立。

完整表述应当是：

> 冷启动请求必须对完整 prompt 执行 Prefill；如果相同前缀曾被计算并由 Prompt Cache 保存，后续请求可以在第一个 token 输出前加载已有 KV，只对未命中的后缀执行 Prefill。
