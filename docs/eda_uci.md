# UCI Online Retail：首轮数据画像

> 数据来源与文件校验值见 [data_access.md](data_access.md)。本页统计结果基于 2026-08-22 下载的原始 XLSX，尚未执行任何清洗。

## 基本结构

| 项目 | 结果 |
| --- | ---: |
| 行数 | 541,909 |
| 列数 | 8 |
| 日期范围 | 2010-12-01 08:26:00 至 2011-12-09 12:50:00 |
| 去重 InvoiceNo 数 | 25,900 |
| 去重 CustomerID 数 | 4,372 |
| 去重国家数 | 38 |

字段：`InvoiceNo`、`StockCode`、`Description`、`Quantity`、`InvoiceDate`、`UnitPrice`、`CustomerID`、`Country`。

## 初始质量发现

| 发现 | 记录数 | 后续处理方向 |
| --- | ---: | --- |
| `Description` 缺失 | 1,454 | 保留 Raw 原值；在 Staging 中按规则标记或拒绝。 |
| `CustomerID` 缺失 | 135,080 | 保留交易事实；客户价值分析范围须排除并记录影响。 |
| 完全重复行 | 5,268 | 记录重复率；以来源行与业务规则决定是否拒绝。 |
| 取消订单（InvoiceNo 以 `C` 开头） | 9,288 | 写入 `is_cancelled=1`，用于净收入与退款口径。 |
| 非正 Quantity | 10,624 | 结合取消订单规则审查；不可修复记录隔离。 |
| 非正 UnitPrice | 2,517 | 作为价格质量规则，区分已知业务例外与拒绝记录。 |

## 对项目设计的影响

1. `CustomerID` 缺失不能在 Raw 层填补；`mart_customer_value` 只对可识别客户计算，并在报告中声明覆盖限制。
2. 取消订单不能直接删除；后续 `fact_order` 将保留取消/退款信息，并以 `net_revenue` 作为收入口径。
3. 重复、非正数量和非正价格将进入 `dq_rules.yml` 的首批规则。
4. 所有本页统计均为原始数据画像，而非业务结论。
