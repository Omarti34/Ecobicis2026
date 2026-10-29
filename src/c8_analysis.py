"""Cuaderno 08: comparación de portafolios publicados (motores 05/06/07).

El 08 NUNCA reejecuta un motor: lee los portafolios publicados y
verificados byte a byte, el contrato de despliegue del cuaderno 04
(sitios, celdas, reglas y métricas reconstruidas con fe04_deployment),
las features del 03 para atributos de las AGEBs anfitrionas y el
universo del 04 para el domain_status global. Reconstruye las métricas
del contrato y las compara contra las que cada motor publicó; cualquier
divergencia o infactibilidad aborta la publicación.

Portafolio oficial por motor y presupuesto B in {15, 30, 50}: Motor 1 =
greedy SIN techos (v3-motor1-3); Motor 2 = greedy con puntaje del bosque
aleatorio SIN techos (v3-motor2-3); Motor 3 = greedy con afinidad
1/(1+saltos a Golden) (v3-motor3-4). Fila secundaria (solo sensibilidad):
la mejor corrida GA del Motor 3 a B=30, `ga_best`.
"""
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import eda02_publication
from V3.src import engine_publication as ep
from V3.src import fe03_publication
from V3.src import fe04_deployment as dep
from V3.src import fe04_publication
from V3.src import m1_publication
from V3.src import m2_publication
from V3.src import m3_publication

VERSION = "v3-comparacion-2"
CONFIG = {
    "metric_crs": dep.DEPLOY_CONFIG["metric_crs"],
    "budget_grid": dep.DEPLOY_CONFIG["budget_grid"],
    "primary_budget": dep.DEPLOY_CONFIG["primary_budget"],
    "max_reach_m": dep.DEPLOY_CONFIG["max_reach_m"],
    "primary_scheme": "fold_spatial_block",
    "metric_rtol": 1e-9,
    "seed": 42,
}
RADAR_AXES = ["cobertura", "eficiencia", "proximidad_red", "equidad",
              "similitud_golden", "dispersion"]
METRIC_KEYS = [
    "n_selected", "new_pop", "new_pop_share", "redundancy", "n_agebs",
    "max_hops_network", "median_hops_golden", "max_hops_golden",
    "mean_dist_to_network_m", "mean_grado_escolar_prom_selected",
    "mean_grado_escolar_prom_all_sites",
    "mean_pct_viviendas_auto_selected",
    "mean_pct_viviendas_auto_all_sites", "out_of_domain_04_share",
]

UPSTREAM_ARTIFACTS = {
    "eda": ["station_environment.parquet"],
    "features": ["entorno_ageb_features.parquet"],
    "validation": ["universo_evaluacion.parquet",
                   "sitios_candidatos.parquet",
                   "celdas_poblacion.parquet",
                   "validation_harness.joblib"],
    "motor1": ["m1_portafolios.parquet"],
    "motor2": ["m2_portafolios.parquet"],
    "motor3": ["m3_portafolios.parquet"],
}
POINTERS = {
    "eda": "audits/02_eda.json",
    "features": "audits/03_feature_engineering.json",
    "validation": "audits/04_backtest_design.json",
    "motor1": "audits/05_motor1_baseline.json",
    "motor2": "audits/06_motor2_transformer.json",
    "motor3": "audits/07_motor3_prescriptivo.json",
}


# ---------------------------------------------------------------------------
# Insumos verificados e identidad
# ---------------------------------------------------------------------------

def check_shared_validation_id(reports):
    """Los tres motores deben haberse publicado sobre el MISMO 04."""
    ids = {name: reports[name]["upstream_refs"]["validation_analysis_id"]
           for name in ("motor1", "motor2", "motor3")}
    if len(set(ids.values())) != 1:
        raise ValueError(
            f"Los motores no comparten el mismo analysis_id del 04: {ids}")
    expected = reports["validation"]["analysis_id"]
    if set(ids.values()) != {expected}:
        raise ValueError(
            "El analysis_id del 04 referenciado por los motores no es el "
            f"del puntero activo: {ids} vs {expected}")
    return expected


