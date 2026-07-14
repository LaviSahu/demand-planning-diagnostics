"""
cli.py — the `python -m demand_planning_diagnostics` command-line interface.

Five subcommands, each a thin wrapper over the engine modules:

    segment                   generate/load history -> SBC segmentation (console + JSON)
    accuracy                  segmentation -> per-SKU/per-layer accuracy scorecard
    fva                       accuracy -> Forecast Value Added at sku/segment/overall levels
    demo                      full pipeline: datagen -> segment -> accuracy -> fva -> kpi -> dashboard
    dashboard                 rebuild output/dashboard.html from persisted data/*.json

Console tables are hand-rolled (aligned, ANSI-colored on a real tty) rather
than pulling in a table-formatting dependency, in keeping with the
stdlib-only constraint.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import accuracy, dashboard, datagen, fva, kpi, segment
from .models import ForecastLayer, jsonable

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # src/demand_planning_diagnostics/.. -> repo root


def _resolve(path_str: str, fallback_under_root: str) -> Path:
    """Prefer a path relative to cwd; fall back to the repo root so the
    CLI works whether invoked from the repo root or elsewhere."""
    p = Path(path_str)
    if p.exists():
        return p
    fallback = _PACKAGE_ROOT / fallback_under_root
    return fallback if fallback.exists() else p


def _default_data_dir() -> str:
    return str(_resolve("data", "data"))


def _default_output_dir() -> str:
    p = Path("output")
    if p.exists():
        return str(p)
    return str(_PACKAGE_ROOT / "output")


# --------------------------------------------------------------------------
# ANSI console table helpers
# --------------------------------------------------------------------------

_RESET = "\033[0m"
_GOOD = "\033[0;32m"
_BAD = "\033[1;31m"
_SEG_COLORS = {
    "smooth": "\033[0;32m",
    "erratic": "\033[0;33m",
    "intermittent": "\033[0;34m",
    "lumpy": "\033[1;31m",
}


def _use_color() -> bool:
    return sys.stdout.isatty()


def _colorize(text: str, code: Optional[str]) -> str:
    if not code or not _use_color():
        return text
    return f"{code}{text}{_RESET}"


def _print_table(headers: list[str], rows: list[list[str]], color_col: Optional[int] = None,
                  color_fn=None) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str], colorize: bool) -> str:
        parts = []
        for i, cell in enumerate(cells):
            padded = cell.ljust(widths[i])
            if colorize and color_col is not None and i == color_col and color_fn is not None:
                padded = _colorize(padded, color_fn(cell.strip()))
            parts.append(padded)
        return "  ".join(parts)

    print(fmt(headers, colorize=False))
    print(fmt(["-" * w for w in widths], colorize=False))
    for row in rows:
        print(fmt(row, colorize=True))


def _seg_color(cell: str) -> Optional[str]:
    return _SEG_COLORS.get(cell.lower())


def _sign_color(cell: str) -> Optional[str]:
    try:
        val = float(cell.replace("+", "").replace("pp", "").strip())
    except ValueError:
        return None
    return _GOOD if val >= 0 else _BAD


def _print_segment_table(catalog, assignments: list, limit: int = 15) -> None:
    sku_by_id = {s.id: s for s in catalog.skus}
    headers = ["SKU", "TRUE", "COMPUTED", "ADI", "CV2", "VOL%"]
    rows = []
    for a in assignments[:limit]:
        sku = sku_by_id[a.sku_id]
        adi_str = "inf" if a.adi == float("inf") else f"{a.adi:.2f}"
        rows.append(
            [a.sku_id, sku.archetype.value, a.segment.value, adi_str, f"{a.cv2:.2f}", f"{a.volume_share * 100:.2f}"]
        )
    _print_table(headers, rows, color_col=2, color_fn=_seg_color)
    if len(assignments) > limit:
        print(f"... and {len(assignments) - limit} more (see data/segments.json)")


def _print_accuracy_summary(history, catalog) -> None:
    headers = ["LAYER", "WMAPE%", "BIAS", "TRACKING_SIGNAL"]
    rows = []
    sku_ids = catalog.sku_ids()
    for layer in ForecastLayer:
        pooled = []
        for sku_id in sku_ids:
            pooled.extend(accuracy.eval_pairs(history.for_sku(sku_id), layer))
        w = accuracy.wmape(pooled)
        b = accuracy.bias(pooled)
        ts = accuracy.tracking_signal(pooled)
        rows.append([layer.value, f"{w:.2f}", f"{b:.2f}", f"{ts:.2f}" if ts is not None else "n/a"])
    _print_table(headers, rows)


def _print_fva_stairstep(results: list, level: str, key_filter: Optional[str] = None) -> None:
    headers = ["LEVEL", "KEY", "FROM", "TO", "WMAPE_FROM", "WMAPE_TO", "FVA(pp)", "FVA%"]
    rows = []
    for r in results:
        if r.level != level:
            continue
        if key_filter is not None and r.key != key_filter:
            continue
        rows.append(
            [
                r.level, r.key, r.from_layer.value, r.to_layer.value,
                f"{r.wmape_from:.2f}", f"{r.wmape_to:.2f}", f"{r.fva:+.2f}", f"{r.fva_pct:+.1f}",
            ]
        )
    _print_table(headers, rows, color_col=6, color_fn=_sign_color)


def _print_worst_overrides(worst: list, catalog, limit: int = 15) -> None:
    if not worst:
        print("(no SKUs where the consensus override hurt accuracy)")
        return
    sku_by_id = {s.id: s for s in catalog.skus}
    headers = ["SKU", "NAME", "WMAPE_STAT", "WMAPE_CONSENSUS", "FVA(pp)"]
    rows = []
    for r in worst[:limit]:
        sku = sku_by_id[r.key]
        rows.append([r.key, sku.name[:28], f"{r.wmape_from:.2f}", f"{r.wmape_to:.2f}", f"{r.fva:+.2f}"])
    _print_table(headers, rows, color_col=4, color_fn=_sign_color)
    if len(worst) > limit:
        print(f"... and {len(worst) - limit} more")


def _print_kpi_summary(kpis: dict) -> None:
    headers = ["KPI", "VALUE", "UNIT", "CONTEXT"]
    rows = [[k.label, f"{k.value:,.3f}", k.unit, k.context] for k in kpis.values()]
    _print_table(headers, rows)


# --------------------------------------------------------------------------
# Shared pipeline steps
# --------------------------------------------------------------------------


def _ensure_dataset(data_dir: str, seed: int, regenerate: bool = False):
    dp = Path(data_dir)
    skus_path = dp / "skus.json"
    history_path = dp / "history.json"
    if regenerate or not (skus_path.exists() and history_path.exists()):
        datagen.write_dataset(dp, seed=seed)
    return datagen.load_dataset(dp)


def _run_full_pipeline(data_dir: str, output_dir: str, seed: int, verbose: bool = True) -> dict:
    out_dir = Path(output_dir)
    catalog, history = _ensure_dataset(data_dir, seed, regenerate=True)
    if verbose:
        print(f"Generated -> {len(catalog.skus)} SKUs x {len({r.week for r in history.records})} weeks (seed={seed})\n")

    assignments = segment.segment_history(catalog, history)
    segment.write_segments(assignments, Path(data_dir) / "segments.json")
    recovery = segment.segment_recovery_rate(catalog, assignments)
    if verbose:
        print(f"Segmentation (recovery rate vs. true archetype: {recovery * 100:.1f}%):")
        _print_segment_table(catalog, assignments)
        print()

    all_accuracy = accuracy.compute_all_accuracy(history, catalog)
    (Path(data_dir) / "accuracy.json").write_text(
        json.dumps([jsonable(a) for a in all_accuracy], indent=2), encoding="utf-8"
    )
    if verbose:
        print("Accuracy (pooled across full portfolio):")
        _print_accuracy_summary(history, catalog)
        print()

    all_fva = fva.compute_all_fva(history, catalog, assignments)
    (Path(data_dir) / "fva.json").write_text(
        json.dumps([jsonable(r) for r in all_fva], indent=2), encoding="utf-8"
    )
    worst = fva.skus_where_overrides_hurt([r for r in all_fva if r.level == "sku"])
    if verbose:
        print("FVA — overall portfolio stairstep:")
        _print_fva_stairstep(all_fva, "overall")
        print("\nFVA — by segment:")
        _print_fva_stairstep(all_fva, "segment")
        print("\nWorst manual overrides (consensus vs. statistical):")
        _print_worst_overrides(worst, catalog)
        print()

    kpis = kpi.compute_kpis(
        history, catalog, assignments, [r for r in all_fva if r.level == "sku"],
        [r for r in all_fva if r.level == "overall"],
    )
    if verbose:
        print("KPI summary:")
        _print_kpi_summary(kpis)

    generated_at = datetime.now(timezone.utc).isoformat()
    context = dashboard.build_context(
        catalog, history, assignments, recovery, all_fva, worst, kpis, generated_at
    )
    dashboard_path = out_dir / "dashboard.html"
    dashboard.render_dashboard(context, dashboard_path)
    if verbose:
        print(f"\nDashboard written -> {dashboard_path}")
    return context


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def cmd_segment(args: argparse.Namespace) -> None:
    catalog, history = _ensure_dataset(args.data, args.seed)
    assignments = segment.segment_history(catalog, history)
    out_path = Path(args.data) / "segments.json"
    segment.write_segments(assignments, out_path)
    recovery = segment.segment_recovery_rate(catalog, assignments)
    print(f"Segmented {len(assignments)} SKUs -> {out_path}  (recovery rate: {recovery * 100:.1f}%)\n")
    _print_segment_table(catalog, assignments)


def cmd_accuracy(args: argparse.Namespace) -> None:
    catalog, history = _ensure_dataset(args.data, args.seed)
    all_accuracy = accuracy.compute_all_accuracy(history, catalog)
    out_path = Path(args.data) / "accuracy.json"
    out_path.write_text(json.dumps([jsonable(a) for a in all_accuracy], indent=2), encoding="utf-8")
    print(f"Scored {len(all_accuracy)} (sku, layer) accuracy rows -> {out_path}\n")
    _print_accuracy_summary(history, catalog)


def cmd_fva(args: argparse.Namespace) -> None:
    catalog, history = _ensure_dataset(args.data, args.seed)
    assignments = segment.segment_history(catalog, history)
    all_fva = fva.compute_all_fva(history, catalog, assignments)
    out_path = Path(args.data) / "fva.json"
    out_path.write_text(json.dumps([jsonable(r) for r in all_fva], indent=2), encoding="utf-8")
    print(f"Computed {len(all_fva)} FVA rows -> {out_path}\n")
    print("Overall portfolio stairstep:")
    _print_fva_stairstep(all_fva, "overall")
    print("\nBy segment:")
    _print_fva_stairstep(all_fva, "segment")
    worst = fva.skus_where_overrides_hurt([r for r in all_fva if r.level == "sku"])
    print("\nWorst manual overrides:")
    _print_worst_overrides(worst, catalog)


def cmd_demo(args: argparse.Namespace) -> None:
    _run_full_pipeline(args.data, args.output, args.seed)


def cmd_dashboard(args: argparse.Namespace) -> None:
    catalog, history = _ensure_dataset(args.data, args.seed)
    assignments = segment.segment_history(catalog, history)
    recovery = segment.segment_recovery_rate(catalog, assignments)
    all_fva = fva.compute_all_fva(history, catalog, assignments)
    worst = fva.skus_where_overrides_hurt([r for r in all_fva if r.level == "sku"])
    kpis = kpi.compute_kpis(
        history, catalog, assignments, [r for r in all_fva if r.level == "sku"],
        [r for r in all_fva if r.level == "overall"],
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    context = dashboard.build_context(catalog, history, assignments, recovery, all_fva, worst, kpis, generated_at)
    out_path = Path(args.output) / "dashboard.html"
    dashboard.render_dashboard(context, out_path)
    print(f"Dashboard rebuilt from persisted data -> {out_path}")


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="demand_planning_diagnostics", description="Demand planning diagnostics: segmentation, accuracy, FVA"
    )
    parser.add_argument("--data", default=None, help="path to data directory")
    parser.add_argument("--output", default=None, help="output directory")
    parser.add_argument("--seed", type=int, default=datagen.DEFAULT_SEED, help="RNG seed for the synthetic dataset")

    sub = parser.add_subparsers(dest="command", required=True)

    p_segment = sub.add_parser("segment", help="generate/load history -> SBC segmentation")
    p_segment.set_defaults(func=cmd_segment)

    p_accuracy = sub.add_parser("accuracy", help="segmentation -> per-SKU/layer accuracy scorecard")
    p_accuracy.set_defaults(func=cmd_accuracy)

    p_fva = sub.add_parser("fva", help="accuracy -> Forecast Value Added at sku/segment/overall levels")
    p_fva.set_defaults(func=cmd_fva)

    p_demo = sub.add_parser("demo", help="full pipeline: datagen -> segment -> accuracy -> fva -> kpi -> dashboard")
    p_demo.set_defaults(func=cmd_demo)

    p_dash = sub.add_parser("dashboard", help="rebuild output/dashboard.html from persisted data/*.json")
    p_dash.set_defaults(func=cmd_dashboard)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.data = args.data or _default_data_dir()
    args.output = args.output or _default_output_dir()

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
