# UCI Raw 质量报告：2010-12-01 至 2011-12-09

## 结论

质量运行 `ff79b0ab-7ad1-466a-bf15-9472840f7b85` 使用规则集 `uci_retail_raw_v1`，状态为 **SUCCEEDED**。5 条 BLOCKER 全部通过，数据已进入 Staging。

## 检查范围

- 导入批次：`7aa2b0f4-12aa-4dfb-890c-ffadc8f9d6fa`
- 数据集：`insightops_raw.uci_retail_line_raw`
- 粒度：一行一条零售订单明细
- 总记录数：541,909

## 结果摘要

| 类别 | 规则数 | 失败规则数 | 结论 |
| --- | ---: | ---: | --- |
| BLOCKER | 5 | 0 | 允许进入交易 Staging |
| WARNING | 6 | 6 | 需按下游指标的适用范围使用标识字段 |

## 警告与处理

| 规则 | 失败行数 | 风险 | Staging 处理 |
| --- | ---: | --- | --- |
| W01 exact duplicate line | 5,268 | 直接累计会重复计算销售 | 标记 `is_exact_duplicate`，有效销售行排除 |
| W02 cancelled invoice line | 9,288 | 取消订单不能计入正常销售 | 标记 `is_cancelled`，有效销售行排除 |
| W03 nonpositive quantity | 10,624 | 退货/修正行不应纳入正向销售 | `is_valid_sale_line = 0` |
| W04 nonpositive unit price | 2,517 | 零价或修正行不应计入 GMV | `is_valid_sale_line = 0` |
| W05 missing customer id | 135,080 | 不能可靠归属到客户 | 标记 `is_customer_identified = 0`，客户分析排除 |
| W06 missing description | 1,454 | 商品描述维度不完整 | 原样保留，商品分析需显式处理 |

警告行之间存在重叠，因此不能将各行数相加后解释为“异常总行数”。

## Staging 核对

`insightops_dw.uci_retail_line_stg` 已写入 541,909 行：

- 524,878 行标记为有效销售行；
- 9,288 行标记为取消行；
- 5,268 行标记为完全重复行；
- 406,829 行有可用客户 ID。

下一步构建订单事实表时，必须只从 `is_valid_sale_line = 1` 的记录聚合 GMV；客户 RFM/LTV 还必须要求 `is_customer_identified = 1`。
