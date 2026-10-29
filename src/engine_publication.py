"""Publicación sellada genérica para los motores (cuadernos 05/06/07).

Factoriza la maquinaria de publicación inmutable usada en 03/04:
staging + renombrado atómico, nunca sobrescribir, reutilización solo
tras verificación completa (identidad, referencias upstream, registros
de artefactos de entrada, conjunto exacto de outputs, bytes/hash de cada
output, igualdad del reporte científico), rechazo de symlinks, rutas
canónicas, puntero con archivo content-addressed y un cargador que solo
devuelve artefactos tras verificación completa.

Cada motor declara un EngineSpec: etiqueta, versión, puntero, conjunto
exacto de outputs requeridos y un par context_fn/identity_fn. Los
outputs se materializan con escritores por tipo: parquet (geo o plano),
csv, joblib, bytes crudos (p. ej. torch .pt) y json.
"""
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from V3.src.eda02_analysis import file_hash

REPORT_RECORD = "report.json.sha256"
HEX64 = re.compile(r"[0-9a-f]{64}")
ADDED_KEYS = {"analysis_id", "analysis_identity", "upstream_refs",
              "input_artifacts", "outputs"}
OUTPUT_KINDS = ("parquet", "csv", "joblib", "bytes", "json")


@dataclass(frozen=True)
class EngineSpec:
    """Contrato de publicación de un motor.

    tag: subcarpeta bajo data/engines/ (p. ej. "05_motor1").
    pointer: puntero de auditoría (p. ej. "audits/05_motor1_baseline.json").
    required_outputs: basenames exactos que todo reporte debe publicar.
    context_fn(v3) -> dict con audit, upstream_refs e input_artifacts.
    identity_fn(v3, context) -> (analysis_id, identity_dict).
    """
    tag: str
    version: str
    pointer: str
    required_outputs: frozenset
    context_fn: object
    identity_fn: object

    @property
    def root(self):
        return f"data/engines/{self.tag}"

    @property
    def archive(self):
        return self.pointer[:-len(".json")] + "_archive"


def _to_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _reject_symlinks(v3, path):
    current = path
    while current != v3.parent and current != current.parent:
        if current.is_symlink():
            raise ValueError("Symlinks are not allowed in publication paths")
        current = current.parent


def _record(spec, path, final_dir):
    return {"path": f"{spec.root}/{final_dir.parent.name}/{final_dir.name}/{path.name}",
            "bytes": path.stat().st_size, "sha256": file_hash(path)}


def _write_output(kind, payload, path, tags):
    if kind == "parquet":
        payload.assign(**tags).to_parquet(path, index=False)
    elif kind == "csv":
        payload.assign(**tags).to_csv(path, index=False)
    elif kind == "joblib":
        joblib.dump(payload, path)
    elif kind == "bytes":
        path.write_bytes(payload)
    elif kind == "json":
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   sort_keys=True, allow_nan=False,
                                   default=_to_builtin))
    else:
        raise ValueError(f"Unknown output kind: {kind}")


def _check_output_records(v3, spec, report_dir, report):
    expected_dir = f"{spec.root}/{report_dir.parent.name}/{report_dir.name}"
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
    if basenames != spec.required_outputs:
        raise ValueError("Report outputs do not match the required artifact set")
    for entry in report_dir.iterdir():
        if entry.is_symlink() or entry.is_dir():
            raise ValueError("Unexpected link/directory in the report directory")
    actual = {p.name for p in report_dir.iterdir() if p.is_file()}
    if actual != declared:
        raise ValueError("Unexpected files in the published report directory")


def _verify_report_dir(v3, spec, report_dir, contract, analysis_id, context):
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
            or report["schema_version"] != spec.version:
        raise ValueError("Report identity does not match the requested analysis")
    expected_id, expected_identity = spec.identity_fn(v3, context)
    if analysis_id != expected_id:
        raise ValueError("Analysis identity drifted from current code/sources")
    if report.get("analysis_identity") != expected_identity:
        raise ValueError("Report analysis_identity drifted from current context")
    if report.get("upstream_refs", {}) != context["upstream_refs"]:
        raise ValueError("Report upstream references drifted")
    if report.get("input_artifacts", {}) != context["input_artifacts"]:
        raise ValueError("Report input artifacts do not match active audits")
    _check_output_records(v3, spec, report_dir, report)
    return report


def _scientific_report(report):
    return {key: value for key, value in report.items() if key not in ADDED_KEYS}


