"""Arnés de validación del cuaderno 04: CV espacial, dominio Mahalanobis y métricas.

Este módulo NO entrena modelos. Construye el laboratorio anti-fraude que los
cuadernos de motores (05, 06, 07) deberán usar: particiones espaciales con
integridad verificada, zona buffer entre entrenamiento y validación, una
compuerta de dominio calibrada sobre el espacio PCA publicado por el
cuaderno 03 y métricas de ranking con denominadores fijados por el universo
evaluado, protocolo explícito de abstención y auto-pruebas sintéticas y de
contraejemplo. Ningún resultado reportado aquí es métrica de un motor.

Qué evalúa el backtest: la capacidad de un motor para redescubrir, entre
AGEBs CON estación interna, las de mayor actividad observada media por
estación. No valida demanda latente en territorio sin servicio.
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
from scipy.spatial.distance import mahalanobis as scipy_mahalanobis
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.stats import chi2
from sklearn.cluster import AgglomerativeClustering
from sklearn.covariance import LedoitWolf
from sklearn.model_selection import GroupKFold
import warnings

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import fe03_publication
from V3.src import fe04_deployment
from V3.src.fe03_analysis import CONFIG as FE03_CONFIG

VERSION = "v3-backtest-4"
CONFIG = {
    "n_folds": 5,
    "k_grid": [10, 20, 50],
    "mahalanobis_quantile": 0.9973,
    "covariance_relative_tolerance": 1e-10,
    "label_quantile": 0.85,
    "n_spatial_blocks": 15,
    "adjacency_tolerance_m": 1.0,
    "buffer_m": FE03_CONFIG["buffer_radius_m"],
    "buffered_schemes": ["fold_spatial_block"],
    "primary_scheme": "fold_spatial_block",
    "min_train_rows": 30,
    "seed": 42,
    "metric_crs": FE03_CONFIG["metric_crs"],
    "target": "actividad_media_estacion",
    "ranking_task": "recover high observed mean per-station activity among "
                    "served AGEBs (diagnostic of observed activity; not a "
                    "validation of latent expansion demand)",
}
FOLD_SCHEMES = {
    "fold_groupkfold_ageb": "cvegeo",
    "fold_spatial_block": "spatial_block_id",
}
TARGET = CONFIG["target"]
FEATURE_POINTERS = "audits/03_feature_engineering.json"
EDA_POINTERS = "audits/02_eda.json"
FEATURE_TABLES = ["pca_espacio_compartido", "entorno_ageb_features"]
EDA_TABLES = ["station_environment"]
STATION_ACTIVITY_COL = "viajes_diarios_prom"
PC_PATTERN = "PC"


def _verified_output(v3, verified_report, stem, geodataframe=False):
    """Lee un artefacto de un reporte ya verificado, con chequeo de bytes/hash."""
    matches = [r for r in verified_report["outputs"]
               if r["path"].endswith(f"/{stem}.parquet")]
    if len(matches) != 1:
        raise ValueError(f"Artifact {stem}.parquet not unique in report outputs")
    record = matches[0]
    path = v3 / record["path"]
    if path.is_symlink() or not path.is_file() \
            or path.stat().st_size != record["bytes"] \
            or file_hash(path) != record["sha256"]:
        raise ValueError(f"Published artifact failed byte/hash check: {stem}")
    return (gpd.read_parquet if geodataframe else pd.read_parquet)(path)


def load_inputs(v3):
    """Carga el espacio PCA publicado (03) y el entorno de estaciones (02).

    Ambas fuentes pasan por su verificador de reporte y por chequeo
    byte/hash por artefacto; el puntero activo debe ser el reporte
    verificado byte a byte, igual que en el cargador del pipeline.
    """
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)

    pointer_path = v3 / FEATURE_POINTERS
    payload = pointer_path.read_bytes()
    fe_report = json.loads(payload)
    report_path = (v3 / fe03_publication.FEATURES_ROOT / fe_report["contract_id"]
                   / fe_report["analysis_id"] / "report.json")
    verified_fe = fe03_publication.verify_report(v3, report_path)
    if report_path.read_bytes() != payload \
            or pointer_path.read_bytes() != payload:
        raise ValueError("Feature pointer is not the verified published report")
    if verified_fe["contract_id"] != audit["contract_id"]:
        raise ValueError("Feature report belongs to another ETL contract")

    context = fe03_publication._context(v3)   # revalida ETL+EDA activos
    eda_verified = context["eda"]
    if eda_verified["contract_id"] != audit["contract_id"]:
        raise ValueError("EDA report belongs to another ETL contract")

    frames = {
        "scores": _verified_output(v3, verified_fe, "pca_espacio_compartido"),
        "features": _verified_output(
            v3, verified_fe, "entorno_ageb_features", geodataframe=True),
        "station_env": _verified_output(
            v3, eda_verified, "station_environment", geodataframe=True),
    }
    input_artifacts = {}
    for table in FEATURE_TABLES:
        record = [r for r in verified_fe["outputs"]
                  if r["path"].endswith(f"/{table}.parquet")][0]
        input_artifacts[f"features/{table}"] = {
            key: record[key] for key in ["path", "bytes", "sha256"]}
    for table in EDA_TABLES:
        record = [r for r in eda_verified["outputs"]
                  if r["path"].endswith(f"/{table}.parquet")][0]
        input_artifacts[f"eda/{table}"] = {
            key: record[key] for key in ["path", "bytes", "sha256"]}

    data = {
        "v3": v3, "audit": audit, "frames": frames,
        "input_artifacts": input_artifacts,
        "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(
            (v3 / EDA_POINTERS).read_bytes()).hexdigest(),
        "feature_audit_sha256": hashlib.sha256(payload).hexdigest(),
        "eda_analysis_id": eda_verified["analysis_id"],
        "feature_analysis_id": verified_fe["analysis_id"],
        "feature_report": verified_fe,
    }
    data["analysis_id"], data["analysis_identity"] = analysis_identity(v3, data)
    return data


def analysis_identity(v3, data):
    identity = {
        "schema_version": VERSION, "contract_id": data["audit"]["contract_id"],
        "configuration": CONFIG,
        "input_artifacts": data["input_artifacts"],
        "etl_audit_sha256": data["etl_audit_sha256"],
        "eda_audit_sha256": data["eda_audit_sha256"],
        "feature_audit_sha256": data["feature_audit_sha256"],
        "eda_analysis_id": data["eda_analysis_id"],
        "feature_analysis_id": data["feature_analysis_id"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "fe04_analysis.py", "fe04_publication.py", "fe04_content.py",
                "fe04_deployment.py", "build_notebook_04.py",
                "fe03_analysis.py", "fe03_publication.py",
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


def pc_columns(scores):
    names = [c for c in scores.columns
             if str(c).startswith(PC_PATTERN) and str(c)[2:].isdigit()]
    names = sorted(names, key=lambda c: int(str(c)[2:]))
    if not names:
        raise ValueError("Published score table has no PC columns")
    return names


# ---------------------------------------------------------------------------
# Universo de evaluación y verdad-terreno
# ---------------------------------------------------------------------------

def build_evaluation_universe(features, scores, station_env):
    """Universo etiquetado: AGEBs proyectables CON estación interna.

    Objetivo: actividad_media_estacion = media de viajes_diarios_prom de las
    estaciones contenidas en el polígono. Se usa la media (no la suma) para
    no premiar mecánicamente a las AGEBs con más estaciones. Las AGEBs sin
    estación interna NO reciben actividad cero: quedan sin etiqueta (NaN),
    porque la ausencia de estación no es evidencia de baja demanda.
    """
    required = {"station_id", "cvegeo", STATION_ACTIVITY_COL, "is_golden"}
    if not required.issubset(station_env.columns):
        raise ValueError(f"station_environment lacks columns: {required - set(station_env.columns)}")
    if station_env.station_id.duplicated().any():
        raise ValueError("Duplicate station_id in station_environment")
    if station_env.cvegeo.isna().any():
        raise ValueError("Stations without host AGEB cannot be aggregated")
    activity_values = station_env[STATION_ACTIVITY_COL].astype(float)
    if not np.isfinite(activity_values).all() or activity_values.lt(0).any():
        raise ValueError("Station activity must be finite and nonnegative")
    activity = station_env.assign(_act=activity_values).groupby("cvegeo").agg(
        actividad_media_estacion=("_act", "mean"),
        actividad_total_diaria=("_act", "sum"),
        n_estaciones=("station_id", "size"),
        has_golden_station=("is_golden", "max"),
    ).rename_axis("cvegeo").reset_index()
    unknown = set(activity.cvegeo) - set(features.cvegeo)
    if unknown:
        raise ValueError(f"Stations hosted by AGEBs absent from features: {len(unknown)}")

    pcs = pc_columns(scores)
    universe = features[[
        "cvegeo", "tipo_ageb", "nom_mun", "area_km2", "fraccion_cobertura",
        "is_candidata_territorial", "is_candidata_proyectable",
        "is_golden_cluster", "is_projectable", "is_rural_nan",
        "exclusion_reason", "geometry",
    ]].merge(
        scores[["cvegeo"] + pcs], on="cvegeo", validate="one_to_one").merge(
        activity, on="cvegeo", how="left", validate="one_to_one")
    if universe.cvegeo.duplicated().any():
        raise ValueError("Duplicate AGEB keys in evaluation universe")

    universe["n_estaciones"] = universe.n_estaciones.fillna(0).astype(int)
    has_station = universe.n_estaciones.gt(0)
    universe["has_golden_station"] = (
        universe.has_golden_station.astype("boolean").fillna(False))
    projectable = universe.is_projectable.astype(bool)
    territorial = universe.is_candidata_territorial.astype(bool)
    in_eval = projectable & has_station & ~territorial
    universe["in_evaluation_universe"] = in_eval
    universe["evaluation_role"] = np.select(
        [in_eval, has_station, territorial],
        ["labeled_served", "served_not_evaluable", "candidate_unlabeled"],
        default="covered_without_station_unlabeled")
    return universe, pcs


# ---------------------------------------------------------------------------
# Compuerta de dominio Mahalanobis
# ---------------------------------------------------------------------------

def fit_mahalanobis(reference_matrix, quantile=None, estimator="empirical"):
    """Ajusta mu y Sigma^-1 sobre una referencia en un espacio de k dimensiones.

    Se rechaza toda covarianza singular o casi singular (autovalor mínimo
    por debajo de tolerancia relativa): una pseudoinversa ignoraría las
    direcciones sin varianza y asignaría distancia cero a desplazamientos
    arbitrariamente grandes en ellas, además de invalidar df = k. Quien use
    una referencia degenerada debe reducir la dimensión explícitamente.

    estimator="empirical" (default): covarianza muestral, exige n > k.
    estimator="ledoit_wolf": LedoitWolf de sklearn (encogimiento hacia la
    diagonal escalada); basta n >= 2 y produce una covarianza definida
    positiva aun con referencias pequeñas (n/p ~ 3). El umbral sigue siendo
    sqrt(chi2.ppf(q, k)) y con encogimiento es nominal: las distancias de
    entrenamiento ya no siguen exactamente una chi^2_k.
    """
    X = np.asarray(reference_matrix, dtype=float)
    if X.ndim != 2 or not np.isfinite(X).all():
        raise ValueError("Reference score matrix must be finite 2-D")
    n, k = X.shape
    quantile = CONFIG["mahalanobis_quantile"] if quantile is None else quantile
    if not 0 < quantile < 1:
        raise ValueError("Mahalanobis quantile must lie in (0, 1)")
    if estimator == "empirical":
        if n <= k:
            raise ValueError(
                "Reference smaller than or equal to the space dimension")
        sigma = np.cov(X, rowvar=False, ddof=1).reshape(k, k)
        shrinkage = 0.0
    elif estimator == "ledoit_wolf":
        if n < 2:
            raise ValueError(
                "Ledoit-Wolf requires at least 2 reference rows")
        lw = LedoitWolf().fit(X)
        sigma = np.asarray(lw.covariance_, dtype=float).reshape(k, k)
        shrinkage = float(lw.shrinkage_)
    else:
        raise ValueError(f"Unknown covariance estimator: {estimator}")
    mu = X.mean(axis=0)
    eigenvalues = np.linalg.eigvalsh(sigma)
    largest = float(eigenvalues.max())
    tolerance = CONFIG["covariance_relative_tolerance"] * max(largest, 0.0)
    rank = int((eigenvalues > tolerance).sum())
    if largest <= 0 or rank < k:
        raise ValueError(
            f"Reference covariance is singular or near-singular (rank {rank}/{k}); "
            "reduce the dimension explicitly instead of using a pseudoinverse")
    sigma_inv = np.linalg.inv(sigma)
    chi2_ppf = float(chi2.ppf(quantile, df=k))
    return {
        "mu": mu, "sigma": sigma, "sigma_inv": sigma_inv,
        "n_reference": n, "k_dims": k, "covariance_rank": rank,
        "min_eigenvalue": float(eigenvalues.min()),
        "condition_number": float(largest / eigenvalues.min()),
        "quantile": quantile, "df": k, "chi2_ppf": chi2_ppf,
        "threshold": float(np.sqrt(chi2_ppf)),
        "estimator": estimator, "shrinkage": shrinkage,
    }


def mahalanobis_distance(X, mu, sigma_inv):
    """D_M(x) = sqrt((x-mu)' Sigma^-1 (x-mu)); filas con NaN -> NaN."""
    X = np.asarray(X, dtype=float)
    out = np.full(len(X), np.nan)
    valid = np.isfinite(X).all(axis=1)
    delta = X[valid] - mu
    out[valid] = np.sqrt(np.einsum("ij,jk,ik->i", delta, sigma_inv, delta))
    return out


def apply_domain_gate(universe, fit, pcs):
    """Banderas de dominio: NA para no proyectables, binaria para el resto.

    in_domain=True no significa 'recomendable'; significa 'dentro del
    soporte estadístico de la referencia'. La abstención tiene dos causas
    explícitas: not_projectable (sin atributos) u out_of_domain.
    """
    X = universe[pcs].to_numpy(dtype=float)
    distances = mahalanobis_distance(X, fit["mu"], fit["sigma_inv"])
    universe = universe.copy()
    universe["mahalanobis_distance"] = distances
    evaluable = universe.is_projectable.to_numpy(bool) & np.isfinite(distances)
    flags = np.where(evaluable, distances <= fit["threshold"], None)
    universe["in_domain"] = pd.Series(flags, index=universe.index,
                                      dtype="boolean")
    universe["domain_status"] = np.select(
        [~evaluable, distances > fit["threshold"]],
        ["not_projectable", "out_of_domain"], default="in_domain")
    return universe


def _selfcheck_mahalanobis(fit):
    """La implementación propia debe coincidir con scipy en vectores de prueba."""
    rng = np.random.default_rng(CONFIG["seed"])
    probes = rng.normal(size=(25, fit["k_dims"]))
    ours = mahalanobis_distance(probes, fit["mu"], fit["sigma_inv"])
    reference = np.array([
        scipy_mahalanobis(row, fit["mu"], fit["sigma_inv"]) for row in probes])
    if not np.allclose(ours, reference, rtol=1e-9, atol=1e-9):
        raise ValueError("Mahalanobis implementation disagrees with scipy")


# ---------------------------------------------------------------------------
# Particiones espaciales, validación de folds y zona buffer
# ---------------------------------------------------------------------------

def polygon_adjacency(geo, tolerance_m=None):
    """Matriz dispersa simétrica de colindancia poligonal.

    Dos AGEBs son vecinas cuando su distancia poligonal en
    CONFIG["metric_crs"] es <= tolerance_m (1 m por defecto: polígonos que
    se tocan). Solo conecta las filas recibidas —el universo evaluado—.
    """
    tolerance_m = CONFIG["adjacency_tolerance_m"] \
        if tolerance_m is None else tolerance_m
    geo = geo.reset_index(drop=True)
    geometry = geo.geometry
    n = len(geo)
    pairs_i, pairs_j = [], []
    sindex = geo.sindex
    for i, geom in enumerate(geometry):
        hits = sindex.intersection(geom.buffer(tolerance_m).bounds)
        for j in set(hits.tolist()):
            if j <= i:
                continue
            if geometry.iloc[int(j)].distance(geom) <= tolerance_m:
                pairs_i.append(i)
                pairs_j.append(int(j))
    adjacency = csr_matrix(
        (np.ones(len(pairs_i), dtype=np.int8), (pairs_i, pairs_j)),
        shape=(n, n))
    return adjacency + adjacency.T


def assign_spatial_blocks(rows, n_blocks=None, adjacency=None):
    """Bloques espaciales contiguos: aglomerativo Ward con conectividad.

    Se ajusta solo sobre las AGEBs del universo etiquetado: los bloques
    fijados sobre toda la ciudad dejaban muy pocos bloques en la zona
    servida. El grafo de adyacencia conecta solo polígonos colindantes
    (distancia <= adjacency_tolerance_m) y el Ward solo fusiona vecinos,
    así que cada bloque es geográficamente coherente. Si el universo
    evaluado está fragmentado, sklearn completa el grafo y los bloques
    pueden reunir componentes separados —el diagnóstico
    block_contiguity publica cuántos—. Determinista, sin semilla. La
    ausencia de fuga por colindancia la garantiza la zona buffer de
    buffer_exclusions(), no la contigüidad.
    """
    n_blocks = n_blocks or CONFIG["n_spatial_blocks"]
    if len(rows) < n_blocks:
        raise ValueError("Fewer AGEBs than declared spatial blocks")
    geo = rows.to_crs(CONFIG["metric_crs"]).reset_index(drop=True)
    if adjacency is None:
        adjacency = polygon_adjacency(geo)
    centroids = geo.geometry.centroid
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=".*connected components.*connectivity.*")
        labels = AgglomerativeClustering(
            n_clusters=n_blocks, connectivity=adjacency,
            linkage="ward").fit_predict(np.c_[centroids.x, centroids.y])
    return pd.Series(labels, index=rows.cvegeo.to_numpy(),
                     name="spatial_block_id")


