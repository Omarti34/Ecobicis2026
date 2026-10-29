"""Feature definitions and the descriptive, shared PCA space for notebook 03."""
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
from scipy.spatial import cKDTree
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_is_fitted

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import EMPLOYMENT_MIDPOINTS, OPEN_BAND, file_hash
from V3.src.eda02_publication import verify_report as verify_eda_report

VERSION = "v3-features-2"
CONFIG = {
    "metric_crs": "EPSG:32614",
    "buffer_radius_m": 500,
    "candidate_area_threshold": 0.15,
    "sensitivity_radii_m": [300, 400, 500, 800],
    "sensitivity_area_thresholds": [0.05, 0.15, 0.30],
    "tertiary_scian_sectors": [
        "43", "46", "48", "49", "51", "52", "53", "54", "55", "56",
        "61", "62", "71", "72", "81", "93",
    ],
    "registration_last_year": 2025,
    "open_employment_band_reference": 300,
    "metro_metrobus_agencies": ["METRO", "MB"],
    "cycle_operational_status": "En operacion",
    "variance_target": 0.80,
    "seed": 42,
    "fit_scope": "descriptive_transductive; not an inductive backtest",
    "coverage_tolerance": 1e-10,
}
FEATURE_NAMES = [
    "densidad_pob_km2", "POBTOT", "pct_edad_productiva", "pct_jovenes_18_24",
    "pct_adultos_mayores", "grado_escolar_prom", "tasa_ocupacion",
    "pct_viviendas_internet", "pct_viviendas_bici", "pct_viviendas_auto",
    "establecimientos_km2", "empleo_proxy_km2", "share_oficinas", "share_comercio",
    "share_alimentos", "share_educacion_salud", "ciclovia_km_km2",
    "dist_metro_metrobus_m",
]
LOG_TRANSFORMS = [
    "densidad_pob_km2", "POBTOT", "establecimientos_km2", "empleo_proxy_km2",
    "ciclovia_km_km2", "dist_metro_metrobus_m",
]
RATE_DEFINITIONS = {
    "pct_edad_productiva": ("POB15_64", "POBTOT"),
    "pct_jovenes_18_24": ("P_18A24", "POBTOT"),
    "pct_adultos_mayores": ("P_60YMAS", "POBTOT"),
    "tasa_ocupacion": ("POCUPADA", "PEA"),
    "pct_viviendas_internet": ("VPH_INTER", "TVIVHAB"),
    "pct_viviendas_bici": ("VPH_BICI", "TVIVHAB"),
    "pct_viviendas_auto": ("VPH_AUTOM", "TVIVHAB"),
}
IMPUTABLE_FEATURES = list(RATE_DEFINITIONS)
INPUT_COLUMNS = FEATURE_NAMES + ["TVIVHAB", "PEA"]
CENSUS_COLUMNS = [
    "POBTOT", "POB15_64", "P_18A24", "P_60YMAS", "GRAPROES", "PEA",
    "POCUPADA", "TVIVHAB", "VPH_BICI", "VPH_AUTOM", "VPH_INTER",
]
INPUTS = [
    "agebs", "estaciones", "censo_ageb_2020", "denue", "gtfs_stops",
    "gtfs_stop_times", "gtfs_trips", "gtfs_routes", "gtfs_calendar",
    "gtfs_agency", "ciclovias_capa_06",
]


