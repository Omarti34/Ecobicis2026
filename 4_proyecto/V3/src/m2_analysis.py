"""Motor 2 — estudio honesto de capacidad de un Transformer tabular (06).

Pregunta acotada: ¿un modelo flexible aprende relaciones útiles fuera de
muestra entre el entorno de la AGEB y la actividad observada media por
estación, o solo memoriza una muestra pequeña (n=242, concentrada en el
centro y con dependencia espacial)? No hay nada temporal aquí: el Motor 2
de series de stock-out quedó descartado del diseño vigente.

Protocolo supervisado estricto: dentro de cada pliegue el preprocesador
(contrato fe03 + imputación por mediana + escalado, SIN PCA —los 18
atributos entran a todos los modelos—) se ajusta solo con las filas de
entrenamiento retenido; el objetivo es log1p(actividad_media_estacion).
Los hiperparámetros están fijados a priori; el Transformer detiene
temprano sobre una partición INTERNA agrupada del entrenamiento (bloques
espaciales en el esquema primario, cvegeo en el esquema AGEB). Ningún
modelo ve objetivos de prueba ni filas de fit_exclusion_ids.

Desde v3-motor2-3 el FT-Transformer queda SOLO como caso de estudio del
backtest (su ventaja sobre el mejor control es mucho menor que su
variación entre semillas: navaja de Ockham). El modelo tabular de
despliegue es el Random Forest —por parsimonia y estabilidad, no por
dominancia demostrada— bajo la misma compuerta de dominio propia y sin
techo por análogos: el número de estaciones por AGEB es resultado puro
de la cobertura con rendimientos decrecientes.
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
import torch
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupShuffleSplit, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from torch import nn

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

VERSION = "v3-motor2-3"
CONFIG = {
    "seed": 42,
    "seeds": [0, 1, 2, 3, 4],
    "learning_curve_seeds": [0, 1, 2],
    "inner_val_fraction": 0.2,
    "k_grid": list(FE04_CONFIG["k_grid"]),
    "schemes": list(FOLD_SCHEMES),
    "primary_scheme": "fold_spatial_block",
    "d_token": 32, "n_layers": 2, "nhead": 4, "dim_feedforward": 64,
    "dropout": 0.1, "lr": 1e-3, "weight_decay": 1e-4,
    "batch_size": 32, "max_epochs": 400, "patience": 40,
    "learning_curve_fractions": [0.5, 0.75, 1.0],
    "permutation_repeats": 10,
    "reference_quantile": 0.85,
    "domain_quantile": 0.9973,
    "ceiling_neighbors": 5,
    "metric_crs": FE04_CONFIG["metric_crs"],
}
MODELS = ["constante", "ridge", "random_forest", "ft_transformer"]
CONTROLS = ["ridge", "random_forest"]
EXTRAPOLATION_FLAG = ("extrapolación a territorio sin servicio; escala de "
                      "actividad observada; exploratorio")
# Portafolio B=30 de la publicación previa (v3-motor2-2: puntaje
# Transformer + techo por análogos), conservado solo como referencia del
# cambio que produjo la remoción del techo.
PREVIOUS_CEILING_PORTFOLIO_B30 = {
    "schema": "v3-motor2-2",
    "new_pop": 275943.27107271005,
    "n_agebs": 26,
    "stations_per_ageb": {"1": 23, "2": 2, "3+": 1},
}

UPSTREAM_ARTIFACTS = {
    "features": ["entorno_ageb_features.parquet"],
    "eda": ["station_environment.parquet"],
    "validation": ["universo_evaluacion.parquet", "cv_folds.parquet",
                   "validation_harness.joblib",
                   "sitios_candidatos.parquet",
                   "celdas_poblacion.parquet"],
}
POINTERS = {
    "features": "audits/03_feature_engineering.json",
    "validation": "audits/04_backtest_design.json",
    "eda": "audits/02_eda.json",
}


# ---------------------------------------------------------------------------
# Insumos verificados e identidad
# ---------------------------------------------------------------------------

def _upstream_context(v3):
    """Verifica ETL + punteros 02/03/04; Motor 2 no usa 05 ni 07."""
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    reports = {
        "features": ep.pointer_verified_report(
            v3, POINTERS["features"], fe03_publication.verify_report,
            fe03_publication.FEATURES_ROOT),
        "validation": ep.pointer_verified_report(
            v3, POINTERS["validation"], fe04_publication.verify_report,
            fe04_publication.VALIDATION_ROOT),
        "eda": ep.pointer_verified_report(
            v3, POINTERS["eda"], eda02_publication.verify_report,
            eda02_publication.EDA_ROOT),
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
        "feature_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["features"]).read_bytes()).hexdigest(),
        "validation_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["validation"]).read_bytes()).hexdigest(),
        "eda_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["eda"]).read_bytes()).hexdigest(),
        "feature_analysis_id": reports["features"]["analysis_id"],
        "validation_analysis_id": reports["validation"]["analysis_id"],
        "eda_analysis_id": reports["eda"]["analysis_id"],
        "motor1_motor3_not_inputs": True,
    }
    return {"audit": audit, "reports": reports,
            "input_artifacts": input_artifacts,
            "upstream_refs": upstream_refs}


def analysis_identity(v3, context):
    identity = {
        "schema_version": VERSION,
        "contract_id": context["audit"]["contract_id"],
        "configuration": CONFIG,
        "models": MODELS,
        "input_artifacts": context["input_artifacts"],
        "upstream_refs": context["upstream_refs"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "m2_analysis.py", "m2_content.py", "m2_publication.py",
                "build_notebook_06.py", "engine_publication.py",
                "fe03_analysis.py", "fe03_publication.py",
                "fe04_analysis.py", "fe04_publication.py",
                "fe04_deployment.py",
            ]
        },
        "versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "geopandas": gpd.__version__,
            "scipy": scipy.__version__, "sklearn": sklearn.__version__,
            "joblib": joblib.__version__, "torch": torch.__version__,
        },
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), identity


def _verified_frame(v3, report, basename, geodataframe=False):
    path = ep.verified_artifact_path(v3, report, basename)
    return (gpd.read_parquet if geodataframe else pd.read_parquet)(path)


def load_inputs(v3):
    """Carga todos los insumos verificados: 02, 03 y 04 (arnés+contrato)."""
    context = _upstream_context(v3)
    reports = context["reports"]
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
        "universe": _verified_frame(v3, reports["validation"],
                                    "universo_evaluacion.parquet",
                                    geodataframe=True),
        "folds": _verified_frame(v3, reports["validation"],
                                 "cv_folds.parquet"),
        "sites": _verified_frame(v3, reports["validation"],
                                 "sitios_candidatos.parquet",
                                 geodataframe=True),
        "cells": _verified_frame(v3, reports["validation"],
                                 "celdas_poblacion.parquet",
                                 geodataframe=True),
        "station_env": _verified_frame(v3, reports["eda"],
                                       "station_environment.parquet",
                                       geodataframe=True),
    }
    data = {**context, "v3": Path(v3).resolve(), "frames": frames,
            "harness": harness}
    data["analysis_id"], data["analysis_identity"] = \
        analysis_identity(v3, context)
    return data


# ---------------------------------------------------------------------------
# Preprocesado supervisado y modelos
# ---------------------------------------------------------------------------

def build_preprocessor():
    """Contrato fe03 + mediana + escalado; SIN PCA (18 atributos)."""
    return Pipeline([
        ("features", fe03_analysis.FeatureContractTransformer()),
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])


class FTTransformer(nn.Module):
    """FT-Transformer tabular: token por atributo + CLS, cabeza sobre CLS."""

    def __init__(self, n_features, d_token=32, n_layers=2, nhead=4,
                 dim_feedforward=64, dropout=0.1):
        super().__init__()
        self.n_features = n_features
        self.d_token = d_token
        self.feature_weight = nn.Parameter(
            torch.randn(n_features, d_token) * 0.02)
        self.feature_bias = nn.Parameter(torch.zeros(n_features, d_token))
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_token))
        layer = nn.TransformerEncoderLayer(
            d_model=d_token, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, batch_first=True, norm_first=True,
            activation="gelu")
        self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
        self.head = nn.Sequential(
            nn.LayerNorm(d_token), nn.ReLU(), nn.Linear(d_token, 1))

    def forward(self, x):
        tokens = x.unsqueeze(-1) * self.feature_weight + self.feature_bias
        cls = self.cls_token.expand(x.shape[0], -1, -1)
        encoded = self.encoder(torch.cat([cls, tokens], dim=1))
        return self.head(encoded[:, 0]).squeeze(-1)


def _torch_seed(seed):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(1)
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass


def fit_ft_transformer(Z, y_log, groups, seed, cfg):
    """Ajusta un FT-Transformer con parada temprana agrupada interna.

    y se estandariza con media/desviación del subconjunto de ajuste; el
    mejor estado según pérdida de validación interna se restaura al final.
    """
    _torch_seed(seed)
    y_mu = float(np.mean(y_log))
    y_sd = float(np.std(y_log)) or 1.0
    ys = (y_log - y_mu) / y_sd
    tr_idx, val_idx = next(GroupShuffleSplit(
        n_splits=1, test_size=cfg["inner_val_fraction"],
        random_state=seed).split(Z, ys, groups))
    model = FTTransformer(
        Z.shape[1], d_token=cfg["d_token"], n_layers=cfg["n_layers"],
        nhead=cfg["nhead"], dim_feedforward=cfg["dim_feedforward"],
        dropout=cfg["dropout"])
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    X_all = torch.tensor(Z, dtype=torch.float32)
    y_all = torch.tensor(ys, dtype=torch.float32)
    X_tr, y_tr = X_all[tr_idx], y_all[tr_idx]
    X_val, y_val = X_all[val_idx], y_all[val_idx]
    rng = np.random.default_rng(seed)
    batch = cfg["batch_size"]
    history, best_state, best_val, best_epoch, wait = [], None, np.inf, -1, 0
    for epoch in range(cfg["max_epochs"]):
        model.train()
        order = rng.permutation(len(tr_idx))
        total, count = 0.0, 0
        for start in range(0, len(order), batch):
            idx = order[start:start + batch]
            loss = nn.functional.mse_loss(model(X_tr[idx]), y_tr[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += float(loss) * len(idx)
            count += len(idx)
        model.eval()
        with torch.no_grad():
            val_loss = float(nn.functional.mse_loss(model(X_val), y_val))
        history.append({"epoch": epoch, "train_loss": total / count,
                        "val_loss": val_loss})
        if val_loss < best_val - 1e-6:
            best_val, best_epoch, wait = val_loss, epoch, 0
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait > cfg["patience"]:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return {"model": model, "y_mu": y_mu, "y_sd": y_sd,
            "history": history, "best_epoch": best_epoch,
            "train_idx": tr_idx, "val_idx": val_idx}


def predict_ft(fit, Z):
    with torch.no_grad():
        pred = fit["model"](torch.tensor(Z, dtype=torch.float32)) \
            .numpy() * fit["y_sd"] + fit["y_mu"]
    return np.asarray(pred, dtype=float)


def fit_model(name, X_train, y_log, groups, cfg, seeds=None):
    """Ajusta un modelo solo con filas/etiquetas de entrenamiento.

    X_train conserva el índice cvegeo; groups alimenta la partición
    interna del Transformer. Devuelve un bundle con el preprocesador.
    """
    if name not in MODELS:
        raise ValueError(f"Undeclared model: {name}")
    prep = build_preprocessor()
    Z = prep.fit_transform(X_train)
    bundle = {"model": name, "prep": prep, "seeds_fits": None}
    if name == "constante":
        bundle["mean"] = float(np.mean(y_log))
    elif name == "ridge":
        bundle["estimator"] = RidgeCV(
            alphas=np.logspace(-3, 3, 13),
            cv=KFold(5, shuffle=True, random_state=cfg["seed"]),
        ).fit(Z, y_log)
    elif name == "random_forest":
        bundle["estimator"] = RandomForestRegressor(
            n_estimators=500, min_samples_leaf=5, max_features=0.5,
            random_state=cfg["seed"], n_jobs=1).fit(Z, y_log)
    else:
        bundle["seeds_fits"] = [
            fit_ft_transformer(Z, y_log, groups, seed, cfg)
            for seed in (seeds if seeds is not None else cfg["seeds"])]
    return bundle


def _predict_Z(bundle, Z):
    if bundle["model"] == "constante":
        return np.full(Z.shape[0], bundle["mean"]), None
    if bundle["model"] in ("ridge", "random_forest"):
        return bundle["estimator"].predict(Z).astype(float), None
    per_seed = {i: predict_ft(fit, Z)
                for i, fit in enumerate(bundle["seeds_fits"])}
    ensemble = np.mean(list(per_seed.values()), axis=0)
    return ensemble, per_seed


def predict_model(bundle, X):
    """Predicción en escala log; para el Transformer también por semilla."""
    return _predict_Z(bundle, bundle["prep"].transform(X))


# ---------------------------------------------------------------------------
# Motor de pliegue supervisado
# ---------------------------------------------------------------------------

def _rank_desc(scores, ids):
    return [c for _, c in sorted(
        zip(scores, ids),
        key=lambda t: (np.isnan(t[0]),
                       -t[0] if np.isfinite(t[0]) else 0.0, t[1]))]


def _inner_groups(task, train_ids, block_of):
    if task["fold_scheme"] == "fold_spatial_block":
        return block_of.reindex(train_ids).to_numpy()
    return np.asarray(train_ids)


def make_engine(features, folds, model, cfg):
    """engine_fn(task) supervisado: ajusta solo con train_ids/train_target.

    Guarda en clausura los bundles ajustados por pliegue y las
    predicciones de prueba (conjunto y por semilla); devuelve el ranking
    completo por predicción descendente. Sin abstención: la pregunta de
    dominio pertenece a los motores 05/07.
    """
    X = features.set_index("cvegeo")
    block_of = folds.set_index("cvegeo").spatial_block_id
    fits, predictions = {}, []

    def engine_fn(task):
        train_ids = list(task["train_ids"])
        test_ids = list(task["test_ids"])
        fold = task["fold"]
        y_tr = np.log1p(
            task["train_target"].reindex(train_ids).to_numpy(float))
        groups = _inner_groups(task, train_ids, block_of)
        bundle = fit_model(model, X.loc[train_ids,
                                        fe03_analysis.INPUT_COLUMNS],
                           y_tr, groups, cfg)
        y_hat_test, per_seed = predict_model(
            bundle, X.loc[test_ids, fe03_analysis.INPUT_COLUMNS])
        y_hat_train, _ = predict_model(
            bundle, X.loc[train_ids, fe03_analysis.INPUT_COLUMNS])
        fits[fold] = {"bundle": bundle, "train_ids": train_ids,
                      "test_ids": test_ids, "y_train": y_tr,
                      "y_pred_train": y_hat_train}
        predictions.extend(
            {"fold_scheme": task["fold_scheme"], "fold": fold,
             "cvegeo": c, "model": model, "seed": -1,
             "y_pred_log": float(p)}
            for c, p in zip(test_ids, y_hat_test))
        if per_seed:
            predictions.extend(
                {"fold_scheme": task["fold_scheme"], "fold": fold,
                 "cvegeo": c, "model": model, "seed": s,
                 "y_pred_log": float(p)}
                for s, arr in per_seed.items() for c, p in zip(test_ids, arr))
        return _rank_desc(y_hat_test, test_ids)

    engine_fn.fits = fits
    engine_fn.predictions = predictions
    return engine_fn


def _recording_engine():
    """Motor que solo registra tareas (ranking trivial) para curvas."""
    tasks = []

    def engine_fn(task):
        tasks.append(task)
        return list(task["test_ids"])

    engine_fn.tasks = tasks
    return engine_fn


# ---------------------------------------------------------------------------
# Métricas de regresión, curvas de aprendizaje e importancia por permutación
# ---------------------------------------------------------------------------

def regression_metrics(y_true, y_pred):
    """RMSE, MAE, R² y Spearman en escala log."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    resid = y_true - y_pred
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    mae = float(np.mean(np.abs(resid)))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = float(1 - np.sum(resid ** 2) / ss_tot) if ss_tot > 0 else np.nan
    rho = float(spearmanr(y_true, y_pred).statistic) if len(y_true) > 2 \
        else np.nan
    return {"rmse": rmse, "mae": mae, "r2": r2, "spearman": rho}