def block_contiguity(universe, folds):
    """Contigüidad de los bloques espaciales dentro del grafo de colindancia.

    blocks_contiguous_share = fracción de bloques que forman exactamente
    un componente conexo. Si el universo evaluado está fragmentado en el
    grafo de adyacencia, n_adjacency_components > 1 y algunos bloques
    pueden reunir islas separadas (Ward las fusiona al completar el grafo):
    entonces la contigüidad es parcial y se reporta como tal.
    """
    geo = universe.loc[universe.in_evaluation_universe] \
        .reset_index(drop=True)
    adjacency = polygon_adjacency(geo)
    n_components = connected_components(
        adjacency, directed=False, return_labels=False)
    block_of = folds.set_index("cvegeo") \
        .loc[geo.cvegeo, "spatial_block_id"].to_numpy()
    per_block = {}
    for block in np.unique(block_of):
        idx = np.flatnonzero(block_of == block)
        per_block[int(block)] = int(connected_components(
            adjacency[idx][:, idx], directed=False, return_labels=False))
    share = float(np.mean([v == 1 for v in per_block.values()]))
    return {
        "n_adjacency_components": int(n_components),
        "blocks_contiguous_share": share,
        "components_per_block": {str(k): int(v)
                                 for k, v in per_block.items()},
        "n_blocks": int(len(per_block)),
    }


