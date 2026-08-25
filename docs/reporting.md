# InsightOps 报告交付说明

## 已交付报告

| 报告 | 面向问题 | 主结论 | 文件 |
| --- | --- | --- | --- |
| 正常周报 | 当前公开 GA4 样例能否支持业务决策？ | 不能。20 条统计异常均不满足业务解释条件；14 日整体有效交易号覆盖率为 29.3%，前 10 天为 0%。 | `artifacts/reports/normal_week/report.md`、`report.html` |
| 合成异常报告 | 覆盖守护通过时，检测—贡献—Agent 是否联通？ | 是。第 8 天订单从 10 升至 40，生成 2 个可解释异常、8 条贡献与 2 条业务发现；仅用于合成测试。 | `artifacts/reports/synthetic_anomaly/report.md`、`report.html` |
| 完整载荷监测报告 | 完整 92 天公开 GA4 载荷是否已形成可审计的监测交付物？ | 是。4,295,584 条事件通过 Raw BLOCKER 门禁；71 条统计异常中 24 条仅作为人工复核候选、47 条受抑制。 | `artifacts/reports/full_ga4_92d/report.md`、`report.html` |

三份 HTML 都是自包含、只读文件：包含同一 `artifact.json` 的受验证快照、图表、表格、来源元数据及无脚本/打印语义回退，不需要启动本地服务或访问网络。

## 事实与边界

- 正常周报只使用守护版 GA4 日指标与异常结果；没有把订单/收入/渠道/设备变化描述成业务表现。
- 合成报告的种子运行标有 `synthetic_case=true`；它验证系统行为，不是生产业务证据。
- 完整载荷报告固定绑定 batch `55c6501e-5403-43a4-b4d5-1a422d87b9d5`、质量运行 `0d9b0ba3-04fd-4adf-a1c8-e2543c79b01f`、日指标运行 `3d901694-d802-4231-8f02-f7d25fea7a76` 与异常运行 `5f4195cc-0b42-4fbb-bc2c-fc728b46b9b8`；不覆盖旧 14 天报告。
- 维度贡献在两个报告中均明确为构成说明，而非因果归因；Agent 始终要求人工复核。

## 验证状态

- 三份 `artifact.json` 已通过报告打包器的来源、快照、块结构和语义回退验证；完整载荷报告包含 14 个报告块、1 个原生图表、2 个指标卡和 1 个审计表。
- 打包器初次未发现可用无头 Chromium，因此生成 `structural_only` 验证；随后发现本机 Google Chrome 并尝试增强渲染，但在静态图表提取阶段超过 43 秒仍超时。
- 2026-08-25 已通过本机临时预览服务完成完整 92 天报告的浏览器 QA：桌面图表、指标来源 tooltip、92 日审计表分页均实际可用；390px 窄屏无水平溢出，语义图表/表格存在，浏览器控制台无 error 或 warn。未下载或安装额外浏览器组件。

## 复跑

```bash
PYTHONPATH=src .venv/bin/python src/build_report_artifacts.py --env-file .env

# 同时生成完整 92 天批次的独立报告
PYTHONPATH=src .venv/bin/python src/build_report_artifacts.py --env-file .env --include-full-ga4

cd /path/to/data-analytics-plugin
npm run report:deliver -- \
  --input /path/to/insightops/artifacts/reports/normal_week/artifact.json \
  --output /path/to/insightops/artifacts/reports/normal_week/report.html
```

对其他报告替换路径中的 `normal_week` 为 `synthetic_anomaly` 或 `full_ga4_92d`。如本机的兼容 Chromium 可用，打包器会自动执行增强浏览器验证；否则仍交付可读的结构化 HTML。
