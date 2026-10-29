"""Motor 1 — baseline estadístico de similitud del coseno (cuaderno 05).

Responde una pregunta acotada: entre AGEBs que ya tienen servicio,
¿puede la similitud de entorno (coseno a un centroide de referencia)
redescubrir las de mayor actividad observada media por estación? Es un
diagnóstico de similitud, NO una estimación de demanda latente ni una
prueba causal: el rankeo territorial final es insumo del Motor 3.

Protocolo inductivo: dentro de cada pliegue se ajusta un pipeline fe03
fresco (imputer/scaler/PCA) únicamente con filas proyectables fuera de
fit_exclusion_ids; la referencia (centroide y compuerta Mahalanobis) se
construye solo con train_target; la compuerta usa df = k_fold. Las
banderas Golden del cuaderno 03 están prohibidas como insumo del motor.
"""
import hashlib
import json
import platform
from pathlib import Path

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import spearmanr

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import eda02_publication
from V3.src import engine_publication as ep
from V3.src import fe03_analysis
from V3.src import fe03_publication
from V3.src import fe04_analysis
from V3.src import fe04_deployment as dep
from V3.src import fe04_publication
from V3.src.fe04_analysis import CONFIG as FE04_CONFIG
from V3.src.fe04_analysis import FOLD_SCHEMES, TARGET

VERSION = "v3-motor1-3"
CONFIG = {
    "variance_target": 0.80,
    "reference_quantile": 0.85,
    "domain_quantile": 0.9973,
    "covariance_estimator": "ledoit_wolf",
    "k_grid": list(FE04_CONFIG["k_grid"]),
    "schemes": list(FOLD_SCHEMES),
    "primary_scheme": "fold_spatial_block",
    "seed": 42,
    "frontier_m": 1000,
    "sensitivity": {
        "variance_target": [0.70, 0.80, 0.90],
        "reference_quantile": [0.75, 0.85, 0.90],
        "domain_quantile": [0.95, 0.99, 0.9973],
    },
    "metric_crs": FE04_CONFIG["metric_crs"],
    "ceiling_neighbors": 5,
}
VARIANTS = ["m1_coseno_compuerta", "m1_coseno_compuerta_empirica",
            "m1_coseno", "m1_euclidiana",
            "heur_metro", "control_aleatorio"]
PRIMARY_VARIANT = "m1_coseno_compuerta"
# publicación previa (v3-motor1-2, con techos por análogos) para el
# contraste documentado de la remoción del techo
PREVIOUS_CEILING_PORTFOLIO_B30 = {
    "new_pop": 153_809.57098202483,
    "n_agebs": 21,
    "stations_per_ageb": {"1": 14, "2": 5, "3+": 2},
}
BIAS_FEATURES = ["grado_escolar_prom", "pct_viviendas_auto",
                 "pct_viviendas_internet", "densidad_pob_km2"]

UPSTREAM_ARTIFACTS = {
    "features": ["entorno_ageb_features.parquet",
                 "pca_espacio_compartido.parquet", "pca_pipeline.joblib"],
    "eda": ["station_environment.parquet"],
    "validation": ["universo_evaluacion.parquet", "cv_folds.parquet",
                   "validation_harness.joblib",
                   "sitios_candidatos.parquet", "celdas_poblacion.parquet"],
}
POINTERS = {
    "eda": "audits/02_eda.json",
    "features": "audits/03_feature_engineering.json",
    "validation": "audits/04_backtest_design.json",
}


# ---------------------------------------------------------------------------
# Insumos verificados e identidad
# ---------------------------------------------------------------------------

def _upstream_context(v3):
    """Verifica ETL + punteros 02/03/04 y registra insumos sin cargar frames."""
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    reports = {
        "features": ep.pointer_verified_report(
            v3, POINTERS["features"], fe03_publication.verify_report,
            fe03_publication.FEATURES_ROOT),
        "eda": ep.pointer_verified_report(
            v3, POINTERS["eda"], eda02_publication.verify_report,
            eda02_publication.EDA_ROOT),
        "validation": ep.pointer_verified_report(
            v3, POINTERS["validation"], fe04_publication.verify_report,
            fe04_publication.VALIDATION_ROOT),
    }
    for name, report in reports.items():
        if report["contract_id"] != contract:
            raise ValueError(f"Upstream {name} report belongs to another contract")
    input_artifacts = {}
    for stage, basenames in UPSTREAM_ARTIFACTS.items():
        for basename, record in ep.artifact_records(
                reports[stage], basenames).items():
            input_artifacts[f"{stage}/{basename}"] = record
    upstream_refs = {
        "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["eda"]).read_bytes()).hexdigest(),
        "feature_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["features"]).read_bytes()).hexdigest(),
        "validation_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["validation"]).read_bytes()).hexdigest(),
        "eda_analysis_id": reports["eda"]["analysis_id"],
        "feature_analysis_id": reports["features"]["analysis_id"],
        "validation_analysis_id": reports["validation"]["analysis_id"],
    }
    return {"audit": audit, "reports": reports,
            "input_artifacts": input_artifacts,
            "upstream_refs": upstream_refs}


