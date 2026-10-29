"""Especificación de publicación del Motor 3 (cuaderno 07).

Delega toda la maquinaria de sellado en engine_publication; aquí solo se
declara el EngineSpec del motor: raíz data/engines/07_motor3, puntero
audits/07_motor3_prescriptivo.json, conjunto exacto de outputs y el par
context_fn/identity_fn de m3_analysis.
"""
from pathlib import Path

from V3.src import engine_publication as ep
from V3.src import m3_analysis

REQUIRED_OUTPUTS = frozenset({
    "m3_flow_communities.csv", "m3_flow_summary.csv",
    "m3_runs.csv", "m3_ga_history.csv", "m3_ga_greedy.csv",
    "m3_portafolios.parquet", "m3_tradeoff.csv",
})

SPEC = ep.EngineSpec(
    tag="07_motor3",
    version=m3_analysis.VERSION,
    pointer="audits/07_motor3_prescriptivo.json",
    required_outputs=REQUIRED_OUTPUTS,
    context_fn=m3_analysis._upstream_context,
    identity_fn=m3_analysis.analysis_identity,
)


def stage_results(v3, data, result):
    return ep.stage_results(v3, SPEC, data, result)


def verify_report(v3, report_path):
    return ep.verify_report(v3, SPEC, report_path)


def activate_report(v3, report_path):
    return ep.activate_report(v3, SPEC, report_path)


def load_verified(v3):
    return ep.load_verified(v3, SPEC)
