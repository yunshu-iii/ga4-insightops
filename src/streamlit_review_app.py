"""Read-only InsightOps evidence review console with local human-review records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from insight_agent import EvidencePackage, HumanReviewRecord, answer_from_evidence

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRECTORY = ROOT / "artifacts" / "evidence_packages"
REVIEW_DIRECTORY = ROOT / "artifacts" / "reviews"

st.set_page_config(page_title="InsightOps · Evidence Review", page_icon="◈", layout="wide")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def apply_design() -> None:
    st.markdown(
        """
        <style>
        .stApp { background:#f8fbfc; color:#17233b; }
        [data-testid="stSidebar"] { background:#17233b; }
        [data-testid="stSidebar"] * { color:#f8fbfc; }
        .kicker { font:600 .72rem Consolas; letter-spacing:.14em; color:#0b6174; }
        .title { font-family:"Avenir Next","PingFang SC",sans-serif; font-size:2.55rem;
          font-weight:720; letter-spacing:-.05em; line-height:1.05; margin:.35rem 0 .6rem; }
        .subtitle { max-width:760px; color:#506176; font-size:1.02rem; line-height:1.7; }
        .gate { border-left:9px solid #ffb703; background:#fff6df; padding:1.05rem 1.25rem;
          margin:1.5rem 0; box-shadow:inset 0 0 0 1px #f0d99a; }
        .gate strong { color:#5d4400; font-size:1.18rem; }
        .claim { border-left:3px solid #0b6174; padding:.7rem 1rem; margin:.65rem 0;
          background:#f0f7f8; }
        .limitation { border-left-color:#9b3f2f; background:#fcf2ef; }
        .ledger { border-top:2px solid #17233b; padding-top:.65rem; margin-top:1rem; }
        .ledger-label { font:600 .72rem Consolas; letter-spacing:.08em; color:#617083; }
        .ledger-value { font:650 1rem Consolas; color:#17233b; }
        .stButton button,[data-testid="stFormSubmitButton"] button{border-radius:0;font-weight:650}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    apply_design()
    evidence_paths = sorted(EVIDENCE_DIRECTORY.glob("*.json"))
    if not evidence_paths:
        st.error("未找到证据包。请先运行 build_insight_evidence_package.py。")
        st.stop()
    with st.sidebar:
        st.markdown("### ◈ InsightOps")
        selected_path = st.selectbox(
            "审阅证据包", evidence_paths, format_func=lambda item: item.name
        )
        st.caption("只读证据 · 人工复核 · 不执行业务动作")
    package = EvidencePackage.model_validate_json(selected_path.read_text())
    question = st.text_input("审阅问题", value="这些异常是否代表业务增长？")
    response = answer_from_evidence(question, package)
    evidence_sha = digest(selected_path.read_bytes())
    response_sha = digest(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode()
    )
    st.markdown('<div class="kicker">Evidence-led human review</div>', unsafe_allow_html=True)
    st.markdown('<div class="title">异常不是结论，证据才是。</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">此页面只展示版本化聚合证据与受限 Agent 的结构化解释。'
        "任何结论都需要人工判断；系统不会查询原始记录，也不会触发外部业务动作。</div>",
        unsafe_allow_html=True,
    )
    if package.business_interpretable_anomaly_count:
        st.success("解释闸门：存在允许业务解释的统计结果，但仍需人工复核，且不证明因果。")
    else:
        st.markdown(
            '<div class="gate"><strong>解释闸门已关闭</strong><br>'
            "该证据包没有可作业务解释的异常。页面只允许记录数据质量诊断，"
            "不允许写作订单、收入、渠道或设备表现变化。</div>",
            unsafe_allow_html=True,
        )
    metrics = st.columns(4)
    for column, label, value in zip(
        metrics,
        ["统计异常", "可作业务解释", "被守护抑制", "维度贡献"],
        [
            package.statistical_anomaly_count,
            package.business_interpretable_anomaly_count,
            package.suppressed_anomaly_count,
            package.contribution_count,
        ],
        strict=True,
    ):
        column.metric(label, value)
    evidence_tab, answer_tab, review_tab = st.tabs(["证据链", "受限回答", "人工复核"])
    with evidence_tab:
        st.subheader("可追溯的统计发现")
        st.caption("每行保留固定 query_id、run_id、metric_id 与日期；不展示原始事件。")
        st.dataframe(
            [
                {
                    "日期": finding.metric_date,
                    "指标": finding.metric_id,
                    "状态": finding.status,
                    "可作业务解释": finding.is_business_interpretable,
                    "说明": finding.interpretation_note,
                    "查询": finding.evidence.query_id,
                    "运行": finding.evidence.run_id,
                }
                for finding in package.findings
            ],
            hide_index=True,
            width="stretch",
        )
        for label, value in [
            ("来源批次", package.source_batch_id),
            ("异常运行", package.anomaly_run_id),
            ("证据包 SHA-256", evidence_sha),
        ]:
            st.markdown(
                f'<div class="ledger"><div class="ledger-label">{label}</div>'
                f'<div class="ledger-value">{value}</div></div>',
                unsafe_allow_html=True,
            )
    with answer_tab:
        st.subheader("受限 Agent 回答")
        st.caption("回答由固定证据包生成；不调用任意 SQL、原始数据或外部执行工具。")
        for claim in response.claims:
            css_class = "limitation" if claim.claim_type == "limitation" else "claim"
            st.markdown(
                f'<div class="claim {css_class}"><strong>{claim.claim_type}</strong><br>'
                f"{claim.text}</div>",
                unsafe_allow_html=True,
            )
            if claim.evidence:
                st.caption(
                    "证据："
                    + " · ".join(
                        f"{item.query_id} / {item.metric_id} / {item.metric_date}"
                        for item in claim.evidence
                    )
                )
        st.markdown("#### 建议的人工下一步")
        for step in response.recommended_next_steps:
            st.markdown(f"- {step}")
    with review_tab:
        st.subheader("记录人工决定")
        st.caption("保存的是本地审阅记录，不会修改数据库、模型、报告或任何业务系统。")
        with st.form("human_review"):
            decision = st.selectbox(
                "审阅决定",
                ["needs_investigation", "confirmed_data_quality", "not_adopted"],
                format_func=lambda item: {
                    "needs_investigation": "需要进一步调查",
                    "confirmed_data_quality": "确认是数据质量问题",
                    "not_adopted": "暂不采纳此诊断",
                }[item],
            )
            reviewer_role = st.text_input("审阅角色", value="数据分析协作者")
            rationale = st.text_area("判断依据（至少 10 个字符）", height=140)
            submitted = st.form_submit_button("保存本地审阅记录")
        if submitted:
            try:
                record = HumanReviewRecord(
                    reviewed_at=datetime.now(UTC),
                    evidence_package_sha256=evidence_sha,
                    response_sha256=response_sha,
                    source_batch_id=package.source_batch_id,
                    anomaly_run_id=package.anomaly_run_id,
                    decision=decision,
                    reviewer_role=reviewer_role.strip(),
                    rationale=rationale.strip(),
                )
            except ValueError as error:
                st.error(f"未保存：{error}")
            else:
                REVIEW_DIRECTORY.mkdir(parents=True, exist_ok=True)
                output = (
                    REVIEW_DIRECTORY
                    / f"review_{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}.json"
                )
                output.write_text(
                    json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
                )
                st.success(f"已保存本地审阅记录：{output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
