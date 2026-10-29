"""Especificación de publicación del Motor 1 (cuaderno 05).

Delega toda la maquinaria de sellado en engine_publication; aquí solo se
declara el EngineSpec del motor: raíz data/engines/05_motor1, puntero
audits/05_motor1_baseline.json, conjunto exacto de outputs y el par
context_fn/identity_fn de m1_analysis.
"""
from pathlib import Path

from V3.src import engine_publication as ep
from V3.src import m1_analysis

REQUIRED_OUTPUTS = frozenset({
    "m1_backtest_detail.csv", "m1_backtest_summary.csv",
    "m1_decisions.parquet", "m1_fold_diagnostics.csv",
    "m1_sensitivity.csv", "m1_ranking_candidatas.parquet",
    "m1_reference.csv", "m1_portafolios.parquet",
    "m1_ceiling_backtest.csv",
    "m1_pipeline.joblib",
})

SPEC = ep.EngineSpec(
    tag="05_motor1",
    version=m1_analysis.VERSION,
    pointer="audits/05_motor1_baseline.json",
    required_outputs=REQUIRED_OUTPUTS,
    context_fn=m1_analysis._upstream_context,
    identity_fn=m1_analysis.analysis_identity,
)


def stage_results(v3, data, result):
    return ep.stage_results(v3, SPEC, data, result)


def verify_report(v3, report_path):
    return ep.verify_report(v3, SPEC, report_path)


def activate_report(v3, report_path):
    return ep.activate_report(v3, SPEC, report_path)


def load_verified(v3):
    return ep.load_verified(v3, SPEC)
