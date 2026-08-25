# GA4 完整公开样例：分段导出与重新接入

## 目标与边界

完整公开样例覆盖 2020-11-01 至 2021-01-31，共 92 天、约 4,295,584 个事件。现在采用最高优先级的
**连续 7 天完整载荷分段导出**：保留全部事件行、现有 12 个分析列，以及未展开的 `event_params_json` /
`items_json` 两列。Raw 层将以 MySQL JSON 字段保留原始载荷；当前 Staging 继续只保存既有分析字段，
而后续商品或扩展参数分析可从可追溯 Raw 批次再展开，不会破坏现有指标口径。

## BigQuery 操作

1. 在 BigQuery Console 打开 `sql/bigquery/05_extract_ga4_events_full_drive_segment.sql`。
2. 每次替换脚本顶部的 `start_suffix` 与 `end_suffix`，运行查询。
3. 在查询结果中选择 **保存结果 → Google Drive → CSV**；每个文件下载后放入
   `data/inbound/ga4/full_2020q4/`，并按下表精确重命名。
4. 若任一 7 天完整载荷分段仍提示太大，优先改为连续 **1 天** 后重试；必须同步调整文件名，并在执行
   合并前告知我，不能静默漏掉日期或重复导出。
5. 若 1 天完整载荷仍无法经 Google Drive 导出，不降低为“偷偷删掉 JSON”：先告知我。届时优先方案是
   启用结算后使用 Cloud Storage 的 Parquet 分片；若不可用，才按明确业务问题选择性展开所需参数/商品字段，
   并记录完整 JSON 未能取得的边界。

| 序号 | BigQuery suffix 范围 | 本地文件名 |
| ---: | --- | --- |
| 1 | `20201101`–`20201107` | `ga4_ecommerce_events_20201101_20201107.csv` |
| 2 | `20201108`–`20201114` | `ga4_ecommerce_events_20201108_20201114.csv` |
| 3 | `20201115`–`20201121` | `ga4_ecommerce_events_20201115_20201121.csv` |
| 4 | `20201122`–`20201128` | `ga4_ecommerce_events_20201122_20201128.csv` |
| 5 | `20201129`–`20201205` | `ga4_ecommerce_events_20201129_20201205.csv` |
| 6 | `20201206`–`20201212` | `ga4_ecommerce_events_20201206_20201212.csv` |
| 7 | `20201213`–`20201219` | `ga4_ecommerce_events_20201213_20201219.csv` |
| 8 | `20201220`–`20201226` | `ga4_ecommerce_events_20201220_20201226.csv` |
| 9 | `20201227`–`20210102` | `ga4_ecommerce_events_20201227_20210102.csv` |
| 10 | `20210103`–`20210109` | `ga4_ecommerce_events_20210103_20210109.csv` |
| 11 | `20210110`–`20210116` | `ga4_ecommerce_events_20210110_20210116.csv` |
| 12 | `20210117`–`20210123` | `ga4_ecommerce_events_20210117_20210123.csv` |
| 13 | `20210124`–`20210130` | `ga4_ecommerce_events_20210124_20210130.csv` |
| 14 | `20210131`–`20210131` | `ga4_ecommerce_events_20210131_20210131.csv` |

## 本地合并与接入顺序

当全部 14 个文件放好后，执行：

```bash
make prepare-ga4-full
```

该命令会严格验证轻量或完整载荷的列顺序、所有分段字段一致性、文件名、每行日期、连续性、单段和合并文件
SHA-256，并生成：

- `data/staged/ga4/ga4_ecommerce_events_20201101_20210131.csv`
- `data/staged/ga4/ga4_ecommerce_events_20201101_20210131.manifest.json`

然后以新的 UUID（绝不覆盖 14 天开发批次）依次运行 Raw 导入、质量门禁、Staging、订单事实、会话漏斗、
日指标、异常检测、Evidence Package、报告和回归。每个运行都须将新的批次/运行 ID 写入项目总结。

## 接入验收门槛

- 合并清单必须精确覆盖 2020-11-01 至 2021-01-31，无日期空洞或重叠。
- 合并清单的 `payload_mode` 必须为 `full_json`，且列清单必须含 `event_params_json` 与 `items_json`；否则不能
  将该批次描述为完整载荷。
- 预期事件总数应与 BigQuery profile 的 4,295,584 对账；若不同，先定位差异，不能导入为“完整样例”。
- Raw 质量门禁全部 BLOCKER 通过后才可写入 Staging。
- 新批次的交易号覆盖率、订单/收入守护、异常结果和报告必须独立复跑；不得复用 14 天轻量样本的结论。
