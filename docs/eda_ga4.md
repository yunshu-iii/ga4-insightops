# GA4 公开样例：访问验证

> 此页只确认数据源规模和日期覆盖；尚未对事件、漏斗或字段质量作出业务结论。

## 查询结果

| 指标 | 结果 |
| --- | ---: |
| 事件数 | 4,295,584 |
| 匿名用户数 | 270,154 |
| 日期数 | 92 |
| 首个日期 | 2020-11-01 |
| 最后日期 | 2021-01-31 |

查询脚本为 `sql/bigquery/01_profile_ga4.sql`，导出证据为 `artifacts/sample_outputs/ga4_profile_result.csv`。结果与官方标注的三个月 GA4 匿名化样例时间范围一致。

## 下一步

运行 `sql/bigquery/02_extract_ga4_events.sql`，导出 2020-11-01 至 2020-11-14 的开发样本。导出 CSV 将进入 `data/inbound/ga4/`，随后进行字段画像并写入 MySQL Raw 层。