def _subsample_ids(train_ids, fraction, fold):
    ids = sorted(train_ids)
    n = max(1, int(round(len(ids) * fraction)))
    rng = np.random.default_rng(42 + fold)
    return sorted(rng.choice(ids, size=n, replace=False).tolist())


def learning_curve(tasks, features, cfg):
    """RMSE de prueba por fracción de entrenamiento retenido.

    Misma submuestra (default_rng(42+fold)) para todos los modelos; el
    Transformer usa cfg["learning_curve_seeds"].
    """
    X = features.set_index("cvegeo")
    rows = []
    for task in tasks:
        fold = task["fold"]
        test_ids = list(task["test_ids"])
        for fraction in cfg["learning_curve_fractions"]:
            sub_ids = _subsample_ids(task["train_ids"], fraction, fold)
            y_sub = np.log1p(
                task["train_target"].reindex(sub_ids).to_numpy(float))
            groups = _inner_groups(task, sub_ids,
                                   task["_block_of"])
            for model in CONTROLS + ["ft_transformer"]:
                seeds = (cfg["learning_curve_seeds"]
                         if model == "ft_transformer" else None)
                bundle = fit_model(
                    model, X.loc[sub_ids, fe03_analysis.INPUT_COLUMNS],
                    y_sub, groups, cfg, seeds=seeds)
                pred, _ = predict_model(
                    bundle, X.loc[test_ids, fe03_analysis.INPUT_COLUMNS])
                rows.append({"fold": fold, "fraction": fraction,
                             "model": model,
                             "n_train": len(sub_ids),
                             "rmse": regression_metrics(
                                 task["_y_test"], pred)["rmse"]})
    return pd.DataFrame(rows)


