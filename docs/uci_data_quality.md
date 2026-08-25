# UCI Online Retail：质量规则与分层约定

## 适用范围

- 输入：`data/inbound/uci_online_retail/Online Retail.xlsx`
- Raw 表：`insightops_raw.uci_retail_line_raw`
- 规则集：`uci_retail_raw_v1`
- 执行脚本：`src/run_uci_quality.py`

## 阻断规则

下列规则失败时，质量运行状态为 `BLOCKED`，禁止写入 Staging：

| 规则 | 检查内容 |
| --- | --- |
| B01_batch_succeeded | 导入批次必须成功完成 |
| B02_rows_present | Raw 层必须至少有一行 |
| B03_source_row_number_unique | 同一批次的源文件行号不可重复 |
| B04_date_within_batch_range | 发票日期必须落在该批次登记的日期范围内 |
| B05_core_fields_populated | 发票号、货号、发票时间和国家不可为空 |

## 警告规则与处理

警告不删除记录，也不阻断 Staging；它们通过字段标识保留给下游模型选择。

| 规则 | Staging 字段/处理 |
| --- | --- |
| W01_exact_duplicate_line | `is_exact_duplicate = 1`；销售指标排除 |
| W02_cancelled_invoice_line | `is_cancelled = 1`；销售指标排除 |
| W03_nonpositive_quantity | `is_valid_sale_line = 0` |
| W04_nonpositive_unit_price | `is_valid_sale_line = 0` |
| W05_missing_customer_id | `is_customer_identified = 0`；不可用于客户级 RFM/LTV |
| W06_missing_description | 保留明细，但后续商品维度需明确处理 |

## 有效销售行定义

`is_valid_sale_line = 1` 当且仅当：发票号不以 `C` 开头、数量大于 0、单价大于 0，且不是完全重复的明细行。该定义用于后续 GMV、订单和商品销售指标；Raw 层始终保留原始事实，以支持审计与规则调整。