def make_splitters():
    """Objetos GroupKFold declarados por esquema (sin ajustar)."""
    return {scheme: GroupKFold(n_splits=CONFIG["n_folds"], shuffle=True,
                               random_state=CONFIG["seed"])
            for scheme in FOLD_SCHEMES}


def make_folds(universe):
    """Dos esquemas de partición sobre el universo etiquetado.

    - fold_groupkfold_ageb: GroupKFold con groups=cvegeo. A granularidad
      AGEB coincide con un KFold mezclado y NO aísla vecinos espaciales: es
      una referencia optimista.
    - fold_spatial_block: GroupKFold con groups=spatial_block_id más zona
      buffer de entrenamiento (ver buffer_exclusions). Es el esquema
      primario para comparar motores.
    """
    eval_rows = universe.loc[universe.in_evaluation_universe].copy()
    n_eval, n_folds = len(eval_rows), CONFIG["n_folds"]
    if n_eval < 2 * n_folds:
        raise ValueError("Evaluation universe too small for the declared folds")
    eval_rows["spatial_block_id"] = eval_rows.cvegeo.map(
        assign_spatial_blocks(eval_rows)).astype(int)

    splitters = make_splitters()
    for column, group_column in FOLD_SCHEMES.items():
        groups = eval_rows[group_column].to_numpy()
        assignments = np.full(n_eval, -1)
        for fold, (_, test_idx) in enumerate(
                splitters[column].split(eval_rows, groups=groups)):
            if (assignments[test_idx] != -1).any():
                raise ValueError("Fold assignment collision")
            assignments[test_idx] = fold
        if (assignments < 0).any():
            raise ValueError("Unassigned evaluation rows")
        eval_rows[column] = assignments

    folds = eval_rows[["cvegeo", "spatial_block_id", *FOLD_SCHEMES]].reset_index(drop=True)
    for scheme in FOLD_SCHEMES:
        validate_folds(universe, folds, scheme)
    info = {
        "n_folds": n_folds,
        "evaluation_universe_size": int(n_eval),
        "n_spatial_blocks": int(eval_rows.spatial_block_id.nunique()),
        "fold_sizes_groupkfold_ageb": folds.fold_groupkfold_ageb.value_counts(
        ).sort_index().astype(int).to_dict(),
        "fold_sizes_spatial_block": folds.fold_spatial_block.value_counts(
        ).sort_index().astype(int).to_dict(),
    }
    return folds, info


def validate_folds(universe, folds, fold_column):
    """Rechaza toda tabla de folds que no cubra exactamente el universo.

    Comprueba: esquema declarado, claves únicas, cobertura exacta del
    universo etiquetado (sin faltantes ni ajenas), identificadores de fold
    enteros en range(n_folds) y todos no vacíos, y que ningún grupo
    (AGEB o bloque espacial) quede repartido entre folds. Para el esquema
    por bloques, el bloque de cada AGEB debe coincidir con el publicado.
    """
    if fold_column not in FOLD_SCHEMES:
        raise ValueError(f"Undeclared fold scheme: {fold_column}")
    group_column = FOLD_SCHEMES[fold_column]
    needed = {"cvegeo", fold_column, group_column}
    if not needed.issubset(folds.columns):
        raise ValueError(f"Fold table lacks columns: {sorted(needed - set(folds.columns))}")
    eval_ids = universe.loc[universe.in_evaluation_universe, "cvegeo"]
    if eval_ids.isna().any() or eval_ids.duplicated().any():
        raise ValueError("Evaluation universe keys are missing or duplicated")
    ids = folds.cvegeo
    if ids.isna().any() or ids.duplicated().any():
        raise ValueError("Duplicate or missing AGEB assignment in fold table")
    missing, extra = set(eval_ids) - set(ids), set(ids) - set(eval_ids)
    if missing or extra:
        raise ValueError(f"Fold table does not cover the evaluation universe exactly "
                         f"(missing={len(missing)}, foreign={len(extra)})")
    values = folds[fold_column]
    if values.isna().any():
        raise ValueError("Missing fold identifiers")
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any() or not np.equal(numeric, np.round(numeric)).all():
        raise ValueError("Fold identifiers must be integers")
    if set(numeric.astype(int)) != set(range(CONFIG["n_folds"])):
        raise ValueError("Fold identifiers must be exactly range(n_folds), all non-empty")
    if folds[group_column].isna().any():
        raise ValueError(f"Missing group identifiers: {group_column}")
    if folds.groupby(group_column)[fold_column].nunique().gt(1).any():
        raise ValueError(f"A group straddles folds in {fold_column}")
    if group_column == "spatial_block_id" and "spatial_block_id" in universe.columns:
        published = universe.set_index("cvegeo").spatial_block_id
        declared = folds.set_index("cvegeo").spatial_block_id
        if not published.loc[declared.index].astype("Int64").equals(
                declared.astype("Int64")):
            raise ValueError("Fold table spatial blocks differ from the universe blocks")
    return True


