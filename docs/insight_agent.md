# 受限 Insight Agent 与证据包

## 目的

该 Agent 是一个**证据受限的解释层**，不是数据库查询代理，也不是自动决策或自动执行工具。它只读取小型、版本化 JSON 证据包，输出结构化事实、数据质量诊断、限制和人工复核建议。

当前 MVP 使用确定性策略来验证权限边界与 Pydantic 契约；未来接入 OpenAI-compatible 模型时，模型只能负责语言组织，必须接收同一证据包、输出同一 `InsightResponse` 契约，且不能调用任意 SQL、读取 Raw 明细或升级被抑制的结果。

## 固定输入与输出

- 输入契约：`EvidencePackage`（版本 `insight_evidence_v1`）。
- 输出契约：`InsightResponse`（版本 `insight_response_v1`）。
- 每条事实性 `business_finding` 或 `data_quality_diagnostic` 都携带一个或多个 `EvidenceReference`，其中包含 `query_id`、`run_id`、`metric_id`、`metric_date` 和来源表。
- 仅允许读取固定 SQL 查询得到的 v2 异常结果与其贡献计数；不接受用户拼接 SQL，不读取 Raw/Staging 明细，也不写入数据库。
- `human_review_required` 始终为 `true`；回答不得声称因果、不得触发营销或运营动作。

## 守护规则

`is_business_interpretable = false` 的结果只能生成 `data_quality_diagnostic`，绝不能生成 `business_finding`。这条规则适用于交易号覆盖不足时的规范订单、收入、结账至规范订单率及其异常。

当前 v2 证据包的实际运行结果：20 条统计异常、0 条可作业务解释、20 条被抑制、0 条维度贡献。对问题“这些异常是否代表业务增长？”的 Agent 追踪输出 0 条业务结论和 1 条带 20 个证据引用的数据质量诊断。

## 可复跑命令

```bash
.venv/bin/python src/build_insight_evidence_package.py \
  --batch-id 9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27 \
  --daily-run-id 8a9acff4-fa36-4921-b1c0-8d8fe4f2ef9d \
  --anomaly-run-id e9975d26-b3c2-4702-b857-622b6c7da4c1 \
  --output artifacts/evidence_packages/ga4_v2_guardrail_evidence.json

.venv/bin/python src/run_insight_agent.py \
  --evidence-package artifacts/evidence_packages/ga4_v2_guardrail_evidence.json \
  --question '这些异常是否代表业务增长？' \
  --output artifacts/run_traces/ga4_v2_guardrail_agent_response.json
```

## 测试范围与边界

- `tests/test_insight_agent.py` 验证：被抑制证据不会成为业务结论；允许解释的合成证据仍保留查询和运行引用，且明确不证明因果。
- 当前测试覆盖契约与解释分流，不覆盖真实 LLM 提示词注入、模型输出校验重试或 Web/Streamlit 界面；这些属于后续接入模型与应用层时的独立测试范围。
