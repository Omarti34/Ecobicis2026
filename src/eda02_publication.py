"""Publicación inmutable del reporte del cuaderno 02 (sin cálculos científicos).

stage_results materializa tablas etiquetadas y report.json bajo
data/eda/<contract_id>/<analysis_id>/ con preparación atómica y reutilización
verificada. activate_report promueve un reporte ya verificado a
audits/02_eda.json preservando el puntero anterior por contenido.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path

import numpy as np

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import VERSION, file_hash
from V3.src.eda02_urban import (
    enriched_analysis_identity as analysis_identity,
    input_specifications,
)

EDA_ROOT = "data/eda"
AUDIT_POINTER = "audits/02_eda.json"
AUDIT_ARCHIVE = "audits/02_eda_archive"
REPORT_RECORD = "report.json.sha256"
HEX64 = re.compile(r"[0-9a-f]{64}")

GOLDEN_CSV_COLUMNS = [
    "cvegeo", "nom_mun", "n_estaciones", "n_golden_stations",
    "golden_mean_daily_activity",
]
PARQUET_TABLES = {
    "golden_agebs": "golden_agebs",
    "environment": "station_environment",
    "agebs": "ageb_diagnostics",
    "population_by_ageb": "census_population_by_ageb",
    "modal_environment": "station_modal_environment",
}
CSV_TABLES = {
    "golden_agebs": "golden_agebs",
    "correlations": "correlations",
    "moran_sensitivity": "moran_sensitivity",
    "employment_sensitivity": "employment_sensitivity",
    "feature_coverage": "feature_coverage",
    "hourly_profile": "hourly_profile",
    "modal_correlations": "modal_correlations",
    "population_summary": "population_summary",
}


def _to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _reject_symlinks(v3, path):
    """Rechaza enlaces simbólicos a lo largo de la ruta de publicación."""
    current = path
    while current != v3.parent and current != current.parent:
        if current.is_symlink():
            raise ValueError("Symlinks are not allowed in publication paths")
        current = current.parent


def _record(path, final_dir):
    return {"path": f"{EDA_ROOT}/{final_dir.parent.name}/{final_dir.name}/{path.name}",
            "bytes": path.stat().st_size, "sha256": file_hash(path)}


def _input_records(audit, contract):
    """Registros únicos del audit activo para cada insumo lógico declarado."""
    records = {}
    for name, relative in input_specifications(contract).items():
        matches = [row for row in audit["outputs"] if row["path"] == relative]
        if len(matches) != 1:
            raise ValueError(f"ETL input artifact not unique: {relative}")
        records[name] = {"path": relative, "bytes": matches[0]["bytes"],
                         "sha256": matches[0]["sha256"]}
    return records


def _check_output_records(v3, report_dir, report):
    expected_dir = f"{EDA_ROOT}/{report_dir.parent.name}/{report_dir.name}"
    paths = [record["path"] for record in report["outputs"]]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate report output paths")
    declared = {REPORT_RECORD, "report.json"}
    for record in report["outputs"]:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts \
                or relative.parent.as_posix() != expected_dir:
            raise ValueError("Unregistered report output path")
        path = v3 / relative
        if path.is_symlink() or not path.is_file() \
                or path.stat().st_size != record["bytes"] \
                or file_hash(path) != record["sha256"]:
            raise ValueError(f"Report output missing or altered: {relative}")
        declared.add(relative.name)
    for entry in report_dir.iterdir():
        if entry.is_symlink() or entry.is_dir():
            raise ValueError("Unexpected link/directory in the report directory")
    actual = {p.name for p in report_dir.iterdir() if p.is_file()}
    if actual != declared:
        raise ValueError("Unexpected files in the published report directory")


def _verify_report_dir(v3, report_dir, contract, analysis_id, audit):
    """Verificación de solo lectura; devuelve el reporte ya validado."""
    _reject_symlinks(v3, report_dir)
    report_path = report_dir / "report.json"
    record_path = report_dir / REPORT_RECORD
    if not report_path.is_file() or not record_path.is_file():
        raise ValueError("Report directory is incomplete")
    if hashlib.sha256(report_path.read_bytes()).hexdigest() \
            != record_path.read_text().strip():
        raise ValueError("Cached report bytes do not match their commit record")
    report = json.loads(report_path.read_text())
    if report["contract_id"] != contract \
            or report["analysis_id"] != analysis_id \
            or report["schema_version"] != VERSION:
        raise ValueError("Report identity does not match the requested analysis")
    expected_id, expected_identity = analysis_identity(v3, contract)
    if analysis_id != expected_id:
        raise ValueError("Analysis identity no longer matches current code")
    if report.get("analysis_identity") != expected_identity:
        raise ValueError("Report analysis_identity does not match current code")
    if report.get("etl_audit_sha256") \
            != file_hash(v3 / "audits/01_etl.json"):
        raise ValueError("Report ETL audit hash does not match the active audit")
    inputs = report.get("input_artifacts", {})
    if inputs != _input_records(audit, contract):
        raise ValueError("Report input artifacts do not match the active audit")
    _check_output_records(v3, report_dir, report)
    return report


def stage_results(v3, data, result):
    """Publica tablas y reporte bajo data/eda/<contract>/<analysis_id>/.

    Devuelve la ruta del report.json inmutable. Si el directorio ya existe,
    reutiliza el resultado únicamente tras verificar su identidad y todas las
    huellas de salida; nunca sobrescribe ni borra contenido previo.
    """
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    if contract != data["audit"]["contract_id"]:
        raise ValueError("Analysis inputs do not match the committed ETL contract")
    analysis_id, identity = analysis_identity(v3, contract)

    target = v3 / EDA_ROOT / contract / analysis_id
    if target.exists():
        _verify_report_dir(v3, target, contract, analysis_id, audit)
        return target / "report.json"

    report = dict(result["report"])
    report["analysis_id"] = analysis_id
    report["analysis_identity"] = identity
    report["etl_audit_sha256"] = file_hash(v3 / "audits/01_etl.json")
    report["input_artifacts"] = _input_records(audit, contract)

    staging = target.parent / f".staging-{target.name}-{uuid.uuid4().hex[:12]}"
    _reject_symlinks(v3, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    tags = {"_etl_contract_id": contract, "_analysis_id": analysis_id}
    outputs = []
    for key, name in PARQUET_TABLES.items():
        path = staging / f"{name}.parquet"
        result[key].assign(**tags).to_parquet(path, index=False)
        outputs.append(_record(path, target))
    for key, name in CSV_TABLES.items():
        frame = result[key].assign(**tags)
        if key == "golden_agebs":
            frame = frame[GOLDEN_CSV_COLUMNS + list(tags)]
        path = staging / f"{name}.csv"
        frame.to_csv(path, index=False)
        outputs.append(_record(path, target))
    report["outputs"] = outputs
    payload = json.dumps(report, ensure_ascii=False, indent=2,
                         sort_keys=True, allow_nan=False,
                         default=_to_builtin).encode("utf-8")
    (staging / "report.json").write_bytes(payload)
    (staging / REPORT_RECORD).write_text(
        hashlib.sha256(payload).hexdigest() + "\n")
    if target.exists():
        raise ValueError("Report directory appeared during staging; refusing to overwrite")
    staging.rename(target)
    return target / "report.json"


def _canonical_report_path(v3, report_path):
    """Restringe el puntero a data/eda/<c>/<a>/report.json sin enlaces."""
    path = Path(report_path)
    if ".." in path.parts:
        raise ValueError("Report path must not contain '..'")
    if not path.is_absolute():
        path = v3 / path
    _reject_symlinks(v3, path)
    resolved = path.resolve()
    if resolved.parent.parent.parent != v3 / EDA_ROOT \
            or resolved.name != "report.json":
        raise ValueError("Report path outside the analysis publication root")
    contract, analysis_id = resolved.parent.parent.name, resolved.parent.name
    if not HEX64.fullmatch(contract) or not HEX64.fullmatch(analysis_id):
        raise ValueError("Noncanonical report directory names")
    return resolved, contract, analysis_id


def verify_report(v3, report_path):
    """Prechequeos de solo lectura antes de activar un reporte."""
    v3 = Path(v3).resolve()
    resolved, contract, analysis_id = _canonical_report_path(v3, report_path)
    audit = load_committed_audit(v3, verify=True)
    if audit["contract_id"] != contract:
        raise ValueError("Report contract is not the active ETL generation")
    return _verify_report_dir(v3, resolved.parent, contract, analysis_id, audit)


def activate_report(v3, report_path):
    """Publica audits/02_eda.json desde un reporte ya verificado.

    El puntero anterior se archiva por contenido bajo audits/02_eda_archive/
    si aún no estaba respaldado; el reemplazo es atómico.
    """
    v3 = Path(v3).resolve()
    resolved, _, _ = _canonical_report_path(v3, report_path)
    verify_report(v3, resolved)
    payload = resolved.read_bytes()

    pointer = v3 / AUDIT_POINTER
    if pointer.is_file():
        digest = hashlib.sha256(pointer.read_bytes()).hexdigest()
        backup = v3 / AUDIT_ARCHIVE / f"{digest}.json"
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(pointer.read_bytes())

    temp = pointer.with_name(pointer.name + f".tmp-{uuid.uuid4().hex[:12]}")
    temp.write_bytes(payload)
    temp.replace(pointer)