def analysis_identity(v3, context):
    identity = {
        "schema_version": VERSION,
        "contract_id": context["audit"]["contract_id"],
        "configuration": CONFIG,
        "variants": VARIANTS, "primary_variant": PRIMARY_VARIANT,
        "input_artifacts": context["input_artifacts"],
        "upstream_refs": context["upstream_refs"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "m1_analysis.py", "m1_content.py", "m1_publication.py",
                "build_notebook_05.py", "engine_publication.py",
                "fe03_analysis.py", "fe03_publication.py",
                "fe04_analysis.py", "fe04_publication.py",
                "fe04_deployment.py",
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
    """Carga todos los insumos verificados: 03, 04, EDA, pipeline y arnés."""
    context = _upstream_context(v3)
    reports = context["reports"]
    pipeline = fe03_publication.load_feature_pipeline(v3)
    harness = fe04_publication.load_validation_harness(v3)
    if harness["callables"]["run_backtest"] is not fe04_analysis.run_backtest:
        raise ValueError("Harness callable is not fe04_analysis.run_backtest")
    deploy_callables = harness["deployment"]["callables"]
    for name in ["is_feasible", "greedy_coverage", "portfolio_metrics"]:
        if deploy_callables[name] is not getattr(dep, name):
            raise ValueError(f"Deployment callable drifted: {name}")
    if harness["deployment"]["config"] != dep.DEPLOY_CONFIG:
        raise ValueError("Deployment config drifted from fe04_deployment")

    frames = {
        "features": _verified_frame(v3, reports["features"],
                                    "entorno_ageb_features.parquet",
                                    geodataframe=True),
        "scores": _verified_frame(v3, reports["features"],
                                  "pca_espacio_compartido.parquet"),
        "universe": _verified_frame(v3, reports["validation"],
                                    "universo_evaluacion.parquet",
                                    geodataframe=True),
        "folds": _verified_frame(v3, reports["validation"],
                                 "cv_folds.parquet"),
        "station_env": _verified_frame(v3, reports["eda"],
                                       "station_environment.parquet",
                                       geodataframe=True),
        "sites": _verified_frame(v3, reports["validation"],
                                 "sitios_candidatos.parquet",
                                 geodataframe=True),
        "cells": _verified_frame(v3, reports["validation"],
                                 "celdas_poblacion.parquet",
                                 geodataframe=True),
    }
    data = {**context, "v3": Path(v3).resolve(), "frames": frames,
            "pipeline": pipeline, "harness": harness}
    data["analysis_id"], data["analysis_identity"] = \
        analysis_identity(v3, context)
    return data


# ---------------------------------------------------------------------------
# Motor: similitud del coseno + compuerta de dominio, por pliegue
# ---------------------------------------------------------------------------

def _cosine_scores(Z, mu):
    """cos(z, mu); norma cero -> NaN (la AGEB no se puede rankear)."""
    Z = np.asarray(Z, dtype=float)
    mu = np.asarray(mu, dtype=float)
    denom = np.linalg.norm(Z, axis=1) * np.linalg.norm(mu)
    out = np.full(Z.shape[0], np.nan)
    valid = denom > 0
    out[valid] = (Z[valid] @ mu) / denom[valid]
    return out


def _euclid_scores(Z, mu):
    return np.linalg.norm(np.asarray(Z, float) - np.asarray(mu, float),
                          axis=1)


def _rank_desc(scores, ids):
    """Orden descendente; NaN al final; desempate por cvegeo ascendente."""
    return [c for _, c in sorted(
        zip(scores, ids),
        key=lambda t: (np.isnan(t[0]),
                       -t[0] if np.isfinite(t[0]) else 0.0, t[1]))]


def _rank_asc(scores, ids):
    """Orden ascendente; NaN al final; desempate por cvegeo ascendente."""
    return [c for _, c in sorted(
        zip(scores, ids),
        key=lambda t: (np.isnan(t[0]),
                       t[0] if np.isfinite(t[0]) else np.inf, t[1]))]


def make_engine(features, variant, cfg):
    """Fábrica de engine_fn(task) con diagnósticos por pliegue en clausura.

    El ajuste no supervisado (pipeline fe03) usa todas las AGEBs
    proyectables fuera de fit_exclusion_ids —incluidas candidatas y
    cubiertas sin estación—; la referencia se construye solo con
    train_target del pliegue.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Undeclared engine variant: {variant}")
    proj = features.loc[features.is_projectable.astype(bool)] \
        .set_index("cvegeo")
    diagnostics, detail_rows = [], []
    rng = np.random.default_rng(cfg["seed"])

    def engine_fn(task):
        test_ids = list(task["test_ids"])
        train_ids = list(task["train_ids"])
        scheme, fold = task["fold_scheme"], task["fold"]
        excluded = set(task["fit_exclusion_ids"])
        diag = {"variant": variant, "fold_scheme": scheme, "fold": fold,
                "k_fold": None, "n_reference": None,
                "reference_threshold": None, "domain_threshold": None,
                "n_in_domain_test": None, "n_test": len(test_ids),
                "covariance_estimator": None, "n_over_p": None,
                "shrinkage": None, "condition_number": None,
                "condition_number_empirical": None,
                "empirical_status": None}

        if variant == "control_aleatorio":
            diagnostics.append(diag)
            return rng.permutation(test_ids).tolist()

        if variant == "heur_metro":
            d = proj.loc[test_ids, "dist_metro_metrobus_m"].to_numpy(float)
            diagnostics.append(diag)
            return _rank_asc(d, test_ids)

        fit_rows = [c for c in proj.index if c not in excluded]
        pipe = fe03_analysis.build_pipeline().set_params(
            pca__n_components=cfg["variance_target"])
        pipe.fit(proj.loc[fit_rows, fe03_analysis.INPUT_COLUMNS])
        k_fold = int(pipe.named_steps["pca"].n_components_)
        Z_train = pipe.transform(
            proj.loc[train_ids, fe03_analysis.INPUT_COLUMNS])
        Z_test = pipe.transform(
            proj.loc[test_ids, fe03_analysis.INPUT_COLUMNS])

        target = task["train_target"].reindex(train_ids).to_numpy(float)
        ref_threshold = float(
            np.quantile(target, cfg["reference_quantile"]))
        ref_mask = target >= ref_threshold
        Z_ref = Z_train[ref_mask]
        mu = Z_ref.mean(axis=0)
        cos = _cosine_scores(Z_test, mu)
        euc = _euclid_scores(Z_test, mu)
        diag.update({"k_fold": k_fold,
                     "n_reference": int(ref_mask.sum()),
                     "reference_threshold": ref_threshold})

        if variant == "m1_euclidiana":
            decision = _rank_asc(euc, test_ids)
            in_domain = np.full(len(test_ids), np.nan)
            dist_m = np.full(len(test_ids), np.nan)
        elif variant == "m1_coseno":
            decision = _rank_desc(cos, test_ids)
            in_domain = np.full(len(test_ids), np.nan)
            dist_m = np.full(len(test_ids), np.nan)
        else:  # coseno + compuerta Mahalanobis (LW primaria / empírica)
            estimator = cfg["covariance_estimator"] \
                if variant == "m1_coseno_compuerta" else "empirical"
            gate = fe04_analysis.fit_mahalanobis(
                Z_ref, quantile=cfg["domain_quantile"],
                estimator=estimator)
            dist_m = fe04_analysis.mahalanobis_distance(
                Z_test, gate["mu"], gate["sigma_inv"])
            in_domain = dist_m <= gate["threshold"]
            eligible = np.isfinite(cos) & in_domain
            kept_ids = [c for c, e in zip(test_ids, eligible) if e]
            ranked = _rank_desc(cos[eligible], kept_ids)
            abstained = sorted(c for c, e in zip(test_ids, eligible)
                               if not e)
            decision = {"ranked": ranked, "abstained": abstained}
            diag.update({
                "domain_threshold": float(gate["threshold"]),
                "n_in_domain_test": int(in_domain.sum()),
                "covariance_estimator": gate["estimator"],
                "n_over_p": gate["n_reference"] / k_fold,
                "shrinkage": float(gate["shrinkage"]),
                "condition_number": _finite(gate["condition_number"])})
            try:
                emp = fe04_analysis.fit_mahalanobis(
                    Z_ref, quantile=cfg["domain_quantile"],
                    estimator="empirical")
                diag.update({
                    "condition_number_empirical": _finite(
                        emp["condition_number"]),
                    "empirical_status": "ok"})
            except ValueError as exc:
                diag.update({"empirical_status": f"rejected: {exc}"})
        diagnostics.append(diag)
        detail_rows.extend(
            {"variant": variant, "fold_scheme": scheme, "fold": fold,
             "cvegeo": c, "cosine": float(c_), "euclidean": float(e_),
             "in_domain": (bool(i) if np.isfinite(i) else None)}
            for c, c_, e_, i in zip(test_ids, cos, euc,
                                    np.asarray(in_domain, dtype=float)))
        return decision

    engine_fn.diagnostics = diagnostics
    engine_fn.detail_rows = detail_rows
    return engine_fn


# ---------------------------------------------------------------------------
# Despliegue: espacio publicado 03 + referencia global + compuerta m1
# ---------------------------------------------------------------------------

def check_deployment_space(pipe, published_scores, proj):
    """El pipeline de despliegue debe reproducir el espacio PCA publicado.

    Reproduce los scores del cuaderno 03 (atol 1e-8) — el espacio de
    despliegue ES el espacio publicado— y coincide con el pipeline
    cargado por el cargador verificado.
    """
    pcs = fe04_analysis.pc_columns(published_scores)
    Z = pipe.transform(proj[fe03_analysis.INPUT_COLUMNS])
    if Z.shape[1] != len(pcs):
        raise ValueError("Deployment space dimension differs from published")
    Z_pub = published_scores.set_index("cvegeo") \
        .loc[proj.index, pcs].to_numpy(float)
    if not np.allclose(Z, Z_pub, rtol=0, atol=1e-8):
        raise ValueError("Deployment pipeline does not reproduce the "
                         "published notebook-03 space")
    return Z


def _attractiveness(cos_score, in_domain):
    """max(cos, 0) dentro de dominio; 0 fuera — insumo declarado del Motor 3."""
    return np.where(in_domain, np.maximum(cos_score, 0.0), 0.0)


def _network_distance(candidates, station_env, metric_crs):
    """Distancia del polígono al punto de estación más cercano, en metros."""
    stations = station_env.to_crs(metric_crs).geometry.union_all()
    return candidates.to_crs(metric_crs).geometry.distance(stations)


def _spearman(x, y):
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3:
        return float("nan")
    return float(spearmanr(pair.x, pair.y).statistic)


def _finite(value):
    value = float(value)
    return value if np.isfinite(value) else None


def _records(df):
    """Registros JSON-seguros: NaN/pd.NA -> None (campo no aplicable)."""
    return df.astype(object).where(pd.notna(df), None) \
        .to_dict(orient="records")


# ---------------------------------------------------------------------------
# Techo teórico por análogos y su backtest (fold-local)
# ---------------------------------------------------------------------------

def _row_cosine(Za, Zb):
    """Coseno fila a fila entre dos matrices (n_a, n_b)."""
    Za = np.asarray(Za, dtype=float)
    Zb = np.asarray(Zb, dtype=float)
    na = np.maximum(np.linalg.norm(Za, axis=1, keepdims=True), 1e-12)
    nb = np.maximum(np.linalg.norm(Zb, axis=1, keepdims=True), 1e-12)
    return (Za / na) @ (Zb / nb).T


def _round_count(x):
    """Redondeo de conteos: floor(x + 0.5), nunca el round() de Python."""
    return int(np.floor(float(x) + 0.5))


def make_ceiling_recorder(features, universe, cfg, k):
    """Engine del esquema primario: misma decisión que la variante
    primaria y, como efecto lateral, el conteo predicho por el techo de
    análogos de cada AGEB de prueba con el pipeline y la referencia del
    pliegue. El comparador ingenuo usa la mediana de densidad de todas
    las AGEBs de entrenamiento retenidas.

    El techo por análogos quedó FUERA del despliegue (v3-motor1-3): este
    backtest se conserva solo como evidencia de esa remoción —en la
    corrida anterior el análogo perdía contra la densidad constante
    mediana, es decir reproducía la densidad histórica de planeación y
    no demanda.
    """
    proj = features.loc[features.is_projectable.astype(bool)] \
        .set_index("cvegeo")
    uni = universe.set_index("cvegeo")
    rows = []

    def engine_fn(task):
        test_ids = list(task["test_ids"])
        train_ids = list(task["train_ids"])
        excluded = set(task["fit_exclusion_ids"])
        scheme, fold = task["fold_scheme"], task["fold"]

        fit_rows = [c for c in proj.index if c not in excluded]
        pipe = fe03_analysis.build_pipeline().set_params(
            pca__n_components=cfg["variance_target"])
        pipe.fit(proj.loc[fit_rows, fe03_analysis.INPUT_COLUMNS])
        Z_train = pipe.transform(
            proj.loc[train_ids, fe03_analysis.INPUT_COLUMNS])
        Z_test = pipe.transform(
            proj.loc[test_ids, fe03_analysis.INPUT_COLUMNS])
        target = task["train_target"].reindex(train_ids).to_numpy(float)
        ref_mask = target >= np.quantile(
            target, cfg["reference_quantile"])
        Z_ref = Z_train[ref_mask]
        ref_ids = np.asarray(train_ids)[ref_mask]
        mu = Z_ref.mean(axis=0)
        cos = _cosine_scores(Z_test, mu)
        gate = fe04_analysis.fit_mahalanobis(
            Z_ref, quantile=cfg["domain_quantile"],
            estimator=cfg["covariance_estimator"])
        dist_m = fe04_analysis.mahalanobis_distance(
            Z_test, gate["mu"], gate["sigma_inv"])
        eligible = np.isfinite(cos) & (dist_m <= gate["threshold"])
        kept_ids = [c for c, e in zip(test_ids, eligible) if e]
        decision = {"ranked": _rank_desc(cos[eligible], kept_ids),
                    "abstained": sorted(
                        c for c, e in zip(test_ids, eligible) if not e)}

        # ---- Registro del techo (no alimenta la decisión) ------------
        ref_density = (uni.n_estaciones / uni.area_km2) \
            .reindex(ref_ids).to_numpy(float)
        retained = [c for c in train_ids if c not in excluded]
        naive_rho = float(np.median(
            (uni.n_estaciones / uni.area_km2)
            .reindex(retained).to_numpy(float)))
        cos_tr = _row_cosine(Z_test, Z_ref)
        for i, cve in enumerate(test_ids):
            top = np.argsort(-cos_tr[i])[:k]
            rho = float(np.median(ref_density[top]))
            area = float(uni.loc[cve, "area_km2"])
            actual = uni.loc[cve, "n_estaciones"]
            rows.append({
                "fold_scheme": scheme, "fold": fold, "cvegeo": cve,
                "rho_analog": rho, "rho_naive": naive_rho,
                "area_km2": area,
                "pred_analog": _round_count(rho * area),
                "pred_naive": _round_count(naive_rho * area),
                "actual": float(actual)
                if pd.notna(actual) else np.nan})
        return decision

    engine_fn.rows = rows
    return engine_fn


def greedy_portfolios(site_score, ctx, deploy_cfg):
    """Portafolios greedy de cobertura SIN techo por AGEB, por presupuesto.

    La cantidad de estaciones que recibe cada AGEB queda determinada solo
    por la cobertura con rendimientos decrecientes; el techo por análogos
    se retiró del despliegue porque reproducía la densidad histórica de
    planeación y perdía contra una densidad constante mediana.
    """
    out = {}
    for budget in deploy_cfg["budget_grid"]:
        sol = dep.greedy_coverage(site_score, ctx, budget)
        if not dep.is_feasible(sol["order"], ctx, budget):
            raise ValueError(f"infeasible Motor1 portfolio at B={budget}")
        out[budget] = sol
    return out


def analyze(data):
    frames = data["frames"]
    universe = frames["universe"]
    folds = frames["folds"]
    features = frames["features"]

    # ---- Backtest: todas las variantes x ambos esquemas ---------------------
    details, summaries, decisions = [], [], []
    diag_rows, engine_detail_rows = [], []
    detail_by = {}
    for variant in VARIANTS:
        for scheme in CONFIG["schemes"]:
            engine = make_engine(features, variant, dict(CONFIG))
            detail, summary, decision = fe04_analysis.run_backtest(
                universe, folds, scheme, engine)
            detail = detail.assign(variant=variant)
            details.append(detail)
            long_summary = summary.reset_index(names="metric").assign(
                variant=variant, fold_scheme=scheme)
            summaries.append(long_summary)
            decisions.append(decision.assign(variant=variant))
            diag_rows.extend(engine.diagnostics)
            engine_detail_rows.extend(engine.detail_rows)
            detail_by[(variant, scheme)] = detail
    backtest_detail = pd.concat(details, ignore_index=True)
    backtest_summary = pd.concat(summaries, ignore_index=True)
    decisions = pd.concat(decisions, ignore_index=True)
    fold_diagnostics = pd.DataFrame(diag_rows)
    engine_detail = pd.DataFrame(engine_detail_rows)

    primary = CONFIG["primary_scheme"]
    # ---- Victorias pliegue a pliegue (descriptivo, 5 pliegues) --------------
    win_counts = []
    for metric in ["ndcg@10", "precision@10"]:
        for other in VARIANTS:
            if other == PRIMARY_VARIANT:
                continue
            a = detail_by[(PRIMARY_VARIANT, primary)][metric]
            b = detail_by[(other, primary)][metric]
            win_counts.append({
                "metric": metric, "comparator": other,
                "wins": int((a > b).sum()), "ties": int((a == b).sum()),
                "losses": int((a < b).sum())})
    win_counts = pd.DataFrame(win_counts)

    # ---- Sensibilidad un factor a la vez (esquema + variante primaria) ------
    sensitivity = []
    for param, values in CONFIG["sensitivity"].items():
        for value in values:
            if value == CONFIG[param]:
                continue
            cfg = dict(CONFIG)
            cfg[param] = value
            engine = make_engine(features, PRIMARY_VARIANT, cfg)
            detail, summary, _ = fe04_analysis.run_backtest(
                universe, folds, primary, engine)
            row = {"parameter": param, "value": value,
                   "k_fold_mean": float(pd.DataFrame(
                       engine.diagnostics).k_fold.mean())}
            for metric in [c for c in detail.columns if "@" in c
                           or c == "decision_coverage"
                           or c == "relevant_abstained"]:
                row[f"mean_{metric}"] = _finite(detail[metric].mean())
            sensitivity.append(row)
    sensitivity = pd.DataFrame(sensitivity)

    # ---- Despliegue: espacio publicado + referencia global + compuerta ------
    proj = features.loc[features.is_projectable.astype(bool)] \
        .set_index("cvegeo")
    pipe_full = fe03_analysis.build_pipeline()
    pipe_full.fit(proj[fe03_analysis.INPUT_COLUMNS])
    Z_full = check_deployment_space(pipe_full, frames["scores"], proj)
    Z_loader = data["pipeline"].transform(proj[fe03_analysis.INPUT_COLUMNS])
    if not np.allclose(Z_full, Z_loader, rtol=0, atol=1e-8):
        raise ValueError("Deployment pipeline disagrees with the verified "
                         "loaded notebook-03 pipeline")

    eval_rows = universe.loc[universe.in_evaluation_universe] \
        .set_index("cvegeo")
    ref_threshold = float(np.quantile(
        eval_rows[TARGET].to_numpy(float), CONFIG["reference_quantile"]))
    reference_ids = eval_rows.index[
        eval_rows[TARGET].to_numpy(float) >= ref_threshold].tolist()
    reference = eval_rows.loc[reference_ids, [
        TARGET, "is_golden_cluster", "domain_status"]].reset_index()
    golden_xtab = pd.crosstab(
        reference_ids_series := eval_rows[TARGET].ge(ref_threshold)
        .map({True: "in_reference", False: "below_reference"}),
        eval_rows.is_golden_cluster.map({True: "golden_03", False: "non_golden"}))
    Z_ref_full = pipe_full.transform(
        proj.loc[reference_ids, fe03_analysis.INPUT_COLUMNS])
    gate_full = fe04_analysis.fit_mahalanobis(
        Z_ref_full, quantile=CONFIG["domain_quantile"],
        estimator=CONFIG["covariance_estimator"])
    try:
        gate_full_emp = fe04_analysis.fit_mahalanobis(
            Z_ref_full, quantile=CONFIG["domain_quantile"],
            estimator="empirical")
        empirical_gate_contrast = {
            "status": "ok",
            "condition_number": _finite(gate_full_emp["condition_number"])}
    except ValueError as exc:
        empirical_gate_contrast = {
            "status": f"rejected: {exc}", "condition_number": None}
    mu_full = Z_ref_full.mean(axis=0)

    # ---- Ranking territorial de candidatas proyectables ---------------------
    candidates = features.loc[
        features.is_candidata_proyectable.astype(bool)].set_index("cvegeo")
    Z_c = pipe_full.transform(candidates[fe03_analysis.INPUT_COLUMNS])
    cos_c = _cosine_scores(Z_c, mu_full)
    dist_c = fe04_analysis.mahalanobis_distance(
        Z_c, gate_full["mu"], gate_full["sigma_inv"])
    in_domain = dist_c <= gate_full["threshold"]

    order_gated = _rank_desc(cos_c[in_domain],
                           candidates.index[in_domain].tolist())
    rank_m1 = pd.Series(
        {c: i + 1 for i, c in enumerate(order_gated)}, dtype="Int64")
    order_all = _rank_desc(cos_c, candidates.index.tolist())
    rank_open = pd.Series(
        {c: i + 1 for i, c in enumerate(order_all)}, dtype="Int64")
    status_04 = universe.set_index("cvegeo").domain_status \
        .reindex(candidates.index)

    ranking = gpd.GeoDataFrame({
        "cvegeo": candidates.index,
        "nom_mun": candidates.nom_mun.to_numpy(),
        "geometry": candidates.geometry.to_numpy(),
        "cos_score": cos_c,
        "mahalanobis_m1": dist_c,
        "domain_status_m1": np.where(in_domain, "in_domain",
                                     "out_of_domain"),
        "domain_status_04": status_04.to_numpy(),
        "rank_m1": candidates.index.map(rank_m1).astype("Int64"),
        "rank_sin_compuerta": candidates.index.map(rank_open)
        .astype("Int64"),
        "attractiveness": _attractiveness(cos_c, in_domain),
        "dist_red_m": _network_distance(
            candidates, frames["station_env"],
            CONFIG["metric_crs"]).to_numpy(),
    }, geometry="geometry", crs=candidates.crs)
    ranking["frontera"] = ranking.dist_red_m <= CONFIG["frontier_m"]

    status_xtab = pd.crosstab(
        ranking.domain_status_m1, ranking.domain_status_04,
        dropna=False)

    top50 = ranking.loc[ranking.rank_m1.notna()].nsmallest(50, "rank_m1")
    # ---- Diagnósticos de sesgo/conectividad ---------------------------------
    bias_rows = []
    for name in BIAS_FEATURES:
        x = candidates[name].astype(float)
        bias_rows.append({
            "feature": name,
            "spearman_cos": _spearman(cos_c, x),
            "mean_top50_in_domain": _finite(x.loc[top50.cvegeo].mean()),
            "mean_all_candidates": _finite(x.mean()),
        })
    bias = pd.DataFrame(bias_rows)

    # ---- Backtest del techo (evidencia de su remoción del despliegue) ------
    recorder = make_ceiling_recorder(
        features, universe, dict(CONFIG), CONFIG["ceiling_neighbors"])
    fe04_analysis.run_backtest(universe, folds, primary, recorder)
    ceiling_bt = pd.DataFrame(recorder.rows)
    ceiling_backtest_summary = {
        "mae_analog": _finite(
            (ceiling_bt.pred_analog - ceiling_bt.actual).abs().mean()),
        "spearman_analog": _finite(_spearman(
            ceiling_bt.pred_analog, ceiling_bt.actual)),
        "mae_naive": _finite(
            (ceiling_bt.pred_naive - ceiling_bt.actual).abs().mean()),
        "spearman_naive": _finite(_spearman(
            ceiling_bt.pred_naive, ceiling_bt.actual)),
        "n_rows": int(len(ceiling_bt)),
        "role": "historical diagnostic only — evidence supporting the "
                "removal of the analog ceiling from deployment: it "
                "reproduces historical planning density, not demand, "
                "and loses against a constant median density",
        "previous_publication": {
            "mae_analog": 1.669, "spearman_analog": 0.355,
            "mae_naive": 1.227, "spearman_naive": 0.295,
            "source": "v3-motor1-2 report"},
    }

    # ---- Portafolio bajo el contrato de despliegue del 04 -------------------
    deploy_cfg = dep.DEPLOY_CONFIG
    metric = CONFIG["metric_crs"]
    sites = frames["sites"].to_crs(metric).reset_index(drop=True)
    cells = frames["cells"].to_crs(metric).reset_index(drop=True)
    incidence = dep.site_cell_incidence(
        np.c_[sites.x, sites.y], cells, deploy_cfg)
    stations_m = frames["station_env"].to_crs(metric)
    ctx = dep.build_network_context(
        sites, cells, incidence, stations_m, deploy_cfg)

    attr_map = ranking.set_index("cvegeo").attractiveness
    site_score = sites.cvegeo.map(attr_map).fillna(0.0).to_numpy()
    portfolios = greedy_portfolios(site_score, ctx, deploy_cfg)

    port_frames, portfolio_metrics_by = [], {}
    for budget, sol in portfolios.items():
        metrics = dep.portfolio_metrics(
            sol["order"], ctx, sites, features, universe)
        portfolio_metrics_by[str(budget)] = {
            "stop_reason": sol["stop_reason"], **metrics}
        frame = dep.portfolio_frame(
            sol["order"], sol["attach"], sites, ctx)
        frame["budget"] = budget
        frame["score"] = site_score[list(sol["order"])]
        port_frames.append(frame)
    portafolios = gpd.GeoDataFrame(
        pd.concat(port_frames, ignore_index=True),
        geometry="geometry", crs=sites.crs)

    # contraste documentado: mismo motor con techos por análogos
    # (publicación v3-motor1-2) vs el portafolio actual sin techos
    prev_b30 = PREVIOUS_CEILING_PORTFOLIO_B30
    new_b30 = portfolio_metrics_by.get("30", {})
    techo_removido = {
        "previous_schema": "v3-motor1-2",
        "previous_B30": prev_b30,
        "current_B30": {k: new_b30.get(k) for k in
                        ["new_pop", "n_agebs", "stations_per_ageb"]},
        "delta_B30_new_pop": _finite(new_b30["new_pop"]
                                     - prev_b30["new_pop"])
        if new_b30.get("new_pop") is not None else None,
        "delta_B30_n_agebs": new_b30["n_agebs"] - prev_b30["n_agebs"]
        if new_b30.get("n_agebs") is not None else None,
    }

    # ---- Reporte ------------------------------------------------------------
    k_metrics = [c for c in backtest_detail.columns if "@" in c
                 or c in ("decision_coverage", "relevant_abstained")]
    means = {}
    for (variant, scheme), detail in detail_by.items():
        means[f"{variant}|{scheme}"] = {
            metric: _finite(detail[metric].mean()) for metric in k_metrics}

    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "notebook": "05_Motor1_Baseline_Estadistico.ipynb",
        "scope": {
            "is_baseline": True, "similarity_is_not_demand": True,
            "territorial_ranking_no_coordinates": True,
            "solves_shared_deployment_task": True,
            "no_motor2_motor3_inputs": True,
            "golden_flags_forbidden_as_inputs": True,
        },
        "configuration": CONFIG,
        "variants": VARIANTS, "primary_variant": PRIMARY_VARIANT,
        "upstream": data["upstream_refs"],
        "backtest": {
            "metric_means_by_variant_scheme": means,
            "win_counts_primary_scheme": win_counts.to_dict(
                orient="records"),
            "win_counts_note": "descriptive 5-fold counts; no "
                               "significance claims",
        },
        "fold_diagnostics": _records(fold_diagnostics),
        "sensitivity": sensitivity.to_dict(orient="records"),
        "deployment": {
            "space_reproduction": "deployment space = published 03 "
                                  "space (atol 1e-8, verified vs scores "
                                  "and loaded pipeline)",
            "reference_quantile": CONFIG["reference_quantile"],
            "reference_threshold": ref_threshold,
            "n_reference": len(reference_ids),
            "reference_vs_golden03": golden_xtab.astype(int).to_dict(),
            "gate": {
                **{key: _finite(gate_full[key]) for key in
                   ["threshold", "min_eigenvalue", "condition_number",
                    "n_reference", "k_dims", "covariance_rank",
                    "quantile", "df", "chi2_ppf", "shrinkage"]},
                "estimator": gate_full["estimator"],
                "n_over_p": gate_full["n_reference"] / gate_full["k_dims"],
                "empirical_contrast": empirical_gate_contrast,
                "threshold_note": "chi2 nominal: under Ledoit-Wolf "
                                  "shrinkage the reference distances no "
                                  "longer follow chi2_k exactly"},
            "candidates": int(len(ranking)),
            "candidates_in_domain_m1": int(in_domain.sum()),
            "candidates_out_domain_m1": int((~in_domain).sum()),
            "m1_vs_04_status": status_xtab.astype(int).to_dict(),
            "top50_in_domain_frontier": int(top50.frontera.sum()),
            "attractiveness_definition": "max(cos_score, 0) if in_domain "
                                         "else 0; Motor 3 input",
        },
        "bias_diagnostics": bias.to_dict(orient="records"),
        "connectivity": {
            "frontier_m": CONFIG["frontier_m"],
            "median_dist_red_top50": _finite(top50.dist_red_m.median()),
            "median_dist_red_all": _finite(ranking.dist_red_m.median()),
            "note": "connectivity is descriptive in the territorial "
                    "ranking; the portfolio solves it under the "
                    "shared contract",
        },
        "ceiling_backtest": ceiling_backtest_summary,
        "portafolio": {
            "metodo": "greedy_coverage del contrato 04 SIN techos "
                      "por AGEB; site_score = attractiveness "
                      "de la AGEB anfitriona; estaciones por AGEB solo "
                      "resultan de la cobertura con rendimientos "
                      "decrecientes",
            "budget_grid": deploy_cfg["budget_grid"],
            "techo_removido": techo_removido,
            "por_presupuesto": portfolio_metrics_by,
        },
        "pending_validation": [
            "Sensitivity of deployment ranking to domain/reference "
            "quantiles beyond one-at-a-time",
        ],
    }

    outputs = [
        ("m1_backtest_detail.csv", "csv", backtest_detail),
        ("m1_backtest_summary.csv", "csv", backtest_summary),
        ("m1_decisions.parquet", "parquet", decisions),
        ("m1_fold_diagnostics.csv", "csv", fold_diagnostics),
        ("m1_sensitivity.csv", "csv", sensitivity),
        ("m1_ranking_candidatas.parquet", "parquet", ranking),
        ("m1_reference.csv", "csv", reference),
        ("m1_portafolios.parquet", "parquet", portafolios),
        ("m1_ceiling_backtest.csv", "csv", ceiling_bt),
        ("m1_pipeline.joblib", "joblib", {
            "pipeline": pipe_full, "mu": mu_full,
            "mahalanobis": {k: gate_full[k] for k in
                            ["mu", "sigma", "sigma_inv", "threshold",
                             "min_eigenvalue", "condition_number",
                             "n_reference", "k_dims", "covariance_rank",
                             "quantile", "df", "chi2_ppf",
                             "estimator", "shrinkage"]}}),
    ]
    return {"report": report, "outputs": outputs,
            "backtest_detail": backtest_detail,
            "backtest_summary": backtest_summary,
            "decisions": decisions,
            "fold_diagnostics": fold_diagnostics,
            "engine_detail": engine_detail,
            "sensitivity": sensitivity,
            "ranking": ranking, "reference": reference,
            "win_counts": win_counts, "bias": bias, "top50": top50,
            "portafolios": portafolios,
            "ceiling_bt": ceiling_bt, "sites": sites,
            "portfolio_metrics_by": portfolio_metrics_by}
