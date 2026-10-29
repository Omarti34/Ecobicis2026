"""Especificación de publicación del cuaderno 09 (registro de claims).

Delega toda la maquinaria de sellado en engine_publication; aquí solo se
declara el EngineSpec: raíz data/engines/09_claims, puntero
audits/09_final_claims_registry.json (el reporte sellado ES el
registro), conjunto exacto de outputs y el par context_fn/identity_fn
de c9_analysis. También vive `publish_docs_copy`, que copia el
documento sellado a docs/TESIS_DATA_POINTS.md de forma atómica después
del sellado.
"""
import os
import uuid
from pathlib import Path

from V3.src import engine_publication as ep
from V3.src import c9_analysis

REQUIRED_OUTPUTS = frozenset({
    "c9_claims.csv", "c9_lineage.csv", "TESIS_DATA_POINTS.md",
})

SPEC = ep.EngineSpec(
    tag="09_claims",
    version=c9_analysis.VERSION,
    pointer="audits/09_final_claims_registry.json",
    required_outputs=REQUIRED_OUTPUTS,
    context_fn=c9_analysis._upstream_context,
    identity_fn=c9_analysis.analysis_identity,
)


def stage_results(v3, data, result):
    return ep.stage_results(v3, SPEC, data, result)


def verify_report(v3, report_path):
    return ep.verify_report(v3, SPEC, report_path)


def activate_report(v3, report_path):
    return ep.activate_report(v3, SPEC, report_path)


def load_verified(v3):
    return ep.load_verified(v3, SPEC)


def publish_docs_copy(v3, report, docs_path=None):
    """Copia atómica del documento sellado a docs/TESIS_DATA_POINTS.md.

    Se llama DESPUÉS del sellado: lee el output TESIS_DATA_POINTS.md del
    directorio del reporte y lo escribe en `docs_path` (por defecto
    CONFIG["docs_target"] relativo a la raíz del proyecto). Si el
    archivo ya existe con bytes distintos, aborta —la divergencia se
    reporta, nunca se sobrescribe en silencio—; si existe con los mismos
    bytes, no hace nada.
    """
    v3 = Path(v3).resolve()
    record = [r for r in report["outputs"]
              if r["path"].endswith("/TESIS_DATA_POINTS.md")]
    if len(record) != 1:
        raise ValueError("Reporte 09 sin output TESIS_DATA_POINTS.md")
    sealed = v3 / record[0]["path"]
    payload = sealed.read_bytes()
    import hashlib
    if hashlib.sha256(payload).hexdigest() \
            != report["document"]["sha256"]:
        raise ValueError("El documento sellado no coincide con el sha "
                         "registrado en el reporte")
    target = (v3.parent / c9_analysis.CONFIG["docs_target"]
              if docs_path is None else Path(docs_path))
    if target.exists():
        prior = target.read_bytes()
        if prior != payload:
            raise ValueError(
                f"{target} ya existe con contenido distinto del "
                "documento sellado; divergencia reportada, no se "
                "sobrescribe")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + f".tmp-{uuid.uuid4().hex[:12]}")
    temp.write_bytes(payload)
    os.replace(temp, target)
    return target
