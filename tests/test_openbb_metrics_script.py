"""Tests for OpenBB metrics dry-run script (no network, no OpenBB install)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.portfolio.metrics_builder import DEFAULT_PRICE_PATH

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = DEFAULT_PRICE_PATH


def test_default_paths():
    from scripts import build_openbb_metrics as script

    assert script.DEFAULT_INPUT_PATH == (
        ROOT / "data" / "processed" / "openbb_price_history_aligned.csv"
    )
    assert script.DEFAULT_OUTPUT_PATH == ROOT / "output" / "openbb_metrics_snapshot.json"
    assert "data/processed" in script.DEFAULT_INPUT_PATH.as_posix()
    assert "output" in script.DEFAULT_OUTPUT_PATH.as_posix()


def test_missing_input_exits_nonzero(tmp_path, capsys):
    from scripts import build_openbb_metrics as script

    missing = tmp_path / "no_openbb.csv"
    with pytest.raises(SystemExit) as exc:
        script.main(input_path=missing, output_path=tmp_path / "out.json")
    assert exc.value.code == 1
    captured = capsys.readouterr().out
    assert script.MISSING_INPUT_MESSAGE in captured
    assert "fetch_openbb_prices.py" in captured
    assert "process_openbb_prices.py" in captured


def test_builds_output_from_openbb_source_csv(tmp_path):
    from scripts import build_openbb_metrics as script

    df = pd.read_csv(SAMPLE_CSV)
    df["source"] = "openbb_yfinance"
    in_path = tmp_path / "openbb_prices.csv"
    out_path = tmp_path / "openbb_metrics_snapshot.json"
    df.to_csv(in_path, index=False)

    script.main(input_path=in_path, output_path=out_path)

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["data_source"] == "openbb_yfinance_computed_from_prices"
    assert len(payload["metrics"]) >= 20
    assert payload["as_of_date"]


def test_build_script_blocks_incomplete_official_eod_panel(tmp_path, capsys):
    from scripts import build_openbb_metrics as script

    df = pd.read_csv(SAMPLE_CSV)
    df["source"] = "openbb_yfinance"
    bad = df.drop(index=df.index[0]).copy()
    in_path = tmp_path / "incomplete_openbb_prices.csv"
    out_path = tmp_path / "openbb_metrics_snapshot.json"
    bad.to_csv(in_path, index=False)

    with pytest.raises(SystemExit) as exc:
        script.main(input_path=in_path, output_path=out_path)

    assert exc.value.code == 1
    assert not out_path.exists()
    captured = capsys.readouterr().out
    assert "official_eod_quality_gate: fail" in captured
    assert "check_openbb_data_quality.py" in captured
