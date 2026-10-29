"""Additive urban diagnostics; the original EDA calculations remain unchanged."""
import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

from V3.src.eda02_analysis import (
    INPUTS, analysis_identity, file_hash, observed_correlations,
)
from V3.src.enterprise_etl import station_lists

URBAN_VERSION = "v3-eda-urban-1"
URBAN_CONFIG = {
    "study_year": 2025,
    "local_timezone": "America/Mexico_City",
    "trip_batch_rows": 250000,
    "day_types": {"weekday": "Monday-Friday, including holidays",
                  "weekend": "Saturday-Sunday"},
    "temporal_cohort": "accepted trips plus valid known endpoint fractions from quarantine",
    "conservation_atol": 1e-5,
    "modal_agencies": {
        "dist_transporte_pesado_m": ["METRO", "MB"],
        "dist_transporte_ligero_m": ["RTP", "TROLE"],
    },
    "modal_service_filter": "has_2025_service; not proof of historical stop position",
    "census_year": 2020,
    "population_variable": "POBTOT",
}


def input_specifications(contract):
    inputs = {name: f"data/processed/{contract}/{name}.parquet" for name in INPUTS}
    for name in ["censo_ageb_2020", "station_aliases"]:
        inputs[name] = f"data/processed/{contract}/{name}.parquet"
    for month in range(1, 13):
        name = f"viajes_2025-{month:02}"
        inputs[name] = f"data/processed/{contract}/{name}.parquet"
        inputs["quarantine_" + name] = f"data/quarantine/{contract}/{name}.parquet"
    return inputs


def enriched_analysis_identity(v3, contract):
    _, identity = analysis_identity(v3, contract)
    identity["urban_enrichment_version"] = URBAN_VERSION
    identity["urban_configuration"] = URBAN_CONFIG
    identity["versions"]["pyarrow"] = pa.__version__
    for name in ["eda02_urban.py", "eda02_urban_content.py"]:
        identity["code_hashes"][name] = file_hash(v3 / "src" / name)
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), identity


def local_hour_buckets(timestamps, weights):
    timestamps = pd.to_datetime(timestamps)
    if timestamps.dt.tz is None:
        raise ValueError("Endpoint timestamps must have an explicit timezone")
    local = timestamps.dt.tz_convert(URBAN_CONFIG["local_timezone"])
    weights = np.asarray(weights, dtype=float)
    if (weights < 0).any() or not np.isfinite(weights).all():
        raise ValueError("Endpoint weights must be finite and nonnegative")
    selected = weights > 0
    if local.loc[selected].isna().any() or local.loc[selected].dt.year.ne(2025).any():
        raise ValueError("Counted endpoints must have a valid local 2025 timestamp")
    day_type = local.loc[selected].dt.dayofweek.ge(5).astype(int).to_numpy()
    hour = local.loc[selected].dt.hour.to_numpy()
    return np.bincount(day_type * 24 + hour, weights=weights[selected],
                       minlength=48).reshape(2, 24)


def quarantine_endpoint_weights(frame, role, known_codes):
    column = "Ciclo_Estacion_Retiro" if role == "retiros" else "Ciclo_EstacionArribo"
    codes, ids_valid = station_lists(frame[column])
    valid = frame["is_valid_2025_" + role].fillna(False) & ids_valid
    fractions = codes.map(
        lambda values: sum(value in known_codes for value in values) / len(values)
        if values else 0.0).to_numpy(dtype=float)
    return fractions * valid.to_numpy(dtype=bool)


