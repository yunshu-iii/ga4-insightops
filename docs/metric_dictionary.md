# InsightOps 指标字典 v1

## 使用边界

UCI 与 GA4 都是公开样例，但数据粒度、货币、时间范围和业务语义不同。任何报告必须分源展示，**不得**将 UCI 的 GBP 交易额与 GA4 的 USD 事件收入相加，也不得把它们解释为同一家企业的统一漏斗。

公开样例没有真实业务目标、预算或干预记录，因此本项目当前只建立可复现的基线，不设“增长目标”或业绩阈值。

## UCI 交易指标

| Metric ID | 名称 | 公式与粒度 | 纳入条件 | 当前基线 |
| --- | --- | --- | --- | ---: |
| `uci_order_count` | 有效订单数 | `COUNT(*)`，一行一个 `invoice_no` | `uci_order_fact` | 19,960 |
| `uci_gmv_gbp` | 有效 GMV（GBP） | `SUM(gmv_gbp)`，订单级 | 仅由 `is_valid_sale_line = 1` 聚合而成 | £10,642,110.80 |
| `uci_aov_gbp` | 平均订单金额（GBP） | `SUM(gmv_gbp) / COUNT(*)` | 同上 | 约 £533.17 |
| `uci_identified_customer_count` | 可识别客户数 | `COUNT(DISTINCT customer_id)` | 仅 `is_customer_identified = 1` 的订单 | 4,338 |
| `uci_identified_order_coverage` | 客户可识别订单覆盖率 | 有客户 ID 的订单 / 有效订单 | 用作客户价值分析的覆盖守护指标 | 18,532 / 19,960（92.85%） |

取消、退货/非正数量、非正单价和完全重复行不进入这些销售指标。无客户 ID 的有效订单仍进入订单数和 GMV，但不可进入客户 RFM/LTV。

## GA4 事件样本订单指标

| Metric ID | 名称 | 公式与粒度 | 纳入条件 | 当前基线 |
| --- | --- | --- | --- | ---: |
| `ga4_canonical_order_count` | 规范订单数 | `COUNT(*)`，一行一个 `transaction_id` | 合格 purchase、交易号非空且不为 `(not set)`/`unknown`；重复交易保留最早事件 | 189 |
| `ga4_canonical_revenue_usd` | 规范订单收入（USD） | `SUM(revenue_usd)`，订单级 | 同上 | $12,836.00 |
| `ga4_unique_buyers` | 匿名购买用户数 | `COUNT(DISTINCT user_pseudo_id)` | `ga4_order_fact` | 170 |
| `ga4_placeholder_transaction_events` | 占位交易号购买事件 | `COUNT(*)`，事件级 | `transaction_id = '(not set)'` | 435 |

GA4 的 435 条占位交易号事件可保留在漏斗/事件分析中，但不能作为订单数、订单收入、RFM 或 LTV 的输入。订单事实中遇到同一有效交易号的多个事件时，按 `event_ts, stg_event_id` 升序保留最早一条，且记录原始 `purchase_event_count`。

## GA4 会话与结账漏斗指标

主漏斗按同一 `user_pseudo_id + ga_session_id` 的事件时间顺序计算，覆盖 2020-11-01 至 2020-11-14 的公开样例。没有设业务目标或阈值，只提供后续异常检测的基线。

| Metric ID | 名称 | 公式与粒度 | 当前基线 |
| --- | --- | --- | ---: |
| `ga4_observed_session_count` | 观察到的会话数 | `COUNT(*)`，一行一个会话键 | 47,911 |
| `ga4_checkout_start_sessions` | 开始结账会话 | `SUM(has_begin_checkout)` | 1,911 |
| `ga4_checkout_to_purchase_event_rate` | 结账至购买事件转化率 | 同会话且购买时间不早于结账时间的会话 / 开始结账会话 | 578 / 1,911（30.25%） |
| `ga4_checkout_to_canonical_order_rate` | 结账至规范订单转化率 | 同会话规范订单 / 开始结账会话 | 176 / 1,911（9.21%） |
| `ga4_add_to_cart_session_coverage` | 加购会话覆盖 | `SUM(has_add_to_cart)`，仅作数据覆盖守护 | 1 |