def _upstream_context(v3):
    """Verifica ETL + punteros 02/03/04/05/06/07; el 08 no ejecuta motores."""
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    reports = {
        "eda": ep.pointer_verified_report(
            v3, POINTERS["eda"], eda02_publication.verify_report,
            eda02_publication.EDA_ROOT),
        "features": ep.pointer_verified_report(
            v3, POINTERS["features"], fe03_publication.verify_report,
            fe03_publication.FEATURES_ROOT),
        "validation": ep.pointer_verified_report(
            v3, POINTERS["validation"], fe04_publication.verify_report,
            fe04_publication.VALIDATION_ROOT),
        "motor1": ep.pointer_verified_report(
            v3, POINTERS["motor1"], m1_publication.verify_report,
            m1_publication.SPEC.root),
        "motor2": ep.pointer_verified_report(
            v3, POINTERS["motor2"], m2_publication.verify_report,
            m2_publication.SPEC.root),
        "motor3": ep.pointer_verified_report(
            v3, POINTERS["motor3"], m3_publication.verify_report,
            m3_publication.SPEC.root),
    }
    for name, report in reports.items():
        if report["contract_id"] != contract:
            raise ValueError(
                f"Upstream {name} report belongs to another contract")
    shared_validation = check_shared_validation_id(reports)
    input_artifacts = {}
    for stage, basenames in UPSTREAM_ARTIFACTS.items():
        records = ep.artifact_records(reports[stage], basenames)
        for basename, record in records.items():
            input_artifacts[f"{stage}/{basename}"] = record
    upstream_refs = {
        "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["eda"]).read_bytes()).hexdigest(),
        "feature_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["features"]).read_bytes()).hexdigest(),
        "validation_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["validation"]).read_bytes()).hexdigest(),
        "motor1_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["motor1"]).read_bytes()).hexdigest(),
        "motor2_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["motor2"]).read_bytes()).hexdigest(),
        "motor3_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["motor3"]).read_bytes()).hexdigest(),
        "eda_analysis_id": reports["eda"]["analysis_id"],
        "feature_analysis_id": reports["features"]["analysis_id"],
        "validation_analysis_id": reports["validation"]["analysis_id"],
        "motor1_analysis_id": reports["motor1"]["analysis_id"],
        "motor2_analysis_id": reports["motor2"]["analysis_id"],
        "motor3_analysis_id": reports["motor3"]["analysis_id"],
        "shared_validation_analysis_id": shared_validation,
        "never_reruns_motors": True,
    }
    return {"audit": audit, "reports": reports,
            "input_artifacts": input_artifacts,
            "upstream_refs": upstream_refs}


def analysis_identity(v3, context):
    identity = {
        "schema_version": VERSION,
        "contract_id": context["audit"]["contract_id"],
        "configuration": CONFIG,
        "input_artifacts": context["input_artifacts"],
        "upstream_refs": context["upstream_refs"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "c8_analysis.py", "c8_content.py", "c8_publication.py",
                "build_notebook_08.py", "engine_publication.py",
                "fe04_deployment.py", "fe04_publication.py",
                "fe03_publication.py", "eda02_publication.py",
                "m1_publication.py", "m2_publication.py",
                "m3_publication.py",
            ]
        },
        "versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "geopandas": gpd.__version__,
            "scipy": scipy.__version__, "sklearn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), identity


def _verified_frame(v3, report, basename, geodataframe=False):
    path = ep.verified_artifact_path(v3, report, basename)
    return (gpd.read_parquet if geodataframe else pd.read_parquet)(path)


