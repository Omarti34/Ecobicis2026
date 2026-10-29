"""Publicación inmutable del reporte del cuaderno 03 (sin cálculos científicos).

stage_results materializa tablas etiquetadas, el pipeline serializado y
report.json bajo data/features/<contract_id>/<analysis_id>/ con preparación
atómica y reutilización verificada. activate_report promueve un reporte ya
verificado a audits/03_feature_engineering.json preservando el puntero
anterior por contenido. load_feature_pipeline solo carga el joblib tras
verificar directorio, bytes y hashes.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path

import joblib
import numpy as np
from sklearn.pipeline import Pipeline

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src.eda02_publication import verify_report as verify_eda_report
from V3.src.fe03_analysis import (
    INPUT_COLUMNS,
    INPUTS,
    VERSION,
    analysis_identity,
)

FEATURES_ROOT = "data/features"
AUDIT_POINTER = "audits/03_feature_engineering.json"
AUDIT_ARCHIVE = "audits/03_feature_engineering_archive"
EDA_POINTER = "audits/02_eda.json"
REPORT_RECORD = "report.json.sha256"
PIPELINE_OUTPUT = "pca_pipeline.joblib"
HEX64 = re.compile(r"[0-9a-f]{64}")
PC_NAME = re.compile(r"PC\d+")

ADDED_KEYS = {
    "analysis_id", "analysis_identity", "etl_audit_sha256",
    "eda_audit_sha256", "eda_report_path", "eda_analysis_id",
    "input_artifacts", "outputs",
}

PARQUET_TABLES = {
    "features": ("entorno_ageb_features", False),
    "scores": ("pca_espacio_compartido", False),
    "loadings": ("pca_loadings", True),
    "centroid": ("golden_centroid", False),
}
CSV_TABLES = {
    "maup_sensitivity": "maup_sensitivity",
}
REQUIRED_OUTPUTS = frozenset(
    [f"{name}.parquet" for name, _ in PARQUET_TABLES.values()]
    + [f"{name}.csv" for name in CSV_TABLES.values()]
    + [PIPELINE_OUTPUT])


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
    return {"path": f"{FEATURES_ROOT}/{final_dir.parent.name}/{final_dir.name}/{path.name}",
            "bytes": path.stat().st_size, "sha256": file_hash(path)}


def _context(v3):
    """Contexto de identidad desde auditorías, sin cargar frames analíticos.

    Reutiliza el lector ETL y el verificador del reporte 02 vigente; la
    identidad solo es válida si ETL y EDA activos coinciden con los insumos
    congelados del análisis.
    """
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    pointer = v3 / EDA_POINTER
    pointer_bytes = pointer.read_bytes()
    eda = json.loads(pointer_bytes)
    if eda["contract_id"] != contract:
        raise ValueError("EDA pointer belongs to another ETL contract")
    eda_path = v3 / "data/eda" / contract / eda["analysis_id"] / "report.json"
    committed_eda = verify_eda_report(v3, eda_path)
    if eda != committed_eda or pointer.read_bytes() != pointer_bytes:
        raise ValueError("EDA pointer is not the verified report or changed")
    records = {}
    for name in INPUTS:
        relative = f"data/processed/{contract}/{name}.parquet"
        matches = [row for row in audit["outputs"] if row["path"] == relative]
        if len(matches) != 1:
            raise ValueError(f"ETL input artifact not unique: {relative}")
        records[name] = {key: matches[0][key]
                         for key in ["path", "bytes", "sha256"]}
    return {
        "audit": audit, "eda": eda, "input_artifacts": records,
        "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(pointer_bytes).hexdigest(),
        "eda_report_path": eda_path.relative_to(v3).as_posix(),
    }


def _check_output_records(v3, report_dir, report):
    expected_dir = f"{FEATURES_ROOT}/{report_dir.parent.name}/{report_dir.name}"
    paths = [record["path"] for record in report["outputs"]]
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate report output paths")
    declared = {REPORT_RECORD, "report.json"}
    for record in report["outputs"]:
        relative = Path(record["path"])
        if relative.as_posix() != record["path"]:
            raise ValueError("Noncanonical report output path string")
        if relative.is_absolute() or ".." in relative.parts \
                or relative.parent.as_posix() != expected_dir:
            raise ValueError("Unregistered report output path")
        path = v3 / relative
        if path.is_symlink() or not path.is_file() \
                or path.stat().st_size != record["bytes"] \
                or file_hash(path) != record["sha256"]:
            raise ValueError(f"Report output missing or altered: {relative}")
        declared.add(relative.name)
    basenames = {Path(record["path"]).name for record in report["outputs"]}
    if basenames != REQUIRED_OUTPUTS:
        raise ValueError("Report outputs do not match the required artifact set")
    for entry in report_dir.iterdir():
        if entry.is_symlink() or entry.is_dir():
            raise ValueError("Unexpected link/directory in the report directory")
    actual = {p.name for p in report_dir.iterdir() if p.is_file()}
    if actual != declared:
        raise ValueError("Unexpected files in the published report directory")


def _verify_report_dir(v3, report_dir, contract, analysis_id, context):
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
    expected_id, expected_identity = analysis_identity(v3, context)
    if analysis_id != expected_id:
        raise ValueError("Analysis identity drifted from current code/sources")
    if report.get("analysis_identity") != expected_identity:
        raise ValueError("Report analysis_identity drifted from current context")
    if report.get("etl_audit_sha256") != context["etl_audit_sha256"]:
        raise ValueError("Report ETL audit hash does not match the active audit")
    if report.get("eda_audit_sha256") != context["eda_audit_sha256"] \
            or report.get("eda_analysis_id") != context["eda"]["analysis_id"] \
            or report.get("eda_report_path") != context["eda_report_path"]:
        raise ValueError("Report EDA reference no longer matches the active report")
    if report.get("input_artifacts", {}) != context["input_artifacts"]:
        raise ValueError("Report input artifacts do not match the active audit")
    _check_output_records(v3, report_dir, report)
    return report


def _scientific_report(report):
    return {key: value for key, value in report.items() if key not in ADDED_KEYS}


def _verify_key_binding(result):
    """Las tablas publicadas deben referirse a las mismas AGEBs en el mismo orden."""
    features, scores = result["features"], result["scores"]
    if not features["cvegeo"].is_unique or not scores["cvegeo"].is_unique:
        raise ValueError("Non-unique AGEB keys in features/scores")
    if list(features["cvegeo"]) != list(scores["cvegeo"]):
        raise ValueError("Feature and score AGEB keys are misbound or permuted")
    if not np.array_equal(
            features["is_projectable"].astype(bool).to_numpy(),
            scores["is_projectable"].astype(bool).to_numpy()):
        raise ValueError("Projectable masks differ between features and scores")


def _verify_serialized_pipeline(result, joblib_path):
    """El joblib escrito debe reproducir los scores publicados al 1e-10."""
    pc_names = [name for name in result["scores"].columns
                if PC_NAME.fullmatch(str(name))]
    if not pc_names:
        raise ValueError("Score table lacks PC columns")
    features, scores = result["features"], result["scores"]
    valid = features["is_projectable"].astype(bool)
    pipeline = joblib.load(joblib_path)
    projected = pipeline.transform(features.loc[valid, INPUT_COLUMNS])
    expected = scores.loc[valid, pc_names].to_numpy(dtype=float)
    if not np.allclose(projected, expected, rtol=0, atol=1e-10):
        raise ValueError("Serialized pipeline does not reproduce published scores")


def stage_results(v3, data, result):
    """Publica tablas, pipeline y reporte bajo data/features/<c>/<a>/.

    Devuelve la ruta del report.json inmutable. Si el directorio ya existe,
    reutiliza el resultado únicamente tras verificar su identidad, todas las
    huellas y que su reporte científico coincide con result["report"];
    nunca sobrescribe ni borra contenido previo.
    """
    v3 = Path(v3).resolve()
    context = _context(v3)
    audit = context["audit"]
    contract = audit["contract_id"]
    if contract != data["audit"]["contract_id"]:
        raise ValueError("Analysis inputs do not match the committed ETL contract")
    analysis_id, identity = analysis_identity(v3, context)
    if analysis_id != data["analysis_id"] \
            or identity != data["analysis_identity"]:
        raise ValueError("Frozen analysis identity no longer matches current context")
    _verify_key_binding(result)

    target = v3 / FEATURES_ROOT / contract / analysis_id
    if target.exists():
        cached = _verify_report_dir(v3, target, contract, analysis_id, context)
        if _scientific_report(cached) != result["report"]:
            raise ValueError("Cached report differs from the computed result")
        return target / "report.json"

    report = dict(result["report"])
    report["analysis_id"] = analysis_id
    report["analysis_identity"] = identity
    report["etl_audit_sha256"] = context["etl_audit_sha256"]
    report["eda_audit_sha256"] = context["eda_audit_sha256"]
    report["eda_report_path"] = context["eda_report_path"]
    report["eda_analysis_id"] = context["eda"]["analysis_id"]
    report["input_artifacts"] = context["input_artifacts"]

    staging = target.parent / f".staging-{target.name}-{uuid.uuid4().hex[:12]}"
    _reject_symlinks(v3, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    tags = {"_etl_contract_id": contract, "_analysis_id": analysis_id}
    outputs = []
    for key, (name, keep_index) in PARQUET_TABLES.items():
        path = staging / f"{name}.parquet"
        result[key].assign(**tags).to_parquet(path, index=keep_index)
        outputs.append(_record(path, target))
    for key, name in CSV_TABLES.items():
        path = staging / f"{name}.csv"
        result[key].assign(**tags).to_csv(path, index=False)
        outputs.append(_record(path, target))
    pipeline_path = staging / PIPELINE_OUTPUT
    joblib.dump(result["pipeline"], pipeline_path)
    outputs.append(_record(pipeline_path, target))
    _verify_serialized_pipeline(result, pipeline_path)

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
    """Restringe el puntero a data/features/<c>/<a>/report.json sin enlaces."""
    path = Path(report_path)
    if ".." in path.parts:
        raise ValueError("Report path must not contain '..'")
    if not path.is_absolute():
        path = v3 / path
    _reject_symlinks(v3, path)
    resolved = path.resolve()
    if resolved.parent.parent.parent != v3 / FEATURES_ROOT \
            or resolved.name != "report.json":
        raise ValueError("Report path outside the features publication root")
    contract, analysis_id = resolved.parent.parent.name, resolved.parent.name
    if not HEX64.fullmatch(contract) or not HEX64.fullmatch(analysis_id):
        raise ValueError("Noncanonical report directory names")
    return resolved, contract, analysis_id


def verify_report(v3, report_path):
    """Prechequeos de solo lectura antes de activar un reporte."""
    v3 = Path(v3).resolve()
    resolved, contract, analysis_id = _canonical_report_path(v3, report_path)
    context = _context(v3)
    if context["audit"]["contract_id"] != contract:
        raise ValueError("Report contract is not the active ETL generation")
    return _verify_report_dir(v3, resolved.parent, contract, analysis_id, context)


def activate_report(v3, report_path):
    """Publica audits/03_feature_engineering.json desde un reporte verificado.

    El puntero anterior se archiva por contenido bajo
    audits/03_feature_engineering_archive/ si aún no estaba respaldado;
    el reemplazo es atómico.
    """
    v3 = Path(v3).resolve()
    resolved, _, _ = _canonical_report_path(v3, report_path)
    verify_report(v3, resolved)
    payload = resolved.read_bytes()

    pointer = v3 / AUDIT_POINTER
    _reject_symlinks(v3, pointer)
    if pointer.is_file():
        prior_bytes = pointer.read_bytes()
        digest = hashlib.sha256(prior_bytes).hexdigest()
        backup = v3 / AUDIT_ARCHIVE / f"{digest}.json"
        if backup.exists():
            if backup.is_symlink() or backup.read_bytes() != prior_bytes:
                raise ValueError(
                    "Content-addressed pointer archive conflicts with prior bytes")
        else:
            _reject_symlinks(v3, backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(prior_bytes)

    temp = pointer.with_name(pointer.name + f".tmp-{uuid.uuid4().hex[:12]}")
    temp.write_bytes(payload)
    temp.replace(pointer)


def load_feature_pipeline(v3):
    """Devuelve el Pipeline publicado tras verificar puntero, bytes y hashes.

    joblib.load solo corre sobre el artefacto cuya integridad quedó
    comprobada por verify_report y por una segunda verificación local.
    """
    v3 = Path(v3).resolve()
    pointer = v3 / AUDIT_POINTER
    payload = pointer.read_bytes()
    report = json.loads(payload)
    resolved, _, _ = _canonical_report_path(
        v3, Path(FEATURES_ROOT) / report["contract_id"]
        / report["analysis_id"] / "report.json")
    verified = verify_report(v3, resolved)
    if resolved.read_bytes() != payload or pointer.read_bytes() != payload:
        raise ValueError("Feature pointer is not the verified published report")
    expected = (f"{FEATURES_ROOT}/{verified['contract_id']}/"
                f"{verified['analysis_id']}/{PIPELINE_OUTPUT}")
    matches = [row for row in verified["outputs"] if row["path"] == expected]
    if len(matches) != 1:
        raise ValueError("Pipeline artifact missing from verified report outputs")
    path = v3 / matches[0]["path"]
    if path.is_symlink() or not path.is_file() \
            or path.stat().st_size != matches[0]["bytes"] \
            or file_hash(path) != matches[0]["sha256"]:
        raise ValueError("Pipeline artifact failed byte/hash verification")
    pipeline = joblib.load(path)
    if not isinstance(pipeline, Pipeline):
        raise ValueError("Published artifact is not a sklearn Pipeline")
    if not hasattr(pipeline.steps[-1][1], "components_"):
        raise ValueError("Published pipeline is not fitted")
    return pipeline
