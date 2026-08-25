# GA4 合成异常 Golden Questions

## 用途与隔离

本文档验证异常检测、交易号覆盖守护、Evidence Package 与受限 Insight Agent 的端到端行为。合成数据直接写入独立的派生日指标批次；每个种子运行的 `input_description` 都含有 `synthetic_case: true`，不接触 Raw、Staging、真实 GA4 批次或 UCI 数据。

这不是对真实业务的模拟，也不验证数据接入或质量门禁；它只验证派生指标之后的决策安全边界。

## Golden Questions 与实际结果

| 场景 | Golden Question | 预期 | 实际运行证据 | 结论 |
| --- | --- | --- | --- | --- |
| `business_interpretable` | 当 8 天完整交易号覆盖下，规范订单由 10 升至 40、收入由 $1,000 升至 $4,000，系统是否识别统计异常并保留贡献？ | 2 个可解释异常、8 条贡献、2 条业务发现，均不主张因果 | batch `084b5707-9fb5-50b5-95df-a3c6ec3916c8`；anomaly run `28d68188-0b8d-4fc9-aed7-88829c6b33b2` | 通过 |
| `coverage_suppressed` | 相同规范订单与收入波动，但每日日有效交易号覆盖仅 50% 时，系统是否阻止业务解释？ | 2 个统计异常、0 个可解释异常、0 条贡献、1 条数据质量诊断、0 条业务发现 | batch `ff23ae2f-683e-5204-a48d-264b888dc84a`；anomaly run `af89c64c-55e9-444e-9752-faf9eac10ed1` | 通过 |
| `insufficient_history` | 只有 4 天历史时，系统是否避免制造异常？ | 0 个统计异常、0 条贡献、0 条业务或数据质量发现 | batch `85bcdfbe-0b1a-5d5c-b012-20b59b698bec`；anomaly run `2d91609f-f545-4201-99e7-aac0ba394bb7` | 通过 |

所有场景的 Agent 输出仍标记 `human_review_required: true`。业务可解释场景仅说明“统计性升高、可进入人工复核”，明确不证明因果；覆盖率不足场景明确禁止将发现写成订单、收入、渠道或设备表现变化。

## 可复跑命令

```bash
PYTHONPATH=src .venv/bin/python src/run_synthetic_ga4_anomaly_cases.py --env-file .env
PYTHONPATH=src .venv/bin/pytest -q \
  tests/test_insight_agent.py tests/test_human_review.py tests/test_synthetic_anomaly_cases.py
```

端到端命令会生成三个独立批次、运行真实异常检测，并将证据包、Agent 输出和 manifest 保存到 `artifacts/evidence_packages/synthetic/`。稳定 batch ID 仅用于隔离与辨识；每次执行都会生成新的 daily/anomaly run ID，且不覆盖真实批次。

## 覆盖范围与边界

- 已覆盖：零 MAD 基线的高异常、95% 交易号覆盖守护、贡献生成开关、历史不足、Evidence Package 追溯、Agent 输出分流。
- 未覆盖：完整 Raw 到 Mart 的合成接入、模型调用安全、多人复核的 RBAC、真实生产阈值校准和因果验证。
- 运行时出现 pandas 对 PyMySQL 连接的兼容性提示；所有 SQL 写入、查询和断言均成功。统一迁移 SQLAlchemy 连接层列入后续性能/工程步骤，当前不影响测试结论。
