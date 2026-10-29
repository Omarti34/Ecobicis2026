"""Observed-data diagnostics for notebook 02; no model fitting or simulated evidence."""
import hashlib
import json
import platform
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import scipy
from scipy import stats
from scipy.spatial import cKDTree

from V3.src.artifact_reader import load_committed_audit

VERSION = "v3-eda-2"
CONFIG = {
    "metric_crs": "EPSG:32614",
    "golden_quantile": 0.85,
    "iqr_multiplier": 1.5,
    "moran_k": 8,
    "moran_sensitivity_k": [4, 8, 12],
    "permutations": 999,
    "seed": 42,
    "bootstrap_ageb_replicates": 1000,
    "bootstrap_percentiles": [2.5, 97.5],
    "diagnostic_access_radius_m": 400,
    "tertiary_scian_sectors": [
        "43", "46", "48", "49", "51", "52", "53", "54", "55", "56",
        "61", "62", "71", "72", "81", "93",
    ],
    "open_employment_band_scenarios": [251, 300, 500, 1000],
    "open_employment_band_reference": 300,
}
EMPLOYMENT_MIDPOINTS = {
    "0 a 5 personas": 2.5, "6 a 10 personas": 8,
    "11 a 30 personas": 20.5, "31 a 50 personas": 40.5,
    "51 a 100 personas": 75.5, "101 a 250 personas": 175.5,
}
OPEN_BAND = "251 y m\u00e1s personas"
INPUTS = [
    "actividad_estaciones", "agebs", "denue", "gtfs_stops", "gtfs_routes",
    "gtfs_trips", "gtfs_stop_times", "gtfs_calendar",
]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs(v3):
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    root = v3 / "data/processed" / audit["contract_id"]
    frames = {name: (gpd.read_parquet if name == "agebs" else pd.read_parquet)(
        root / (name + ".parquet")) for name in INPUTS}
    frames["agebs"] = frames["agebs"].to_crs(CONFIG["metric_crs"])
    activity = frames["actividad_estaciones"]
    frames["stations"] = gpd.GeoDataFrame(
        activity.copy(), geometry=gpd.points_from_xy(activity.lon, activity.lat),
        crs="EPSG:4326").to_crs(CONFIG["metric_crs"])
    if not activity.ce_id.is_unique or not frames["agebs"].cvegeo.is_unique:
        raise ValueError("Station/AGEB identifiers must be unique")
    return {"v3": v3, "audit": audit, "frames": frames}


def gini_lorenz(values):
    x = np.sort(np.asarray(values, dtype=float))
    if not len(x) or not np.isfinite(x).all() or (x < 0).any() or x.sum() <= 0:
        raise ValueError("Gini requires finite, nonnegative values with a positive sum")
    ranks = np.arange(1, len(x) + 1)
    gini = (2 * (ranks * x).sum() - (len(x) + 1) * x.sum()) / (len(x) * x.sum())
    return float(gini), np.r_[0, ranks / len(x)], np.r_[0, np.cumsum(x) / x.sum()]


def knn_weights(coords, k):
    coords = np.asarray(coords, dtype=float)
    if k < 1 or k >= len(coords) or not np.isfinite(coords).all():
        raise ValueError("Invalid K-NN coordinates or k")
    distances, indices = cKDTree(coords).query(coords, k=k + 1)
    weights = np.zeros((len(coords), len(coords)))
    neighbor_distances = []
    for i in range(len(coords)):
        # Remove self by identity, not position: tied coordinates are allowed.
        keep = indices[i] != i
        neighbors = indices[i][keep][:k]
        if len(neighbors) != k:
            raise ValueError("Insufficient non-self neighbors")
        weights[i, neighbors] = 1 / k
        neighbor_distances.append(float(distances[i][keep][:k][-1]))
    return weights, np.asarray(neighbor_distances)


def moran_global(values, weights, permutations=999, seed=42):
    y = np.asarray(values, dtype=float)
    z = y - y.mean()
    denominator = float(z @ z)
    if denominator == 0 or not np.isfinite(z).all():
        raise ValueError("Moran requires finite, nonconstant observations")
    factor = len(y) / weights.sum() / denominator
    observed = float(factor * (z @ (weights @ z)))
    rng = np.random.RandomState(seed)
    simulated = []
    for _ in range(permutations):
        permuted = rng.permutation(z)
        simulated.append(float(factor * (permuted @ (weights @ permuted))))
    exceedances = int(np.sum(np.asarray(simulated) >= observed))
    return {
        "i": observed, "expected_i": -1 / (len(y) - 1),
        "p_value": (exceedances + 1) / (permutations + 1),
        "permutation_exceedances": exceedances, "permutations": permutations,
        "seed": seed, "alternative": "positive_autocorrelation_upper_tail",
    }