class FeatureContractTransformer(TransformerMixin, BaseEstimator):
    """Validate raw features/denominators and apply the fixed log transforms.

    Denominators are required at inference too: an undefined residential rate
    must not silently become an average residential profile.
    """

    def fit(self, X, y=None):
        prepared = self._prepare(X)
        if prepared.isna().all().any():
            raise ValueError("An entire training feature is missing")
        self.feature_names_in_ = np.asarray(INPUT_COLUMNS, dtype=object)
        self.n_features_in_ = len(INPUT_COLUMNS)
        self.is_fitted_ = True
        return self

    def transform(self, X):
        check_is_fitted(self, "is_fitted_")
        return self._prepare(X)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "is_fitted_")
        return np.asarray(FEATURE_NAMES, dtype=object)

    @staticmethod
    def _prepare(X):
        if not isinstance(X, pd.DataFrame):
            raise ValueError("Pipeline input must be a named pandas DataFrame")
        missing = set(INPUT_COLUMNS) - set(X.columns)
        if missing or X.columns.duplicated().any():
            raise ValueError(f"Missing/duplicate input columns: {sorted(missing)}")
        values = X[INPUT_COLUMNS].astype(float)
        for denominator in ["POBTOT", "TVIVHAB", "PEA"]:
            if not (np.isfinite(values[denominator]) & values[denominator].gt(0)).all():
                raise ValueError(f"Undefined residential denominator: {denominator}")
        features = values[FEATURE_NAMES].copy()
        if np.isinf(features.to_numpy()).any() or features.lt(0).any().any():
            raise ValueError("Features must be nonnegative and cannot be infinite")
        required = [name for name in FEATURE_NAMES if name not in IMPUTABLE_FEATURES]
        if features[required].isna().any().any():
            raise ValueError("Missing non-imputable feature")
        for name in IMPUTABLE_FEATURES + [
                "share_oficinas", "share_comercio", "share_alimentos",
                "share_educacion_salud"]:
            if features[name].dropna().gt(1).any():
                raise ValueError(f"Fraction outside [0, 1]: {name}")
        sector_shares = features[[
            "share_oficinas", "share_comercio", "share_alimentos",
            "share_educacion_salud",
        ]].sum(axis=1)
        if sector_shares.gt(1 + 1e-12).any():
            raise ValueError("Disjoint sector shares cannot sum above one")
        for name in LOG_TRANSFORMS:
            features[name] = np.log1p(features[name])
        return features


def build_pipeline():
    """Fresh instance; notebook 04 must fit one inside each training fold."""
    return Pipeline([
        ("features", FeatureContractTransformer()),
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("pca", PCA(n_components=CONFIG["variance_target"], svd_solver="full",
                    random_state=CONFIG["seed"])),
    ])


def load_inputs(v3):
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    root = v3 / "data/processed" / audit["contract_id"]
    eda_pointer = v3 / "audits/02_eda.json"
    pointer_bytes = eda_pointer.read_bytes()
    eda = json.loads(pointer_bytes)
    if eda["contract_id"] != audit["contract_id"]:
        raise ValueError("Golden reference belongs to another ETL contract")
    eda_path = v3 / "data/eda" / eda["contract_id"] / eda["analysis_id"] / "report.json"
    committed_eda = verify_eda_report(v3, eda_path)
    if eda != committed_eda or eda_pointer.read_bytes() != pointer_bytes:
        raise ValueError("EDA pointer is not the verified report or changed during reading")
    frames, records = {}, {}
    for name in INPUTS:
        path = root / f"{name}.parquet"
        frames[name] = (gpd.read_parquet if name in ["agebs", "ciclovias_capa_06"]
                        else pd.read_parquet)(path)
        matches = [record for record in audit["outputs"]
                   if record["path"] == path.relative_to(v3).as_posix()]
        if len(matches) != 1:
            raise ValueError(f"ETL input must be registered exactly once: {name}")
        records[name] = {key: matches[0][key] for key in ["path", "bytes", "sha256"]}
    data = {
        "v3": v3, "audit": audit, "eda": eda, "frames": frames,
        "input_artifacts": records, "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(pointer_bytes).hexdigest(),
        "eda_report_path": eda_path.relative_to(v3).as_posix(),
    }
    data["analysis_id"], data["analysis_identity"] = analysis_identity(v3, data)
    return data


