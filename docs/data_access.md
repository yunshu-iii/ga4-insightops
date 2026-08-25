# 数据访问与来源登记

## UCI Online Retail

- 来源：<https://archive.ics.uci.edu/dataset/352/online+retail>
- 下载日期：2026-08-22
- 许可：CC BY 4.0
- 本地压缩文件：`data/inbound/uci_online_retail.zip`（不提交 Git）
- 解压文件：`data/inbound/uci_online_retail/Online Retail.xlsx`（不提交 Git）
- ZIP SHA-256：`f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b`
- XLSX SHA-256：`43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d`
- MySQL Raw 导入批次：`7aa2b0f4-12aa-4dfb-890c-ffadc8f9d6fa`；导入行数为 541,909。

UCI 将其定义为英国非实体零售商在 2010-12-01 至 2011-12-09 期间的交易数据。该数据只用于技术与方法验证，不能表述为真实企业生产数据或真实业务成效。

## GA4 Google Merchandise Store 样例

- 官方说明：<https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset>
- BigQuery 数据集：`bigquery-public-data.ga4_obfuscated_sample_ecommerce`
- 表模式：`events_*`
- 覆盖日期：2020-11-01 至 2021-01-31
- 前置条件：使用你的 Google 账号创建或选择一个已启用 BigQuery API 的 Google Cloud 项目；BigQuery Sandbox 可用于探索。

### 已验证的概览查询

- 执行日期：2026-08-22
- Google Cloud 项目：用户本地已启用的 BigQuery 项目（项目 ID 不提交）。
- 查询脚本：`sql/bigquery/01_profile_ga4.sql`
- 导出结果：`artifacts/sample_outputs/ga4_profile_result.csv`
- 下载原件 SHA-256：`f666e8437b132f1d1fe11d6834de05fc2b8e779266f50e98d56616d570d04af9`
- 项目归档副本 SHA-256：`d48ef7b6b3024047338ce0ae43b8d7f1c7d0a5c2eaf48e2356dc9f1d57463c51`
- 结果：4,295,584 条事件、270,154 名匿名用户、92 个日期；日期范围为 2020-11-01 至 2021-01-31。

公开 GA4 数据为匿名化样例，含占位值，内部一致性有限。项目中的报告、演示和任何对外项目说明必须说明这一限制。

### 已接入的开发样本

- 提取脚本：`sql/bigquery/03_extract_ga4_events_drive.sql`
- 本地文件：`data/inbound/ga4/ga4_ecommerce_events_20201101_20201114.csv`（不提交 Git）
- 文件 SHA-256：`944597cc399ae4855f568daab105132771a9a7c0628c12551bfb871d6cf3848c`
- 粒度与范围：事件级，640,055 条记录，2020-11-01 至 2020-11-14。
- 已保留字段：事件时间、匿名用户、会话、页面、设备、国家、首次获得来源/媒介、交易号和 USD 收入。
- 未保留字段：未展开的 `event_params` 和 `items` JSON。它们体积较大，超出无结算账号下 Google Drive 单文件导出的限制。
- MySQL Raw 导入批次：`9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27`；导入行数与源文件一致，为 640,055。

### 已接入完整 JSON 载荷

- 导出脚本：`sql/bigquery/05_extract_ga4_events_full_drive_segment.sql`；采用连续分段导出，其中 2020-12-06 至 2020-12-12 因体积拆为两个连续文件。
- 合并清单：`data/staged/ga4/ga4_ecommerce_events_20201101_20210131.manifest.json`（本地忽略文件）；覆盖 2020-11-01 至 2021-01-31、15 段、4,295,584 行。
- 合并 SHA-256：`52694651cfcbb098c9e56424cce32382ca862167b9dfb82e7b5de042a20d69c6`；模式为 `full_json`，14 列包含 `event_params_json` 与 `items_json`。
- Raw 表迁移：`sql/migrations/002_ga4_full_payload_columns.sql` 已执行；完整 Raw 批次为 `55c6501e-5403-43a4-b4d5-1a422d87b9d5`，4,295,584 行。完整批次与 14 天开发批次同时保留，互不覆盖。

## 后续访问步骤

1. 在 BigQuery 控制台登录你的 Google 账号。
2. 新建或选择一个启用了 BigQuery API 的项目。
3. 执行 `sql/bigquery/01_profile_ga4.sql`，保存结果 CSV 或截图。
4. 无结算账号时，优先执行 `sql/bigquery/03_extract_ga4_events_drive.sql`，经 Google Drive 导出连续 14 天轻量事件样本为 CSV。
5. 将导出的 CSV 放入 `data/inbound/ga4/`，并记录实际 SQL、导出日期和文件 SHA-256。
6. 需要重取或扩展完整载荷时，按 `docs/ga4_full_refresh.md` 执行：优先连续日期分段与完整 JSON；单段超限时进一步缩短连续区间，只有在明确接受结算账号后才评估 Cloud Storage Parquet。