def buffer_exclusions(universe, folds, fold_column, buffer_m=None):
    """AGEBs de entrenamiento a <= buffer_m (distancia poligonal) del fold de prueba.

    Solo aplica a los esquemas declarados en CONFIG['buffered_schemes'];
    en ellos esas AGEBs se retiran de TODO ajuste del fold (preprocesamiento,
    referencia, etiquetas). Se recalcula siempre desde la geometría: el
    arnés no acepta exclusiones suministradas externamente.
    """
    columns = ["fold_scheme", "fold", "cvegeo", "distance_to_test_m"]
    if fold_column not in CONFIG["buffered_schemes"]:
        return pd.DataFrame(columns=columns)
    buffer_m = CONFIG["buffer_m"] if buffer_m is None else buffer_m
    geo = universe.loc[universe.in_evaluation_universe, ["cvegeo", "geometry"]]
    geo = gpd.GeoDataFrame(geo, geometry="geometry").to_crs(CONFIG["metric_crs"])
    geo = geo.merge(folds[["cvegeo", fold_column]], on="cvegeo", validate="one_to_one")
    rows = []
    for fold in range(CONFIG["n_folds"]):
        test_union = geo.loc[geo[fold_column] == fold].geometry.union_all()
        train = geo.loc[geo[fold_column] != fold]
        distance = train.geometry.distance(test_union)
        near = distance <= buffer_m
        rows.extend({"fold_scheme": fold_column, "fold": fold, "cvegeo": c,
                     "distance_to_test_m": float(d)}
                    for c, d in zip(train.cvegeo[near], distance[near]))
    return pd.DataFrame(rows, columns=columns)


