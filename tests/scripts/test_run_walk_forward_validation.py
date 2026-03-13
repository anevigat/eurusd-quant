from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_walk_forward_validation.py"
)


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_walk_forward_validation", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load walk-forward validation script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_config_requests_accepts_valid_parameter_neighborhood_json(tmp_path: Path) -> None:
    module = load_script_module()
    csv_path = tmp_path / "configs.csv"
    pd.DataFrame(
        [
            {
                "config_hash": "cfg_1",
                "param_alpha": 1,
                "parameter_neighborhood_json": json.dumps(
                    {"evaluated_neighbors": 5, "passing_neighbors": 4, "pass_rate": 0.8}
                ),
            }
        ]
    ).to_csv(csv_path, index=False)

    requests = module.load_config_requests(
        "session_breakout",
        {"session_breakout": {"timeframe": "15m"}},
        str(csv_path),
        None,
        base_metadata={},
    )

    assert len(requests) == 1
    assert requests[0].parameter_neighborhood == {"evaluated_neighbors": 5, "passing_neighbors": 4, "pass_rate": 0.8}
    assert requests[0].metadata["parameter_neighborhood"]["pass_rate"] == 0.8


def test_load_config_requests_missing_parameter_neighborhood_field_defaults_to_none(tmp_path: Path) -> None:
    module = load_script_module()
    csv_path = tmp_path / "configs.csv"
    pd.DataFrame([{"config_hash": "cfg_1", "param_alpha": 1}]).to_csv(csv_path, index=False)

    requests = module.load_config_requests(
        "session_breakout",
        {"session_breakout": {"timeframe": "15m"}},
        str(csv_path),
        None,
        base_metadata={},
    )

    assert requests[0].parameter_neighborhood is None


def test_load_config_requests_malformed_parameter_neighborhood_json_raises_clear_error(tmp_path: Path) -> None:
    module = load_script_module()
    csv_path = tmp_path / "configs.csv"
    pd.DataFrame(
        [{"config_hash": "cfg_bad", "param_alpha": 1, "parameter_neighborhood_json": "{\"bad\": "}],
    ).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match=r"parameter_neighborhood_json.*cfg_bad"):
        module.load_config_requests(
            "session_breakout",
            {"session_breakout": {"timeframe": "15m"}},
            str(csv_path),
            None,
            base_metadata={},
        )


def test_main_passes_cross_pair_flag_to_validation_layer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module()
    captured: list[dict] = []

    monkeypatch.setattr(module, "load_bars", lambda _path: pd.DataFrame({"timestamp": []}))
    monkeypatch.setattr(
        module,
        "load_yaml",
        lambda path: {"session_breakout": {"timeframe": "15m"}} if path.name == "strategies.yaml" else {"market_slippage_pips": 0.1, "stop_slippage_pips": 0.2, "fee_per_trade": 0.0},
    )
    monkeypatch.setattr(
        module,
        "run_walk_forward_validation",
        lambda **kwargs: captured.append(kwargs)
        or SimpleNamespace(
            config_hash="cfg",
            splits=[],
            splits_df=pd.DataFrame(),
            aggregate_metrics={"total_trades": 0, "profit_factor": 0.0},
            yearly_metrics=pd.DataFrame(),
            equity_curve=pd.DataFrame(),
            promotion_report={"decision": "continue"},
            stress_results={},
            oos_trades=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_walk_forward_validation.py",
            "--strategy",
            "session_breakout",
            "--bars",
            "dummy.parquet",
            "--output-dir",
            str(tmp_path / "out"),
            "--cross-pair-validated",
            "true",
        ],
    )

    module.main()

    assert captured[0]["metadata"]["cross_pair_validated"] is True
    assert captured[0]["parameter_neighborhood"] is None


def test_main_merges_file_metadata_and_csv_row_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_script_module()
    captured: list[dict] = []

    metadata_path = tmp_path / "promotion_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "cross_pair_validated": False,
                "parameter_neighborhood": {"evaluated_neighbors": 2, "passing_neighbors": 1, "pass_rate": 0.5},
                "source": "global",
            }
        ),
        encoding="utf-8",
    )
    csv_path = tmp_path / "configs.csv"
    pd.DataFrame(
        [
            {
                "config_hash": "cfg_override",
                "param_alpha": 1,
                "cross_pair_validated": True,
                "parameter_neighborhood_json": json.dumps(
                    {"evaluated_neighbors": 5, "passing_neighbors": 4, "pass_rate": 0.8}
                ),
            }
        ]
    ).to_csv(csv_path, index=False)

    monkeypatch.setattr(module, "load_bars", lambda _path: pd.DataFrame({"timestamp": []}))
    monkeypatch.setattr(
        module,
        "load_yaml",
        lambda path: {"session_breakout": {"timeframe": "15m"}} if path.name == "strategies.yaml" else {"market_slippage_pips": 0.1, "stop_slippage_pips": 0.2, "fee_per_trade": 0.0},
    )
    monkeypatch.setattr(
        module,
        "run_walk_forward_validation",
        lambda **kwargs: captured.append(kwargs)
        or SimpleNamespace(
            config_hash="cfg",
            splits=[],
            splits_df=pd.DataFrame(),
            aggregate_metrics={"total_trades": 0, "profit_factor": 0.0},
            yearly_metrics=pd.DataFrame(),
            equity_curve=pd.DataFrame(),
            promotion_report={"decision": "continue"},
            stress_results={},
            oos_trades=pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_walk_forward_validation.py",
            "--strategy",
            "session_breakout",
            "--bars",
            "dummy.parquet",
            "--output-dir",
            str(tmp_path / "out"),
            "--cross-pair-validated",
            "false",
            "--promotion-metadata-json",
            str(metadata_path),
            "--input-configs",
            str(csv_path),
        ],
    )

    module.main()

    assert captured[0]["metadata"]["cross_pair_validated"] is True
    assert captured[0]["metadata"]["source"] == "global"
    assert captured[0]["parameter_neighborhood"] == {"evaluated_neighbors": 5, "passing_neighbors": 4, "pass_rate": 0.8}
