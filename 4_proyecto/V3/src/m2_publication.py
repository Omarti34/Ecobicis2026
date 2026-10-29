"""Especificación de publicación del Motor 2 (cuaderno 06).

Delega toda la maquinaria de sellado en engine_publication; aquí solo se
declara el EngineSpec del motor: raíz data/engines/06_motor2, puntero
audits/06_motor2_transformer.json, conjunto exacto de outputs y el par
context_fn/identity_fn de m2_analysis.
"""
from pathlib import Path

from V3.src import engine_publication as ep
from V3.src import m2_analysis

REQUIRED_OUTPUTS = frozenset({
    "m2_cv_predictions.parquet", "m2_cv_metrics.csv",
    "m2_ranking_metrics.csv", "m2_learning_curve.csv",
    "m2_permutation_importance.csv", "m2_training_curves.csv",
    "m2_candidate_predictions.parquet", "m2_portafolios.parquet",
    "m2_ceiling_backtest.csv",
    "m2_final_models.joblib",
})

SPEC = ep.EngineSpec(
    tag="06_motor2",
    version=m2_analysis.VERSION,
    pointer="audits/06_motor2_transformer.json",
    required_outputs=REQUIRED_OUTPUTS,
    context_fn=m2_analysis._upstream_context,
    identity_fn=m2_analysis.analysis_identity,
)


def stage_results(v3, data, result):
    return ep.stage_results(v3, SPEC, data, result)


def verify_report(v3, report_path):
    return ep.verify_report(v3, SPEC, report_path)


def activate_report(v3, report_path):
    return ep.activate_report(v3, SPEC, report_path)


def load_verified(v3):
    return ep.load_verified(v3, SPEC)