def observed_correlations(frame, predictors):
    rows = []
    for name, transform in predictors.items():
        x = frame[name].to_numpy(dtype=float, na_value=np.nan)
        if transform == "log1p":
            x = np.log1p(x)
        y = frame.viajes_diarios_prom.to_numpy(dtype=float, na_value=np.nan)
        valid = np.isfinite(x) & np.isfinite(y)
        xv, yv = x[valid], y[valid]
        groups = frame.loc[valid, "cvegeo"].to_numpy()
        group_ids = np.unique(groups)
        group_rows = [np.flatnonzero(groups == key) for key in group_ids]
        pearson, spearman = stats.pearsonr(xv, yv), stats.spearmanr(xv, yv)
        rng = np.random.default_rng(CONFIG["seed"])
        samples = []
        for _ in range(CONFIG["bootstrap_ageb_replicates"]):
            indices = np.concatenate([
                group_rows[i] for i in rng.integers(0, len(group_ids), len(group_ids))
            ])
            xb, yb = xv[indices], yv[indices]
            if np.ptp(xb) and np.ptp(yb):
                samples.append((stats.pearsonr(xb, yb).statistic,
                                stats.spearmanr(xb, yb).statistic))
        intervals = np.percentile(samples, CONFIG["bootstrap_percentiles"], axis=0)
        rows.append({
            "predictor": name, "transform": transform, "n_stations": int(valid.sum()),
            "n_agebs": len(group_ids), "pearson_r": float(pearson.statistic),
            "pearson_p_iid_reference": float(pearson.pvalue),
            "spearman_rho": float(spearman.statistic),
            "spearman_p_iid_reference": float(spearman.pvalue),
            "pearson_ci_ageb_low": float(intervals[0, 0]),
            "pearson_ci_ageb_high": float(intervals[1, 0]),
            "spearman_ci_ageb_low": float(intervals[0, 1]),
            "spearman_ci_ageb_high": float(intervals[1, 1]),
        })
    return pd.DataFrame(rows)


def denue_proxy(denue, agebs, open_band=300):
    dates = denue.fecha_alta_parsed
    historical_registration = dates.notna() & dates.dt.year.le(2025)
    tertiary = denue.codigo_act.astype("string").str[:2].isin(
        CONFIG["tertiary_scian_sectors"])
    selected = denue.loc[historical_registration & tertiary].copy()
    selected["employment_scenario"] = selected.per_ocu.map(
        {**EMPLOYMENT_MIDPOINTS, OPEN_BAND: float(open_band)}).astype(float)
    if selected.employment_scenario.isna().any():
        raise ValueError("Unknown employment band: no silent imputation allowed")
    matched = selected.loc[selected.cvegeo.isin(agebs.cvegeo)]
    totals = matched.groupby("cvegeo").agg(
        establecimientos_terciarios=("id", "size"),
        empleo_terciario_proxy=("employment_scenario", "sum"))
    # Zero means no matched, eligible establishment in this snapshot, not zero jobs in 2025.
    totals = totals.reindex(agebs.cvegeo, fill_value=0).rename_axis("cvegeo").reset_index()
    diagnostics = {
        "snapshot_years": sorted(int(x) for x in denue.snapshot_year.dropna().unique()),
        "input_establishments": len(denue),
        "registration_after_2025": int(denue.registered_after_study_year.sum()),
        "registration_unknown": int(dates.isna().sum()),
        "tertiary_with_known_registration_through_2025": len(selected),
        "tertiary_unmatched_ageb": len(selected) - len(matched),
        "tertiary_open_employment_band": int(selected.per_ocu.eq(OPEN_BAND).sum()),
        "historical_2025_stock_reconstructed": False,
    }
    return totals, diagnostics


