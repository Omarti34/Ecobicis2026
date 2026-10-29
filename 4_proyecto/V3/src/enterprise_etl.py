"""Non-destructive V3 ETL. Inputs immutable; outputs committed by audit marker."""
import json
import hashlib
import os
import shutil
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj.exceptions import ProjError
from shapely.errors import GEOSException
from shapely.geometry import shape

from .etl_contract import (
    POLICY, TRIP_COLUMNS, canonical_json, provenance, sha256, verify_manifest, write_json,
)


@contextmanager
def exclusive_lock(path):
    """Never auto-remove another process's lock, including after a crash."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(token)
    try:
        yield
    finally:
        if path.exists() and path.read_text() == token:
            path.unlink()


def text(value):
    return pd.NA if value is None or value is pd.NA else unicodedata.normalize("NFC", str(value)).strip()


def strict_integer(series):
    normalized = series.astype("string").str.strip()
    number = pd.to_numeric(normalized, errors="coerce")
    present = normalized.notna() & normalized.ne("")
    invalid = present & (number.isna() | ~np.isfinite(number) | number.mod(1).ne(0)
                         | number.abs().gt(2**53 - 1))
    return number.mask(invalid).astype("Int64"), invalid.fillna(False)


def update_time(value):
    if value is None or value is pd.NA:
        return pd.NaT
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return pd.to_datetime(float(value), unit="s", utc=True)
        return pd.to_datetime(value, utc=True, errors="coerce")
    except (ValueError, OverflowError, TypeError):
        return pd.NaT


def annotate_records(records, source, manifest):
    rows = []
    for index, original in enumerate(records, start=1):
        row = {key: text(value) if isinstance(value, str) else value for key, value in original.items()}
        row["_raw_record"] = canonical_json(original)
        row["_record_sha256"] = hashlib.sha256(row["_raw_record"].encode("utf-8")).hexdigest()
        row["_source_row"] = index
        rows.append(row)
    frame = provenance(pd.DataFrame(rows), source, manifest)
    frame["_source_row"] = frame["_source_row"].astype("Int64")
    return frame


def split_duplicates(frame, key):
    eligible = frame[key].notna() & frame[key].astype("string").ne("")
    ordered = frame.sort_values(
        [key, "_updated_at", "_record_sha256", "_source_file", "_source_row"],
        kind="mergesort", na_position="first",
    )
    duplicate = ordered[key].duplicated(keep="last") & eligible.reindex(ordered.index)
    rejected = ordered.loc[duplicate].copy()
    rejected["_quarantine_reason"] = "superseded_duplicate"
    return ordered.loc[~duplicate].copy(), rejected


def parquet_safe(frame):
    """Original JSON retains nested/unparseable values; table columns use explicit types."""
    frame = frame.copy()
    for column in frame:
        if frame[column].dtype == object:
            frame[column] = frame[column].map(
                lambda value: canonical_json(value) if isinstance(value, (dict, list)) else text(value)
            ).astype("string")
    return frame


def write_frame(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = parquet_safe(frame)
    if isinstance(frame, gpd.GeoDataFrame):
        frame.to_parquet(path, index=False, compression="zstd")
    else:
        frame.to_parquet(path, index=False, engine="pyarrow", compression="zstd")


def load_stations(v3, manifest):
    relative = "data/raw/ecobici_stations/station_information.json"
    document = json.loads((v3 / relative).read_text(encoding="utf-8"))
    records = document["data"]["stations"]
    if not records:
        raise ValueError("Empty station catalogue")
    frame = annotate_records(records, relative, manifest)
    frame["ce_id"] = frame.get("short_name", pd.Series(pd.NA, index=frame.index)).astype("string")
    id_ok = frame.ce_id.str.fullmatch(r"[0-9]+(?:-[0-9]+)*", na=False)
    frame["ce_aliases"] = frame.ce_id.where(id_ok).map(
        lambda value: canonical_json(list(dict.fromkeys(str(int(part)).zfill(3)
                                                        for part in value.split("-"))))
        if pd.notna(value) else "[]"
    ).astype("string")
    frame["ce_id"] = frame.ce_id.where(id_ok).map(
        lambda value: str(int(value.split("-")[0])).zfill(3) if pd.notna(value) else pd.NA
    ).astype("string")
    feed_update = update_time(document.get("last_updated"))
    frame["_updated_at"] = pd.Series(
        [update_time(row.get("updated_at", row.get("last_updated", document.get("last_updated"))))
         for row in records], dtype="datetime64[ns, UTC]",
    )
    frame["_update_basis"] = pd.Series(
        ["record" if "updated_at" in row or "last_updated" in row else "feed" for row in records],
        dtype="string",
    )
    frame, duplicates = split_duplicates(frame, "ce_id")
    for column in ["lat", "lon"]:
        frame[column] = pd.to_numeric(frame.get(column, pd.Series(pd.NA, index=frame.index)),
                                      errors="coerce").astype("Float64")
    frame["capacity"], capacity_bad = strict_integer(
        frame.get("capacity", pd.Series(pd.NA, index=frame.index)))
    reasons = pd.Series("", index=frame.index, dtype="string")
    rules = {
        "invalid_station_key": frame.ce_id.isna(),
        "missing_or_invalid_coordinates": ~(
            frame.lat.between(-90, 90) & frame.lon.between(-180, 180)
        ).fillna(False),
        "invalid_integer_capacity": capacity_bad | frame.capacity.lt(0).fillna(False),
    }
    for reason, mask in rules.items():
        reasons.loc[mask] += reason + "|"
    invalid = frame.loc[reasons.ne("")].copy()
    invalid["_quarantine_reason"] = reasons.loc[invalid.index].str.rstrip("|")
    accepted = frame.loc[reasons.eq("")].sort_values("ce_id").reset_index(drop=True)
    accepted["catalog_snapshot_outside_2025"] = accepted["_updated_at"].dt.year.ne(2025).fillna(True)
    for column in ["lat", "lon"]:
        duplicates[column] = pd.to_numeric(duplicates[column], errors="coerce").astype("Float64")
    duplicates["capacity"], _ = strict_integer(duplicates["capacity"])
    rejection_parts = [part for part in [duplicates, invalid] if not part.empty]
    rejected = pd.concat(rejection_parts, ignore_index=True) if rejection_parts else invalid.iloc[:0].copy()
    assert len(accepted) + len(rejected) == len(records)
    if not accepted.ce_id.is_unique or accepted.empty:
        raise ValueError("No unique usable station catalogue")
    return accepted, rejected, {
        "input_rows": len(records), "accepted_rows": len(accepted), "quarantine_rows": len(rejected),
        "superseded_duplicates": len(duplicates),
        "feed_last_updated": feed_update.isoformat() if pd.notna(feed_update) else None,
        "snapshot_is_not_2025_active_station_evidence": True,
        "compound_physical_stations": int(accepted.ce_aliases.map(lambda value: len(json.loads(value)) > 1).sum()),
    }


def station_aliases(catalogue):
    aliases = {}
    records = []
    for row in catalogue.itertuples(index=False):
        for alias in json.loads(row.ce_aliases):
            if alias in aliases and aliases[alias] != row.ce_id:
                raise ValueError(f"Ambiguous station alias {alias}; refusing guessed identity")
            aliases[alias] = row.ce_id
            record = catalogue.loc[catalogue.ce_id.eq(row.ce_id)].iloc[0]
            records.append({"station_code": alias, "ce_id": row.ce_id,
                            "_source_file": record["_source_file"],
                            "_processed_at": record["_processed_at"]})
    table = pd.DataFrame(records).sort_values(["station_code", "ce_id"]).reset_index(drop=True)
    for column in ["station_code", "ce_id", "_source_file"]:
        table[column] = table[column].astype("string")
    table["_processed_at"] = table["_processed_at"].astype("datetime64[ns, UTC]")
    return aliases, table


def load_agebs(v3, manifest):
    frames = []
    for name, kind in [("ageb_urbana_cdmx.geojson", "urbana"), ("ageb_rural_cdmx.geojson", "rural")]:
        relative = "data/raw/inegi_ageb/" + name
        document = json.loads((v3 / relative).read_text(encoding="utf-8"))
        features = document["features"]
        rows = []
        for feature in features:
            original = dict(feature.get("properties") or {})
            original["_original_feature"] = feature
            rows.append(original)
        frame = annotate_records(rows, relative, manifest)
        frame["tipo_ageb"] = pd.Series(kind, index=frame.index, dtype="string")
        frame["cvegeo"] = frame.get("cvegeo", pd.Series(pd.NA, index=frame.index)).astype("string")
        frame["_updated_at"] = pd.Series(
            [update_time(row.get("updated_at", row.get("last_updated"))) for row in rows],
            dtype="datetime64[ns, UTC]",
        )
        frame["_update_basis"] = np.where(frame["_updated_at"].notna(), "record", "unavailable")
        geometry, failures, crs_labels = [], [], []
        for feature in features:
            raw_geometry = feature.get("geometry")
            try:
                if not isinstance(raw_geometry, dict):
                    raise ValueError("missing geometry")
                declared = raw_geometry.get("crs", {}).get("properties", {}).get(
                    "name", POLICY["ageb_default_declared_crs"])
                item = shape(raw_geometry)
                if item.is_empty or not item.is_valid or item.geom_type not in {"Polygon", "MultiPolygon"}:
                    raise ValueError("invalid polygon")
                transformed = gpd.GeoSeries([item], crs=declared).to_crs("EPSG:4326").iloc[0]
                if not np.isfinite(transformed.bounds).all():
                    raise ValueError("nonfinite geometry")
                geometry.append(transformed)
                failures.append(False)
                crs_labels.append(declared)
            except (ValueError, TypeError, KeyError, OverflowError, ProjError, GEOSException):
                geometry.append(None)
                failures.append(True)
                crs_labels.append("unusable")
        frame["geometry"] = geometry
        frame["_geometry_invalid"] = failures
        frame["_geometry_source_crs"] = pd.Series(crs_labels, dtype="string")
        frames.append(frame.drop(columns="_original_feature"))
    all_rows = pd.concat(frames, ignore_index=True)
    selected, duplicates = split_duplicates(all_rows, "cvegeo")
    population, population_bad = strict_integer(
        selected.get("pob_total", pd.Series(pd.NA, index=selected.index)))
    selected["pob_total"] = population
    selected["is_rural_nan"] = (selected.tipo_ageb.eq("rural") & population.isna()).astype("boolean")
    valid_key = selected.cvegeo.str.fullmatch(r"[0-9A-Z]{9}", na=False).where(
        selected.tipo_ageb.eq("rural"),
        selected.cvegeo.str.fullmatch(r"[0-9A-Z]{13}", na=False))
    reasons = pd.Series("", index=selected.index, dtype="string")
    for name, mask in {
        "invalid_ageb_key": ~valid_key,
        "corrupt_geometry_or_crs": selected["_geometry_invalid"],
        "invalid_integer_population": population_bad | population.lt(0).fillna(False),
    }.items():
        reasons.loc[mask] += name + "|"
    invalid = selected.loc[reasons.ne("")].copy()
    invalid["_quarantine_reason"] = reasons.loc[invalid.index].str.rstrip("|")
    accepted = gpd.GeoDataFrame(selected.loc[reasons.eq("")].copy(), geometry="geometry", crs="EPSG:4326")
    accepted = accepted.sort_values("cvegeo").reset_index(drop=True)
    accepted["area_km2"] = accepted.to_crs(POLICY["metric_crs"]).area / 1e6
    if accepted.area_km2.le(0).any():
        raise ValueError("Nonpositive polygon area")
    accepted["densidad_pob_km2"] = accepted.pob_total / accepted.area_km2
    rejected = pd.concat([duplicates, invalid], ignore_index=True).drop(columns="geometry")
    assert len(accepted) + len(rejected) == len(all_rows)
    return accepted, rejected, {
        "input_rows": len(all_rows), "accepted_rows": len(accepted), "quarantine_rows": len(rejected),
        "superseded_duplicates": len(duplicates), "rural_nan_rows": int(accepted.is_rural_nan.sum()),
        "population_missing_rows": int(accepted.pob_total.isna().sum()),
        "crs_respects_per_feature_declared_epsg6365": True,
    }


class ChunkWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = None
        self.rows = 0

    def write(self, frame):
        table = pa.Table.from_pandas(frame, preserve_index=False)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, table.schema, compression="zstd",
                                           use_dictionary=False, version="2.6")
        self.writer.write_table(table)
        self.rows += len(frame)

    def close(self):
        if self.writer is not None:
            self.writer.close()


def station_lists(series):
    normalized = series.astype("string").str.strip()
    valid = normalized.str.fullmatch(r"\d+(?:-\d+)*", na=False)
    mapping = {
        value: list(dict.fromkeys(str(int(part)).zfill(3) for part in value.split("-")))
        for value in normalized.loc[valid].unique()
    }
    return normalized.map(mapping).map(lambda value: value if isinstance(value, list) else []), valid


def endpoint(chunk, role):
    suffix = "Retiro" if role == "retiros" else "Arribo"
    column = "Ciclo_Estacion_Retiro" if role == "retiros" else "Ciclo_EstacionArribo"
    parsed = pd.to_datetime(chunk["Fecha_" + suffix], format="%d/%m/%Y", errors="coerce")
    clock = chunk["Hora_" + suffix].str.extract(r"^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")
    parts = clock.apply(pd.to_numeric, errors="coerce")
    time_ok = (parts[0].between(0, 23) & parts[1].between(0, 59) & parts[2].ge(0)
               & parts[2].lt(60)).fillna(False)
    ids, ids_ok = station_lists(chunk[column])
    year_ok = parsed.dt.year.eq(POLICY["year"])
    ts = (parsed + pd.to_timedelta(parts[0].fillna(0), unit="h")
          + pd.to_timedelta(parts[1].fillna(0), unit="m")
          + pd.to_timedelta(parts[2].fillna(0), unit="s"))
    ts = ts.where(year_ok & time_ok).dt.tz_localize("America/Mexico_City")
    valid = year_ok & time_ok & ids_ok
    return ids, valid, ts, {
        "date_invalid": parsed.isna(), "outside_2025": parsed.notna() & ~year_ok,
        "time_invalid": ~time_ok, "station_id_invalid": ~ids_ok,
    }


def process_trips(v3, manifest, catalogue, processed, quarantine):
    keys = catalogue.ce_id.tolist()
    aliases, _ = station_aliases(catalogue)
    known_ids = set(aliases)
    totals = {"retiros": pd.Series(0.0, index=keys), "arribos": pd.Series(0.0, index=keys)}
    quality = []
    for month in range(1, 13):
        relative = f"data/raw/ecobici_trips/2025-{month:02}.csv"
        path = v3 / relative
        columns = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns.tolist()
        if columns != TRIP_COLUMNS:
            raise ValueError(f"Schema drift in {relative}: {columns}")
        writers = {
            "accepted": ChunkWriter(processed / f"viajes_2025-{month:02}.parquet"),
            "quarantine": ChunkWriter(quarantine / f"viajes_2025-{month:02}.parquet"),
            "unknown_events": ChunkWriter(quarantine / f"eventos_sin_catalogo_2025-{month:02}.parquet"),
        }
        count = {"archivo": relative, "input_rows": 0, "accepted_rows": 0, "quarantine_rows": 0,
                 "valid_retiros": 0, "valid_arribos": 0,
                 "known_retiros_weight": 0.0, "known_arribos_weight": 0.0,
                 "unknown_retiros_weight": 0.0, "unknown_arribos_weight": 0.0}
        offset = 0
        try:
            for raw in pd.read_csv(path, dtype="string", encoding="utf-8-sig",
                                   chunksize=POLICY["trip_chunksize"], on_bad_lines="error"):
                raw = raw.reset_index(drop=True)
                chunk = raw.copy()
                for column in chunk:
                    chunk[column] = chunk[column].map(
                        lambda value: text(value) if pd.notna(value) else pd.NA).astype("string")
                chunk["_source_row"] = pd.Series(np.arange(offset + 1, offset + len(chunk) + 1), dtype="Int64")
                offset += len(chunk)
                reasons = pd.Series("", index=chunk.index, dtype="string")
                parsed_age, age_bad = strict_integer(chunk.Edad_Usuario)
                age_bad |= parsed_age.lt(0).fillna(False)
                reasons.loc[age_bad] += "invalid_integer_age|"
                unknown_parts = []
                for role in ["retiros", "arribos"]:
                    ids, valid, ts, failures = endpoint(chunk, role)
                    chunk["ts_" + role] = ts
                    chunk["is_valid_2025_" + role] = valid.astype("boolean")
                    for reason, mask in failures.items():
                        reasons.loc[mask] += role + "_" + reason + "|"
                    outside_catalog = ids.map(lambda values: any(value not in known_ids for value in values))
                    reasons.loc[outside_catalog] += role + "_station_outside_catalog|"
                    selected = valid.loc[valid].index
                    events = pd.DataFrame({
                        "ce_id": ids.loc[selected], "weight": ids.loc[selected].map(lambda value: 1.0 / len(value)),
                        "ts_evento": ts.loc[selected], "_source_row": chunk.loc[selected, "_source_row"],
                    }).explode("ce_id").reset_index(drop=True)
                    events["ce_id"] = events.ce_id.astype("string")
                    events["station_code"] = events.ce_id.copy()
                    events["ce_id"] = events.station_code.map(aliases).fillna(events.station_code).astype("string")
                    events["weight"] = events.weight.astype("Float64")
                    events["_source_row"] = events["_source_row"].astype("Int64")
                    known = events.station_code.isin(known_ids)
                    grouped = events.loc[known].groupby("ce_id").weight.sum()
                    totals[role] = totals[role].add(grouped.astype(float), fill_value=0)
                    unmatched = events.loc[~known].copy()
                    unmatched["rol"] = pd.Series(role, index=unmatched.index, dtype="string")
                    unmatched["_quarantine_reason"] = pd.Series(
                        "station_outside_catalog", index=unmatched.index, dtype="string")
                    unknown_parts.append(provenance(unmatched, relative, manifest))
                    count["valid_" + role] += int(valid.sum())
                    count["known_" + role + "_weight"] += float(events.loc[known, "weight"].sum())
                    count["unknown_" + role + "_weight"] += float(events.loc[~known, "weight"].sum())
                chunk["is_negative_duration"] = (
                    chunk.ts_arribos < chunk.ts_retiros).fillna(False).astype("boolean")
                accepted_mask = reasons.eq("")
                accepted = chunk.loc[accepted_mask].copy()
                accepted["Edad_Usuario"] = parsed_age.loc[accepted.index]
                writers["accepted"].write(provenance(accepted, relative, manifest))
                rejected = chunk.loc[~accepted_mask].copy()
                rejected["_quarantine_reason"] = reasons.loc[rejected.index].str.rstrip("|")
                originals = raw.loc[rejected.index].astype(object).where(raw.loc[rejected.index].notna(), None)
                rejected["_raw_record"] = pd.Series(
                    [canonical_json(row) for row in originals.to_dict("records")],
                    index=rejected.index, dtype="string")
                writers["quarantine"].write(provenance(rejected, relative, manifest))
                writers["unknown_events"].write(pd.concat(unknown_parts, ignore_index=True))
                count["input_rows"] += len(chunk)
                count["accepted_rows"] += len(accepted)
                count["quarantine_rows"] += len(rejected)
        finally:
            for writer in writers.values():
                writer.close()
        if not count["input_rows"]:
            raise ValueError(f"Empty monthly file: {relative}")
        assert count["accepted_rows"] + count["quarantine_rows"] == count["input_rows"]
        for role in ["retiros", "arribos"]:
            if not np.isclose(count["valid_" + role], count["known_" + role + "_weight"]
                              + count["unknown_" + role + "_weight"], rtol=0, atol=1e-5):
                raise ValueError("Endpoint weight conservation failed")
        quality.append(count)
        print(f"{relative}: {count['input_rows']} rows; quarantine {count['quarantine_rows']}", flush=True)
    activity = catalogue.copy()
    for role, column in [("retiros", "viajes_retiro_anio"), ("arribos", "viajes_arribo_anio")]:
        activity[column] = activity.ce_id.map(totals[role]).astype("Float64")
    activity["dias_calendario"] = pd.Series(POLICY["calendar_days"], index=activity.index, dtype="Int64")
    activity["viajes_diarios_prom"] = (
        activity.viajes_retiro_anio + activity.viajes_arribo_anio) / (2 * POLICY["calendar_days"])
    q1, q3 = activity.viajes_diarios_prom.quantile([0.25, 0.75])
    upper = float(q3 + POLICY["outlier_iqr_multiplier"] * (q3 - q1))
    activity["is_outlier_high"] = activity.viajes_diarios_prom.gt(upper).astype("boolean")
    aggregate_sources = canonical_json(
        ["data/raw/ecobici_stations/station_information.json"]
        + [row["archivo"] for row in quality])
    activity = provenance(activity, aggregate_sources, manifest)
    quality_frame = pd.DataFrame(quality)
    integer_columns = ["input_rows", "accepted_rows", "quarantine_rows", "valid_retiros", "valid_arribos"]
    quality_frame[integer_columns] = quality_frame[integer_columns].astype("Int64")
    quality_frame = provenance(quality_frame, quality_frame.archivo.astype("string"), manifest)
    return activity, quality_frame, {"q1": float(q1), "q3": float(q3), "upper_fence": upper,
                                     "outlier_high_rows": int(activity.is_outlier_high.sum())}


def artifact_inventory(folder, v3, target_prefix=None):
    items = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError("Output symlinks not allowed")
        if path.is_file():
            relative = (target_prefix / path.relative_to(folder)).as_posix() if target_prefix else path.relative_to(v3).as_posix()
            items.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return items


def verify_outputs(v3, audit):
    for output in audit["outputs"]:
        path = v3 / output["path"]
        if path.is_symlink() or not path.is_file() or sha256(path) != output["sha256"]:
            raise ValueError(f"Missing or altered committed artifact: {output['path']}")
    for root in audit["generation_directories"]:
        actual = {path.relative_to(v3).as_posix() for path in (v3 / root).rglob("*") if path.is_file()}
        expected = {row["path"] for row in audit["outputs"] if row["path"].startswith(root + "/")}
        if actual != expected:
            raise ValueError("Unexpected/missing files in committed generation")


def publish_directory(staged, destination, v3):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        expected = artifact_inventory(staged, v3, destination.relative_to(v3))
        actual = artifact_inventory(destination, v3)
        if expected != actual:
            raise ValueError("Partial previous publication differs; refusing overwrite")
    else:
        staged.rename(destination)


def run_etl(v3, force_rebuild=False):
    v3 = Path(v3).resolve()
    started = datetime.now(timezone.utc)
    execution_id = uuid.uuid4().hex
    audit_path = v3 / "audits/01_etl.json"
    execution_dir = v3 / "audits/executions"
    execution_dir.mkdir(parents=True, exist_ok=True)
    run_record = {"started_at": started.isoformat(), "execution_id": execution_id}
    try:
        with exclusive_lock(v3 / "audits/.etl.lock"):
            manifest = verify_manifest(v3)
            generation = manifest["contract_id"]
            run_record["contract_id"] = generation
            if audit_path.exists() and not force_rebuild:
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                if audit["contract_id"] != generation:
                    raise ValueError("ETL commit belongs to a different contract")
                verify_outputs(v3, audit)
                run_record["mode"] = "verified_reuse"
                return audit
            processed_root = v3 / "data/processed"
            quarantine_root = v3 / "data/quarantine"
            processed_root.mkdir(parents=True, exist_ok=True)
            quarantine_root.mkdir(parents=True, exist_ok=True)
            staged_p = processed_root / (".staging-" + execution_id)
            staged_q = quarantine_root / (".staging-" + execution_id)
            staged_p.mkdir()
            staged_q.mkdir()
            try:
                stations, stations_dlq, station_audit = load_stations(v3, manifest)
                agebs, agebs_dlq, ageb_audit = load_agebs(v3, manifest)
                write_frame(staged_p / "estaciones.parquet", stations)
                _, alias_table = station_aliases(stations)
                write_frame(staged_p / "station_aliases.parquet", alias_table)
                write_frame(staged_p / "agebs.parquet", agebs)
                write_frame(staged_q / "estaciones.parquet", stations_dlq)
                write_frame(staged_q / "agebs.parquet", agebs_dlq)
                activity, trip_quality, iqr = process_trips(
                    v3, manifest, stations, staged_p, staged_q)
                write_frame(staged_p / "actividad_estaciones.parquet", activity)
                write_frame(staged_p / "auditoria_viajes.parquet", trip_quality)
                from .auxiliary_etl import run_auxiliary
                auxiliary = run_auxiliary(v3, manifest, staged_p, staged_q, agebs)
                verify_manifest(v3)
                final_p = processed_root / generation
                final_q = quarantine_root / generation
                outputs = (artifact_inventory(staged_p, v3, final_p.relative_to(v3))
                           + artifact_inventory(staged_q, v3, final_q.relative_to(v3)))
                audit = {
                    "contract_id": generation, "processed_at": manifest["processed_at"],
                    "source_hashes": {row["path"]: row["sha256"] for row in manifest["files"]},
                    "generation_directories": [final_p.relative_to(v3).as_posix(), final_q.relative_to(v3).as_posix()],
                    "outputs": outputs, "stations": station_audit, "agebs": ageb_audit,
                    "trip_rows": {
                        column: int(trip_quality[column].sum()) for column in
                        ["input_rows", "accepted_rows", "quarantine_rows", "valid_retiros", "valid_arribos"]
                    },
                    "endpoint_weights": {
                        column: float(trip_quality[column].sum()) for column in
                        ["known_retiros_weight", "known_arribos_weight", "unknown_retiros_weight", "unknown_arribos_weight"]
                    },
                    "iqr": iqr, "policy": POLICY, "raw_unchanged": True,
                    "no_silent_deletions": True, "integer_counts_nullable_Int64": True,
                    "weighted_event_counts_Float64": True,
                    "auxiliary_disposition": "normalized_datasets_documents_and_verified_mirrors",
                    "auxiliary": auxiliary,
                    "publication": "audit01_is_commit_marker; readers_must_verify_it",
                }
                if audit_path.exists():
                    previous = json.loads(audit_path.read_text(encoding="utf-8"))
                    if audit != previous:
                        raise ValueError("Forced rebuild differs from committed deterministic outputs")
                publish_directory(staged_p, final_p, v3)
                publish_directory(staged_q, final_q, v3)
                verify_outputs(v3, audit)
                write_json(audit_path, audit)
                run_record["mode"] = "computed_and_verified"
                return audit
            finally:
                # These exact UUID directories were created by this invocation.
                for staged in [staged_p, staged_q]:
                    if staged.exists() and not staged.is_symlink():
                        shutil.rmtree(staged)
    except Exception as exc:
        run_record["error_type"] = type(exc).__name__
        run_record["error"] = str(exc)
        raise
    finally:
        run_record["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(execution_dir / (execution_id + ".json"), run_record)