def hourly_profile(data):
    v3, contract = data["v3"], data["audit"]["contract_id"]
    processed = v3 / "data/processed" / contract
    quarantine = v3 / "data/quarantine" / contract
    aliases = pd.read_parquet(processed / "station_aliases.parquet", columns=["station_code"])
    known_codes = set(aliases.station_code)
    counts = {role: np.zeros((2, 24), dtype=float) for role in ["retiros", "arribos"]}
    accepted_rows, quarantine_rows = 0, 0
    for month in range(1, 13):
        name = f"viajes_2025-{month:02}.parquet"
        for batch in pq.ParquetFile(processed / name).iter_batches(
                batch_size=URBAN_CONFIG["trip_batch_rows"], columns=["ts_retiros", "ts_arribos"]):
            frame = batch.to_pandas()
            accepted_rows += len(frame)
            for role in counts:
                counts[role] += local_hour_buckets(frame["ts_" + role], np.ones(len(frame)))
        columns = [
            "ts_retiros", "ts_arribos", "is_valid_2025_retiros", "is_valid_2025_arribos",
            "Ciclo_Estacion_Retiro", "Ciclo_EstacionArribo",
        ]
        for batch in pq.ParquetFile(quarantine / name).iter_batches(
                batch_size=URBAN_CONFIG["trip_batch_rows"], columns=columns):
            frame = batch.to_pandas()
            quarantine_rows += len(frame)
            for role in counts:
                weights = quarantine_endpoint_weights(frame, role, known_codes)
                counts[role] += local_hour_buckets(frame["ts_" + role], weights)
    audit = data["audit"]
    if (accepted_rows != audit["trip_rows"]["accepted_rows"]
            or quarantine_rows != audit["trip_rows"]["quarantine_rows"]):
        raise ValueError("Temporal input-row accounting does not match ETL")
    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    n_days = [int((dates.dayofweek < 5).sum()), int((dates.dayofweek >= 5).sum())]
    rows, diagnostics = [], {}
    for role, source_column in [("retiros", "viajes_retiro_anio"),
                                ("arribos", "viajes_arribo_anio")]:
        expected = float(data["frames"]["actividad_estaciones"][source_column].sum())
        if not np.isclose(counts[role].sum(), expected, rtol=0,
                          atol=URBAN_CONFIG["conservation_atol"]):
            raise ValueError(f"Hourly {role} counts do not conserve ETL activity")
        diagnostics[role + "_known_endpoint_weight"] = float(counts[role].sum())
        for index, day_type in enumerate(["weekday", "weekend"]):
            rate = counts[role][index] / n_days[index]
            diagnostics[f"{role}_{day_type}_peak_hour"] = int(np.argmax(rate))
            diagnostics[f"{role}_{day_type}_top_three_hours"] = [
                int(i) for i in np.argsort(-rate, kind="stable")[:3]
            ]
            for hour in range(24):
                rows.append({
                    "role": role, "day_type": day_type, "hour_local": hour,
                    "weighted_events": float(counts[role][index, hour]),
                    "calendar_days": n_days[index],
                    "events_per_calendar_day_at_hour": float(rate[hour]),
                })
    diagnostics.update({
        "calendar_weekdays": n_days[0], "calendar_weekend_days": n_days[1],
        "accepted_trip_rows": accepted_rows, "quarantine_trip_rows": quarantine_rows,
        "timezone": URBAN_CONFIG["local_timezone"],
        "cohort": URBAN_CONFIG["temporal_cohort"],
        "trip_purpose_identified": False,
        "holidays_excluded_from_weekdays": False,
        "endpoint_day_type_uses_each_endpoint_own_date": True,
    })
    return pd.DataFrame(rows), diagnostics