def permutation_importance(fits, features, cfg):
    """ΔRMSE al permutar cada atributo en la prueba de cada pliegue.

    Se permuta la columna ya transformada (la entrada real del modelo):
    permutar columnas crudas rompería el contrato de fe03 —p. ej. la suma
    de shares sectoriales <= 1—. 10 repeticiones con rng 42, promediadas
    sobre pliegues. Es asociación predictiva dentro del modelo ajustado,
    no causalidad.
    """
    X = features.set_index("cvegeo")
    rng = np.random.default_rng(42)
    rows = []
    for fold in sorted(fits):
        fit = fits[fold]
        test_ids = fit["test_ids"]
        Z_test = np.asarray(fit["bundle"]["prep"].transform(
            X.loc[test_ids, fe03_analysis.INPUT_COLUMNS]), dtype=float)
        y_test = fit["_y_test"]
        base_pred, _ = _predict_Z(fit["bundle"], Z_test)
        base_rmse = regression_metrics(y_test, base_pred)["rmse"]
        for j, feature in enumerate(fe03_analysis.FEATURE_NAMES):
            deltas = []
            for _ in range(cfg["permutation_repeats"]):
                Z_perm = Z_test.copy()
                Z_perm[:, j] = rng.permutation(Z_perm[:, j])
                pred, _ = _predict_Z(fit["bundle"], Z_perm)
                deltas.append(regression_metrics(y_test, pred)["rmse"]
                              - base_rmse)
            rows.append({"fold": fold, "feature": feature,
                         "delta_rmse_mean": float(np.mean(deltas)),
                         "delta_rmse_std": float(np.std(deltas))})
    return pd.DataFrame(rows)


