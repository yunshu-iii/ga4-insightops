# Streamlit 证据审阅台

## 目的

该页面将版本化聚合 Evidence Package、受限 Insight Agent 的结构化回答和人工决定置于同一个本地审阅界面。它不是查询工作台、模型训练界面或业务自动化工具。

## 启动

在项目根目录执行：

```bash
PYTHONPATH=src .venv/bin/streamlit run src/streamlit_review_app.py --server.headless true --server.port 8501
```

浏览器访问 `http://localhost:8501`。页面会从 `artifacts/evidence_packages/` 中选择已有的 JSON 证据包；不提供上传任意文件、原始事件浏览或 SQL 输入。

## 审阅链路

1. 选择版本化 Evidence Package。
2. 阅读解释闸门、统计发现及其 `query_id`、`run_id`、`metric_id`、日期引用。
3. 查看受限 Agent 基于相同证据包生成的回答。被抑制发现只能形成数据质量诊断，不能形成业务结论。
4. 人工选择决定并填写至少 10 个字符的判断依据。
5. 表单只将经过 Pydantic 校验的 JSON 写到 `artifacts/reviews/`，其中包含证据包与回答的 SHA-256、来源批次与异常运行 ID。

## 安全边界

- 不连接数据库，不执行任意 SQL，不读取原始事件。
- 不调用 LLM，也不允许模型决定口径或业务动作。
- 不修改数据库、模型、报告或外部业务系统；`automated_action_taken` 固定为 `false`。
- 当前实现是本地审阅 MVP，尚未加入用户身份、访问控制或集中式审阅记录存储；若对外部署，需先补齐这些能力。

## 当前示例

`ga4_v2_guardrail_evidence.json` 包含 20 条统计异常，但 0 条可作业务解释。页面会关闭解释闸门，并只允许数据质量诊断与人工复核，不允许将其写成订单、收入、渠道或设备表现变化。
