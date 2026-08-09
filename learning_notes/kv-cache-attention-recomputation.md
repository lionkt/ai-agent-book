# KV Cache：为什么增量解码不需要重算历史 Token

## 问题

已有上下文 `[a, b, c, d]`，随后生成新 token `e`：

- 没有 KV cache 时，`a-d` 是否需要重新计算？
- 有 KV cache 时，是否只需计算 `e` 与 `a-d` 之间的 attention？

## 结论

基本判断正确，但有两个关键修正：

1. Attention 在 Transformer 的每一层、每个 head 中都会计算，不是全模型只计算一次。
2. KV cache 保存的是历史 token 在每一层的 K 和 V，不是已经算出的 attention 权重。

## 无 KV Cache

因果语言模型中，第 `i` 个 token 只能关注自己及之前的 token。输入 `[a, b, c, d]` 时，计算关系是：

```text
a -> [a]
b -> [a, b]
c -> [a, b, c]
d -> [a, b, c, d]
```

这些位置通常由 GPU 以带 causal mask 的下三角 attention 矩阵并行计算。

当 `e` 到来时，模型重新接收 `[a, b, c, d, e]`。由于没有保存上一次前向传播的中间状态，`a-d` 的隐藏状态、Q/K/V 和 attention 都会被重新计算，尽管结果与上次相同。

## 有 KV Cache

Causal mask 保证 `a-d` 看不到未来的 `e`，所以它们的隐藏状态以及 K/V 不会因 `e` 到来而改变，可以安全复用。

模型只为 `e` 计算新的 `Q_e`、`K_e`、`V_e`，把 `K_e`、`V_e` 追加到缓存，然后计算：

\[
\operatorname{softmax}\left(
\frac{Q_e[K_a,K_b,K_c,K_d,K_e]^T}{\sqrt{d}}
\right)[V_a,V_b,V_c,V_d,V_e]
\]

因此，更准确的表述是：

> 只计算 `e` 作为 query 对 `[a,b,c,d,e]` 的 attention；不再计算 `a-d` 作为 query 的 attention。

注意 `e` 也需要关注自身，不只是历史的 `a-d`。

## 计算量

设已有上下文长度为 `n`，再生成一个 token：

| 模式 | 新一步的 attention 计算量 | 额外存储 |
| --- | --- | --- |
| 无 KV cache | 重新计算整个序列，约 `O(n²)` | 较少 |
| 有 KV cache | 只计算新 query 对全部 K，约 `O(n)` | 保存每层 K/V，约 `O(n)` |

KV cache 优化的是逐 token 解码阶段。首次处理完整输入的 prefill 仍然需要计算完整的 causal attention，复杂度约为 `O(n²)`。