def dictamen(rmse_by_model, seed_std_mean, min_wins=4):
    """Regla mecánica declarada a priori.

    transformer_aporta iff (a) media RMSE primario del Transformer <
    min(media ridge, media bosque), (b) gana al mejor control en >=4 de
    5 pliegues y (c) la mejora media supera la media del std por semilla.
    """
    means = {m: float(np.mean(v)) for m, v in rmse_by_model.items()}
    best_control = min(CONTROLS, key=lambda m: means[m])
    ft_mean = means["ft_transformer"]
    fold_wins = int(np.sum(
        np.asarray(rmse_by_model["ft_transformer"])
        < np.asarray(rmse_by_model[best_control])))
    improvement = means[best_control] - ft_mean
    a = ft_mean < min(means["ridge"], means["random_forest"])
    b = fold_wins >= min_wins
    c = improvement > seed_std_mean
    return {
        "transformer_aporta": bool(a and b and c),
        "condition_a_rmse_below_controls": bool(a),
        "condition_b_fold_wins_vs_best_control": fold_wins,
        "condition_b_required": min_wins,
        "condition_c_improvement": improvement,
        "condition_c_seed_std_mean": seed_std_mean,
        "condition_c_holds": bool(c),
        "best_control": best_control,
        "mean_rmse": means,
    }


def _finite(value):
    value = float(value)
    return value if np.isfinite(value) else None


def _records(df):
    """Registros JSON-seguros: NaN/pd.NA -> None (campo no aplicable)."""
    return df.astype(object).where(pd.notna(df), None) \
        .to_dict(orient="records")