def stage_results(v3, spec, data, result):
    """Publica outputs + report.json bajo data/engines/<tag>/<contract>/<id>.

    Si el directorio ya existe, lo reutiliza únicamente tras verificar
    identidad, huellas y reporte científico idéntico; nunca sobrescribe.
    """
    v3 = Path(v3).resolve()
    context = spec.context_fn(v3)
    contract = context["audit"]["contract_id"]
    if contract != data["audit"]["contract_id"]:
        raise ValueError("Analysis inputs do not match the committed ETL contract")
    analysis_id, identity = spec.identity_fn(v3, context)
    if analysis_id != data["analysis_id"] \
            or identity != data["analysis_identity"]:
        raise ValueError("Frozen analysis identity no longer matches current context")

    target = v3 / spec.root / contract / analysis_id
    if target.exists():
        cached = _verify_report_dir(v3, spec, target, contract,
                                    analysis_id, context)
        if _scientific_report(cached) != result["report"]:
            raise ValueError("Cached report differs from the computed result")
        return target / "report.json"

    report = dict(result["report"])
    report["analysis_id"] = analysis_id
    report["analysis_identity"] = identity
    report["upstream_refs"] = context["upstream_refs"]
    report["input_artifacts"] = context["input_artifacts"]

    staging = target.parent / f".staging-{target.name}-{uuid.uuid4().hex[:12]}"
    _reject_symlinks(v3, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    tags = {"_etl_contract_id": contract, "_analysis_id": analysis_id}
    outputs = []
    for basename, kind, payload in result["outputs"]:
        if kind not in OUTPUT_KINDS:
            raise ValueError(f"Unknown output kind: {kind}")
        path = staging / basename
        _write_output(kind, payload, path, tags)
        outputs.append(_record(spec, path, target))

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


def _canonical_report_path(v3, spec, report_path):
    path = Path(report_path)
    if ".." in path.parts:
        raise ValueError("Report path must not contain '..'")
    if not path.is_absolute():
        path = v3 / path
    _reject_symlinks(v3, path)
    resolved = path.resolve()
    if resolved.parent.parent.parent != v3 / spec.root \
            or resolved.name != "report.json":
        raise ValueError("Report path outside the engine publication root")
    contract, analysis_id = resolved.parent.parent.name, resolved.parent.name
    if not HEX64.fullmatch(contract) or not HEX64.fullmatch(analysis_id):
        raise ValueError("Noncanonical report directory names")
    return resolved, contract, analysis_id


def verify_report(v3, spec, report_path):
    v3 = Path(v3).resolve()
    resolved, contract, analysis_id = _canonical_report_path(
        v3, spec, report_path)
    context = spec.context_fn(v3)
    if context["audit"]["contract_id"] != contract:
        raise ValueError("Report contract is not the active ETL generation")
    return _verify_report_dir(v3, spec, resolved.parent, contract,
                              analysis_id, context)


def activate_report(v3, spec, report_path):
    """Activa el puntero del motor con archivo por contenido."""
    v3 = Path(v3).resolve()
    resolved, _, _ = _canonical_report_path(v3, spec, report_path)
    verify_report(v3, spec, resolved)
    payload = resolved.read_bytes()

    pointer = v3 / spec.pointer
    _reject_symlinks(v3, pointer)
    if pointer.is_file():
        prior_bytes = pointer.read_bytes()
        digest = hashlib.sha256(prior_bytes).hexdigest()
        backup = v3 / spec.archive / f"{digest}.json"
        if backup.exists():
            if backup.is_symlink() or backup.read_bytes() != prior_bytes:
                raise ValueError(
                    "Content-addressed pointer archive conflicts with prior bytes")
        else:
            _reject_symlinks(v3, backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(prior_bytes)

    pointer.parent.mkdir(parents=True, exist_ok=True)
    temp = pointer.with_name(pointer.name + f".tmp-{uuid.uuid4().hex[:12]}")
    temp.write_bytes(payload)
    temp.replace(pointer)


def load_verified(v3, spec):
    """Devuelve el reporte verificado y las rutas de sus outputs.

    Solo retorna tras: puntero == reporte publicado byte a byte,
    verificación completa del reporte (identidad, upstream, insumos,
    conjunto exacto de outputs y bytes/hash de cada artefacto).
    """
    v3 = Path(v3).resolve()
    pointer = v3 / spec.pointer
    payload = pointer.read_bytes()
    report = json.loads(payload)
    resolved, _, _ = _canonical_report_path(
        v3, spec, Path(spec.root) / report["contract_id"]
        / report["analysis_id"] / "report.json")
    verified = verify_report(v3, spec, resolved)
    if resolved.read_bytes() != payload or pointer.read_bytes() != payload:
        raise ValueError("Engine pointer is not the verified published report")
    outputs = {}
    for record in verified["outputs"]:
        path = v3 / record["path"]
        if path.is_symlink() or not path.is_file() \
                or path.stat().st_size != record["bytes"] \
                or file_hash(path) != record["sha256"]:
            raise ValueError(
                f"Engine output failed byte/hash check: {record['path']}")
        outputs[path.name] = path
    return {"report": verified, "report_path": resolved, "outputs": outputs}


def pointer_verified_report(v3, pointer, verify_fn, root):
    """Puntero de auditoría -> reporte verificado byte a byte.

    Reutilizable por los context_fn de cada motor para encadenar la
    verificación de publicaciones upstream (02, 03, 04 y motores previos).
    """
    v3 = Path(v3).resolve()
    pointer_path = v3 / pointer
    payload = pointer_path.read_bytes()
    report = json.loads(payload)
    report_path = (v3 / root / report["contract_id"]
                   / report["analysis_id"] / "report.json")
    verified = verify_fn(v3, report_path)
    if report_path.read_bytes() != payload \
            or pointer_path.read_bytes() != payload:
        raise ValueError(f"Upstream pointer is not its verified report: {pointer}")
    return verified


def artifact_records(report, basenames):
    """Registros path/bytes/sha256 de los artefactos declarados en un reporte."""
    records = {}
    for basename in basenames:
        matches = [r for r in report["outputs"]
                   if r["path"].endswith(f"/{basename}")]
        if len(matches) != 1:
            raise ValueError(f"Upstream artifact not unique: {basename}")
        records[basename] = {key: matches[0][key]
                             for key in ["path", "bytes", "sha256"]}
    return records


def verified_artifact_path(v3, report, basename):
    """Ruta verificada (bytes+hash) de un artefacto de un reporte upstream."""
    v3 = Path(v3).resolve()
    records = artifact_records(report, [basename])
    record = records[basename]
    path = v3 / record["path"]
    if path.is_symlink() or not path.is_file() \
            or path.stat().st_size != record["bytes"] \
            or file_hash(path) != record["sha256"]:
        raise ValueError(f"Upstream artifact failed byte/hash check: {basename}")
    return path