def census_population(census, agebs):
    if not census.cvegeo.is_unique or not agebs.cvegeo.is_unique:
        raise ValueError("Population join requires unique AGEB keys")
    if not census.nivel_geografico.eq("ageb").all():
        raise ValueError("Population requires AGEB totals, not manzana or higher-level sums")
    population = census[["cvegeo", "POBTOT"]].rename(
        columns={"POBTOT": "POBTOT_censo2020"})
    if population.POBTOT_censo2020.dropna().lt(0).any():
        raise ValueError("Population cannot be negative")
    joined = agebs.merge(population, on="cvegeo", how="left",
                        validate="one_to_one", indicator="census_join")
    joined["POBTOT_censo2020"] = joined.POBTOT_censo2020.astype("Int64")
    joined["population_known"] = joined.POBTOT_censo2020.notna()
    rows = []
    for name, mask in [
        ("with_internal_station", joined.n_estaciones.gt(0)),
        ("without_internal_station", joined.n_estaciones.eq(0)),
        ("all_polygons", np.ones(len(joined), dtype=bool)),
    ]:
        subset = joined.loc[mask]
        total = subset.POBTOT_censo2020.sum(min_count=1)
        rows.append({
            "cohort": name, "n_agebs": len(subset),
            "population_known_agebs": int(subset.population_known.sum()),
            "population_unknown_agebs": int((~subset.population_known).sum()),
            "population_total_known": None if pd.isna(total) else int(total),
            "rural_agebs": int(subset.tipo_ageb.eq("rural").sum()),
        })
    summary = pd.DataFrame(rows)
    unserved = rows[1]
    diagnostics = {
        "census_year": 2020, "variable": "POBTOT", "join": "unique cvegeo, AGEB totals",
        "population_without_internal_station_known": unserved["population_total_known"],
        "agebs_without_internal_station": unserved["n_agebs"],
        "unknown_population_without_internal_station_agebs": unserved["population_unknown_agebs"],
        "known_population_is_complete_for_all_polygons": unserved["population_unknown_agebs"] == 0,
        "census_keys_without_geometry": int((~census.cvegeo.isin(agebs.cvegeo)).sum()),
        "walking_access_measured": False, "population_updated_to_2025": False,
    }
    return joined, summary, diagnostics


def modal_proximity(frames, environment):
    links = frames["gtfs_stop_times"][["trip_id", "stop_id"]].merge(
        frames["gtfs_trips"][["trip_id", "route_id", "service_id"]],
        on="trip_id", validate="many_to_one").merge(
        frames["gtfs_routes"][["route_id", "agency_id"]],
        on="route_id", validate="many_to_one").merge(
        frames["gtfs_calendar"][["service_id", "has_2025_service"]],
        on="service_id", validate="many_to_one")
    eligible = links.loc[links.has_2025_service]
    coords = np.c_[environment.geometry.x, environment.geometry.y]
    enriched, groups, sets = environment.copy(), {}, {}
    stops = frames["gtfs_stops"]
    for column, agencies in URBAN_CONFIG["modal_agencies"].items():
        ids = set(eligible.loc[eligible.agency_id.isin(agencies), "stop_id"])
        selected = stops.loc[stops.stop_id.isin(ids)]
        if selected.empty:
            raise ValueError(f"No eligible stops for {column}; distance cannot be imputed")
        stops_m = gpd.GeoDataFrame(
            selected, geometry=gpd.points_from_xy(selected.stop_lon, selected.stop_lat),
            crs="EPSG:4326").to_crs(environment.crs)
        distances, neighbors = cKDTree(
            np.c_[stops_m.geometry.x, stops_m.geometry.y]).query(coords)
        enriched[column] = distances
        enriched[column + "_nearest_stop_id"] = selected.iloc[neighbors].stop_id.to_numpy()
        sets[column] = ids
        groups[column] = {"agencies": agencies, "eligible_stop_ids": len(ids)}
    correlations = observed_correlations(
        enriched, {column: "identity" for column in URBAN_CONFIG["modal_agencies"]})
    diagnostics = {
        "groups": groups, "calendar_filter": URBAN_CONFIG["modal_service_filter"],
        "group_names_are_operational_not_vehicle_weight_classification": True,
        "stop_ids_shared_between_groups": len(set.intersection(*sets.values())),
        "correlations": correlations.to_dict("records"),
        "causal_impact_on_adoption_identified": False,
        "unit": "observed stations; annual activity, not individual adoption",
    }
    return enriched, correlations, diagnostics
