from datetime import date
import importlib.util
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / "scripts/import_accidents.py"
spec = importlib.util.spec_from_file_location("import_date_filter", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def row(day, order):
    fields = [""] * len(module.COLS)
    fields[module.I["發生日期"]] = day
    fields[module.I["當事者順位"]] = str(order)
    return fields


def test_date_filter_keeps_whole_accidents_and_includes_first_day():
    rows = [row("20260501", 1), row("20260501", 2), row("20260502", 1), row("20260502", 2)]
    assert module.rows_since(rows, date(2026, 5, 2)) == rows[2:]


def test_no_filter_retains_original_rows():
    rows = [row("20260501", 1)]
    assert module.rows_since(rows, None) is rows


def test_filter_does_not_require_sorted_input():
    rows = [row("20260503", 1), row("20260501", 1), row("20260502", 1)]
    assert module.rows_since(rows, date(2026, 5, 2)) == [rows[0], rows[2]]