def gtfs_proximity(frames, stations):
    stops = frames["gtfs_stops"]
    stops_m = gpd.GeoDataFrame(
        stops, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat),
        crs="EPSG:4326").to_crs(CONFIG["metric_crs"])
    distances, nearest = cKDTree(np.c_[stops_m.geometry.x, stops_m.geometry.y]).query(
        np.c_[stations.geometry.x, stations.geometry.y])
    links = frames["gtfs_stop_times"][["trip_id", "stop_id"]].merge(
        frames["gtfs_trips"][["trip_id", "route_id", "service_id"]],
        on="trip_id", validate="many_to_one").merge(
        frames["gtfs_routes"][["route_id", "agency_id", "route_type"]],
        on="route_id", validate="many_to_one").merge(
        frames["gtfs_calendar"][["service_id", "has_2025_service"]],
        on="service_id", validate="many_to_one")
    agencies = links.groupby("stop_id").agency_id.agg(lambda x: "|".join(sorted(set(x))))
    stops_2025 = set(links.loc[links.has_2025_service, "stop_id"])
    nearest_ids = stops.iloc[nearest].stop_id.reset_index(drop=True)
    result = pd.DataFrame({
        "ce_id": stations.ce_id.to_numpy(), "dist_gtfs_m": distances,
        "nearest_gtfs_stop_id": nearest_ids,
        "nearest_gtfs_agencies": nearest_ids.map(agencies).fillna("unlinked_in_accepted_trips"),
        "nearest_stop_linked_to_2025_calendar": nearest_ids.isin(stops_2025),
    })
    diagnostics = {
        "distance_universe": "all accepted GTFS stops; not Metro-only or 2025-only",
        "accepted_stops": len(stops), "stops_linked_to_accepted_trips": links.stop_id.nunique(),
        "nearest_agency_counts": result.nearest_gtfs_agencies.value_counts().to_dict(),
        "nearest_without_2025_calendar_link": int(
            (~result.nearest_stop_linked_to_2025_calendar).sum()),
        "route_type_counts": {
            str(k): int(v) for k, v in frames["gtfs_routes"].route_type.value_counts().items()
        },
        "calendar_link_is_not_proof_of_historical_stop_location": True,
    }
    return result, diagnostics