def load_inputs(v3):
    """Carga verificada: contrato 04, features 03, estaciones 02 y los
    portafolios publicados de los tres motores (jamás los reejecuta)."""
    context = _upstream_context(v3)
    reports = context["reports"]
    harness = fe04_publication.load_validation_harness(v3)
    deploy = harness["deployment"]
    for name in ["is_feasible", "greedy_coverage", "new_pop",
                 "portfolio_metrics", "P_norm", "build_network_context"]:
        if deploy["callables"].get(name) is not getattr(dep, name):
            raise ValueError(f"Deployment callable drifted: {name}")
    if deploy["config"] != dep.DEPLOY_CONFIG:
        raise ValueError("Deployment config drifted from fe04_deployment")
    frames = {
        "features": _verified_frame(
            v3, reports["features"], "entorno_ageb_features.parquet",
            geodataframe=True),
        "station_env": _verified_frame(
            v3, reports["eda"], "station_environment.parquet",
            geodataframe=True),
        "sites": _verified_frame(
            v3, reports["validation"], "sitios_candidatos.parquet",
            geodataframe=True),
        "cells": _verified_frame(
            v3, reports["validation"], "celdas_poblacion.parquet",
            geodataframe=True),
        "universe04": _verified_frame(
            v3, reports["validation"], "universo_evaluacion.parquet"),
        "m1_portafolios": _verified_frame(
            v3, reports["motor1"], "m1_portafolios.parquet",
            geodataframe=True),
        "m2_portafolios": _verified_frame(
            v3, reports["motor2"], "m2_portafolios.parquet",
            geodataframe=True),
        "m3_portafolios": _verified_frame(
            v3, reports["motor3"], "m3_portafolios.parquet",
            geodataframe=True),
    }
    data = {**context, "v3": Path(v3).resolve(), "frames": frames,
            "harness": harness}
    data["analysis_id"], data["analysis_identity"] = \
        analysis_identity(v3, context)
    return data


# ---------------------------------------------------------------------------
# Catálogo de portafolios oficiales y de sensibilidad
# ---------------------------------------------------------------------------

def _portfolio_order(port_sel, site_pos, tag):
    """Orden posicional en el ctx: filas del parquet ordenadas por su
    columna `order`, mapeadas por site_id (estable del contrato 04)."""
    sel = port_sel.sort_values("order")
    missing = [s for s in sel.site_id if s not in site_pos]
    if missing:
        raise ValueError(f"{tag}: site_id ausente del contrato 04: "
                         f"{missing[:5]}")
    return [site_pos[s] for s in sel.site_id]


