"""Run the restricted Insight Agent against an existing evidence package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from insight_agent import EvidencePackage, answer_from_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-package", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    package = EvidencePackage.model_validate_json(arguments.evidence_package.read_text())
    response = answer_from_evidence(arguments.question, package)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Insight response written: {arguments.output}; claims={len(response.claims)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
