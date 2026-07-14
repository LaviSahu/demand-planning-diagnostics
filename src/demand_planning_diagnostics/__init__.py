"""
demand_planning_diagnostics — a demand planner's diagnostic toolkit: is the
forecast actually adding value, and where is it worst?

Pure Python 3.10+ standard library. No dependencies, no network calls, no
API keys. `python -m demand_planning_diagnostics demo` generates a seeded
synthetic weekly demand history for a fictional FMCG maker ("Northwind
Foods"), segments every SKU by demand pattern (ADI/CV²), scores three
layered forecasts against a naive benchmark, computes Forecast Value Added
at each process step, and renders a single-file HTML dashboard.

See SPEC.md for the full design and DESIGN.md for the dashboard's visual
design.
"""

__version__ = "0.1.0"
