"""Evidence strings must render as text rather than page markup."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_evidence_html_is_escaped_in_review_console(tmp_path: Path) -> None:
    payload = '<img src="https://example.invalid/leak"><b>untrusted</b> · 中文证据'
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "sample.json").write_text(
        json.dumps(
            {
                "package_version": "insight_evidence_v1",
                "generated_at": "2026-11-05T00:00:00Z",
                "source_batch_id": payload,
                "daily_metric_run_id": "daily",
                "anomaly_run_id": "anomaly",
                "metric_definition_version": "test",
                "anomaly_definition_version": "test",
                "statistical_anomaly_count": 0,
                "business_interpretable_anomaly_count": 0,
                "suppressed_anomaly_count": 0,
                "contribution_count": 0,
                "findings": [],
                "limitations": [payload],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = AppTest.from_string(
        "from pathlib import Path\n"
        "import streamlit_review_app as console\n"
        f"console.EVIDENCE_DIRECTORY = Path({str(evidence)!r})\n"
        f"console.REVIEW_DIRECTORY = Path({str(tmp_path / 'reviews')!r})\n"
        "console.main()\n"
    ).run()

    assert not app.exception
    markup = "\n".join(element.value for element in app.markdown)
    assert '<img src="https://example.invalid/leak">' not in markup
    assert "&lt;img" in markup
    assert "&lt;b&gt;untrusted&lt;/b&gt;" in markup
    assert "中文证据" in markup

    app.text_area[0].input("这是合成安全回归测试的审阅依据。")
    app.button[0].click().run()
    assert not app.exception
    records = list((tmp_path / "reviews").glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["rationale"] == "这是合成安全回归测试的审阅依据。"
    assert record["source_batch_id"] == payload