def analysis_identity(v3, data):
    identity = {
        "schema_version": VERSION, "contract_id": data["audit"]["contract_id"],
        "configuration": CONFIG, "feature_names": FEATURE_NAMES,
        "input_columns": INPUT_COLUMNS, "log_transforms": LOG_TRANSFORMS,
        "imputable_features": IMPUTABLE_FEATURES,
        "input_artifacts": data["input_artifacts"],
        "etl_audit_sha256": data["etl_audit_sha256"],
        "eda_audit_sha256": data["eda_audit_sha256"],
        "eda_analysis_id": data["eda"]["analysis_id"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "fe03_analysis.py", "fe03_publication.py", "fe03_content.py",
                "build_notebook_03.py", "eda02_analysis.py", "eda02_publication.py",
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


def coverage(agebs, stations, golden_ids):
    agebs = agebs.to_crs(CONFIG["metric_crs"]).copy()
    if not agebs.cvegeo.is_unique:
        raise ValueError("AGEB keys must be unique")
    if (agebs.geometry.isna().any() or agebs.geometry.is_empty.any()
            or not agebs.geometry.is_valid.all()):
        raise ValueError("AGEB geometry must be present, nonempty and valid")
    if not set(golden_ids).issubset(set(agebs.cvegeo)):
        raise ValueError("Golden reference contains missing AGEBs")
    if (agebs.geometry.area <= 0).any():
        raise ValueError("AGEB area must be positive")
    stations = stations.to_crs(agebs.crs)
    area = agebs.geometry.area
    rows = []
    for radius in CONFIG["sensitivity_radii_m"]:
        union = stations.geometry.buffer(radius).union_all()
        fractions = agebs.geometry.intersection(union).area / area
        tolerance = CONFIG["coverage_tolerance"]
        if ((fractions < -tolerance) | (fractions > 1 + tolerance)).any():
            raise ValueError("Coverage outside geometric bounds")
        fractions = fractions.clip(0, 1)
        for threshold in CONFIG["sensitivity_area_thresholds"]:
            candidates = fractions.lt(threshold)
            rows.append({
                "radius_m": radius, "area_threshold": threshold,
                "candidate_count": int(candidates.sum()),
                "candidate_ageb_share": float(candidates.mean()),
                "candidate_area_share": float(area[candidates].sum() / area.sum()),
            })
        if radius == CONFIG["buffer_radius_m"]:
            agebs["fraccion_cobertura"] = fractions
            buffer_area_km2 = float(union.area / 1e6)
    agebs["area_km2"] = area / 1e6
    agebs["is_candidata_territorial"] = agebs.fraccion_cobertura.lt(
        CONFIG["candidate_area_threshold"])
    agebs["is_golden_cluster"] = agebs.cvegeo.isin(golden_ids)
    return agebs, pd.DataFrame(rows), buffer_area_km2


def tertiary_environment(denue, keys):
    if not denue.id.is_unique:
        raise ValueError("DENUE establishment IDs must be unique")
    dates = denue.fecha_alta_parsed
    sector = denue.codigo_act.astype("string").str[:2]
    registered = dates.notna() & dates.dt.year.le(CONFIG["registration_last_year"])
    tertiary = sector.isin(CONFIG["tertiary_scian_sectors"])
    selected = denue.loc[registered & tertiary].copy()
    selected["emp_proxy"] = selected.per_ocu.map({
        **EMPLOYMENT_MIDPOINTS, OPEN_BAND: CONFIG["open_employment_band_reference"],
    }).astype(float)
    if selected.emp_proxy.isna().any():
        raise ValueError("Unknown DENUE employment band; no silent default")
    selected_sector = selected.codigo_act.astype("string").str[:2]
    for name, sectors in {
        "oficinas": ["51", "52", "53", "54", "55", "56"],
        "comercio": ["43", "46"], "alimentos": ["72"],
        "educ_salud": ["61", "62"],
    }.items():
        selected[name] = selected_sector.isin(sectors)
    matched = selected.loc[selected.cvegeo.isin(keys)]
    totals = matched.groupby("cvegeo").agg(
        establecimientos=("id", "size"), empleo_proxy=("emp_proxy", "sum"),
        oficinas=("oficinas", "sum"), comercio=("comercio", "sum"),
        alimentos=("alimentos", "sum"), educ_salud=("educ_salud", "sum"),
    ).reindex(keys, fill_value=0).rename_axis("cvegeo").reset_index()
    return totals, {
        "input_records": len(denue), "selected_tertiary_records": len(selected),
        "matched_tertiary_records": len(matched),
        "selected_without_geometry": len(selected) - len(matched),
        "registration_after_2025": int(dates.dt.year.gt(2025).sum()),
        "registration_unknown_excluded": int(dates.isna().sum()),
        "nontertiary_known_registration_through_2025_excluded": int(
            (registered & ~tertiary).sum()),
        "open_band_selected_records": int(selected.per_ocu.eq(OPEN_BAND).sum()),
        "open_band_assumed_employees": CONFIG["open_employment_band_reference"],
        "snapshot_years": sorted(int(x) for x in denue.snapshot_year.dropna().unique()),
        "historical_2025_stock_reconstructed": False,
        "zero_semantics": "no matched eligible establishment; not zero jobs in 2025",
    }


def metro_metrobus_proximity(frames, agebs):
    links = frames["gtfs_stop_times"][["stop_id", "trip_id"]].merge(
        frames["gtfs_trips"][["trip_id", "route_id", "service_id"]],
        on="trip_id", validate="many_to_one").merge(
        frames["gtfs_routes"][["route_id", "agency_id"]],
        on="route_id", validate="many_to_one").merge(
        frames["gtfs_calendar"][["service_id", "has_2025_service"]],
        on="service_id", validate="many_to_one")
    selected = links.loc[
        links.has_2025_service.fillna(False)
        & links.agency_id.isin(CONFIG["metro_metrobus_agencies"]),
        ["stop_id", "agency_id"],
    ].drop_duplicates()
    agencies = selected.groupby("stop_id").agency_id.agg(
        lambda values: "|".join(sorted(set(values))))
    stops = frames["gtfs_stops"]
    if not stops.stop_id.is_unique:
        raise ValueError("GTFS stop IDs must be unique")
    stops = stops.loc[stops.stop_id.isin(agencies.index)].copy()
    if stops.empty:
        raise ValueError("No Metro/Metrobus stops eligible; distance cannot be zero-imputed")
    points = gpd.GeoDataFrame(
        stops, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat),
        crs="EPSG:4326").to_crs(agebs.crs)
    centroids = agebs.geometry.centroid
    distances, neighbors = cKDTree(
        np.c_[points.geometry.x, points.geometry.y]).query(
        np.c_[centroids.x, centroids.y])
    nearest_ids = stops.iloc[neighbors].stop_id.to_numpy()
    result = pd.DataFrame({
        "cvegeo": agebs.cvegeo.to_numpy(), "dist_metro_metrobus_m": distances,
        "nearest_metro_metrobus_stop_id": nearest_ids,
        "nearest_metro_metrobus_agencies": pd.Series(nearest_ids).map(agencies).to_numpy(),
        "centroid_within_polygon": agebs.geometry.covers(centroids).to_numpy(),
    })
    return result, {
        "agencies": CONFIG["metro_metrobus_agencies"],
        "eligible_unique_stop_ids": len(stops),
        "stop_ids_by_agency": selected.groupby("agency_id").stop_id.nunique().to_dict(),
        "calendar_rule": "has_2025_service; declared coverage, not observed service",
        "distance_method": "AGEB centroid to eligible stop; Euclidean in EPSG:32614",
        "centroids_outside_polygon": int((~result.centroid_within_polygon).sum()),
        "historical_stop_positions_reconstructed": False,
        "walking_access_measured": False,
    }


def operational_cycle_lengths(cycle, agebs):
    cycle = cycle.to_crs(agebs.crs)
    active = cycle.ESTADO.astype("string").str.strip().eq(
        CONFIG["cycle_operational_status"]).fillna(False)
    selected = cycle.loc[active]
    intersections = gpd.overlay(
        agebs[["cvegeo", "geometry"]], selected[["geometry"]],
        how="intersection", keep_geom_type=False)
    lines = intersections.loc[
        intersections.geom_type.isin(["LineString", "MultiLineString"])].copy()
    lines["ciclovia_km"] = lines.length / 1000
    totals = lines.groupby("cvegeo").ciclovia_km.sum().reindex(
        agebs.cvegeo, fill_value=0).rename_axis("cvegeo").reset_index()
    return totals, {
        "input_segments": len(cycle), "included_segments": int(active.sum()),
        "excluded_segments": int((~active).sum()),
        "included_status": CONFIG["cycle_operational_status"],
        "excluded_status_counts": cycle.loc[~active, "ESTADO"].fillna(
            "unknown").value_counts().to_dict(),
        "included_typologies": selected.TIPO_IC.value_counts().to_dict(),
        "length_inside_agebs_km": float(totals.ciclovia_km.sum()),
        "segregated_infrastructure_only": False,
        "operation_verified_in_field": False,
    }


def feature_matrix(data):
    frames = data["frames"]
    station_source = frames["estaciones"]
    if not station_source.ce_id.is_unique:
        raise ValueError("Physical station IDs must be unique")
    stations = gpd.GeoDataFrame(
        station_source, geometry=gpd.points_from_xy(station_source.lon, station_source.lat),
        crs="EPSG:4326")
    golden_ids = data["eda"]["golden_cluster"]["ageb_ids"]
    if len(golden_ids) != len(set(golden_ids)):
        raise ValueError("Golden reference contains duplicate AGEBs")
    agebs, sensitivity, buffer_area = coverage(frames["agebs"], stations, golden_ids)
    census = frames["censo_ageb_2020"]
    if not census.cvegeo.is_unique or not census.nivel_geografico.eq("ageb").all():
        raise ValueError("Census must contain unique AGEB totals only")
    census = census[["cvegeo"] + CENSUS_COLUMNS].copy()
    for name in CENSUS_COLUMNS:
        census[name] = pd.to_numeric(census[name], errors="raise").astype(float)
        if census[name].dropna().lt(0).any():
            raise ValueError(f"Negative census value: {name}")
    economic, denue_info = tertiary_environment(frames["denue"], agebs.cvegeo)
    proximity, gtfs_info = metro_metrobus_proximity(frames, agebs)
    cycling, cycle_info = operational_cycle_lengths(frames["ciclovias_capa_06"], agebs)
    features = agebs[["cvegeo", "tipo_ageb", "nom_mun", "geometry", "area_km2",
                     "fraccion_cobertura", "is_candidata_territorial",
                     "is_golden_cluster"]].merge(
        census, on="cvegeo", how="left", validate="one_to_one").merge(
        economic, on="cvegeo", how="left", validate="one_to_one").merge(
        proximity, on="cvegeo", how="left", validate="one_to_one").merge(
        cycling, on="cvegeo", how="left", validate="one_to_one")
    for name, (numerator, denominator) in RATE_DEFINITIONS.items():
        features[name] = features[numerator] / features[denominator].where(
            features[denominator].gt(0))
    features["grado_escolar_prom"] = features.GRAPROES
    for name, numerator in {
        "densidad_pob_km2": "POBTOT", "establecimientos_km2": "establecimientos",
        "empleo_proxy_km2": "empleo_proxy", "ciclovia_km_km2": "ciclovia_km",
    }.items():
        features[name] = features[numerator] / features.area_km2
    for name, numerator in {
        "share_oficinas": "oficinas", "share_comercio": "comercio",
        "share_alimentos": "alimentos", "share_educacion_salud": "educ_salud",
    }.items():
        # This is a convention for no eligible units, not an observed sector mix.
        features[name] = (features[numerator] / features.establecimientos.where(
            features.establecimientos.gt(0))).fillna(0)
    features["sector_mix_defined"] = features.establecimientos.gt(0)
    reasons = pd.DataFrame({
        "nonurban": ~features.tipo_ageb.eq("urbana"),
        "population_missing": features.POBTOT.isna(),
        "no_resident_population": features.POBTOT.le(0),
        "schooling_missing": features.GRAPROES.isna(),
        "undefined_household_denominator": ~features.TVIVHAB.gt(0),
        "undefined_labour_denominator": ~features.PEA.gt(0),
    }).fillna(False)
    essential = [name for name in FEATURE_NAMES if name not in IMPUTABLE_FEATURES]
    reasons["nonimputable_feature_missing"] = features[essential].isna().any(axis=1)
    features["is_projectable"] = ~reasons.any(axis=1)
    features["exclusion_reason"] = reasons.apply(
        lambda row: ";".join(row.index[row.to_numpy(bool)]), axis=1)
    features["is_candidata_proyectable"] = (
        features.is_candidata_territorial & features.is_projectable)
    features["is_rural_nan"] = features.tipo_ageb.eq("rural") & features.POBTOT.isna()
    missing = features[FEATURE_NAMES].astype(float).isna()
    features["n_missing_features_raw"] = missing.sum(axis=1)
    features["imputed_features"] = [
        ";".join(missing.columns[row]) if projectable else ""
        for row, projectable in zip(missing.to_numpy(bool), features.is_projectable)
    ]
    for name in IMPUTABLE_FEATURES:
        features[name + "_missing"] = missing[name]
    return features, sensitivity, {
        "denue": denue_info, "gtfs": gtfs_info, "cycling": cycle_info,
        "buffer_area_km2": buffer_area,
        "exclusion_reason_counts_nonexclusive": reasons.sum().astype(int).to_dict(),
        "census_keys_without_geometry": int((~census.cvegeo.isin(agebs.cvegeo)).sum()),
    }


def feature_contract():
    definitions = {
        "densidad_pob_km2": ("Censo 2020 + geometry", "inhabitants/km2", "POBTOT", "area_km2"),
        "POBTOT": ("Censo 2020", "inhabitants", "POBTOT", None),
        "grado_escolar_prom": ("Censo 2020", "school years", "GRAPROES", None),
        "establecimientos_km2": ("eligible tertiary DENUE", "units/km2", "establecimientos", "area_km2"),
        "empleo_proxy_km2": ("eligible tertiary DENUE", "proxy persons/km2", "empleo_proxy", "area_km2"),
        "share_oficinas": ("eligible tertiary DENUE", "fraction", "oficinas", "establecimientos"),
        "share_comercio": ("eligible tertiary DENUE", "fraction", "comercio", "establecimientos"),
        "share_alimentos": ("eligible tertiary DENUE", "fraction", "alimentos", "establecimientos"),
        "share_educacion_salud": ("eligible tertiary DENUE", "fraction", "educ_salud", "establecimientos"),
        "ciclovia_km_km2": ("cycle total layer; En operacion only", "km/km2", "ciclovia_km", "area_km2"),
        "dist_metro_metrobus_m": ("eligible METRO/MB GTFS stops", "Euclidean meters", None, None),
    }
    definitions.update({
        name: ("Censo 2020", "fraction", numerator, denominator)
        for name, (numerator, denominator) in RATE_DEFINITIONS.items()
    })
    return [{
        "name": name, "source": definitions[name][0], "unit": definitions[name][1],
        "numerator": definitions[name][2], "denominator": definitions[name][3],
        "transform": "log1p" if name in LOG_TRANSFORMS else "identity",
        "missing_policy": "median only with applicable positive denominator"
        if name in IMPUTABLE_FEATURES else "must be observed or defined by source convention",
    } for name in FEATURE_NAMES]


def analyze(data):
    features, sensitivity, source_info = feature_matrix(data)
    valid = features.is_projectable
    if valid.sum() <= len(FEATURE_NAMES):
        raise ValueError("Too few eligible rows to fit the descriptive PCA")
    raw = features.loc[valid, INPUT_COLUMNS]
    if raw[FEATURE_NAMES].isna().all().any():
        raise ValueError("An entire feature is missing; cannot preserve the feature contract")
    pipeline = build_pipeline()
    projected = pipeline.fit_transform(raw)
    scaler, pca = pipeline.named_steps["scaler"], pipeline.named_steps["pca"]
    k = pca.n_components_
    pc_names = [f"PC{i + 1}" for i in range(k)]
    if not np.isfinite(projected).all() or not (scaler.var_ > 0).all():
        raise ValueError("Nonfinite scores or a constant feature")
    if not np.allclose(pca.components_ @ pca.components_.T, np.eye(k), atol=1e-10):
        raise ValueError("PCA basis is not orthonormal")
    if not np.allclose(projected, pipeline.transform(raw), rtol=0, atol=1e-10):
        raise ValueError("Fit/transform projection mismatch")
    scores = features[[
        "cvegeo", "is_candidata_territorial", "is_candidata_proyectable",
        "is_golden_cluster", "is_projectable", "is_rural_nan", "exclusion_reason",
        "n_missing_features_raw", "imputed_features",
    ]].copy()
    for i, name in enumerate(pc_names):
        scores[name] = np.nan
        scores.loc[valid, name] = projected[:, i]
    golden_mask = valid & features.is_golden_cluster
    if not golden_mask.any():
        raise ValueError("No projectable Golden reference")
    golden = scores.loc[golden_mask, pc_names].to_numpy(float)
    center = golden.mean(axis=0)
    centroid = pd.DataFrame([dict(zip(pc_names, center))])
    centroid["n_golden_agebs"] = int(golden_mask.sum())
    loadings = pd.DataFrame(pca.components_.T, index=FEATURE_NAMES, columns=pc_names)
    loadings.index.name = "feature"
    imputed_rows = valid & features.n_missing_features_raw.gt(0)
    missing_counts = features.loc[valid, FEATURE_NAMES].isna().sum()
    top = loadings.PC1.abs().sort_values(ascending=False).head(5).index
    report = {
        "schema_version": VERSION, "contract_id": data["audit"]["contract_id"],
        "notebook": "03_Feature_Engineering.ipynb", "configuration": CONFIG,
        "maup_mitigation": {
            "coverage_method": "Euclidean projected buffer; not a walking service area",
            "maup_resolved": False, "buffer_radius_m": CONFIG["buffer_radius_m"],
            "buffer_area_km2": source_info["buffer_area_km2"],
            "pure_candidate_threshold": CONFIG["candidate_area_threshold"],
            "total_agebs": len(features),
            "territorial_candidates_count": int(features.is_candidata_territorial.sum()),
            "projectable_candidates_count": int(features.is_candidata_proyectable.sum()),
            "unprojectable_candidates_count": int(
                (features.is_candidata_territorial & ~valid).sum()),
            "covered_or_consolidated_count": int((~features.is_candidata_territorial).sum()),
            "candidate_ageb_share": float(features.is_candidata_territorial.mean()),
            "candidate_area_share": float(
                features.loc[features.is_candidata_territorial, "area_km2"].sum()
                / features.area_km2.sum()),
            "golden_cluster_agebs_count": int(features.is_golden_cluster.sum()),
            "golden_projected_count": int(golden_mask.sum()),
            "golden_territorial_candidate_overlap": int(
                (features.is_golden_cluster & features.is_candidata_territorial).sum()),
        },
        "source_filters": source_info,
        "feature_matrix": {
            "n_features_raw": len(FEATURE_NAMES), "feature_names": FEATURE_NAMES,
            "input_columns": INPUT_COLUMNS, "feature_contract": feature_contract(),
            "log_transformed_features": LOG_TRANSFORMS,
            "imputable_features": IMPUTABLE_FEATURES,
            "projectable_agebs": int(valid.sum()),
            "unprojectable_agebs": int((~valid).sum()),
            "rural_nans_preserved_count": int(features.is_rural_nan.sum()),
            "imputed_rows": int(imputed_rows.sum()),
            "imputed_candidate_rows": int((imputed_rows & features.is_candidata_territorial).sum()),
            "imputed_golden_rows": int((imputed_rows & features.is_golden_cluster).sum()),
            "imputed_cells": int(missing_counts.sum()),
            "imputed_cells_by_feature": missing_counts.astype(int).to_dict(),
            "operational_target_features_used": False,
            "historical_ex_ante_eligibility_certified": False,
        },
        "pca_reduction": {
            "fit_scope": CONFIG["fit_scope"],
            "k_components_80_pct": int(k),
            "cumulative_variance_explained": float(pca.explained_variance_ratio_.sum()),
            "individual_variance_explained": pca.explained_variance_ratio_.tolist(),
            "loadings_definition": "eigenvector coefficients, not causal effects or correlations",
            "top_pc1_features": top.to_list(),
            "top_pc1_signed_coefficients": loadings.loc[top, "PC1"].to_dict(),
            "pc1_label": "Eje de Equipamiento y Composici\u00f3n Socioecon\u00f3mica Residencial",
            "income_bias_risk": True, "income_measured_directly": False,
            "golden_weighting": "one equal weight per projectable Golden AGEB",
            "golden_cluster_centroid_vector": center.tolist(),
            "whiten": False,
            "imputer_statistics_transformed_scale": pipeline.named_steps[
                "imputer"].statistics_.tolist(),
            "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
        },
        "mathematical_checks": {
            "unique_ageb_keys": bool(features.cvegeo.is_unique),
            "finite_projected_scores": True, "shared_pipeline_for_all_rows": True,
            "orthonormal_components": True, "no_projection_for_ineligible_rows": bool(
                scores.loc[~valid, pc_names].isna().all().all()),
            "rural_scores_remain_missing": bool(
                scores.loc[features.is_rural_nan, pc_names].isna().all().all()),
            "golden_covariance_rank": int(np.linalg.matrix_rank(np.cov(golden, rowvar=False))),
        },
        "pending_validation": [
            "Fold-local preprocessing, Golden selection and centroid for inductive evaluation",
            "Spatial blocks/buffers; GroupKFold alone does not isolate neighboring AGEBs",
            "Ranking sensitivity to imputation, PCA truncation and Golden P85 threshold",
            "Nonresidential candidate representation; exclusions do not mean no potential demand",
            "Physical network connectivity and spatial out-of-domain screening",
            "Historical source availability and equity-versus-similarity objectives",
            "Declared Mahalanobis reference covariance and calibrated domain threshold",
        ],
    }
    return {
        "features": features, "scores": scores, "loadings": loadings,
        "centroid": centroid, "maup_sensitivity": sensitivity,
        "pipeline": pipeline, "report": report,
    }