`add_to_cart` 在样例中只有 4 个事件、1 个会话，无法形成可靠的正式漏斗阶段。它必须作为采集/导出覆盖限制报告，不能解读为业务加购表现。

## GA4 日指标与异常检测

| Metric ID | 名称 | 公式与粒度 | 基线与限制 |
| --- | --- | --- | --- |
| `ga4_daily_canonical_orders` | 日规范订单数 | `COUNT(*)`，日×规范 `transaction_id` | 来自 `ga4_order_fact`；排除占位/未知交易号并去重 |
| `ga4_daily_canonical_revenue_usd` | 日规范订单收入（USD） | `SUM(revenue_usd)`，日 | 同上；不能与 UCI GBP 相加 |
| `ga4_daily_checkout_to_canonical_order_rate` | 日结账至规范订单转化率 | 日规范订单会话 / 日开始结账会话 | 分子为同会话、时序合格的规范订单会话；分母为开始结账会话 |
| `ga4_purchase_event_count` | 日购买事件数 | `SUM(is_purchase)`，日×事件 | 用于区分购买活动与交易号字段覆盖；当前全期 648 |
| `ga4_purchase_valid_transaction_id_coverage` | 购买事件有效交易号覆盖率 | 具备非空且非 `(not set)`/`unknown` 交易号的 purchase 事件 / 全部 purchase 事件 | 数据质量守护指标；当前日或此前 7 天窗口任一日低于 95% 时，禁止解释规范订单、订单收入和相关转化率的业务异常 |
| `ga4_mad_anomaly_status` | 日异常状态 | 每个日期仅用此前最多 7 天值计算中位数与 MAD；至少 5 个历史点；稳健 Z 阈值 3.5 | 历史不足为 `INSUFFICIENT_HISTORY`；MAD=0 且值变化时标记异常但不伪造无限 Z 分数；异常记录保留 `is_business_interpretable` 与解释备注 |
| `ga4_anomaly_contribution_share` | 异常贡献份额 | 维度当日值减去该维度历史中位数，再除以全量指标的相同差值 | 仅对守护通过的订单数和收入异常生成；设备与渠道不能相加，且不是因果归因 |

当前 14 天公开样例中，11 月 1–10 日有 421 条 purchase 事件，但有效交易号覆盖率为 0%（398 条为 `(not set)`、23 条缺交易号）；11 月 11–14 日才出现有效交易号。因此订单/收入相关高异常主要反映订单标识覆盖变化，是数据审计线索，不是可直接投产的告警阈值或业务因果结论。

全期的 190 条有效交易号 purchase 事件再按交易号去重后为 189 笔规范订单；唯一的重复交易号为 `350590`。覆盖率守护项按事件计算，订单指标按去重交易号计算，二者不得混用。

`ga4_daily_metrics_v2` 与 `ga4_mad_anomaly_v2` 已把上述口径落地：648 与 190 分别和 Staging 逐日汇总一致；56 条规范订单依赖的日期×指标结果均为 `is_business_interpretable = 0`，且 v2 贡献记录为 0。95% 是当前公开样例的保守默认值，接入有稳定交易号的完整数据后必须复核。

## UCI 客户价值指标

| Metric ID | 名称 | 公式与粒度 | 当前基线 |
| --- | --- | --- | ---: |
| `uci_identified_order_coverage` | 客户可识别订单覆盖率 | 有客户 ID 的有效订单 / 全部有效订单 | 18,532 / 19,960（92.845691%） |
| `uci_identified_customer_count` | 可识别客户数 | `COUNT(*)`，一行一个 `customer_id` | 4,338 |
| `uci_repeat_customer_count` | 复购客户数 | `SUM(frequency_orders > 1)` | 2,845 |
| `uci_historical_value_gbp` | 历史价值代理（GBP） | 观察期累计有效 GMV，客户级 | £8,887,208.89 |

`uci_historical_value_gbp` 仅是观察期内的实际累计消费，不能解释为未来 LTV 预测。RFM 的适用范围、快照日、并列值处理和分群规则见 `docs/uci_customer_value.md`。

## 可追溯性

每条订单事实都保存来源批次、来源质量运行、构建运行和定义版本。`insightops_ops.fact_build_audit` 记录输入行、排除行、输出订单数与规则说明；对应的 `transformation_run.input_description` 保存占位交易号排除参数。