# ---------------------------------------------------------------------------
# Compuerta propia, techo por análogos euclídeos y portafolios
# ---------------------------------------------------------------------------

def _round_count(x):
    """Redondeo de conteos: floor(x + 0.5), nunca el round() de Python."""
    return int(np.floor(float(x) + 0.5))


def fit_deployment_gate(Z_labeled, quantile):
    """Compuerta de dominio del Motor 2 ajustada sobre el soporte
    completo del entrenamiento: TODAS las AGEBs servidas etiquetadas,
    no solo la referencia de alta actividad usada para los techos."""
    return fe04_analysis.fit_mahalanobis(Z_labeled, quantile=quantile)


def ockham_comparison(cv_metrics, scheme):
    """Navaja de Ockham, mecánica desde las métricas por pliegue.

    Publica la diferencia de RMSE medio RF−Ridge y cuántos pliegues gana
    RF, más el R² espacial medio de TODOS los modelos —ninguno es
    predictivamente fuerte; RF se elige por parsimonia y estabilidad, no
    por dominancia demostrada—.
    """
    prim = cv_metrics.loc[cv_metrics.fold_scheme.eq(scheme)]
    per_fold = {
        model: prim.loc[prim.model.eq(model)].sort_values("fold")
        for model in MODELS}
    rf, rg = per_fold["random_forest"], per_fold["ridge"]
    return {
        "rf_vs_ridge": {
            "delta_rmse_mean": _finite(
                rf.rmse.mean() - rg.rmse.mean()),
            "rf_fold_wins": int(
                (rf.rmse.to_numpy() < rg.rmse.to_numpy()).sum()),
            "n_folds": int(len(rf)),
        },
        "r2_spatial_mean": {
            model: _finite(sub.r2.mean())
            for model, sub in per_fold.items()},
    }


def make_ceiling_recorder_m2(features, universe, cfg, k):
    """Recorder del esquema primario: preprocesado AJUSTADO SOLO CON
    train_ids del pliegue; para cada AGEB de prueba registra el conteo
    predicho por los k análogos euclídeos de referencia y por el
    comparador ingenuo (mediana de densidad de las retenidas)."""
    X = features.set_index("cvegeo")
    uni = universe.set_index("cvegeo")
    density = uni.n_estaciones / uni.area_km2
    rows = []

    def engine_fn(task):
        test_ids = list(task["test_ids"])
        train_ids = list(task["train_ids"])
        excluded = set(task["fit_exclusion_ids"])
        scheme, fold = task["fold_scheme"], task["fold"]
        prep = build_preprocessor()
        Z_train = prep.fit_transform(
            X.loc[train_ids, fe03_analysis.INPUT_COLUMNS])
        Z_test = prep.transform(
            X.loc[test_ids, fe03_analysis.INPUT_COLUMNS])
        target = task["train_target"].reindex(train_ids).to_numpy(float)
        ref_mask = target >= np.quantile(
            target, cfg["reference_quantile"])
        Z_ref = Z_train[ref_mask]
        ref_ids = np.asarray(train_ids)[ref_mask]
        ref_density = density.reindex(ref_ids).to_numpy(float)
        retained = [c for c in train_ids if c not in excluded]
        naive_rho = float(np.median(
            density.reindex(retained).to_numpy(float)))
        dist = np.sqrt(((Z_test[:, None, :]
                         - Z_ref[None, :, :]) ** 2).sum(-1))
        for i, cve in enumerate(test_ids):
            top = np.argsort(dist[i])[:k]
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
        return list(test_ids)

    engine_fn.rows = rows
    return engine_fn


def _spearman(x, y):
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3:
        return float("nan")
    return float(spearmanr(pair.x, pair.y).statistic)


def _none_if_nan(value):
    """floats no finitos -> None para el reporte JSON (allow_nan=False)."""
    return None if isinstance(value, float) \
        and not np.isfinite(value) else value


def _metrics_jsonable(metrics):
    return {key: _none_if_nan(value)
            for key, value in metrics.items()}


# ---------------------------------------------------------------------------
# Análisis completo
# ---------------------------------------------------------------------------

