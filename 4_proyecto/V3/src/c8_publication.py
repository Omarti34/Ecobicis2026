"""Especificación de publicación del cuaderno 08 (comparación).

Delega toda la maquinaria de sellado en engine_publication; aquí solo se
declara el EngineSpec: raíz data/engines/08_comparacion, puntero
audits/08_comparacion_portafolios.json, conjunto exacto de outputs y el
par context_fn/identity_fn de c8_analysis.
"""
from pathlib import Path

from V3.src import engine_publication as ep
from V3.src import c8_analysis

REQUIRED_OUTPUTS = frozenset({
    "c8_metricas.csv", "c8_radar.csv", "c8_overlap.csv",
    "c8_consensus.parquet", "c8_asignacion.csv",
    "c8_backtest_contexto.csv",
})

SPEC = ep.EngineSpec(
    tag="08_comparacion",
    version=c8_analysis.VERSION,
    pointer="audits/08_comparacion_portafolios.json",
    required_outputs=REQUIRED_OUTPUTS,
    context_fn=c8_analysis._upstream_context,
    identity_fn=c8_analysis.analysis_identity,
)


def stage_results(v3, data, result):
    return ep.stage_results(v3, SPEC, data, result)


def verify_report(v3, report_path):
    return ep.verify_report(v3, SPEC, report_path)


def activate_report(v3, report_path):
    return ep.activate_report(v3, SPEC, report_path)


def load_verified(v3):
    return ep.load_verified(v3, SPEC)
