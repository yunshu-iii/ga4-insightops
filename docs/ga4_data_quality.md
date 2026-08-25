# GA4 Raw 数据质量门禁

## 用途与粒度

检查对象为 `insightops_raw.ga4_event_raw` 的单一 `batch_id`。一行代表一个 GA4 事件，所有时间按导出时的 UTC 值处理。通过门禁后才可写入 Staging；Raw 数据永不修改。

## 规则集 `ga4_raw_v2`

| 规则 | 级别 | 判定 |
| --- | --- | --- |
| B01 | BLOCKER | 导入批次状态为 `SUCCEEDED` |
| B02 | BLOCKER | 批次至少有一行事件 |
| B03 | BLOCKER | 事件日期位于登记的提取日期范围内 |
| B04 | BLOCKER | UTC 事件时间的日期等于 `event_date` |
| B05 | BLOCKER | 用户、事件、会话、页面、设备、国家与首次获得字段非空 |
| B06 | BLOCKER | 设备类别只能是 desktop、mobile 或 tablet |
| B07 | BLOCKER | 页面地址以 HTTP 或 HTTPS 开头 |
| B08 | BLOCKER | 购买收入不得为负数 |
| B09 | BLOCKER | 非 purchase 事件不得带购买收入 |
| B10 | BLOCKER | purchase 事件必须有购买收入 |
| B11 | BLOCKER | 同一批次的源文件行号唯一 |
| W01 | WARNING | 首次获得来源或媒介为 `unknown` |
| W02 | WARNING | 同一交易号出现多个 purchase 事件 |
| W03 | WARNING | purchase 事件缺少交易号；仅在构建订单事实表时排除并记录原因 |

BLOCKER 失败会将质量运行标记为 `BLOCKED`，并把对应源文件行号写入 `insightops_ops.data_quality_reject`；WARNING 不阻断 Staging，但必须被记录和解释。

首次 `ga4_raw_v1` 运行曾将“purchase 缺交易号”定义为 BLOCKER。检查实际结果后发现 23 条购买事件具有收入但没有交易号：它们是有效事件，但不能形成可靠订单键。因此从 `ga4_raw_v2` 起，该条件降为 WARNING；事件 Staging 可继续，订单 Staging 必须单独排除这些记录。

## 执行命令

```bash
.venv/bin/python src/run_ga4_quality.py \
  --batch-id 9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27
```

执行结果写入 `data_quality_run`、`data_quality_result` 和 `data_quality_reject` 三张 Ops 审计表。

## 订单事实层补充

`is_order_eligible = 1` 仅代表事件层同时具备交易号和收入。订单事实还必须排除语义占位交易号（已观测到 `(not set)`），并按交易号去重；完整口径见 `docs/metric_dictionary.md`。

## 订单事实层补充

`is_order_eligible = 1` 仅代表事件层同时具备交易号和收入。订单事实还必须排除语义占位交易号（已观测到 `(not set)`），并按交易号去重；完整口径见 `docs/metric_dictionary.md`。
