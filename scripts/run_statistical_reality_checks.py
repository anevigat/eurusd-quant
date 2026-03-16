from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from eurusd_quant.research.statistical_reality_checks import run_reality_checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run R7 statistical reality checks on reset candidate patterns.")
    parser.add_argument(
        "--diagnostics-root",
        type=Path,
        default=Path("outputs/diagnostics"),
        help="Root directory containing prior R2–R6 diagnostics outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/diagnostics/statistical_reality_checks"),
        help="Directory to write the reality-check artifacts into.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = run_reality_checks(args.diagnostics_root)

    for name, value in artifacts.items():
        if name.endswith("_notes"):
            continue
        output_path = args.output_dir / f"{name}.csv"
        value.to_csv(output_path, index=False)

    notes_path = args.output_dir / "statistical_reality_notes.json"
    notes_path.write_text(json.dumps(artifacts["statistical_reality_notes"], indent=2) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
