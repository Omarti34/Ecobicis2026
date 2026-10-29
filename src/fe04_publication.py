"""Publicación inmutable del arnés de validación del cuaderno 04.

stage_results materializa el universo de evaluación, las particiones
espaciales, las auto-pruebas de métricas y el paquete serializado del
arnés bajo data/validation/<contract_id>/<analysis_id>/ con preparación
atómica y reutilización verificada. activate_report promueve el reporte a
audits/04_backtest_design.json preservando el puntero anterior por
contenido. load_validation_harness solo deserializa tras verificación
completa de bytes y hashes.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path

import joblib
import numpy as np

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import fe03_publication
from V3.src import fe04_analysis
from V3.src import fe04_deployment
from V3.src.fe04_analysis import (
    CONFIG,
    EDA_TABLES,
    FEATURE_TABLES,
    TARGET,
    VERSION,
    analysis_identity,
)

VALIDATION_ROOT = "data/validation"
AUDIT_POINTER = "audits/04_backtest_design.json"
AUDIT_ARCHIVE = "audits/04_backtest_design_archive"
FE_POINTER = "audits/03_feature_engineering.json"
REPORT_RECORD = "report.json.sha256"
HARNESS_OUTPUT = "validation_harness.joblib"
HEX64 = re.compile(r"[0-9a-f]{64}")

ADDED_KEYS = {
    "analysis_id", "analysis_identity", "etl_audit_sha256",
    "eda_audit_sha256", "feature_audit_sha256", "eda_analysis_id",
    "feature_analysis_id", "input_artifacts", "outputs",
}

PARQUET_TABLES = {
    "universe": ("universo_evaluacion", False),
    "folds": ("cv_folds", False),
    "buffer_exclusions": ("cv_buffer_exclusions", False),
    "deploy_sites": ("sitios_candidatos", False),
    "deploy_cells": ("celdas_poblacion", False),
}
CSV_TABLES = {
    "selftests": "metric_selftests",
    "separation": "cv_separation",
    "deploy_link_table": "red_enlace",
}
DEPLOY_CALLABLES = [
    "link_distance_analysis", "check_link_distance",
    "nearest_neighbor_quantiles", "build_sites", "population_surface",
    "site_cell_incidence", "build_network_context", "new_pop", "P_norm",
    "is_feasible", "greedy_coverage", "portfolio_metrics", "hops",
    "portfolio_marginals", "portfolio_frame", "attach_name",
    "_attach_communities",
]
HARNESS_CALLABLES = [
    "precision_at_k", "recall_at_k", "conditional_precision_at_k",
    "ndcg_at_k", "ndcg_cond_at_k", "dcg_at_k", "effective_k",
    "evaluate_ranking",
    "fold_labels", "validate_folds", "buffer_exclusions",
    "run_backtest", "mahalanobis_distance", "fit_mahalanobis",
    "polygon_adjacency", "assign_spatial_blocks", "block_contiguity",
]
# assignment_key -> (splitter_key, group_assignment_key o None para cvegeo)
_REPLAY_SCHEMES = {
    "groupkfold_ageb": ("fold_groupkfold_ageb", None),
    "spatial_block": ("fold_spatial_block", "block_id"),
}
REQUIRED_OUTPUTS = frozenset(
    [f"{name}.parquet" for name, _ in PARQUET_TABLES.values()]
    + [f"{name}.csv" for name in CSV_TABLES.values()]
    + [HARNESS_OUTPUT])


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


def _record(path, final_dir):
    return {"path": f"{VALIDATION_ROOT}/{final_dir.parent.name}/{final_dir.name}/{path.name}",
            "bytes": path.stat().st_size, "sha256": file_hash(path)}


def _context(v3):
    """Identidad desde auditorías encadenadas: ETL -> EDA -> features -> 04."""
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    context03 = fe03_publication._context(v3)   # ETL + EDA activos verificados

    pointer = v3 / FE_POINTER
    payload = pointer.read_bytes()
    fe_report = json.loads(payload)
    if fe_report["contract_id"] != contract:
        raise ValueError("Feature pointer belongs to another ETL contract")
    fe_path = (v3 / fe03_publication.FEATURES_ROOT / contract
               / fe_report["analysis_id"] / "report.json")
    verified_fe = fe03_publication.verify_report(v3, fe_path)
    if fe_path.read_bytes() != payload or pointer.read_bytes() != payload:
        raise ValueError("Feature pointer is not the verified published report")

    records = {}
    for table in FEATURE_TABLES:
        matches = [r for r in verified_fe["outputs"]
                   if r["path"].endswith(f"/{table}.parquet")]
        if len(matches) != 1:
            raise ValueError(f"Feature artifact not unique: {table}")
        records[f"features/{table}"] = {
            key: matches[0][key] for key in ["path", "bytes", "sha256"]}
    for table in EDA_TABLES:
        matches = [r for r in context03["eda"]["outputs"]
                   if r["path"].endswith(f"/{table}.parquet")]
        if len(matches) != 1:
            raise ValueError(f"EDA artifact not unique: {table}")
        records[f"eda/{table}"] = {
            key: matches[0][key] for key in ["path", "bytes", "sha256"]}

    return {
        "audit": audit, "eda": context03["eda"], "feature_report": verified_fe,
        "input_artifacts": records,
        "etl_audit_sha256": context03["etl_audit_sha256"],
        "eda_audit_sha256": context03["eda_audit_sha256"],
        "feature_audit_sha256": hashlib.sha256(payload).hexdigest(),
        "eda_analysis_id": context03["eda"]["analysis_id"],
        "feature_analysis_id": verified_fe["analysis_id"],
    }


def _check_output_records(v3, report_dir, report):
    expected_dir = f"{VALIDATION_ROOT}/{report_dir.parent.name}/{report_dir.name}"
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
    for key in ["etl_audit_sha256", "eda_audit_sha256", "feature_audit_sha256",
                "eda_analysis_id", "feature_analysis_id"]:
        if report.get(key) != context[key]:
            raise ValueError(f"Report upstream reference drifted: {key}")
    if report.get("input_artifacts", {}) != context["input_artifacts"]:
        raise ValueError("Report input artifacts do not match active audits")
    _check_output_records(v3, report_dir, report)
    return report


def _scientific_report(report):
    return {key: value for key, value in report.items() if key not in ADDED_KEYS}


def build_harness_bundle(result):
    """Paquete serializable del arnés de validación.

    Contiene los parámetros calibrados de Mahalanobis, las asignaciones
    completas de pliegues (ambos esquemas y el bloque espacial), la
    configuración del protocolo, los separadores no ajustados y las
    funciones del módulo fe04_analysis. Los callables se serializan por
    referencia al módulo (comportamiento estándar e intencional de
    joblib/pickle para funciones de nivel superior): al cargarse deben
    ser idénticos a los del código vigente, lo cual verifica
    _verify_serialized_harness.
    """
    fit = result["mahalanobis_fit"]
    folds = result["folds"]
    indexed = folds.set_index("cvegeo")
    return {
        "schema_version": VERSION,
        "mahalanobis": {
            "mu": fit["mu"], "sigma_inv": fit["sigma_inv"],
            "sigma": fit["sigma"], "threshold": fit["threshold"],
            "chi2_ppf": fit["chi2_ppf"], "quantile": fit["quantile"],
            "df": fit["df"], "covariance_rank": fit["covariance_rank"],
            "min_eigenvalue": fit["min_eigenvalue"],
            "condition_number": fit["condition_number"],
            "n_reference": fit["n_reference"], "k_dims": fit["k_dims"],
            "estimator": fit["estimator"], "shrinkage": fit["shrinkage"],
        },
        "fold_assignments": {
            "groupkfold_ageb": indexed["fold_groupkfold_ageb"].to_dict(),
            "spatial_block": indexed["fold_spatial_block"].to_dict(),
            "block_id": indexed["spatial_block_id"].to_dict(),
        },
        "splitters": fe04_analysis.make_splitters(),
        "callables": {name: getattr(fe04_analysis, name)
                      for name in HARNESS_CALLABLES},
        "k_grid": list(CONFIG["k_grid"]),
        "label_quantile": CONFIG["label_quantile"],
        "buffer_m": CONFIG["buffer_m"],
        "buffered_schemes": list(CONFIG["buffered_schemes"]),
        "primary_scheme": CONFIG["primary_scheme"],
        "target": TARGET,
        "fold_local_protocol": result["report"]["fold_local_protocol"],
        "selftests_passed": bool(result["selftests"]["pass"].all()),
        "deployment": {
            "config": fe04_deployment.DEPLOY_CONFIG,
            "callables": {name: getattr(fe04_deployment, name)
                          for name in DEPLOY_CALLABLES},
        },
    }


def _replay_assignment(splitter, ids, groups):
    """Reejecuta un GroupKFold serializado sobre el orden publicado."""
    assignments = {}
    for fold, (_, test_idx) in enumerate(
            splitter.split(np.zeros(len(ids)), groups=list(groups))):
        for i in test_idx:
            assignments[ids[int(i)]] = int(fold)
    return assignments


def _verify_serialized_harness(bundle, joblib_path):
    """El joblib escrito debe contener el arnés exacto y rejugable."""
    loaded = joblib.load(joblib_path)
    fit = bundle["mahalanobis"]
    for key in ["mu", "sigma_inv", "sigma"]:
        if not np.allclose(loaded["mahalanobis"][key], fit[key],
                           rtol=0, atol=1e-12):
            raise ValueError(f"Serialized harness drifted: {key}")
    if loaded["mahalanobis"]["threshold"] != fit["threshold"]:
        raise ValueError("Serialized harness drifted: threshold")
    for name in ["groupkfold_ageb", "spatial_block", "block_id"]:
        declared = {str(c): int(v) for c, v
                    in bundle["fold_assignments"][name].items()}
        serialized = {str(c): int(v) for c, v
                      in loaded["fold_assignments"][name].items()}
        if serialized != declared:
            raise ValueError(f"Serialized harness drifted: {name}")
    for scheme, splitter in bundle["splitters"].items():
        loaded_splitter = loaded["splitters"].get(scheme)
        params = ("n_splits", "shuffle", "random_state")
        if loaded_splitter is None or type(loaded_splitter) is not type(splitter) \
                or any(getattr(loaded_splitter, p, None)
                       != getattr(splitter, p, None) for p in params):
            raise ValueError(f"Serialized harness drifted: {scheme}")
    for name, fn in bundle["callables"].items():
        if loaded["callables"].get(name) is not getattr(fe04_analysis, name):
            raise ValueError(f"Serialized harness drifted: callable {name}")
    deploy = bundle["deployment"]
    loaded_deploy = loaded.get("deployment") or {}
    if loaded_deploy.get("config") != deploy["config"]:
        raise ValueError("Serialized harness drifted: deployment config")
    for name in deploy["callables"]:
        if loaded_deploy.get("callables", {}).get(name) \
                is not getattr(fe04_deployment, name):
            raise ValueError(
                f"Serialized harness drifted: deployment callable {name}")
    for name, (splitter_key, group_key) in _REPLAY_SCHEMES.items():
        ids = list(bundle["fold_assignments"][name])
        groups = ids if group_key is None \
            else [bundle["fold_assignments"][group_key][c] for c in ids]
        replayed = _replay_assignment(
            loaded["splitters"][splitter_key], ids, groups)
        expected = {str(c): int(v) for c, v
                    in bundle["fold_assignments"][name].items()}
        if {str(c): v for c, v in replayed.items()} != expected:
            raise ValueError(f"Serialized harness does not replay: {name}")


def stage_results(v3, data, result):
    """Publica universo, folds, auto-pruebas y arnés serializado.

    Si el directorio ya existe, lo reutiliza únicamente tras verificar
    identidad, huellas y reporte científico idéntico; nunca sobrescribe.
    """
    v3 = Path(v3).resolve()
    context = _context(v3)
    contract = context["audit"]["contract_id"]
    if contract != data["audit"]["contract_id"]:
        raise ValueError("Analysis inputs do not match the committed ETL contract")
    analysis_id, identity = analysis_identity(v3, context)
    if analysis_id != data["analysis_id"] \
            or identity != data["analysis_identity"]:
        raise ValueError("Frozen analysis identity no longer matches current context")

    target = v3 / VALIDATION_ROOT / contract / analysis_id
    if target.exists():
        cached = _verify_report_dir(v3, target, contract, analysis_id, context)
        if _scientific_report(cached) != result["report"]:
            raise ValueError("Cached report differs from the computed result")
        return target / "report.json"

    report = dict(result["report"])
    report["analysis_id"] = analysis_id
    report["analysis_identity"] = identity
    for key in ["etl_audit_sha256", "eda_audit_sha256", "feature_audit_sha256",
                "eda_analysis_id", "feature_analysis_id"]:
        report[key] = context[key]
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
    bundle = build_harness_bundle(result)
    harness_path = staging / HARNESS_OUTPUT
    joblib.dump(bundle, harness_path)
    outputs.append(_record(harness_path, target))
    _verify_serialized_harness(bundle, harness_path)

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
    path = Path(report_path)
    if ".." in path.parts:
        raise ValueError("Report path must not contain '..'")
    if not path.is_absolute():
        path = v3 / path
    _reject_symlinks(v3, path)
    resolved = path.resolve()
    if resolved.parent.parent.parent != v3 / VALIDATION_ROOT \
            or resolved.name != "report.json":
        raise ValueError("Report path outside the validation publication root")
    contract, analysis_id = resolved.parent.parent.name, resolved.parent.name
    if not HEX64.fullmatch(contract) or not HEX64.fullmatch(analysis_id):
        raise ValueError("Noncanonical report directory names")
    return resolved, contract, analysis_id


def verify_report(v3, report_path):
    v3 = Path(v3).resolve()
    resolved, contract, analysis_id = _canonical_report_path(v3, report_path)
    context = _context(v3)
    if context["audit"]["contract_id"] != contract:
        raise ValueError("Report contract is not the active ETL generation")
    return _verify_report_dir(v3, resolved.parent, contract, analysis_id, context)


def activate_report(v3, report_path):
    """Activa audits/04_backtest_design.json con archivo por contenido."""
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


def load_validation_harness(v3):
    """Devuelve el paquete del arnés tras verificar puntero, bytes y hashes."""
    v3 = Path(v3).resolve()
    pointer = v3 / AUDIT_POINTER
    payload = pointer.read_bytes()
    report = json.loads(payload)
    resolved, _, _ = _canonical_report_path(
        v3, Path(VALIDATION_ROOT) / report["contract_id"]
        / report["analysis_id"] / "report.json")
    verified = verify_report(v3, resolved)
    if resolved.read_bytes() != payload or pointer.read_bytes() != payload:
        raise ValueError("Validation pointer is not the verified published report")
    expected = (f"{VALIDATION_ROOT}/{verified['contract_id']}/"
                f"{verified['analysis_id']}/{HARNESS_OUTPUT}")
    matches = [row for row in verified["outputs"] if row["path"] == expected]
    if len(matches) != 1:
        raise ValueError("Harness artifact missing from verified report outputs")
    path = v3 / matches[0]["path"]
    if path.is_symlink() or not path.is_file() \
            or path.stat().st_size != matches[0]["bytes"] \
            or file_hash(path) != matches[0]["sha256"]:
        raise ValueError("Harness artifact failed byte/hash verification")
    bundle = joblib.load(path)
    required = {"mahalanobis", "fold_assignments", "k_grid",
                "fold_local_protocol", "splitters", "callables",
                "deployment"}
    if not isinstance(bundle, dict) or not required.issubset(bundle):
        raise ValueError("Published harness lacks required components")
    return bundle