def analyze(data):
    frames = data["frames"]
    universe = frames["universe"]
    folds = frames["folds"]
    features = frames["features"]
    primary = CONFIG["primary_scheme"]

    eval_rows = universe.loc[universe.in_evaluation_universe] \
        .set_index("cvegeo")
    target = eval_rows[TARGET].astype(float)
    y_true_log = np.log1p(target)
    block_of = folds.set_index("cvegeo").spatial_block_id

    # ---- Backtest: todos los modelos x ambos esquemas ----------------------
    engines, ranking_details = {}, []
    predictions = []
    for model in MODELS:
        for scheme in CONFIG["schemes"]:
            engine = make_engine(features, folds, model, dict(CONFIG))
            detail, _, _ = fe04_analysis.run_backtest(
                universe, folds, scheme, engine)
            ranking_details.append(detail.assign(model=model))
            engines[(model, scheme)] = engine
            for row in engine.predictions:
                row = dict(row)
                row["y_true_log"] = float(y_true_log[row["cvegeo"]])
                predictions.append(row)
    ranking_detail = pd.concat(ranking_details, ignore_index=True)
    cv_predictions = pd.DataFrame(predictions)

    # ---- Métricas de regresión desde las predicciones almacenadas ----------
    metric_rows, seed_rmse_rows = [], []
    for (model, scheme), engine in engines.items():
        for fold, fit in sorted(engine.fits.items()):
            test_ids = fit["test_ids"]
            ens = cv_predictions.query(
                "model == @model and fold_scheme == @scheme and "
                "fold == @fold and seed == -1").set_index("cvegeo")
            y_true = y_true_log.loc[test_ids]
            metrics = regression_metrics(y_true, ens.loc[test_ids,
                                                         "y_pred_log"])
            train_rmse = regression_metrics(fit["y_train"],
                                            fit["y_pred_train"])["rmse"]
            row = {"fold_scheme": scheme, "fold": fold, "model": model,
                   "n_test": len(test_ids), "train_rmse": train_rmse,
                   **metrics}
            if model == "ft_transformer":
                per_seed = cv_predictions.query(
                    "model == @model and fold_scheme == @scheme and "
                    "fold == @fold and seed >= 0")
                seed_rmse = per_seed.groupby("seed").apply(
                    lambda g: regression_metrics(
                        y_true_log.loc[g.cvegeo],
                        g.set_index("cvegeo").loc[g.cvegeo,
                                                  "y_pred_log"])["rmse"])
                row["seed_rmse_std"] = float(seed_rmse.std())
                for s, r in seed_rmse.items():
                    seed_rmse_rows.append({"fold_scheme": scheme,
                                           "fold": fold, "seed": int(s),
                                           "rmse": float(r)})
            metric_rows.append(row)
    cv_metrics = pd.DataFrame(metric_rows)
    seed_rmse = pd.DataFrame(seed_rmse_rows)

    # ---- Curvas de aprendizaje (esquema primario) --------------------------
    recorder = _recording_engine()
    fe04_analysis.run_backtest(universe, folds, primary, recorder)
    curve_tasks = []
    for task in recorder.tasks:
        task = dict(task)
        task["_block_of"] = block_of
        task["_y_test"] = y_true_log.loc[task["test_ids"]].to_numpy()
        curve_tasks.append(task)
    curve = learning_curve(curve_tasks, features, dict(CONFIG))

    # ---- Importancia por permutación (esquema primario) --------------------
    importance_rows = []
    for model in CONTROLS + ["ft_transformer"]:
        engine = engines[(model, primary)]
        fits = {}
        for fold, fit in engine.fits.items():
            fit = dict(fit)
            fit["_y_test"] = y_true_log.loc[fit["test_ids"]].to_numpy()
            fits[fold] = fit
        imp = permutation_importance(fits, features, dict(CONFIG))
        imp["model"] = model
        importance_rows.append(imp)
    importance = pd.concat(importance_rows, ignore_index=True)
    importance_summary = importance.groupby(["model", "feature"])[
        "delta_rmse_mean"].mean().reset_index()

    # ---- Curvas de entrenamiento del Transformer ---------------------------
    training_rows = []
    for (model, scheme), engine in engines.items():
        if model != "ft_transformer":
            continue
        for fold, fit in sorted(engine.fits.items()):
            for seed, seed_fit in enumerate(fit["bundle"]["seeds_fits"]):
                training_rows.extend(
                    {"fold_scheme": scheme, "fold": fold, "seed": seed,
                     **record}
                    for record in seed_fit["history"])
    training_curves = pd.DataFrame(training_rows)

    # ---- Dictamen ----------------------------------------------------------
    rmse_by_model = {
        model: cv_metrics.loc[
            cv_metrics.model.eq(model)
            & cv_metrics.fold_scheme.eq(primary)].sort_values("fold")
        .rmse.to_numpy()
        for model in MODELS}
    seed_std_mean = float(cv_metrics.loc[
        cv_metrics.model.eq("ft_transformer")
        & cv_metrics.fold_scheme.eq(primary), "seed_rmse_std"].mean())
    verdict = dictamen(rmse_by_model, seed_std_mean)
    beats_constante = {
        model: {
            "mean_rmse_below_constante": bool(
                rmse_by_model[model].mean()
                < rmse_by_model["constante"].mean()),
            "fold_wins_vs_constante": int(np.sum(
                rmse_by_model[model] < rmse_by_model["constante"]))}
        for model in MODELS if model != "constante"}

    # ---- Despliegue: compuerta propia + portafolios SIN techos ---------
    # Navaja de Ockham: el FT-Transformer sale del despliegue (ver el
    # bloque "ockham" del reporte); el modelo tabular de despliegue es el
    # Random Forest —parsimonia y estabilidad, no dominancia demostrada—.
    selected = "random_forest"
    X = features.set_index("cvegeo")
    groups_all = block_of.reindex(eval_rows.index).to_numpy()
    deployment_fits = {}
    for model in CONTROLS:
        deployment_fits[model] = fit_model(
            model, X.loc[eval_rows.index, fe03_analysis.INPUT_COLUMNS],
            y_true_log.to_numpy(), groups_all, dict(CONFIG))
    candidates = features.loc[
        features.is_candidata_proyectable.astype(bool)].set_index("cvegeo")

    # Compuerta de dominio propia del Motor 2: el soporte completo de su
    # entrenamiento (todas las AGEBs servidas etiquetadas), no la
    # referencia de alta actividad —a diferencia del Motor 1, cuya
    # compuerta mide similitud a esa referencia—.
    prep_full = build_preprocessor().fit(
        X.loc[eval_rows.index, fe03_analysis.INPUT_COLUMNS])
    Z_eval = np.asarray(prep_full.transform(
        X.loc[eval_rows.index, fe03_analysis.INPUT_COLUMNS]),
        dtype=float)
    Z_c = np.asarray(prep_full.transform(
        candidates[fe03_analysis.INPUT_COLUMNS]), dtype=float)
    # Si el soporte es singular/insuficiente, fit_mahalanobis aborta:
    # se reporta el bloqueo, no se improvisa un pseudoinverso.
    gate_m2 = fit_deployment_gate(Z_eval, CONFIG["domain_quantile"])
    dist_c = fe04_analysis.mahalanobis_distance(
        Z_c, gate_m2["mu"], gate_m2["sigma_inv"])
    in_domain = dist_c <= gate_m2["threshold"]

    candidate_frame = candidate_frame_deployment(
        deployment_fits, selected, candidates,
        universe.set_index("cvegeo").domain_status,
        np.where(in_domain, "in_domain", "out_of_domain"))

    # ---- Backtest del techo: SOLO evidencia histórica de la remoción ---
    recorder_m2 = make_ceiling_recorder_m2(
        features, universe, dict(CONFIG), CONFIG["ceiling_neighbors"])
    fe04_analysis.run_backtest(universe, folds, primary, recorder_m2)
    ceiling_bt = pd.DataFrame(recorder_m2.rows)
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
        "role": "evidencia histórica de la remoción del techo; no "
                "alimenta el portafolio",
        "note": "reproduce la densidad histórica de planeación, "
                "no demanda",
    }

    # ---- Portafolios bajo el contrato de despliegue del 04 -----------------
    # greedy_coverage SIN techos: el número de estaciones por AGEB es
    # resultado puro de la cobertura con rendimientos decrecientes.
    deploy_cfg = dep.DEPLOY_CONFIG
    metric = CONFIG["metric_crs"]
    sites = frames["sites"].to_crs(metric).reset_index(drop=True)
    cells = frames["cells"].to_crs(metric).reset_index(drop=True)
    incidence = dep.site_cell_incidence(
        np.c_[sites.x, sites.y], cells, deploy_cfg)
    stations_m = frames["station_env"].to_crs(metric)
    ctx = dep.build_network_context(
        sites, cells, incidence, stations_m, deploy_cfg)

    score_rf = pd.Series(
        np.where(in_domain, candidate_frame.pred_random_forest, 0.0),
        index=candidates.index)
    port_frames, portfolio_metrics_by = [], {}
    for budget in deploy_cfg["budget_grid"]:
        sol = dep.greedy_coverage(
            sites.cvegeo.map(score_rf).fillna(0.0).to_numpy(), ctx,
            budget)
        if not dep.is_feasible(sol["order"], ctx, budget):
            raise ValueError(
                f"infeasible Motor2 portfolio at B={budget}")
        metrics = dep.portfolio_metrics(
            sol["order"], ctx, sites, features, universe)
        portfolio_metrics_by[str(budget)] = {
            "stop_reason": sol["stop_reason"],
            **_metrics_jsonable(metrics)}
        frame = dep.portfolio_frame(sol["order"], sol["attach"],
                                    sites, ctx)
        frame["budget"] = budget
        frame["method"] = "random_forest"
        frame["score"] = sites.cvegeo.map(score_rf).fillna(
            0.0).to_numpy()[list(sol["order"])]
        port_frames.append(frame)
    portafolios = gpd.GeoDataFrame(
        pd.concat(port_frames, ignore_index=True),
        geometry="geometry", crs=sites.crs)

    b_primary = deploy_cfg["primary_budget"]

    # ---- Reporte -------------------------------------------------------------
    mean_by = cv_metrics.groupby(["model", "fold_scheme"]).agg(
        rmse=("rmse", "mean"), mae=("mae", "mean"), r2=("r2", "mean"),
        spearman=("spearman", "mean"), train_rmse=("train_rmse", "mean"),
    ).reset_index()
    rank_metrics = [c for c in ranking_detail.columns
                    if "@" in c or c in ("decision_coverage",
                                         "relevant_abstained")]
    rank_means = {}
    for (model, scheme), detail in ranking_detail.groupby(
            ["model", "fold_scheme"]):
        rank_means[f"{model}|{scheme}"] = {
            m: _finite(detail[m].mean()) for m in rank_metrics}
    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "notebook": "06_Motor2_Transformer_Honesto.ipynb",
        "scope": {
            "capacity_study": True, "nothing_temporal": True,
            "hyperparameters_fixed_a_priori": True,
            "n_evaluable": int(len(eval_rows)),
            "own_domain_gate_m2": True,
            "transformer_removed_from_deployment": True,
            "random_forest_is_deployment_model": True,
            "no_analog_ceilings_in_deployment": True,
            "solves_shared_deployment_task": True,
            "no_motor1_motor3_inputs": True,
            "importance_is_associative_not_causal": True,
        },
        "configuration": CONFIG,
        "models": MODELS,
        "upstream": data["upstream_refs"],
        "regression_means": _records(mean_by),
        "ranking_means_by_model_scheme": rank_means,
        "beats_constante": beats_constante,
        "train_test_gap_rmse": _records(mean_by.assign(
            gap=mean_by.train_rmse - mean_by.rmse)),
        "dictamen": verdict,
        "learning_curve": _records(curve),
        "permutation_importance_mean": _records(importance_summary),
        "deployment": {
            "selected_model": selected,
            "transformer_case_study_only": True,
            "dictamen_no_added_capacity_vs_rf":
                not verdict["transformer_aporta"],
            "gate_m2": {
                "basis": f"soporte del entrenamiento "
                         f"({int(len(eval_rows))} AGEBs servidas)",
                "contrast_motor1": "el Motor 1 mide similitud a la "
                                   "referencia de alta actividad",
                "n_support": int(len(eval_rows)),
                **{key: _finite(gate_m2[key]) for key in
                   ["threshold", "min_eigenvalue", "condition_number",
                    "k_dims", "covariance_rank", "quantile", "df",
                    "chi2_ppf"]}},
            "candidates": int(len(candidate_frame)),
            "candidates_in_domain_m2": int(in_domain.sum()),
            "candidates_out_domain_m2": int((~in_domain).sum()),
            "extrapolation_flag": EXTRAPOLATION_FLAG,
        },
        "ockham": {
            "transformer_removed_from_deployment": True,
            "dictamen_no_added_capacity": not verdict["transformer_aporta"],
            **ockham_comparison(cv_metrics, primary),
        },
        "ceiling_backtest": ceiling_backtest_summary,
        "portafolio": {
            "metodo": "greedy_coverage del contrato 04 SIN techos; "
                      "site_score = predicción expm1 del Random Forest "
                      "de la AGEB anfitriona (0 fuera del dominio m2)",
            "budget_grid": deploy_cfg["budget_grid"],
            "por_presupuesto": portfolio_metrics_by,
            "techo_removido": {
                "previous_schema": PREVIOUS_CEILING_PORTFOLIO_B30["schema"],
                "previous_B30": {
                    "new_pop": PREVIOUS_CEILING_PORTFOLIO_B30["new_pop"],
                    "n_agebs": PREVIOUS_CEILING_PORTFOLIO_B30["n_agebs"],
                    "stations_per_ageb":
                        PREVIOUS_CEILING_PORTFOLIO_B30[
                            "stations_per_ageb"]},
                "current_B30": portfolio_metrics_by[str(b_primary)],
                "delta_B30_new_pop": _finite(
                    portfolio_metrics_by[str(b_primary)]["new_pop"]
                    - PREVIOUS_CEILING_PORTFOLIO_B30["new_pop"]),
                "delta_B30_n_agebs":
                    portfolio_metrics_by[str(b_primary)]["n_agebs"]
                    - PREVIOUS_CEILING_PORTFOLIO_B30["n_agebs"],
            },
        },
        "pending_validation": [
            "Analog-ceiling backtest is removal evidence, not an active "
            "allocation rule",
            "Capacity study says nothing about latent demand",
            "RF is the deployment model by parsimony, not by proven "
            "dominance; no model is predictively strong",
            "Deployment predictions are extrapolation outside the "
            "observed activity scale",
        ],
    }

    outputs = [
        ("m2_cv_predictions.parquet", "parquet", cv_predictions),
        ("m2_cv_metrics.csv", "csv", cv_metrics),
        ("m2_ranking_metrics.csv", "csv", ranking_detail),
        ("m2_learning_curve.csv", "csv", curve),
        ("m2_permutation_importance.csv", "csv", importance),
        ("m2_training_curves.csv", "csv", training_curves),
        ("m2_candidate_predictions.parquet", "parquet", candidate_frame),
        ("m2_portafolios.parquet", "parquet", portafolios),
        ("m2_ceiling_backtest.csv", "csv", ceiling_bt),
        ("m2_final_models.joblib", "joblib", {
            "models": deployment_fits,
            "feature_names": list(fe03_analysis.FEATURE_NAMES),
            "seeds": list(CONFIG["seeds"]),
            "selected_model": selected}),
    ]
    return {"report": report, "outputs": outputs,
            "cv_predictions": cv_predictions, "cv_metrics": cv_metrics,
            "ranking_detail": ranking_detail, "learning_curve": curve,
            "importance": importance,
            "importance_summary": importance_summary,
            "training_curves": training_curves, "seed_rmse": seed_rmse,
            "candidate_predictions": candidate_frame,
            "deployment_fits": deployment_fits, "dictamen": verdict,
            "mean_by": mean_by,
            "portafolios": portafolios,
            "ceiling_bt": ceiling_bt, "sites": sites,
            "portfolio_metrics_by": portfolio_metrics_by,
            "gate_m2": gate_m2, "in_domain": in_domain}


def candidate_frame_deployment(deployment_fits, selected, candidates,
                               status_04, status_m2):
    """Predicciones expm1 de candidatas con banderas de dominio y aviso.

    Solo modelos de despliegue (controles): el FT-Transformer vive solo
    en el backtest como caso de estudio y no predice en despliegue.
    """
    frame = gpd.GeoDataFrame({
        "cvegeo": candidates.index,
        "nom_mun": candidates.nom_mun.to_numpy(),
        "geometry": candidates.geometry.to_numpy(),
    }, geometry="geometry", crs=candidates.crs)
    for model in CONTROLS:
        pred, _ = predict_model(
            deployment_fits[model],
            candidates[fe03_analysis.INPUT_COLUMNS])
        frame[f"pred_{model}"] = np.expm1(pred)
    frame["pred_selected"] = frame[f"pred_{selected}"]
    frame["selected_model"] = selected
    frame["domain_status_04"] = status_04.reindex(
        candidates.index).to_numpy()
    frame["domain_status_m2"] = np.asarray(status_m2)
    frame["advertencia"] = EXTRAPOLATION_FLAG
    return frame