def portfolio_catalog(frames, site_pos, budgets, primary_weight=0.5):
    """Catálogo (motor, variante, tier, budget, order, filas).

    Oficiales: M1 greedy sin techos; M2 greedy con puntaje del bosque
    sin techos; M3 greedy con afinidad de saltos w=0.5. Sensibilidad:
    M3 ga_best a B30 si está publicado.
    """
    p1, p2, p3 = (frames["m1_portafolios"], frames["m2_portafolios"],
                  frames["m3_portafolios"])
    entries = []
    for b in budgets:
        entries.append({
            "motor": "m1", "variant": "greedy", "tier": "oficial",
            "budget": b, "published_key": ("por_presupuesto", str(b)),
            "sel": p1.loc[p1.budget == b]})
        entries.append({
            "motor": "m2", "variant": "random_forest", "tier": "oficial",
            "budget": b, "published_key": ("por_presupuesto", str(b)),
            "sel": p2.loc[(p2.method == "random_forest")
                          & (p2.budget == b)]})
        entries.append({
            "motor": "m3", "variant": "greedy", "tier": "oficial",
            "budget": b,
            "published_key": ("budget_sensitivity", str(b)),
            "sel": p3.loc[(p3.method == "greedy")
                          & (p3.weight == primary_weight)
                          & (p3.budget == b)]})
    b30 = 30 if 30 in budgets else budgets[len(budgets) // 2]
    secondaries = [
        {"motor": "m3", "variant": "ga_best", "tier": "sensibilidad",
         "budget": b30, "published_key": ("ga_best",),
         "sel": p3.loc[(p3.method == "ga")
                       & (p3.weight == primary_weight)
                       & (p3.budget == b30)]},
    ]
    for e in entries + secondaries:
        e["order"] = _portfolio_order(
            e["sel"], site_pos,
            f"{e['motor']}/{e['variant']}/B{e['budget']}")
        if e["tier"] == "oficial" and len(e["order"]) == 0:
            # Portafolio oficial vacío es legítimo (Motor 2 publicó
            # no_feasible en una iteración previa); se mantiene.
            pass
    return entries + [e for e in secondaries if len(e["order"]) > 0]


def published_metrics(report, motor, published_key):
    """Métricas publicadas por el motor para un portafolio del catálogo."""
    if motor == "m1" or motor == "m2":
        node = report["portafolio"]
    else:
        node = report["portfolios"]
    for key in published_key:
        node = node[key]
    return {k: node[k] for k in METRIC_KEYS + ["stations_per_ageb"]
            if k in node}


def compare_metrics(published, recomputed, rtol=1e-9):
    """Compara métricas publicadas vs recalculadas (rtol 1e-9).

    Devuelve la lista de diferencias; None publicado equivale a NaN
    recalculado (métrica no aplicable en portafolio vacío).
    """
    diffs = []
    keys = [k for k in METRIC_KEYS if k in published or k in recomputed]
    for key in keys:
        pub, rec = published.get(key), recomputed.get(key)
        if pub is None and (rec is None or (
                isinstance(rec, float) and not np.isfinite(rec))):
            continue
        if pub is None or rec is None:
            diffs.append((key, pub, rec))
            continue
        if not np.isclose(float(pub), float(rec), rtol=rtol, atol=0.0):
            diffs.append((key, pub, rec))
    for bucket in ("1", "2", "3+"):
        pub = (published.get("stations_per_ageb") or {}).get(bucket)
        rec = (recomputed.get("stations_per_ageb") or {}).get(bucket)
        if pub is not None and rec is not None and int(pub) != int(rec):
            diffs.append((f"stations_per_ageb[{bucket}]", pub, rec))
        elif (pub is None) != (rec is None):
            diffs.append((f"stations_per_ageb[{bucket}]", pub, rec))
    return diffs


# ---------------------------------------------------------------------------
# Ejes del radar (escalas fijas [0,1], jamás min-max entre motores)
# ---------------------------------------------------------------------------

def radar_axes(metrics, order, ctx, sites, features, budget,
               max_reach_m):
    """Seis ejes en [0,1] con semántica fija por eje.

    cobertura: new_pop / P_norm(ctx, B) (cota submodular común);
    eficiencia: 1 - redundancia; proximidad_red: 1 - distancia media a
    la red / max_reach; equidad: fracción de sitios seleccionados cuya
    AGEB anfitriona tiene grado_escolar_prom bajo la mediana de TODOS
    los sitios; similitud_golden: 1 - fracción en AGEBs fuera del
    dominio global del 04; dispersion: n_agebs / n_selected.
    """
    nan = float("nan")
    sel = list(order)
    feat = features.set_index("cvegeo") \
        if "cvegeo" in features.columns else features
    host_all = feat.loc[sites.cvegeo, "grado_escolar_prom"]
    med = float(host_all.median())
    if sel:
        host_sel = feat.loc[sites.iloc[sel].cvegeo, "grado_escolar_prom"]
        equity = float(np.mean(host_sel.to_numpy() < med))
    else:
        equity = nan
    p_norm = dep.P_norm(ctx, budget)
    n_sel = metrics["n_selected"]
    return {
        "cobertura": float(metrics["new_pop"] / p_norm)
        if p_norm > 0 else nan,
        "eficiencia": float(1.0 - metrics["redundancy"])
        if np.isfinite(metrics["redundancy"]) else nan,
        "proximidad_red": float(
            1.0 - metrics["mean_dist_to_network_m"] / max_reach_m)
        if np.isfinite(metrics.get("mean_dist_to_network_m", nan))
        else nan,
        "equidad": equity,
        "similitud_golden": float(1.0 - metrics["out_of_domain_04_share"])
        if np.isfinite(metrics.get("out_of_domain_04_share", nan))
        else nan,
        "dispersion": float(metrics["n_agebs"] / n_sel)
        if n_sel else nan,
    }


def _jaccard(a, b):
    a, b = set(a), set(b)
    return float(len(a & b) / len(a | b)) if a | b else 1.0


def consensus_votes(per_motor):
    """Votos por site_id entre los portafolios oficiales de un B:
    {site_id: conjunto de motores que lo seleccionaron}."""
    votes = {}
    for motor, entry in per_motor.items():
        for sid in entry["sel"].site_id:
            votes.setdefault(sid, set()).add(motor)
    return votes


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    return value if np.isfinite(value) else None


def _records(df):
    """Registros JSON-seguros: NaN/pd.NA -> None (campo no aplicable)."""
    return df.astype(object).where(pd.notna(df), None) \
        .to_dict(orient="records")


# ---------------------------------------------------------------------------
# Análisis completo
# ---------------------------------------------------------------------------

def analyze(data, verbose=False):
    started = time.perf_counter()

    def tick(label):
        if verbose:
            print(f"[c8] {label}: {time.perf_counter() - started:.1f}s",
                  file=sys.stderr, flush=True)

    frames = data["frames"]
    cfg = dep.DEPLOY_CONFIG
    budgets = list(CONFIG["budget_grid"])
    metric = CONFIG["metric_crs"]
    sites = frames["sites"].to_crs(metric).reset_index(drop=True)
    cells = frames["cells"].to_crs(metric).reset_index(drop=True)
    stations = frames["station_env"].to_crs(metric)
    features = frames["features"]
    universe04 = frames["universe04"]
    incidence = dep.site_cell_incidence(
        np.c_[sites.x, sites.y], cells, cfg)
    ctx = dep.build_network_context(sites, cells, incidence,
                                    stations, cfg)
    site_pos = {sid: i for i, sid in enumerate(sites.site_id)}
    tick("ctx")

    reports = data["reports"]
    catalog = portfolio_catalog(frames, site_pos, budgets)
    tick("catalog")

    # ---- 1. Chequeo de consistencia: recomputar y comparar ------------
    # Desde v3-motor1-3 / v3-motor2-3 ningún motor usa techos por AGEB:
    # la factibilidad se verifica sin ellos.
    metric_rows, radar_rows, consistency = [], [], []
    for e in catalog:
        tag = f"{e['motor']}/{e['variant']}/B{e['budget']}"
        feasible = dep.is_feasible(
            e["order"], ctx, e["budget"])
        if not feasible:
            raise ValueError(
                f"Portafolio publicado no pasa is_feasible: {tag}")
        metrics = dep.portfolio_metrics(
            e["order"], ctx, sites, features, universe04)
        rep = reports[{"m1": "motor1", "m2": "motor2",
                       "m3": "motor3"}[e["motor"]]]
        diffs = compare_metrics(
            published_metrics(rep, e["motor"], e["published_key"]),
            metrics, CONFIG["metric_rtol"])
        if diffs:
            raise ValueError(
                f"Métricas publicadas no reproducibles en {tag}: {diffs}")
        consistency.append({"tag": tag, "n_selected": len(e["order"]),
                            "is_feasible": True, "metrics_equal": True})
        row = {"motor": e["motor"], "variant": e["variant"],
               "tier": e["tier"], "budget": e["budget"],
               **{k: metrics[k] for k in METRIC_KEYS},
               "agebs_1": metrics["stations_per_ageb"]["1"],
               "agebs_2": metrics["stations_per_ageb"]["2"],
               "agebs_3plus": metrics["stations_per_ageb"]["3+"],
               "p_norm": dep.P_norm(ctx, e["budget"])}
        metric_rows.append(row)
        for axis, value in radar_axes(
                metrics, e["order"], ctx, sites, features,
                e["budget"], CONFIG["max_reach_m"]).items():
            radar_rows.append({"motor": e["motor"], "variant": e["variant"],
                               "tier": e["tier"], "budget": e["budget"],
                               "axis": axis, "value": value})
        e["metrics"] = metrics
    metricas = pd.DataFrame(metric_rows)
    radar = pd.DataFrame(radar_rows)
    tick("metrics+consistency")

    # ---- 2. Traslape y consenso (portafolios oficiales) ----------------
    official = [e for e in catalog if e["tier"] == "oficial"]
    overlap_rows, consensus_rows = [], []
    for b in budgets:
        per = {e["motor"]: e for e in official if e["budget"] == b}
        motors = sorted(per)
        for i, a in enumerate(motors):
            for c in motors[i + 1:]:
                sa = set(per[a]["sel"].site_id)
                sc = set(per[c]["sel"].site_id)
                aa = set(per[a]["sel"].cvegeo)
                ac = set(per[c]["sel"].cvegeo)
                overlap_rows.append({
                    "budget": b, "motor_a": a, "motor_b": c,
                    "n_a_sites": len(sa), "n_b_sites": len(sc),
                    "n_inter_sites": len(sa & sc),
                    "jaccard_sites": _jaccard(sa, sc),
                    "n_a_agebs": len(aa), "n_b_agebs": len(ac),
                    "n_inter_agebs": len(aa & ac),
                    "jaccard_agebs": _jaccard(aa, ac)})
        for sid, ms in consensus_votes(per).items():
            if len(ms) >= 2:
                consensus_rows.append({
                    "budget": b, "site_id": sid,
                    "n_motors": len(ms),
                    "motors": "+".join(sorted(ms))})
    overlap = pd.DataFrame(overlap_rows)
    consensus = sites.merge(
        pd.DataFrame(consensus_rows), on="site_id", how="inner") \
        if consensus_rows else sites.iloc[[]].assign(
            budget=pd.Series(dtype=int), n_motors=pd.Series(dtype=int),
            motors=pd.Series(dtype=str))
    tick("overlap")

    # ---- 3. Asignación por AGEB (sin techos) ---------------------------
    asig_rows = []
    for e in official:
        per_ageb = e["sel"].cvegeo.value_counts()
        asig_rows.append({
            "motor": e["motor"], "budget": e["budget"],
            "n_agebs": int(per_ageb.size),
            "agebs_1": int((per_ageb == 1).sum()),
            "agebs_2": int((per_ageb == 2).sum()),
            "agebs_3plus": int((per_ageb >= 3).sum())})
    asignacion = pd.DataFrame(asig_rows)
    tick("asignacion")

    # ---- 4. Contexto de backtest (leído, no recalculado) ---------------
    scheme = CONFIG["primary_scheme"]
    bt_rows = []
    rep1 = reports["motor1"]
    mm = rep1["backtest"]["metric_means_by_variant_scheme"]
    for variant in [rep1["primary_variant"], "heur_metro",
                    "control_aleatorio"]:
        key = f"{variant}|{scheme}"
        if key not in mm:
            raise ValueError(f"Backtest del Motor 1 sin la clave {key}")
        v = mm[key]
        bt_rows.append({
            "motor": "m1", "subject": variant, "scheme": scheme,
            "precision_at_10": v.get("precision@10"),
            "recall_at_10": v.get("recall@10"),
            "ndcg_at_10": v.get("ndcg@10"),
            "decision_coverage": v.get("decision_coverage"),
            "note": None})
    rep2 = reports["motor2"]
    rm = rep2["ranking_means_by_model_scheme"]
    for model in ["constante", "ridge", "random_forest",
                  "ft_transformer"]:
        key = f"{model}|{scheme}"
        if key not in rm:
            raise ValueError(f"Ranking del Motor 2 sin la clave {key}")
        v = rm[key]
        bt_rows.append({
            "motor": "m2", "subject": model, "scheme": scheme,
            "precision_at_10": v.get("precision@10"),
            "recall_at_10": v.get("recall@10"),
            "ndcg_at_10": v.get("ndcg@10"),
            "decision_coverage": v.get("decision_coverage"),
            "note": None})
    bt_rows.append({
        "motor": "m3", "subject": "afinidad_estructural",
        "scheme": None, "precision_at_10": None, "recall_at_10": None,
        "ndcg_at_10": None, "decision_coverage": None,
        "note": "sin backtest de AGEB: el puntaje del Motor 3 es "
                "afinidad estructural, no un modelo de actividad"})
    backtest = pd.DataFrame(bt_rows)
    tick("backtest")

    # ---- Reporte y outputs ----------------------------------------------
    metricas_out = metricas.drop(columns=["metrics"], errors="ignore")
    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "notebook": "08_Evaluacion_Comparativa.ipynb",
        "scope": {
            "never_reruns_motors": True,
            "same_task_same_contract_same_rules": True,
            "radar_area_not_a_score": True,
            "no_aggregate_winner": True,
            "fixed_0_1_axis_scales": True,
            "metrics_recomputed_and_verified": True,
            "m1_m2_no_analog_ceilings": True,
            "m3_golden_proximity_by_construction": True,
        },
        "configuration": CONFIG,
        "upstream": data["upstream_refs"],
        "shared_validation_analysis_id":
            data["upstream_refs"]["shared_validation_analysis_id"],
        "consistency": {
            "n_portfolios_checked": len(consistency),
            "all_feasible": all(c["is_feasible"] for c in consistency),
            "all_metrics_reproduced":
                all(c["metrics_equal"] for c in consistency),
            "rtol": CONFIG["metric_rtol"],
            "checked": consistency,
        },
        "radar_axes_semantics": {
            "cobertura": "new_pop / P_norm(ctx, B)",
            "eficiencia": "1 - redundancia",
            "proximidad_red": "1 - distancia media a la red / max_reach_m",
            "equidad": "fracción de sitios en AGEBs bajo la mediana de "
                       "grado_escolar_prom de todos los sitios",
            "similitud_golden": "1 - fracción de sitios en AGEBs "
                                "out_of_domain del 04",
            "dispersion": "n_agebs / n_selected",
        },
        "metricas": _records(metricas_out),
        "radar": _records(radar),
        "overlap": _records(overlap),
        "consensus_counts": {
            str(b): {
                "selected_by_2plus": int(
                    (consensus.loc[consensus.budget == b, "n_motors"]
                     >= 2).sum()),
                "selected_by_3": int(
                    (consensus.loc[consensus.budget == b, "n_motors"]
                     >= 3).sum()),
            } for b in budgets},
        "asignacion": _records(asignacion),
        "backtest_context": _records(backtest),
        "method_context": {
            "m1_techo_removido": reports["motor1"]["portafolio"].get(
                "techo_removido"),
            "m2_techo_removido": reports["motor2"]["portafolio"].get(
                "techo_removido"),
            "m3_ga_vs_greedy": reports["motor3"].get("ga_vs_greedy"),
            "m3_affinity_scope_warning": reports["motor3"].get(
                "affinity", {}).get("scope_warning"),
            "read_from_published_reports": True,
        },
        "pending_validation": [
            "Comparison is descriptive: no aggregate winner is declared",
            "Radar area is not a score; axes encode different objectives",
            "Motor 3 optimizes golden-hop affinity directly: its "
            "proximity-to-golden metrics are by construction, not "
            "independent evidence",
            "Motors 1 and 2 dropped analog ceilings; their portfolios "
            "changed relative to the previous publications",
            "Areal interpolation and 500 m catchments are assumptions, "
            "not observed demand",
            "No street network, cost, or field validation",
            "Motor 3 has no AGEB backtest: its score is structural "
            "affinity, not an activity model",
        ],
    }

    outputs = [
        ("c8_metricas.csv", "csv", metricas_out),
        ("c8_radar.csv", "csv", radar),
        ("c8_overlap.csv", "csv", overlap),
        ("c8_consensus.parquet", "parquet",
         gpd.GeoDataFrame(consensus, geometry="geometry",
                          crs=sites.crs)),
        ("c8_asignacion.csv", "csv", asignacion),
        ("c8_backtest_contexto.csv", "csv", backtest),
    ]
    return {"report": report, "outputs": outputs,
            "metricas": metricas, "radar": radar, "overlap": overlap,
            "consensus": consensus, "asignacion": asignacion,
            "backtest": backtest, "catalog": catalog,
            "sites": sites, "cells": cells, "stations": stations,
            "features": features, "universe04": universe04,
            "ctx": ctx}
