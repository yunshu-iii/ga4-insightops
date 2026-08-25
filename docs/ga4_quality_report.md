# GA4 Raw 质量报告：2020-11-01 至 2020-11-14

## 结论

质量运行 `3d6ec6a4-6192-4707-81d2-0c12b3c1d1e9` 使用规则集 `ga4_raw_v2`，状态为 **SUCCEEDED**。11 条 BLOCKER 全部通过，事件数据可以进入 Staging。

## 检查范围

- 导入批次：`9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27`
- 数据集：`insightops_raw.ga4_event_raw`
- 粒度：一行一个 GA4 事件
- 总记录数：640,055

## 结果摘要

| 类别 | 规则数 | 失败规则数 | 结论 |
| --- | ---: | ---: | --- |
| BLOCKER | 11 | 0 | 允许进入事件 Staging |
| WARNING | 3 | 2 | 事件分析可用；订单事实需应用去重与排除策略 |

## 警告与处理

| 规则 | 证据 | 风险 | Staging 处理 |
| --- | --- | --- | --- |
| W02 duplicate purchase transaction | 437 个 purchase 事件属于 2 个重复交易号 | 直接按 purchase 行累计会重复计算订单和收入 | 事件 Staging 保留全部事件；订单事实层按 `transaction_id` 选择一条规范记录 |
| W03 purchase missing transaction id | 23 个 purchase 事件缺交易号，占全部事件 0.003593% | 无法作为可靠订单键参与订单数、RFM 或 LTV | 事件 Staging 保留；订单事实层排除并记录原因 |

这两项是公开 GA4 样例的可解释数据边界，不影响事件漏斗、会话、设备、渠道和事件级收入检查；所有订单级指标必须使用后续规范订单表，不能直接累计原始 `purchase` 行。

## Staging 核对

质量通过后，`ga4_event_stg` 已写入 640,055 条事件，日期范围仍为 2020-11-01 至 2020-11-14，且所有页面路径均成功派生。648 条 purchase 事件被完整保留；其中 625 条被标记为 `is_order_eligible = 1`，供后续订单事实表使用。