def analyze(data):
    frames, audit = data["frames"], data["audit"]
    stations, agebs = frames["stations"].copy(), frames["agebs"].copy()
    joined = gpd.sjoin(
        stations, agebs[["cvegeo", "nom_mun", "densidad_pob_km2", "geometry"]],
        how="left", predicate="within")
    if len(joined) != len(stations) or joined.ce_id.duplicated().any() or joined.cvegeo.isna().any():
        raise ValueError("Each station must have exactly one audited AGEB assignment")
    counts = joined.groupby("cvegeo").size()
    activity = joined.groupby("cvegeo").viajes_diarios_prom.sum()
    agebs["n_estaciones"] = agebs.cvegeo.map(counts).fillna(0).astype("Int64")
    agebs["actividad_diaria"] = agebs.cvegeo.map(activity).fillna(0).astype("Float64")
    gini_st, lorenz_x, lorenz_y = gini_lorenz(agebs.n_estaciones)
    gini_activity, _, _ = gini_lorenz(agebs.actividad_diaria)
    coords = np.c_[stations.geometry.x, stations.geometry.y]
    tree = cKDTree(coords)
    centroids = agebs.geometry.centroid
    gaps, _ = tree.query(np.c_[centroids.x, centroids.y])
    agebs["dist_centroide_red_km"] = gaps / 1000
    agebs["centroid_within_polygon"] = agebs.geometry.covers(centroids).to_numpy()
    unserved = agebs.loc[agebs.n_estaciones.eq(0)]
    y = stations.viajes_diarios_prom.to_numpy(dtype=float)
    q1, q3 = np.quantile(y, [0.25, 0.75])
    p85 = float(np.quantile(y, CONFIG["golden_quantile"]))
    weights, eighth_distances = knn_weights(coords, CONFIG["moran_k"])
    moran = moran_global(y, weights, CONFIG["permutations"], CONFIG["seed"])
    centered = y - y.mean()
    lag = weights @ centered
    stations["moran_centered_activity"] = centered
    stations["moran_spatial_lag"] = lag
    stations["moran_quadrant"] = np.select(
        [(centered >= 0) & (lag >= 0), (centered < 0) & (lag < 0),
         (centered >= 0) & (lag < 0)], ["High-High", "Low-Low", "High-Low"],
        default="Low-High")
    sensitivity = []
    for k in CONFIG["moran_sensitivity_k"]:
        wk, _ = knn_weights(coords, k)
        for transform, vector in [("raw", y), ("log1p", np.log1p(y))]:
            measurement = (moran if k == CONFIG["moran_k"] and transform == "raw"
                           else moran_global(vector, wk, CONFIG["permutations"], CONFIG["seed"]))
            sensitivity.append({"k": k, "transform": transform, **measurement})
    proximity, gtfs_info = gtfs_proximity(frames, stations)
    denue_agg, denue_info = denue_proxy(
        frames["denue"], agebs, CONFIG["open_employment_band_reference"])
    env = joined.drop(columns="index_right").merge(
        proximity, on="ce_id", validate="one_to_one").merge(
        denue_agg, on="cvegeo", validate="many_to_one")
    predictors = {
        "densidad_pob_km2": "identity", "dist_gtfs_m": "identity",
        "empleo_terciario_proxy": "log1p",
    }
    correlations = observed_correlations(env, predictors)
    employment_sensitivity = []
    for scenario in CONFIG["open_employment_band_scenarios"]:
        totals, _ = denue_proxy(frames["denue"], agebs, scenario)
        lookup = totals.set_index("cvegeo").empleo_terciario_proxy
        vector = env.cvegeo.map(lookup).to_numpy(dtype=float)
        observed_activity = env.viajes_diarios_prom.to_numpy(dtype=float)
        employment_sensitivity.append({
            "open_band_assumption": scenario,
            "pearson_log1p": float(stats.pearsonr(np.log1p(vector), observed_activity).statistic),
            "spearman": float(stats.spearmanr(vector, observed_activity).statistic),
        })
    env["is_golden"] = env.viajes_diarios_prom.ge(p85)
    golden = env.loc[env.is_golden].copy()
    golden_stats = golden.groupby("cvegeo").agg(
        n_golden_stations=("ce_id", "size"),
        golden_mean_daily_activity=("viajes_diarios_prom", "mean")).reset_index()
    golden_agebs = agebs.merge(golden_stats, on="cvegeo", how="inner", validate="one_to_one")
    golden_coords = np.c_[golden.geometry.x, golden.geometry.y]
    golden_nn, _ = cKDTree(golden_coords).query(golden_coords, k=2)
    network_nn, _ = tree.query(coords, k=2)
    capacity_valid = env.capacity.notna() & env.capacity.gt(0)
    turnover = 2 * env.loc[capacity_valid, "viajes_diarios_prom"] / env.loc[capacity_valid, "capacity"]
    turnover_rho = float(stats.spearmanr(
        env.loc[capacity_valid, "viajes_diarios_prom"], turnover).statistic)
    coverage_rows = []
    for name, mask in [("with_internal_station", agebs.n_estaciones.gt(0)),
                       ("without_internal_station", agebs.n_estaciones.eq(0))]:
        subset = agebs.loc[mask].merge(denue_agg, on="cvegeo", validate="one_to_one")
        coverage_rows.append({
            "cohort": name, "n_agebs": len(subset),
            "population_missing": int(subset.pob_total.isna().sum()),
            "density_missing": int(subset.densidad_pob_km2.isna().sum()),
            "rural_missing_population": int(subset.is_rural_nan.sum()),
            "zero_matched_tertiary_establishments": int(subset.establecimientos_terciarios.eq(0).sum()),
        })
    trip_rows = audit["trip_rows"]
    report = {
        "schema_version": VERSION, "contract_id": audit["contract_id"],
        "notebook": "02_EDA_y_Equidad.ipynb", "configuration": CONFIG,
        "sample_accounting": {
            **trip_rows,
            "retention_percent": 100 * trip_rows["accepted_rows"] / trip_rows["input_rows"],
            "known_withdrawal_events": float(stations.viajes_retiro_anio.sum()),
            "known_arrival_events": float(stations.viajes_arribo_anio.sum()),
            "endpoint_activity_trip_equivalents": float(y.sum() * 365),
            "activity_is_latent_demand": False,
            "catalog_feed_updated_at": audit["stations"]["feed_last_updated"],
        },
        "target_metrics": {
            "n_stations": len(y), "mean_daily_activity": float(y.mean()),
            "median_daily_activity": float(np.median(y)), "q1": float(q1), "q3": float(q3),
            "upper_fence": float(q3 + CONFIG["iqr_multiplier"] * (q3 - q1)),
            "p85": p85, "calendar_denominator_days": 365,
        },
        "spatial_equity": {
            "total_agebs": len(agebs), "agebs_with_internal_station": len(agebs) - len(unserved),
            "agebs_without_internal_station": len(unserved),
            "gini_stations": gini_st, "gini_activity": gini_activity,
            "gini_unit": "equal-weight AGEB polygons; raw counts, not per capita",
            "population_access_equity_measured": False,
        },
        "spatial_autocorrelation": {
            **moran, "weights": "directed K-NN; row-standardized; zero diagonal",
            "k": CONFIG["moran_k"], "coordinate_crs": CONFIG["metric_crs"],
            "unit": "stations", "local_significance_tested": False,
            "quadrant_counts": stations.moran_quadrant.value_counts().to_dict(),
            "eighth_neighbor_distance_m_quantiles": np.quantile(
                eighth_distances, [0, 0.5, 0.95, 1]).tolist(),
            "sensitivity": sensitivity,
        },
        "territorial_gap": {
            "unit": "unweighted AGEB centroid to nearest current catalog station",
            "median_km": float(unserved.dist_centroide_red_km.median()),
            "mean_km": float(unserved.dist_centroide_red_km.mean()),
            "p75_km": float(unserved.dist_centroide_red_km.quantile(0.75)),
            "centroids_outside_own_polygon": int((~unserved.centroid_within_polygon).sum()),
            "no_internal_station_but_centroid_within_400m": int(
                unserved.dist_centroide_red_km.le(CONFIG["diagnostic_access_radius_m"] / 1000).sum()),
            "continuous_expansion_impossibility_established": False,
        },
        "denue_retrospective_proxy": {**denue_info, "open_band_sensitivity": employment_sensitivity},
        "gtfs_proximity": gtfs_info,
        "correlations": correlations.to_dict("records"),
        "uncertainty": {
            "iid_p_values": "reference only; spatial/station independence is not established",
            "intervals": "percentile bootstrap resampling AGEB groups with replacement",
            "remaining_limitation": "between-AGEB spatial dependence is not removed by this bootstrap",
        },
        "golden_cluster": {
            "n_stations": len(golden), "n_unique_agebs": len(golden_agebs),
            "ageb_ids": sorted(golden_agebs.cvegeo.tolist()),
            "golden_neighbor_median_m": float(np.median(golden_nn[:, 1])),
            "network_neighbor_median_m": float(np.median(network_nn[:, 1])),
            "cannibalization_identified": False, "optimal_spacing_identified": False,
            "ageb_pca_weighting": "not decided by EDA; station and AGEB weighting differ",
        },
        "leakage_audit": {
            "turnover_ratio_spearman": turnover_rho, "n_valid_capacity": int(capacity_valid.sum()),
            "n_undefined_turnover": int((~capacity_valid).sum()),
            "undefined_turnover_station_ids": env.loc[~capacity_valid, "ce_id"].tolist(),
            "undefined_turnover_reason": "catalog capacity missing or nonpositive; station retained elsewhere",
            "turnover_ratio_definition": "2 * daily_activity / catalog_capacity",
            "turnover_ratio_predictor_eligible": False,
            "pagerank_empirically_measured_here": False,
            "same_period_od_centrality_predictor_eligible": False,
            "models_trained": False,
        },
        "feature_coverage": coverage_rows,
        "pending_validation": [
            "Population-weighted and walking-network accessibility, social equity covariates",
            "Monthly/hourly activity and Golden stability; withdrawals versus arrivals",
            "Spatial blocks/buffers, temporal eligibility and fold-local PCA/centroids",
            "Remove held-out observed flows before graph backtesting",
            "Physical connectivity and greedy baselines before graph/genetic comparisons",
        ],
    }
    return {
        "report": report, "stations": stations, "environment": env, "agebs": agebs,
        "golden_agebs": golden_agebs, "golden_stations": golden,
        "correlations": correlations, "moran_sensitivity": pd.DataFrame(sensitivity),
        "employment_sensitivity": pd.DataFrame(employment_sensitivity),
        "feature_coverage": pd.DataFrame(coverage_rows),
        "lorenz_x": lorenz_x, "lorenz_y": lorenz_y,
        "golden_nn_m": golden_nn[:, 1], "network_nn_m": network_nn[:, 1],
        "weights": weights,
    }


def analysis_identity(v3, contract_id):
    sources = ["eda02_analysis.py", "eda02_content.py", "build_notebook_02.py",
               "eda02_publication.py"]
    code_hashes = {name: file_hash(Path(v3) / "src" / name) for name in sources}
    identity = {
        "contract_id": contract_id, "configuration": CONFIG, "code_hashes": code_hashes,
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "pandas": pd.__version__, "geopandas": gpd.__version__,
                     "scipy": scipy.__version__},
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), identity