def separation_diagnostics(universe, folds, fold_column, exclusions):
    """Distancia poligonal mínima train-test retenida y pares colindantes.

    touching_train_test_pairs_before_buffer cuenta pares (prueba,
    entrenamiento) con distancia poligonal <= adjacency_tolerance_m antes
    de aplicar el buffer; after_buffer los cuenta sobre el entrenamiento
    retenido. En un esquema declarado con buffer (fold_spatial_block) el
    conteo posterior DEBE ser 0: si no lo es, el arnés falla —la ausencia
    de fuga por colindancia la garantiza el buffer, no la contigüidad de
    los bloques.
    """
    geo = universe.loc[universe.in_evaluation_universe, ["cvegeo", "geometry"]]
    geo = gpd.GeoDataFrame(geo, geometry="geometry").to_crs(CONFIG["metric_crs"])
    geo = geo.merge(folds[["cvegeo", fold_column]], on="cvegeo", validate="one_to_one")
    adjacency = polygon_adjacency(geo)
    records = []
    for fold in range(CONFIG["n_folds"]):
        excluded = set(exclusions.loc[exclusions.fold == fold, "cvegeo"])
        test_mask = geo[fold_column].to_numpy() == fold
        test = geo.loc[test_mask]
        train_mask = ~test_mask
        retained_mask = train_mask & ~geo.cvegeo.isin(excluded).to_numpy()
        train = geo.loc[retained_mask]
        distance = train.geometry.distance(test.geometry.union_all())
        test_idx = np.flatnonzero(test_mask)
        touching_before = int(
            adjacency[test_idx][:, np.flatnonzero(train_mask)].nnz)
        touching_after = int(
            adjacency[test_idx][:, np.flatnonzero(retained_mask)].nnz)
        if fold_column in CONFIG["buffered_schemes"] \
                and touching_after != 0:
            raise ValueError(
                f"fold_spatial_block fold {fold}: {touching_after} pares "
                "colindantes prueba-entrenamiento sobrevivieron al buffer")
        records.append({
            "fold_scheme": fold_column, "fold": fold, "n_test": len(test),
            "n_train_retained": len(train), "n_buffer_excluded": len(excluded),
            "min_train_test_distance_m": float(distance.min()),
            "train_within_buffer": int((distance <= CONFIG["buffer_m"]).sum()),
            "touching_train_test_pairs_before_buffer": touching_before,
            "touching_train_test_pairs_after_buffer": touching_after,
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Métricas de ranking con universo declarado y abstención explícita
# ---------------------------------------------------------------------------

def _check_k(k):
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 1:
        raise ValueError("K must be a positive integer")
    return int(k)


def _validate_ranking_inputs(ranked_ids, universe_ids, relevant_ids, gains=None):
    """Valida unicidad y pertenencia; el universo fija los denominadores."""
    universe = list(universe_ids)
    universe_set = set(universe)
    if not universe or len(universe_set) != len(universe):
        raise ValueError("Evaluation universe must be non-empty and unique")
    ranked = list(ranked_ids)
    if len(set(ranked)) != len(ranked):
        raise ValueError("Duplicate IDs in ranking")
    if set(ranked) - universe_set:
        raise ValueError("Ranking contains IDs outside the evaluation universe")
    relevant = set(relevant_ids)
    if relevant - universe_set:
        raise ValueError("Relevant IDs outside the evaluation universe")
    if gains is not None:
        if set(gains) != universe_set:
            raise ValueError("Gains must be defined for exactly the evaluation universe")
        values = np.asarray(list(gains.values()), dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Gains must be finite and nonnegative")
    return ranked, universe_set, relevant


def effective_k(k, universe_ids):
    """K efectivo = min(K, |universo|): un fold de 38 AGEBs no admite top-50."""
    return min(_check_k(k), len(set(universe_ids)))


def precision_at_k(ranked_ids, relevant_ids, k, universe_ids):
    """|top-K ∩ relevantes| / K_eff; abstenerse no reduce el denominador."""
    ranked, universe, relevant = _validate_ranking_inputs(
        ranked_ids, universe_ids, relevant_ids)
    k_eff = effective_k(k, universe)
    return sum(item in relevant for item in ranked[:k_eff]) / k_eff


def recall_at_k(ranked_ids, relevant_ids, k, universe_ids):
    """|top-K ∩ relevantes| / |relevantes del universo|; NaN si no hay relevantes.

    El denominador no depende del ranking entregado: omitir o abstenerse
    sobre una relevante cuenta como no recuperada.
    """
    ranked, universe, relevant = _validate_ranking_inputs(
        ranked_ids, universe_ids, relevant_ids)
    k_eff = effective_k(k, universe)
    if not relevant:
        return float("nan")
    return sum(item in relevant for item in ranked[:k_eff]) / len(relevant)


def conditional_precision_at_k(ranked_ids, relevant_ids, k, universe_ids):
    """Precisión entre lo efectivamente recomendado: hits / min(K, |ranking|)."""
    ranked, universe, relevant = _validate_ranking_inputs(
        ranked_ids, universe_ids, relevant_ids)
    k_rec = min(effective_k(k, universe), len(ranked))
    if k_rec == 0:
        return float("nan")
    return sum(item in relevant for item in ranked[:k_rec]) / k_rec


def dcg_at_k(ranked_ids, gains, k):
    """DCG@K con ganancias lineales y descuento log2(posición+1)."""
    k = _check_k(k)
    return float(sum(
        gains[item] / np.log2(position + 2)
        for position, item in enumerate(list(ranked_ids)[:k])))


def ndcg_at_k(ranked_ids, gains, k, universe_ids=None):
    """NDCG@K = DCG@K / IDCG@K_eff; IDCG usa todo el universo; NaN si IDCG=0.

    Con IDs únicos dentro del universo, NDCG queda acotado en [0, 1].
    """
    universe_ids = list(gains) if universe_ids is None else universe_ids
    ranked, universe, _ = _validate_ranking_inputs(
        ranked_ids, universe_ids, [], gains)
    k_eff = effective_k(k, universe)
    ideal = sorted(gains.values(), reverse=True)[:k_eff]
    idcg = float(sum(g / np.log2(p + 2) for p, g in enumerate(ideal)))
    if idcg <= 0:
        return float("nan")
    return dcg_at_k(ranked, gains, k_eff) / idcg


def ndcg_cond_at_k(ranked_ids, gains, k, universe_ids):
    """NDCG condicional: IDCG solo sobre el conjunto efectivamente rankeado.

    k_eff = min(effective_k(k, universe), len(ranked)) y el IDCG se calcula
    con las mayores ganancias disponibles ENTRE los IDs rankeados (los
    abstenidos no entran al denominador). Por eso no penaliza abstenciones
    y puede premiar compuertas que se abstienen en casos difíciles: siempre
    se lee junto con decision_coverage. NaN si no hay ranking o IDCG<=0.
    """
    ranked, universe, _ = _validate_ranking_inputs(
        ranked_ids, universe_ids, [], gains)
    k_eff = min(effective_k(k, universe), len(ranked))
    if k_eff == 0:
        return float("nan")
    ideal = sorted((gains[item] for item in ranked), reverse=True)[:k_eff]
    idcg = float(sum(g / np.log2(p + 2) for p, g in enumerate(ideal)))
    if idcg <= 0:
        return float("nan")
    return dcg_at_k(ranked, gains, k_eff) / idcg


def evaluate_ranking(ranked_ids, universe_ids, relevant_ids, gains,
                     k_grid=None, abstained_ids=None):
    """Métricas @K sobre un universo declarado, con cobertura de decisión.

    Lo no rankeado se considera abstención. Si se declara abstained_ids,
    ranking y abstenciones deben particionar exactamente el universo.
    Se reportan por separado las métricas incondicionales (denominador =
    universo/relevantes) y la precisión condicional entre lo recomendado.
    """
    k_grid = CONFIG["k_grid"] if k_grid is None else k_grid
    ranked, universe, relevant = _validate_ranking_inputs(
        ranked_ids, universe_ids, relevant_ids, gains)
    implicit = universe - set(ranked)
    if abstained_ids is not None:
        abstained = list(abstained_ids)
        if len(set(abstained)) != len(abstained) or set(abstained) != implicit:
            raise ValueError("Ranked and abstained IDs must partition the universe")
    out = {
        "n_universe": len(universe), "n_ranked": len(ranked),
        "n_abstained": len(implicit),
        "decision_coverage": len(ranked) / len(universe),
        "n_relevant": len(relevant),
        "relevant_abstained": len(relevant & implicit),
    }
    for k in k_grid:
        out[f"effective_k@{k}"] = effective_k(k, universe)
        out[f"precision@{k}"] = precision_at_k(ranked, relevant, k, universe)
        out[f"recall@{k}"] = recall_at_k(ranked, relevant, k, universe)
        out[f"ndcg@{k}"] = ndcg_at_k(ranked, gains, k, universe)
        out[f"ndcg_cond@{k}"] = ndcg_cond_at_k(ranked, gains, k, universe)
        out[f"precision_cond@{k}"] = conditional_precision_at_k(
            ranked, relevant, k, universe)
    return out


def fold_labels(train_target, test_target, quantile=None):
    """Relevante: objetivo de prueba >= cuantil ajustado SOLO en entrenamiento."""
    quantile = CONFIG["label_quantile"] if quantile is None else quantile
    train = np.asarray(train_target, float)
    test = np.asarray(test_target, float)
    if not len(train) or not np.isfinite(train).all() or not np.isfinite(test).all():
        raise ValueError("Fold targets must be non-empty and finite")
    threshold = float(np.quantile(train, quantile))
    return test >= threshold, threshold


def _normalize_decision(decision, test_ids, fold):
    """Una lista = ranking completo; un dict = {'ranked', 'abstained'}."""
    if isinstance(decision, dict):
        if set(decision) - {"ranked", "abstained"}:
            raise ValueError("Engine decision keys must be 'ranked'/'abstained'")
        ranked = list(decision.get("ranked", []))
        abstained = list(decision.get("abstained", []))
    else:
        ranked, abstained = list(decision), []
    together = ranked + abstained
    if len(set(together)) != len(together) or set(together) != set(test_ids):
        raise ValueError(
            f"Engine decision for fold {fold} must partition the test fold "
            "into unique ranked and abstained IDs")
    return ranked, abstained


def run_backtest(universe, folds, fold_column, engine_fn, k_grid=None,
                 label_quantile=None):
    """Ejecuta el protocolo sobre una función de motor.

    engine_fn(task) recibe un dict con: fold_scheme, fold, train_ids,
    train_target (pd.Series del objetivo SOLO en entrenamiento retenido),
    test_ids y fit_exclusion_ids (prueba ∪ buffer: filas que el motor no
    debe usar en ningún ajuste, ni siquiera no supervisado). El arnés nunca
    entrega objetivos, etiquetas Golden ni coordenadas PCA globales.
    Devuelve una lista (ranking completo) o {'ranked', 'abstained'}.
    """
    k_grid = CONFIG["k_grid"] if k_grid is None else k_grid
    validate_folds(universe, folds, fold_column)
    eval_rows = universe.loc[universe.in_evaluation_universe].set_index("cvegeo")
    target = eval_rows[TARGET].astype(float)
    if not np.isfinite(target).all() or target.lt(0).any():
        raise ValueError("Evaluation target must be finite and nonnegative")
    fold_of = folds.set_index("cvegeo")[fold_column].astype(int)
    exclusions = buffer_exclusions(universe, folds, fold_column)

    records, decisions = [], []
    for fold in range(CONFIG["n_folds"]):
        test_ids = sorted(fold_of.index[fold_of == fold])
        excluded = set(exclusions.loc[exclusions.fold == fold, "cvegeo"])
        train_ids = sorted(set(fold_of.index[fold_of != fold]) - excluded)
        if len(train_ids) < CONFIG["min_train_rows"]:
            raise ValueError(f"Fold {fold} keeps too few training rows after the buffer")
        relevant_mask, threshold = fold_labels(
            target.loc[train_ids], target.loc[test_ids], label_quantile)
        relevant_ids = set(np.asarray(test_ids)[relevant_mask])
        gains = target.loc[test_ids].to_dict()
        task = {
            "fold_scheme": fold_column, "fold": fold,
            "train_ids": list(train_ids),
            "train_target": target.loc[train_ids].copy(),
            "test_ids": list(test_ids),
            "fit_exclusion_ids": sorted(set(test_ids) | excluded),
        }
        ranked, abstained = _normalize_decision(engine_fn(task), test_ids, fold)
        metrics = evaluate_ranking(ranked, test_ids, relevant_ids, gains,
                                   k_grid=k_grid, abstained_ids=abstained)
        records.append({"fold": fold, "fold_scheme": fold_column,
                        "n_train_used": len(train_ids),
                        "n_buffer_excluded": len(excluded),
                        "label_threshold_train": threshold, **metrics})
        decisions.extend({"fold_scheme": fold_column, "fold": fold, "cvegeo": c,
                          "rank": i + 1, "decision": "ranked",
                          "relevant": c in relevant_ids}
                         for i, c in enumerate(ranked))
        decisions.extend({"fold_scheme": fold_column, "fold": fold, "cvegeo": c,
                          "rank": pd.NA, "decision": "abstained",
                          "relevant": c in relevant_ids}
                         for c in sorted(abstained))
    detail = pd.DataFrame(records)
    metric_columns = [c for c in detail.columns
                      if "@" in c or c in ("decision_coverage", "relevant_abstained")]
    summary = detail[metric_columns].agg(["mean", "std", "min", "max", "count"]).T
    decision_table = pd.DataFrame(decisions)
    decision_table["rank"] = decision_table["rank"].astype("Int64")
    return detail, summary, decision_table


# ---------------------------------------------------------------------------
# Auto-pruebas y contraejemplos del arnés
# ---------------------------------------------------------------------------

def _raises(fn):
    try:
        fn()
    except ValueError:
        return 1.0
    return 0.0


def metric_selftests():
    """Respuestas conocidas y contraejemplos sintéticos de las métricas."""
    universe = ["a", "b", "c", "d", "e"]
    relevant = {"a", "b", "c"}
    gains = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 0.0, "e": 0.0}
    ideal_dcg = 3.0 + 2.0 / np.log2(3) + 1.0 / np.log2(4)
    mid_dcg = 3.0 / np.log2(3)
    grid = [1, 2, 3, 5, 10]

    def ev(ranked, abstained=None):
        return evaluate_ranking(ranked, universe, relevant, gains,
                                k_grid=grid, abstained_ids=abstained)

    scenarios = [
        ("perfect_ranking", ev(["a", "b", "c", "d", "e"]), {
            "precision@2": 1.0, "recall@2": 2 / 3, "ndcg@3": 1.0,
            "precision@5": 0.6, "recall@5": 1.0, "effective_k@10": 5.0,
            "precision@10": 0.6, "decision_coverage": 1.0}),
        ("worst_ranking", ev(["e", "d", "c", "b", "a"]), {
            "precision@2": 0.0, "recall@2": 0.0}),
        ("middle_ranking", ev(["d", "a", "e", "b", "c"]), {
            "precision@2": 0.5, "recall@2": 1 / 3,
            "ndcg@3": mid_dcg / ideal_dcg}),
        ("explicit_abstention", ev(["a"], ["b", "c", "d", "e"]), {
            "recall@5": 1 / 3, "precision@5": 0.2, "precision_cond@5": 1.0,
            "decision_coverage": 0.2, "relevant_abstained": 2.0,
            "ndcg@5": 3.0 / ideal_dcg, "ndcg_cond@5": 1.0}),
        # abstenerse sobre la de mayor ganancia infla el NDCG condicional:
        # IDCG se calcula solo sobre lo rankeado -> lectura junto a
        # decision_coverage
        ("abstention_inflates_ndcg_cond", ev(["b", "c", "d", "e"], ["a"]), {
            "ndcg_cond@5": 1.0, "ndcg@5":
            (2.0 + 1.0 / np.log2(3)) / ideal_dcg,
            "decision_coverage": 0.8}),
        ("omission_cannot_inflate_recall", ev(["a"]), {
            "recall@2": 1 / 3, "recall@5": 1 / 3}),
    ]
    rows = [{"family": "metric", "scenario": name, "metric": metric,
             "expected": float(exp), "observed": float(observed[metric]),
             "pass": bool(np.isclose(observed[metric], exp))}
            for name, observed, expected in scenarios
            for metric, exp in expected.items()]
    rejections = {
        "duplicate_ranked_ids": lambda: ev(["a", "a", "b"]),
        "foreign_ranked_id": lambda: ev(["a", "zz"]),
        "gains_not_matching_universe": lambda: evaluate_ranking(
            ["a"], universe, relevant, {"a": 1.0}, k_grid=grid),
        "relevant_outside_universe": lambda: evaluate_ranking(
            ["a"], universe, {"zz"}, gains, k_grid=grid),
        "abstention_not_partitioning": lambda: ev(["a"], ["b"]),
        "nonpositive_k": lambda: precision_at_k(["a"], relevant, 0, universe),
    }
    rows += [{"family": "metric", "scenario": name, "metric": "raises_ValueError",
              "expected": 1.0, "observed": _raises(fn),
              "pass": _raises(fn) == 1.0}
             for name, fn in rejections.items()]
    bounded = all(0 <= ev(order)[f"{m}@{k}"] <= 1 + 1e-12
                  for order in (["a", "b", "c", "d", "e"], ["c", "e", "a"])
                  for k in grid for m in ("ndcg", "ndcg_cond"))
    rows.append({"family": "metric", "scenario": "ndcg_bounded_unit_interval",
                 "metric": "bounded", "expected": 1.0,
                 "observed": float(bounded), "pass": bounded})
    table = pd.DataFrame(rows)
    if not table["pass"].all():
        raise ValueError("Ranking metric self-tests failed")
    return table


def harness_probes(universe, folds):
    """Contraejemplos sobre los folds REALES: el arnés debe rechazarlos todos."""
    eval_ids = folds.cvegeo.tolist()
    block_counts = folds.spatial_block_id.value_counts()
    multi_block = block_counts.index[block_counts.gt(1)][0]

    def split_block():
        bad = folds.copy()
        rows = bad.index[bad.spatial_block_id == multi_block]
        fold = int(bad.loc[rows[0], "fold_spatial_block"])
        bad.loc[rows[0], "fold_spatial_block"] = (fold + 1) % CONFIG["n_folds"]
        return validate_folds(universe, bad, "fold_spatial_block")

    probes = {
        "fold_table_missing_one_ageb": lambda: validate_folds(
            universe, folds.iloc[1:], "fold_groupkfold_ageb"),
        "fold_table_duplicate_ageb": lambda: validate_folds(
            universe, pd.concat([folds, folds.iloc[[0]]]), "fold_groupkfold_ageb"),
        "fold_table_foreign_ageb": lambda: validate_folds(
            universe, pd.concat([folds, folds.iloc[[0]].assign(cvegeo="FOREIGN")]),
            "fold_groupkfold_ageb"),
        "fold_id_out_of_range": lambda: validate_folds(
            universe, folds.assign(fold_groupkfold_ageb=folds.fold_groupkfold_ageb
                                   .where(folds.cvegeo != eval_ids[0], 99)),
            "fold_groupkfold_ageb"),
        "spatial_block_split_between_folds": split_block,
        "engine_duplicates_ids": lambda: run_backtest(
            universe, folds, "fold_groupkfold_ageb",
            lambda task: task["test_ids"] + task["test_ids"][:1]),
        "engine_drops_ids_without_abstaining": lambda: run_backtest(
            universe, folds, "fold_groupkfold_ageb",
            lambda task: task["test_ids"][1:]),
        "engine_returns_foreign_id": lambda: run_backtest(
            universe, folds, "fold_groupkfold_ageb",
            lambda task: task["test_ids"][1:] + ["FOREIGN"]),
        "singular_reference_covariance": lambda: fit_mahalanobis(
            np.c_[np.random.default_rng(0).normal(size=(40, 7)), np.zeros(40)]),
    }
    rows = [{"family": "harness", "scenario": name, "metric": "raises_ValueError",
             "expected": 1.0, "observed": _raises(fn), "pass": _raises(fn) == 1.0}
            for name, fn in probes.items()]
    accepted = 1.0 - _raises(lambda: run_backtest(
        universe, folds, "fold_spatial_block",
        lambda task: {"ranked": task["test_ids"][:3],
                      "abstained": task["test_ids"][3:]}))
    rows.append({"family": "harness", "scenario": "explicit_abstention_accepted",
                 "metric": "accepted", "expected": 1.0, "observed": accepted,
                 "pass": accepted == 1.0})
    table = pd.DataFrame(rows)
    if not table["pass"].all():
        raise ValueError(f"Harness counterexample probes failed: "
                         f"{table.loc[~table['pass'], 'scenario'].tolist()}")
    return table


def fold_local_protocol_spec():
    """Especificación normativa del reajuste por pliegue para los motores."""
    return {
        "description": "Todo estimador de preprocesamiento y referencia se "
                       "ajusta exclusivamente con filas fuera de "
                       "fit_exclusion_ids (prueba ∪ buffer) del pliegue.",
        "refit_inside_each_training_fold": [
            "SimpleImputer(strategy='median') sobre las tasas permitidas",
            "StandardScaler",
            "PCA (n_components=0.80, svd_solver='full'); k puede variar por fold",
            "Umbral P85 del objetivo para la referencia de alta actividad",
            "Centroide y covarianza de la referencia de entrenamiento",
            "Umbral de dominio sqrt(chi2.ppf(0.9973, df=k_fold))",
        ],
        "applied_as_transform_to_validation": [
            "Pipeline fe03.build_pipeline() re-instanciado y ajustado fuera "
            "de fit_exclusion_ids; prueba solo recibe .transform()",
            "Distancia de Mahalanobis con mu/Sigma_inv del fold",
        ],
        "forbidden": [
            "Reutilizar el PCA global del cuaderno 03 como preprocesamiento "
            "de validación",
            "Usar is_golden_cluster/has_golden_station: su umbral P85 se "
            "calculó con todas las estaciones, incluidas las de prueba",
            "Calcular P85/centroide/covarianza con filas de prueba o del buffer",
            "Partir AGEBs de un mismo bloque espacial entre pliegues",
            "Tratar AGEBs sin estación interna como negativos de demanda",
        ],
        "engine_interface": "engine_fn(task) -> list (ranking completo) o "
                            "{'ranked': [...], 'abstained': [...]} que "
                            "particionen exactamente task['test_ids']",
    }


def analyze(data):
    frames = data["frames"]
    universe, pcs = build_evaluation_universe(
        frames["features"], frames["scores"], frames["station_env"])
    golden_mask = universe.is_golden_cluster & universe.is_projectable
    if not golden_mask.any():
        raise ValueError("No projectable Golden AGEBs in the published space")
    fit = fit_mahalanobis(universe.loc[golden_mask, pcs].to_numpy(float))
    _selfcheck_mahalanobis(fit)
    fit_lw = fit_mahalanobis(universe.loc[golden_mask, pcs].to_numpy(float),
                             estimator="ledoit_wolf")
    _selfcheck_mahalanobis(fit_lw)
    universe = apply_domain_gate(universe, fit, pcs)
    dist_lw = mahalanobis_distance(
        universe[pcs].to_numpy(float), fit_lw["mu"], fit_lw["sigma_inv"])
    evaluable_lw = universe.is_projectable.to_numpy(bool) \
        & np.isfinite(dist_lw)
    in_domain_lw = evaluable_lw & (dist_lw <= fit_lw["threshold"])
    folds, fold_info = make_folds(universe)
    universe = universe.merge(folds[["cvegeo", "spatial_block_id"]], on="cvegeo",
                              how="left", validate="one_to_one")
    universe["spatial_block_id"] = universe.spatial_block_id.astype("Int64")
    contiguity = block_contiguity(universe, folds)

    exclusions = pd.concat([buffer_exclusions(universe, folds, scheme)
                            for scheme in CONFIG["buffered_schemes"]],
                           ignore_index=True)
    separation = pd.concat([
        separation_diagnostics(universe, folds, scheme,
                               exclusions.loc[exclusions.fold_scheme == scheme])
        for scheme in FOLD_SCHEMES], ignore_index=True)
    selftests = pd.concat([metric_selftests(), harness_probes(universe, folds)],
                          ignore_index=True)

    # ---- Contrato de despliegue común (motores 05/06/07 en paralelo) --
    dep = fe04_deployment
    dcfg = dep.DEPLOY_CONFIG
    stations = frames["station_env"].to_crs(
        dcfg["metric_crs"]).reset_index(drop=True)
    stations_xy = np.c_[stations.geometry.x, stations.geometry.y]
    is_golden = stations.is_golden.astype(bool).to_numpy()
    link_table = dep.link_distance_analysis(
        stations_xy, is_golden, dcfg["link_grid"])
    dep.check_link_distance(link_table, dcfg)
    nn_q = dep.nearest_neighbor_quantiles(stations_xy, dcfg["nn_quantiles"])
    dep_candidates = frames["features"].loc[
        frames["features"].is_candidata_proyectable.astype(bool)]
    deploy_sites = dep.build_sites(dep_candidates, stations_xy, dcfg)
    deploy_cells = dep.population_surface(
        frames["features"], stations_xy, dcfg)
    deploy_incidence = dep.site_cell_incidence(
        np.c_[deploy_sites.x, deploy_sites.y], deploy_cells, dcfg)
    deploy_ctx = dep.build_network_context(
        deploy_sites, deploy_cells, deploy_incidence, stations, dcfg)

    # Control de plomería: ranking aleatorio con semilla fija, sin abstención.
    rng = np.random.default_rng(CONFIG["seed"])

    def random_engine(task):
        return rng.permutation(task["test_ids"]).tolist()

    random_detail, random_summary = {}, {}
    for scheme in FOLD_SCHEMES:
        detail, summary, _ = run_backtest(universe, folds, scheme, random_engine)
        random_detail[scheme], random_summary[scheme] = detail, summary

    in_eval = universe.in_evaluation_universe
    candidates = universe.is_candidata_proyectable
    golden_in_eval = universe.is_golden_cluster & in_eval
    target = universe.loc[in_eval, TARGET]
    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "notebook": "04_Diseno_Validacion_Backtest.ipynb",
        "configuration": CONFIG,
        "scope": {
            "is_validation_harness_only": True,
            "models_trained": False,
            "time_series_validation": "excluded; operational Motor 2 "
                                      "(stockouts) officially descoped",
            "produces_engine_results": False,
            "random_control_is_a_plumbing_check": True,
            "what_the_backtest_tests": CONFIG["ranking_task"],
            "what_it_does_not_test": "latent demand in AGEBs without stations; "
                                     "physical feasibility; network design",
        },
        "upstream": {
            "feature_analysis_id": data["feature_analysis_id"],
            "eda_analysis_id": data["eda_analysis_id"],
            "pca_space_k": len(pcs),
            "pca_space_fit_scope": data["feature_report"]["pca_reduction"][
                "fit_scope"],
        },
        "evaluation_universe": {
            "definition": "is_projectable AND n_estaciones > 0 AND NOT "
                          "is_candidata_territorial",
            "size": int(in_eval.sum()),
            "roles": universe.evaluation_role.value_counts().astype(int).to_dict(),
            "target": TARGET,
            "target_definition": "mean viajes_diarios_prom of stations hosted "
                                 "by the AGEB polygon",
            "why_mean_not_sum": "the AGEB sum grows with station count; the "
                                "mean per station measures intensity per site",
            "target_spearman_with_station_count": float(
                universe.loc[in_eval, [TARGET, "n_estaciones"]].corr(
                    "spearman").iloc[0, 1]),
            "sum_spearman_with_station_count": float(
                universe.loc[in_eval, ["actividad_total_diaria", "n_estaciones"]]
                .corr("spearman").iloc[0, 1]),
            "target_quantiles": {str(q): float(target.quantile(q))
                                 for q in (0.0, 0.25, 0.5, 0.75, 0.85, 1.0)},
            "covered_without_station_treatment": "excluded from labels; their "
                                                 "absence of stations is not "
                                                 "evidence of low demand",
            "label": "target >= P85 fitted on the retained TRAIN rows only",
            "gain_for_ndcg": f"linear {TARGET}",
            "golden_reference_relation": {
                "golden_03_definition": "AGEB hosting >=1 station above the "
                                        "station-level P85 over ALL stations",
                "golden_in_universe": int(golden_in_eval.sum()),
                "golden_mean_target": float(
                    universe.loc[golden_in_eval, TARGET].mean()),
                "non_golden_mean_target": float(
                    universe.loc[in_eval & ~universe.is_golden_cluster,
                                 TARGET].mean()),
                "note": "Golden labels use test-fold stations in their P85 "
                        "and are forbidden as engine inputs; fold-local "
                        "references are rebuilt from the train target",
            },
        },
        "mahalanobis_gate": {
            "scope": "global descriptive gate referenced to the 61 Golden "
                     "AGEBs of notebook 03; engines must refit a fold-local "
                     "gate for backtests",
            "k_dims": fit["k_dims"], "n_reference": fit["n_reference"],
            "covariance_rank": fit["covariance_rank"],
            "singular_covariance_policy": "rejected (no pseudoinverse)",
            "min_eigenvalue": fit["min_eigenvalue"],
            "condition_number": fit["condition_number"],
            "quantile": fit["quantile"], "df": fit["df"],
            "chi2_ppf": fit["chi2_ppf"], "threshold": fit["threshold"],
            "estimator": fit["estimator"],
            "covariance_estimator_comparison": {
                "empirical": {
                    "condition_number": fit["condition_number"],
                    "covariance_rank": fit["covariance_rank"],
                    "in_domain_count": int(
                        universe.domain_status.eq("in_domain").sum()),
                },
                "ledoit_wolf": {
                    "condition_number": fit_lw["condition_number"],
                    "covariance_rank": fit_lw["covariance_rank"],
                    "shrinkage": fit_lw["shrinkage"],
                    "in_domain_count": int(in_domain_lw.sum()),
                },
                "note": "descriptive comparison over the Golden gate, "
                        "which stays empirical; the chi-square threshold "
                        "is nominal under shrinkage (train distances no "
                        "longer follow chi2_k exactly)",
            },
            "normality_assumption": "chi-square calibration assumes "
                                    "approximately elliptical reference "
                                    "scores; it is a support heuristic, not "
                                    "a probability guarantee",
            "in_domain_counts": universe.domain_status.value_counts()
            .astype(int).to_dict(),
            "golden_self_in_domain": int(
                (universe.is_golden_cluster
                 & universe.domain_status.eq("in_domain")).sum()),
            "golden_self_in_domain_interpretation": "descriptive only; does "
                                                    "not demonstrate "
                                                    "calibration",
            "candidates_in_domain": int(
                (candidates & universe.domain_status.eq("in_domain")).sum()),
            "candidates_out_of_domain": int(
                (candidates & universe.domain_status.eq("out_of_domain")).sum()),
            "out_of_domain_interpretation": "outside the Golden statistical "
                                            "envelope; not evidence of a bad "
                                            "location",
        },
        "spatial_cv": {
            **fold_info,
            **contiguity,
            "primary_scheme": CONFIG["primary_scheme"],
            "groupkfold_ageb_note": "at AGEB granularity equals shuffled "
                                    "KFold; no spatial isolation; optimistic "
                                    "reference",
            "spatial_block_note": "Ward agglomerative clustering on "
                                  "centroids with polygon-adjacency "
                                  "connectivity: Ward only merges "
                                  "neighbouring AGEBs, so blocks are "
                                  "geographically coherent; if the "
                                  "adjacency graph is fragmented "
                                  "(n_adjacency_components > 1) blocks may "
                                  "join separate islands — reported via "
                                  "blocks_contiguous_share. Adjacency "
                                  "leakage is prevented by the training "
                                  "buffer, not by block contiguity",
            "buffer_m": CONFIG["buffer_m"],
            "buffered_schemes": CONFIG["buffered_schemes"],
            "buffer_exclusions_by_scheme": exclusions.groupby("fold_scheme")
            .size().astype(int).to_dict(),
            "separation": separation.to_dict(orient="records"),
            "shuffle": True, "random_state": CONFIG["seed"],
        },
        "ranking_metrics": {
            "k_grid": CONFIG["k_grid"],
            "precision_at_k": "|top-K ∩ relevant| / K_eff, K_eff = min(K, |fold|)",
            "recall_at_k": "|top-K ∩ relevant| / |relevant in fold| (NaN if 0)",
            "ndcg_at_k": "linear gains, log2(position+1) discount, IDCG over "
                         "the full fold at K_eff (NaN if IDCG = 0); "
                         "unconditional primary",
            "ndcg_cond_at_k": "IDCG over the effectively ranked set only: "
                              "does not penalize abstention and may reward "
                              "gates that abstain on hard cases; always read "
                              "together with decision_coverage",
            "precision_cond_at_k": "hits / min(K_eff, |ranked|): quality "
                                   "among recommended only",
            "abstention": "unranked test IDs count as abstained: they never "
                          "shrink denominators; decision_coverage and "
                          "relevant_abstained are reported",
            "input_validation": "duplicate, foreign or missing IDs are "
                                "rejected",
            "effective_k_by_fold": {
                scheme: detail[[f"effective_k@{k}" for k in CONFIG["k_grid"]]]
                .to_dict(orient="list")
                for scheme, detail in random_detail.items()},
            "selftests_all_passed": bool(selftests["pass"].all()),
            "n_selftests": int(len(selftests)),
        },
        "random_control": {
            scheme: {metric: float(summary.loc[metric, "mean"])
                     for metric in summary.index}
            for scheme, summary in random_summary.items()
        },
        "fold_local_protocol": fold_local_protocol_spec(),
        "deployment_contract": {
            "statement": "Los motores 05, 06 y 07 usan exactamente estos "
                         "sitios, reglas de factibilidad, superficie "
                         "poblacional, métricas de portafolio y la misma "
                         "malla de presupuestos fijada por el usuario",
            "config": dep.DEPLOY_CONFIG,
            "link_distance_table": link_table.astype(object)
            .where(pd.notna(link_table), None).to_dict(orient="records"),
            "asserted_min_single_component_m": dcfg["link_distance_m"],
            "nn_distance_quantiles_m": nn_q,
            "n_sites": int(len(deploy_sites)),
            "n_agebs_with_sites": int(deploy_sites.cvegeo.nunique()),
            "sites_per_ageb": {
                k: float(v) for k, v in
                deploy_sites.cvegeo.value_counts().describe().items()},
            "population": {
                "n_cells": int(len(deploy_cells)),
                "total_pop": float(deploy_cells["pop"].sum()),
                "covered_existing_pop": float(
                    deploy_cells.loc[deploy_cells.covered_existing,
                                     "pop"].sum()),
                "uncovered_pop": float(
                    deploy_cells.loc[~deploy_cells.covered_existing,
                                     "pop"].sum()),
                "unknown_area_share": float(
                    deploy_cells.unknown_share.sum() / len(deploy_cells)),
            },
        },
        "serialization": "validation_harness.joblib stores calibrated "
                         "parameters, full fold assignments, unfitted "
                         "GroupKFold splitters and the metric/backtest "
                         "callables pickled by reference to fe04_analysis; "
                         "their code is pinned by code_hashes",
        "pending_validation": [
            "Engine rankings themselves (cuadernos 05/06/07)",
            "Sensitivity of in_domain to the Mahalanobis quantile",
            "Sensitivity of metrics to the label quantile",
            "Alternative NDCG gains (binary vs linear vs log)",
            "Buffer distance sensitivity (500 m declared)",
        ],
    }
    return {
        "universe": universe, "folds": folds, "mahalanobis_fit": fit,
        "buffer_exclusions": exclusions, "separation": separation,
        "selftests": selftests, "random_detail": random_detail,
        "random_summary": random_summary, "report": report,
        "deploy_sites": deploy_sites, "deploy_cells": deploy_cells,
        "deploy_link_table": link_table, "deploy_ctx": deploy_ctx,
    }
