from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_backtest.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_backtest", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_backtest script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_strategy_config_uses_base_when_no_override() -> None:
    module = load_script_module()
    base_config = {"timeframe": "15m", "entry_start_utc": "07:00"}

    resolved = module.resolve_strategy_config(
        base_config=base_config,
        config_json=None,
        config_file=None,
    )

    assert resolved == base_config
    assert resolved is not base_config


def test_resolve_strategy_config_accepts_config_json_override() -> None:
    module = load_script_module()

    resolved = module.resolve_strategy_config(
        base_config={"timeframe": "15m"},
        config_json=json.dumps({"timeframe": "1d", "fast_window": 20}),
        config_file=None,
    )

    assert resolved == {"timeframe": "1d", "fast_window": 20}


def test_resolve_strategy_config_accepts_config_file_override(tmp_path: Path) -> None:
    module = load_script_module()
    config_path = tmp_path / "override.yaml"
    config_path.write_text("timeframe: 1d\nfast_window: 20\n", encoding="utf-8")

    resolved = module.resolve_strategy_config(
        base_config={"timeframe": "15m"},
        config_json=None,
        config_file=str(config_path),
    )

    assert resolved == {"timeframe": "1d", "fast_window": 20}


def test_resolve_strategy_config_rejects_non_object_json() -> None:
    module = load_script_module()

    with pytest.raises(ValueError, match="JSON object"):
        module.resolve_strategy_config(
            base_config={"timeframe": "15m"},
            config_json='["not", "an", "object"]',
            config_file=None,
        )
