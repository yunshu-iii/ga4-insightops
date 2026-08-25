from run_project_regression import validate_report_structure


def test_report_contract_does_not_require_local_generated_artifacts() -> None:
    artifact = {
        "surface": "report",
        "snapshot": {"status": "ready"},
        "sources": [{"id": "source-1"}],
        "manifest": {
            "surface": "report",
            "title": "Test report",
            "blocks": [
                {"type": "markdown", "body": "# Test report"},
                {"type": "chart", "chartId": "chart-1"},
                {"type": "table", "tableId": "table-1"},
            ],
            "cards": [{"id": "card-1", "sourceId": "source-1"}],
            "charts": [{"id": "chart-1", "sourceId": "source-1"}],
            "tables": [{"id": "table-1", "sourceId": "source-1"}],
        },
    }

    assert validate_report_structure(artifact, "test fixture") == {
        "blocks": 3,
        "cards": 1,
        "charts": 1,
        "tables": 1,
    }


def test_report_contract_allows_an_independent_full_batch_report() -> None:
    artifact = {
        "surface": "report",
        "snapshot": {"status": "ready"},
        "sources": [{"id": "full-daily"}, {"id": "full-anomaly"}],
        "manifest": {
            "surface": "report",
            "title": "Full GA4 report",
            "blocks": [
                {"type": "markdown", "body": "# Full GA4 report"},
                {"type": "metric-strip", "cardIds": ["coverage", "anomalies"]},
                {"type": "chart", "chartId": "coverage-trend"},
                {"type": "table", "tableId": "daily-audit"},
            ],
            "cards": [
                {"id": "coverage", "sourceId": "full-daily"},
                {"id": "anomalies", "sourceId": "full-anomaly"},
            ],
            "charts": [{"id": "coverage-trend", "sourceId": "full-daily"}],
            "tables": [{"id": "daily-audit", "sourceId": "full-daily"}],
        },
    }

    assert validate_report_structure(artifact, "full fixture")["blocks"] == 4
