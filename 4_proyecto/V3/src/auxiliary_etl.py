"""Source-specific normalization of all ancillary V3 inputs."""
import hashlib
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from bs4 import BeautifulSoup
from shapely.errors import GEOSException
from shapely.geometry import shape
from pyproj.exceptions import ProjError

from .etl_contract import POLICY, canonical_json, provenance, sha256
from .enterprise_etl import ChunkWriter, strict_integer, text, update_time, write_frame

CENSUS_DECIMALS = {
    "REL_H_M", "PROM_HNV", "GRAPROES", "GRAPROES_F", "GRAPROES_M", "PROM_OCUP", "PRO_OCUP_C",
}
MISSING_TOKENS = {"", "*", "N/D", "ND", "N/D."}
GTFS_KEYS = {
    "agency": ["agency_id"], "routes": ["route_id"], "calendar": ["service_id"],
    "calendar_dates": ["service_id", "date"], "stops": ["stop_id"], "trips": ["trip_id"],
    "shapes": ["shape_id", "shape_pt_sequence"], "stop_times": ["trip_id", "stop_sequence"],
    "frequencies": ["trip_id", "start_time"],
}


def prepare(raw, source, manifest, offset=0):
    frame = pd.DataFrame(raw).copy().reset_index(drop=True)
    if "geometry" in frame:
        geometry = frame.pop("geometry")
        frame["_original_geometry_wkb"] = geometry.map(
            lambda value: value.wkb_hex if value is not None else None)
    original = frame.astype(object).where(frame.notna(), None).to_dict("records")
    payload = pd.Series([canonical_json(row) for row in original], dtype="string")
    for column in frame:
        if frame[column].dtype == object or isinstance(frame[column].dtype, pd.StringDtype):
            frame[column] = frame[column].map(
                lambda value: text(value) if pd.notna(value) else pd.NA).astype("string")
    frame = provenance(frame, source, manifest)
    frame["_source_row"] = pd.Series(np.arange(offset + 1, offset + len(frame) + 1), dtype="Int64")
    frame["_raw_record"] = payload
    frame["_record_sha256"] = payload.map(lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()).astype("string")
    frame["_updated_at"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    frame["_quarantine_reason"] = pd.Series("", index=frame.index, dtype="string")
    return frame


def reason(frame, mask, name):
    mask = pd.Series(mask, index=frame.index).fillna(False).astype(bool)
    frame.loc[mask, "_quarantine_reason"] += name + "|"


def integer(frame, column, required=False, minimum=None):
    if column not in frame:
        if not required:
            return
        raise ValueError(f"Required column missing: {column}")
    values, invalid = strict_integer(frame[column])
    frame[column] = values
    reason(frame, invalid | (values.isna() if required else False), "invalid_integer_" + column)
    if minimum is not None:
        reason(frame, values.lt(minimum), "below_minimum_" + column)


def real_number(frame, column, required=False):
    if column not in frame:
        if required:
            raise ValueError(f"Required column missing: {column}")
        return
    raw = frame[column].astype("string")
    numeric = pd.to_numeric(raw, errors="coerce").astype("Float64")
    present = raw.notna() & raw.ne("")
    bad = present & (numeric.isna() | ~np.isfinite(numeric))
    frame[column] = numeric.mask(bad)
    reason(frame, bad | (numeric.isna() if required else False), "invalid_numeric_" + column)


def coordinates(frame, latitude, longitude, required=True):
    real_number(frame, latitude, required)
    real_number(frame, longitude, required)
    valid = (frame[latitude].between(-90, 90) & frame[longitude].between(-180, 180)).fillna(False)
    any_present = frame[latitude].notna() | frame[longitude].notna()
    reason(frame, ~valid & (True if required else any_present), "invalid_coordinates")
    frame["has_valid_coordinates"] = valid.astype("boolean")
    frame["coordinates_zero_pair"] = (frame[latitude].eq(0) & frame[longitude].eq(0)).fillna(False).astype("boolean")


def key(frame, columns):
    for column in columns:
        if column not in frame:
            raise ValueError(f"Missing primary key component: {column}")
        reason(frame, frame[column].isna() | frame[column].astype("string").eq(""), "missing_key_" + column)
    result = frame[columns].astype("string").agg(
        lambda row: canonical_json([None if pd.isna(value) else str(value) for value in row]), axis=1)
    incomplete = frame[columns].isna().any(axis=1)
    return result.mask(incomplete).astype("string")


def finish(frame, key_columns=None):
    frame = frame.copy()
    duplicates = pd.Series(False, index=frame.index)
    if key_columns:
        frame["_dedup_key"] = key(frame, key_columns)
        ordered = frame.sort_values(["_dedup_key", "_updated_at", "_record_sha256", "_source_row"],
                                    na_position="first", kind="mergesort")
        duplicates = ordered["_dedup_key"].notna() & ordered["_dedup_key"].duplicated(keep="last")
        frame = ordered
        reason(frame, duplicates, "superseded_duplicate")
    frame["_quarantine_reason"] = frame["_quarantine_reason"].str.rstrip("|")
    accepted = frame.loc[frame["_quarantine_reason"].eq("")].copy()
    rejected = frame.loc[frame["_quarantine_reason"].ne("")].copy()
    if len(accepted) + len(rejected) != len(frame):
        raise ValueError("Source row conservation failed")
    return accepted.reset_index(drop=True), rejected.reset_index(drop=True), int(duplicates.sum())


def summary(accepted, rejected, input_rows, duplicates=0):
    counts = rejected["_quarantine_reason"].str.split("|").explode().value_counts()
    return {
        "input_rows": int(input_rows), "accepted_rows": len(accepted), "quarantine_rows": len(rejected),
        "superseded_duplicates": int(duplicates), "reason_occurrences": {str(k): int(v) for k, v in counts.items()},
        "null_counts": {column: int(accepted[column].isna().sum()) for column in accepted
                        if not column.startswith("_")},
    }


def publish_table(name, frame, processed, quarantine, key_columns=None):
    accepted, rejected, duplicates = finish(frame, key_columns)
    write_frame(processed / (name + ".parquet"), accepted)
    write_frame(quarantine / (name + ".parquet"), rejected)
    return accepted, summary(accepted, rejected, len(frame), duplicates)


def stream_table(name, chunks, transform, key_columns, source, manifest, processed, quarantine):
    """Disk-backed global dedup; memory use is bounded by a chunk."""
    work = processed / (".work_" + name)
    work.mkdir()
    connection = sqlite3.connect(work / "winners.sqlite")
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("CREATE TABLE winners(k TEXT PRIMARY KEY, stamp TEXT, digest TEXT, row_id INTEGER)")
    insert = """
    INSERT INTO winners VALUES(?,?,?,?)
    ON CONFLICT(k) DO UPDATE SET stamp=excluded.stamp,digest=excluded.digest,row_id=excluded.row_id
    WHERE (excluded.stamp,excluded.digest,excluded.row_id) >
          (winners.stamp,winners.digest,winners.row_id)
    """
    output, dlq = ChunkWriter(processed / (name + ".parquet")), ChunkWriter(quarantine / (name + ".parquet"))
    offset = accepted_count = rejected_count = duplicates = 0
    nulls, reasons = {}, {}
    try:
        for part, raw in enumerate(chunks):
            frame = transform(prepare(raw, source, manifest, offset))
            offset += len(frame)
            frame["_dedup_key"] = key(frame, key_columns)
            values = [(row["_dedup_key"],
                       row["_updated_at"].isoformat() if pd.notna(row["_updated_at"]) else "",
                       row["_record_sha256"], int(row["_source_row"]))
                      for row in frame.loc[frame["_dedup_key"].notna()].to_dict("records")]
            connection.executemany(insert, values)
            connection.commit()
            write_frame(work / f"{part:05}.parquet", frame)
        if not offset:
            raise ValueError(f"Empty data source: {source}")
        for path in sorted(work.glob("*.parquet")):
            frame = pd.read_parquet(path)
            valid_keys = frame["_dedup_key"].dropna().unique().tolist()
            winners = {}
            for start in range(0, len(valid_keys), 500):
                batch = valid_keys[start:start + 500]
                query = "SELECT k,row_id FROM winners WHERE k IN (" + ",".join(["?"] * len(batch)) + ")"
                winners.update(connection.execute(query, batch).fetchall())
            superseded = (frame["_dedup_key"].notna()
                          & frame["_source_row"].ne(frame["_dedup_key"].map(winners)))
            reason(frame, superseded, "superseded_duplicate")
            accepted, rejected, _ = finish(frame)
            output.write(accepted)
            dlq.write(rejected)
            accepted_count += len(accepted)
            rejected_count += len(rejected)
            duplicates += int(superseded.sum())
            for column in accepted:
                if not column.startswith("_"):
                    nulls[column] = nulls.get(column, 0) + int(accepted[column].isna().sum())
            for label, count in rejected["_quarantine_reason"].str.split("|").explode().value_counts().items():
                reasons[label] = reasons.get(label, 0) + int(count)
        if accepted_count + rejected_count != offset:
            raise ValueError("Stream partition conservation failed")
        return {"input_rows": offset, "accepted_rows": accepted_count, "quarantine_rows": rejected_count,
                "superseded_duplicates": duplicates, "null_counts": nulls, "reason_occurrences": reasons}
    finally:
        output.close()
        dlq.close()
        connection.close()
        shutil.rmtree(work)


def census_transform(frame):
    names = ["ENTIDAD", "NOM_ENT", "MUN", "NOM_MUN", "LOC", "NOM_LOC", "AGEB", "MZA"]
    if not set(names).issubset(frame):
        raise ValueError("Census geographic schema changed")
    for column, size in [("ENTIDAD", 2), ("MUN", 3), ("LOC", 4), ("AGEB", 4), ("MZA", 3)]:
        frame[column] = frame[column].astype("string").str.upper().str.zfill(size)
        pattern = rf"[0-9A-Z]{{{size}}}" if column == "AGEB" else rf"[0-9]{{{size}}}"
        reason(frame, ~frame[column].str.fullmatch(pattern, na=False), "invalid_geographic_" + column)
    reason(frame, frame.ENTIDAD.ne("09"), "outside_cdmx")
    frame["cvegeo"] = frame.ENTIDAD + frame.MUN + frame.LOC + frame.AGEB
    frame["nivel_geografico"] = pd.Series(np.select(
        [frame.MUN.eq("000"), frame.LOC.eq("0000"), frame.AGEB.eq("0000"), frame.MZA.eq("000")],
        ["entidad", "municipio", "localidad", "ageb"], default="manzana"), dtype="string")
    numeric_columns = [column for column in frame if column not in names and not column.startswith("_")
                       and column not in {"cvegeo", "nivel_geografico"}]
    suppressed = pd.DataFrame({column: frame[column].astype("string").eq("*").fillna(False)
                               for column in numeric_columns})
    frame["_suppressed_columns"] = pd.Series(
        [canonical_json([column for column, flag in row.items() if flag])
         for row in suppressed.to_dict("records")], dtype="string")
    frame["has_suppressed_values"] = suppressed.any(axis=1).astype("boolean")
    for column in numeric_columns:
        frame[column] = frame[column].astype("string").mask(frame[column].astype("string").isin(MISSING_TOKENS))
        if column in CENSUS_DECIMALS:
            real_number(frame, column)
        else:
            integer(frame, column, minimum=0)
    return frame


def census(v3, manifest, processed, quarantine):
    source = "data/raw/inegi_ageb/ageb_mza_urbana_09_cpv2020_csv.zip"
    with zipfile.ZipFile(v3 / source) as archive:
        members = [name for name in archive.namelist() if "/conjunto_de_datos/" in name
                   and name.endswith(".csv")]
        if len(members) != 1:
            raise ValueError("Ambiguous census data member")
        member = members[0]
        with archive.open(member) as stream:
            chunks = pd.read_csv(stream, dtype="string", encoding="utf-8-sig", chunksize=10000,
                                 on_bad_lines="error")
            report = stream_table("censo_2020", chunks, census_transform,
                                  ["ENTIDAD", "MUN", "LOC", "AGEB", "MZA"], source + "::" + member,
                                  manifest, processed, quarantine)
    # Totals are views, not a sum of blocks plus higher-level totals.
    accepted = pd.read_parquet(processed / "censo_2020.parquet")
    view = accepted.loc[accepted.nivel_geografico.eq("ageb")].copy()
    if not view.cvegeo.is_unique:
        raise ValueError("AGEB census view is not unique")
    write_frame(processed / "censo_ageb_2020.parquet", view)
    report["ageb_view_rows"] = len(view)
    report["geographic_levels"] = {str(k): int(value) for k, value in accepted.nivel_geografico.value_counts().items()}
    return report


def denue_transform(frame, ageb_keys, snapshot_year=2026):
    for column in ["id", "codigo_act", "latitud", "longitud", "cve_ent", "cve_mun", "cve_loc", "ageb"]:
        if column not in frame:
            raise ValueError(f"DENUE required field missing: {column}")
    reason(frame, ~frame.id.str.fullmatch(r"\d+", na=False), "invalid_establishment_id")
    reason(frame, ~frame.codigo_act.str.fullmatch(r"\d{6}", na=False), "invalid_scian_code")
    coordinates(frame, "latitud", "longitud")
    for column, size in [("cve_ent", 2), ("cve_mun", 3), ("cve_loc", 4), ("ageb", 4)]:
        frame[column] = frame[column].astype("string").str.upper().str.zfill(size)
    frame["cvegeo"] = frame.cve_ent + frame.cve_mun + frame.cve_loc + frame.ageb
    frame["ageb_key_unmatched"] = (~frame.cvegeo.isin(ageb_keys)).astype("boolean")
    reason(frame, frame.cve_ent.ne("09"), "outside_cdmx")
    frame["snapshot_year"] = pd.Series(snapshot_year, index=frame.index, dtype="Int64")
    frame["snapshot_outside_study_year"] = pd.Series(snapshot_year != POLICY["year"], index=frame.index, dtype="boolean")
    if "fecha_alta" in frame:
        original = frame.fecha_alta.astype("string")
        frame["fecha_alta_parsed"] = pd.to_datetime(original, format="%Y-%m", errors="coerce")
        frame["registration_date_invalid"] = (original.notna() & frame.fecha_alta_parsed.isna()).astype("boolean")
        frame["registered_after_study_year"] = frame.fecha_alta_parsed.dt.year.gt(2025).fillna(False).astype("boolean")
    if "per_ocu" in frame:
        bands = {"0 a 5 personas", "6 a 10 personas", "11 a 30 personas", "31 a 50 personas",
                 "51 a 100 personas", "101 a 250 personas", "251 y m\u00e1s personas"}
        frame["employment_band_unknown"] = (~frame.per_ocu.isin(bands)).astype("boolean")
    return frame


def denue(v3, manifest, processed, quarantine, agebs):
    source = "data/raw/inegi_ageb/denue_09_csv.zip"
    with zipfile.ZipFile(v3 / source) as archive:
        metadata = [name for name in archive.namelist() if "metadatos" in name and name.endswith(".txt")]
        years = set()
        for name in metadata:
            years.update(int(year) for year in re.findall(
                r"DENUE-(20\d{2})", archive.read(name).decode("utf-8-sig")))
        if len(years) != 1:
            raise ValueError("DENUE snapshot year cannot be established from its metadata")
        snapshot_year = years.pop()
        members = [name for name in archive.namelist() if name.endswith(".csv")
                   and Path(name).name.startswith("denue_inegi")]
        if len(members) != 1:
            raise ValueError("Ambiguous DENUE data member")
        with archive.open(members[0]) as stream:
            chunks = pd.read_csv(stream, dtype="string", encoding="latin1", chunksize=50000,
                                 on_bad_lines="error")
            return stream_table("denue", chunks, lambda frame: denue_transform(frame, set(agebs.cvegeo), snapshot_year),
                                ["id"], source + "::" + members[0], manifest, processed, quarantine)


def gtfs_time(frame, column, required=False):
    raw = frame[column].astype("string")
    parts = raw.str.extract(r"^(\d+):(\d{2}):(\d{2})$").apply(pd.to_numeric, errors="coerce")
    valid = (parts[0].ge(0) & parts[0].le((2**53 - 1) // 3600)
             & parts[1].between(0, 59) & parts[2].between(0, 59)).fillna(False)
    present = raw.notna() & raw.ne("")
    reason(frame, (present & ~valid) | (~present if required else False), "invalid_time_" + column)
    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    frame[column + "_seconds"] = seconds.where(valid).astype("Int64")


def gtfs(v3, manifest, processed, quarantine):
    source = "data/raw/gtfs/gtfs.zip"
    tables, reports = {}, {}
    with zipfile.ZipFile(v3 / source) as archive:
        files = {Path(name).stem: name for name in archive.namelist() if name.endswith(".txt")}
        required = {"agency", "routes", "stops", "trips", "stop_times"}
        if not required.issubset(files) or not ({"calendar", "calendar_dates"} & set(files)):
            raise ValueError("Missing mandatory GTFS tables")
        if set(files) - set(GTFS_KEYS):
            raise ValueError(f"Unregistered GTFS tables: {sorted(set(files) - set(GTFS_KEYS))}")
        order = ["agency", "calendar", "calendar_dates", "stops", "routes", "shapes", "trips",
                 "stop_times", "frequencies"]
        for name in order:
            if name not in files:
                continue
            raw = pd.read_csv(archive.open(files[name]), dtype="string", encoding="utf-8-sig",
                              on_bad_lines="error")
            frame = prepare(raw, source + "::" + files[name], manifest)
            for column in GTFS_KEYS[name]:
                if column not in frame:
                    raise ValueError(f"GTFS {name}: missing key {column}")
            if name == "calendar":
                for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    integer(frame, day, required=True)
                    reason(frame, ~frame[day].isin([0, 1]), "invalid_weekday_" + day)
                for column in ["start_date", "end_date"]:
                    frame[column + "_parsed"] = pd.to_datetime(frame[column], format="%Y%m%d", errors="coerce")
                    reason(frame, frame[column + "_parsed"].isna(), "invalid_" + column)
                reason(frame, frame.start_date_parsed.gt(frame.end_date_parsed), "reversed_service_period")
                frame["has_2025_service"] = (frame.start_date_parsed.le(pd.Timestamp("2025-12-31"))
                                            & frame.end_date_parsed.ge(pd.Timestamp("2025-01-01"))).astype("boolean")
            elif name == "calendar_dates":
                frame["date_parsed"] = pd.to_datetime(frame.date, format="%Y%m%d", errors="coerce")
                integer(frame, "exception_type", required=True)
                reason(frame, frame.date_parsed.isna() | ~frame.exception_type.isin([1, 2]), "invalid_calendar_exception")
            elif name == "stops":
                if "location_type" not in frame:
                    frame["location_type"] = pd.Series(0, index=frame.index, dtype="Int64")
                integer(frame, "location_type", minimum=0)
                # GTFS specifies default0 when omitted, not population imputation.
                frame["location_type"] = frame.location_type.fillna(0).astype("Int64")
                reason(frame, ~frame.location_type.isin([0, 1, 2, 3, 4]), "invalid_location_type")
                if "stop_lat" not in frame:
                    frame["stop_lat"] = pd.Series(pd.NA, index=frame.index, dtype="string")
                if "stop_lon" not in frame:
                    frame["stop_lon"] = pd.Series(pd.NA, index=frame.index, dtype="string")
                coordinates(frame, "stop_lat", "stop_lon", required=False)
                reason(frame, frame.location_type.isin([0, 1]) & ~frame.has_valid_coordinates, "required_stop_coordinates_missing")
                if "parent_station" in frame:
                    parent = frame.parent_station
                    reason(frame, parent.notna() & ~parent.isin(set(frame.stop_id)), "unknown_parent_station")
                integer(frame, "wheelchair_boarding", minimum=0)
                if "wheelchair_boarding" in frame:
                    reason(frame, frame.wheelchair_boarding.notna() & ~frame.wheelchair_boarding.isin([0, 1, 2]),
                           "invalid_wheelchair_boarding")
            elif name == "routes":
                integer(frame, "route_type", required=True, minimum=0)
                reason(frame, ~frame.agency_id.isin(set(tables["agency"].agency_id)), "unknown_agency")
            elif name == "shapes":
                integer(frame, "shape_pt_sequence", required=True, minimum=0)
                coordinates(frame, "shape_pt_lat", "shape_pt_lon")
                real_number(frame, "shape_dist_traveled")
                if "shape_dist_traveled" in frame:
                    reason(frame, frame.shape_dist_traveled.lt(0), "negative_shape_distance")
            elif name == "trips":
                reason(frame, ~frame.route_id.isin(set(tables["routes"].route_id)), "unknown_route")
                services = set()
                for calendar in ["calendar", "calendar_dates"]:
                    if calendar in tables:
                        services.update(tables[calendar].service_id)
                reason(frame, ~frame.service_id.isin(services), "unknown_service")
                if "shape_id" in frame and "shapes" in tables:
                    reason(frame, frame.shape_id.notna() & ~frame.shape_id.isin(set(tables["shapes"].shape_id)),
                           "unknown_shape")
                integer(frame, "direction_id", minimum=0)
                if "direction_id" in frame:
                    reason(frame, frame.direction_id.notna() & ~frame.direction_id.isin([0, 1]), "invalid_direction_id")
            elif name in {"stop_times", "frequencies"}:
                reason(frame, ~frame.trip_id.isin(set(tables["trips"].trip_id)), "unknown_trip")
                if name == "stop_times":
                    integer(frame, "stop_sequence", required=True, minimum=0)
                    reason(frame, ~frame.stop_id.isin(set(tables["stops"].stop_id)), "unknown_stop")
                    for column in ["arrival_time", "departure_time"]:
                        gtfs_time(frame, column)
                    integer(frame, "timepoint", minimum=0)
                    if "timepoint" in frame:
                        reason(frame, frame.timepoint.notna() & ~frame.timepoint.isin([0, 1]), "invalid_timepoint")
                        reason(frame, frame.timepoint.eq(1) & (frame.arrival_time_seconds.isna()
                                                               | frame.departure_time_seconds.isna()), "missing_exact_time")
                else:
                    gtfs_time(frame, "start_time", True)
                    gtfs_time(frame, "end_time", True)
                    integer(frame, "headway_secs", required=True, minimum=1)
                    reason(frame, frame.start_time_seconds.ge(frame.end_time_seconds), "reversed_frequency_period")
                    integer(frame, "exact_times", minimum=0)
                    if "exact_times" in frame:
                        reason(frame, frame.exact_times.notna() & ~frame.exact_times.isin([0, 1]), "invalid_exact_times")
            tables[name], reports[name] = publish_table("gtfs_" + name, frame, processed, quarantine, GTFS_KEYS[name])
            if name == "stops" and "parent_station" in frame:
                accepted = tables[name]
                rejected = pd.read_parquet(quarantine / "gtfs_stops.parquet")
                while not accepted.empty:
                    parent = accepted.parent_station
                    parent_type = parent.map(accepted.set_index("stop_id").location_type)
                    has_parent = parent.notna() & parent.ne("")
                    needs_parent = accepted.location_type.isin([2, 3, 4])
                    bad = ((has_parent & parent_type.isna()) | (needs_parent & ~has_parent)
                           | (accepted.location_type.eq(1) & has_parent)
                           | (has_parent & accepted.location_type.isin([0, 2, 3]) & parent_type.ne(1))
                           | (has_parent & accepted.location_type.eq(4) & parent_type.ne(0)))
                    if not bad.fillna(False).any():
                        break
                    newly_rejected = accepted.loc[bad.fillna(False)].copy()
                    reason(newly_rejected, pd.Series(True, index=newly_rejected.index), "invalid_parent_structure")
                    newly_rejected["_quarantine_reason"] = newly_rejected["_quarantine_reason"].str.rstrip("|")
                    rejected = pd.concat([part for part in [rejected, newly_rejected] if not part.empty],
                                         ignore_index=True)
                    accepted = accepted.loc[~bad.fillna(False)].copy()
                tables[name] = accepted.reset_index(drop=True)
                write_frame(processed / "gtfs_stops.parquet", tables[name])
                write_frame(quarantine / "gtfs_stops.parquet", rejected)
                reports[name] = summary(tables[name], rejected, len(raw),
                                        reports[name]["superseded_duplicates"])
    return reports


def c5_transform(frame):
    for column in ["folio", "fecha_creacion", "latitud", "longitud"]:
        if column not in frame:
            raise ValueError("C5 schema changed")
    coordinates(frame, "latitud", "longitud")
    frame["fecha_creacion_parsed"] = pd.to_datetime(frame.fecha_creacion, format="%Y-%m-%d", errors="coerce")
    reason(frame, frame.fecha_creacion_parsed.isna(), "invalid_creation_date")
    reason(frame, frame.fecha_creacion_parsed.notna() & frame.fecha_creacion_parsed.dt.year.ne(2025),
           "outside_study_year")
    if "fecha_cierre" in frame:
        frame["fecha_cierre_parsed"] = pd.to_datetime(frame.fecha_cierre, format="%Y-%m-%d", errors="coerce")
        frame["invalid_closing_date"] = (frame.fecha_cierre.notna() & frame.fecha_cierre_parsed.isna()).astype("boolean")
    if "hora_creacion" in frame:
        raw = frame.hora_creacion.astype("string")
        parts = raw.str.extract(r"^(\d{1,2}):(\d{2}):(\d{2})$").apply(pd.to_numeric, errors="coerce")
        valid = (parts[0].between(0, 23) & parts[1].between(0, 59) & parts[2].between(0, 59)).fillna(False)
        frame["valid_creation_time"] = valid.astype("boolean")
        frame["ts_creacion"] = (frame.fecha_creacion_parsed + pd.to_timedelta(parts[0].fillna(0), unit="h")
                                + pd.to_timedelta(parts[1].fillna(0), unit="m")
                                + pd.to_timedelta(parts[2].fillna(0), unit="s")).where(
                                    valid & frame.fecha_creacion_parsed.dt.year.eq(2025)).dt.tz_localize("America/Mexico_City")
    return frame


def c5(v3, manifest, processed, quarantine):
    source = "data/raw/urban_environment/incidentes_viales_c5.csv"
    chunks = pd.read_csv(v3 / source, dtype="string", encoding="utf-8-sig", chunksize=50000,
                         on_bad_lines="error")
    return stream_table("incidentes_c5_2025", chunks, c5_transform, ["folio"], source,
                        manifest, processed, quarantine)


def geodata(name, raw, source, manifest, processed, quarantine, kind, key_columns=None):
    if raw.crs is None:
        raise ValueError(f"Missing declared geometry CRS: {source}")
    frame = prepare(raw, source, manifest)
    original = raw.geometry.reset_index(drop=True)
    good, transformed = [], []
    allowed = {"LineString", "MultiLineString"} if kind == "cycling" else {"Point"}
    for geometry in original:
        try:
            valid = (geometry is not None and not geometry.is_empty and geometry.is_valid
                     and geometry.geom_type in allowed and np.isfinite(geometry.bounds).all())
            result = gpd.GeoSeries([geometry], crs=raw.crs).to_crs(4326).iloc[0] if valid else None
            valid = valid and result is not None and np.isfinite(result.bounds).all()
            good.append(valid)
            transformed.append(result if valid else None)
        except (ValueError, TypeError, GEOSException, ProjError):
            good.append(False)
            transformed.append(None)
    reason(frame, ~pd.Series(good), "invalid_geometry")
    frame["geometry"] = transformed
    frame["_geometry_source_crs"] = pd.Series(str(raw.crs), index=frame.index, dtype="string")
    if kind == "cycling":
        for column in ["ID_TRAMO", "ID_PROY"]:
            integer(frame, column, minimum=0)
        if "LONG_KM" in frame:
            real_number(frame, "LONG_KM")
            reason(frame, frame.LONG_KM.lt(0), "negative_declared_length")
        for column in ["A_INICIO", "A_TERMINO"]:
            if column in frame:
                parsed = pd.to_numeric(frame[column].astype("string").mask(
                    frame[column].astype("string").isin(MISSING_TOKENS)), errors="coerce")
                frame[column.lower() + "_year"] = parsed.where(
                    parsed.between(1800, 2100) & parsed.mod(1).eq(0)).astype("Int64")
        metric = gpd.GeoSeries(transformed, crs=4326).to_crs(POLICY["metric_crs"])
        frame["length_km"] = metric.length.astype("Float64") / 1000
        q1, q3 = frame.length_km.quantile([.25, .75])
        frame["is_outlier_high"] = frame.length_km.gt(q3 + 1.5 * (q3 - q1)).fillna(False).astype("boolean")
        if "ESTADO" in frame:
            frame["is_reported_operational"] = frame.ESTADO.astype("string").str.lower().isin(
                ["en operacion", "en operaci\u00f3n"]).astype("boolean")
    elif kind == "accidents":
        if "fecha" not in frame:
            raise ValueError("Accident date missing")
        raw_date = pd.to_numeric(frame.fecha, errors="coerce")
        frame["fecha_parsed"] = pd.to_datetime(raw_date, unit="ms", utc=True, errors="coerce")
        reason(frame, frame.fecha_parsed.isna(), "invalid_accident_date")
        reason(frame, frame.fecha_parsed.notna() & frame.fecha_parsed.dt.year.ne(2025), "outside_study_year")
        for column in ["fid", "fid_1", "id", "lesionados", "fallecidos"]:
            integer(frame, column, minimum=0)
    accepted, rejected, duplicates = finish(frame, key_columns)
    accepted = gpd.GeoDataFrame(accepted, geometry="geometry", crs=4326)
    rejected = rejected.drop(columns="geometry")
    write_frame(processed / (name + ".parquet"), accepted)
    write_frame(quarantine / (name + ".parquet"), rejected)
    return summary(accepted, rejected, len(raw), duplicates)


def spatial_sources(v3, manifest, processed, quarantine):
    reports = {}
    for file, name, kind, keys in [
        ("ciclovias.geojson", "ciclovias_geojson", "cycling", ["ID_TRAMO"]),
        ("accidentes_viales_2025.geojson", "accidentes_viales_2025", "accidents", ["fid"]),
    ]:
        source = "data/raw/urban_environment/" + file
        # GeoJSON with corrupt individual geometries must not abort the entire file.
        document = json.loads((v3 / source).read_text(encoding="utf-8"))
        rows, geometry = [], []
        for feature in document["features"]:
            properties = dict(feature.get("properties") or {})
            properties["_original_feature"] = canonical_json(feature)
            rows.append(properties)
            try:
                geometry.append(shape(feature["geometry"]) if feature.get("geometry") else None)
            except (ValueError, TypeError, GEOSException):
                geometry.append(None)
        declared = document.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
        raw = gpd.GeoDataFrame(rows, geometry=geometry, crs=declared)
        reports[name] = geodata(name, raw, source, manifest, processed, quarantine, kind, keys)
    source = "data/raw/urban_environment/ciclovias_semovi_2025.zip"
    duplicate_zip = "data/raw/urban_environment/ciclovias.zip"
    if sha256(v3 / source) != sha256(v3 / duplicate_zip):
        raise ValueError("The two cycling archives differ; source precedence requires review")
    with zipfile.ZipFile(v3 / source) as archive:
        members = sorted(name for name in archive.namelist() if name.endswith(".shp"))
        if not members:
            raise ValueError("No cycling shapefiles")
        layer_registry = []
        for index, member in enumerate(members):
            raw = gpd.read_file("/vsizip/" + str((v3 / source).resolve()) + "/" + member)
            name = f"ciclovias_capa_{index:02}"
            reports[name] = geodata(name, raw, source + "::" + member, manifest,
                                   processed, quarantine, "cycling", ["ID_TRAMO"])
            layer_registry.append({"artifact": name + ".parquet", "layer": Path(member).stem,
                                   "is_total_layer": Path(member).stem == "Infraestructura ciclista total",
                                   "not_additive_with_other_layers": True})
        registry = provenance(pd.DataFrame(layer_registry), source, manifest)
        write_frame(processed / "ciclovias_capas.parquet", registry)
    return reports


def ssc(v3, manifest, processed, quarantine):
    source = "data/raw/urban_environment/ssc_semovi_2025_mapa.html"
    html = (v3 / source).read_text(encoding="utf-8")
    blocks = re.findall(r'<script\b[^>]*type=["\x27]application/json["\x27][^>]*>(.*?)</script>',
                        html, flags=re.S | re.I)
    categories = {role + " " + outcome for role in ["Ciclista", "Peat\u00f3n", "Motociclista", "Conductor", "Pasajero"]
                  for outcome in ["Lesionado", "Fallecido"]}
    rows = []
    calls_registry = []
    for block in blocks:
        payload = json.loads(block)
        for call in payload.get("x", {}).get("calls", []):
            if call.get("method") != "addCircleMarkers":
                continue
            args = call["args"]
            category = args[4] if len(args) > 4 else None
            included = category in categories
            calls_registry.append({"category": category, "is_observation_layer": included})
            if not included:
                continue
            if len(args) < 11 or not (len(args[0]) == len(args[1]) == len(args[10])):
                raise ValueError("SSC marker arrays changed")
            for lat, lon, label in zip(args[0], args[1], args[10]):
                rows.append({"lat": lat, "lon": lon, "category": category, "label": label})
    if not rows:
        raise ValueError("No SSC victim observation layers found")
    frame = prepare(pd.DataFrame(rows), source, manifest)
    coordinates(frame, "lat", "lon")
    match = frame.label.astype("string").str.extract(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2})\s+HRS")
    date = pd.to_datetime(match[0], format="%Y-%m-%d", errors="coerce")
    hour = pd.to_numeric(match[1], errors="coerce")
    valid = date.notna() & hour.between(0, 23)
    reason(frame, ~valid, "invalid_victim_datetime")
    reason(frame, date.notna() & date.dt.year.ne(2025), "outside_study_year")
    frame["ts_evento"] = (date + pd.to_timedelta(hour.fillna(0), unit="h")).where(valid).dt.tz_localize("America/Mexico_City")
    frame["is_possible_repeat"] = frame.duplicated(["category", "ts_evento", "lat", "lon"], keep=False).astype("boolean")
    _, report = publish_table("ssc_victimas_2025", frame, processed, quarantine)
    write_frame(processed / "ssc_capas.parquet", provenance(pd.DataFrame(calls_registry), source, manifest))
    return report


def documents(v3, manifest, processed, quarantine):
    reports, resources = {}, []
    archives = [
        ("data/raw/inegi_ageb/denue_09_csv.zip", "latin1", 1),
        ("data/raw/inegi_ageb/ageb_mza_urbana_09_cpv2020_csv.zip", "utf-8-sig", 3),
    ]
    for source, encoding, skiprows in archives:
        with zipfile.ZipFile(v3 / source) as archive:
            for member in archive.namelist():
                if member.endswith(".csv") and "diccionario" in member:
                    raw = pd.read_csv(archive.open(member), dtype="string", encoding=encoding,
                                      skiprows=skiprows, on_bad_lines="error",
                                      keep_default_na=False, na_values=[""])
                    raw.columns = [str(column).strip() for column in raw.columns]
                    name = "diccionario_denue" if "denue" in source else "diccionario_censo"
                    _, reports[name] = publish_table(name, prepare(raw, source + "::" + member, manifest),
                                                     processed, quarantine)
                elif member.endswith(".txt") and "metadatos" in member:
                    body = archive.read(member).decode("utf-8-sig")
                    resources.append({"resource_type": "metadata", "content": body,
                                      "_source_file": source + "::" + member})
    publication = "data/raw/urban_environment/ssc_semovi_2025_publicacion.html"
    body = (v3 / publication).read_text(encoding="utf-8")
    parsed = BeautifulSoup(body, "html.parser")
    resources.append({"resource_type": "publication", "content": parsed.get_text(" ", strip=True),
                      "_source_file": publication})
    source = "data/raw/urban_environment/fuentes_diagnostico.json"
    registry = json.loads((v3 / source).read_text(encoding="utf-8"))
    resources.append({"resource_type": "source_registry", "content": canonical_json(registry),
                      "_source_file": source})
    resource_table = pd.DataFrame(resources)
    resource_table = provenance(resource_table, resource_table["_source_file"].astype("string"), manifest)
    write_frame(processed / "documentacion_fuentes.parquet", resource_table)
    reports["documentacion_fuentes"] = {"resource_records": len(resource_table), "not_an_observation_table": True}
    return reports


def mirrors(v3, manifest):
    records = []
    prefixes = {
        "data/raw/gtfs/gtfs/": "data/raw/gtfs/gtfs.zip",
        "data/raw/inegi_ageb/denue_09_csv/": "data/raw/inegi_ageb/denue_09_csv.zip",
    }
    for item in manifest["files"]:
        path = item["path"]
        for prefix, parent in prefixes.items():
            if not path.startswith(prefix):
                continue
            with zipfile.ZipFile(v3 / parent) as archive:
                candidates = [member for member in archive.namelist()
                              if Path(member).name == Path(path).name and not member.endswith("/")]
                if len(candidates) != 1:
                    raise ValueError(f"Mirror cannot be uniquely matched: {path}")
                digest = hashlib.sha256()
                with archive.open(candidates[0]) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError(f"Extracted mirror differs from archive: {path}")
                records.append({"path": path, "archive": parent, "member": candidates[0],
                                "sha256": item["sha256"], "status": "verified_not_double_ingested"})
    return records


def run_auxiliary(v3, manifest, processed, quarantine, agebs):
    expected = {
        "data/raw/ecobici_stations/station_information.json",
        "data/raw/inegi_ageb/ageb_urbana_cdmx.geojson", "data/raw/inegi_ageb/ageb_rural_cdmx.geojson",
        "data/raw/inegi_ageb/denue_09_csv.zip", "data/raw/inegi_ageb/ageb_mza_urbana_09_cpv2020_csv.zip",
        "data/raw/gtfs/gtfs.zip",
        *[f"data/raw/ecobici_trips/2025-{month:02}.csv" for month in range(1, 13)],
        *["data/raw/urban_environment/" + name for name in [
            "ciclovias.geojson", "accidentes_viales_2025.geojson", "ciclovias.zip",
            "ciclovias_semovi_2025.zip", "incidentes_viales_c5.csv",
            "ssc_semovi_2025_mapa.html", "ssc_semovi_2025_publicacion.html", "fuentes_diagnostico.json"]],
    }
    mirror_records = mirrors(v3, manifest)
    registered = expected | {record["path"] for record in mirror_records}
    unexpected = {record["path"] for record in manifest["files"]} - registered
    if unexpected:
        raise ValueError(f"Unregistered RAW source disposition: {sorted(unexpected)}")
    reports = {}
    reports["censo_2020"] = census(v3, manifest, processed, quarantine)
    print("Census normalized", flush=True)
    reports["denue"] = denue(v3, manifest, processed, quarantine, agebs)
    print("DENUE normalized", flush=True)
    reports.update({"gtfs_" + name: report for name, report in gtfs(v3, manifest, processed, quarantine).items()})
    reports.update(spatial_sources(v3, manifest, processed, quarantine))
    reports["incidentes_c5_2025"] = c5(v3, manifest, processed, quarantine)
    print("C5 normalized", flush=True)
    reports["ssc_victimas_2025"] = ssc(v3, manifest, processed, quarantine)
    reports.update(documents(v3, manifest, processed, quarantine))
    mirror_table = pd.DataFrame(mirror_records, columns=["path", "archive", "member", "sha256", "status"])
    write_frame(processed / "raw_mirrors.parquet",
                provenance(mirror_table, mirror_table["path"].astype("string"), manifest))
    dispositions = []
    for item in manifest["files"]:
        path = item["path"]
        disposition = "verified_mirror" if path in {r["path"] for r in mirror_records} else (
            "normalized_core" if item["role"] == "core_etl" else "normalized_dataset_or_document")
        dispositions.append({"path": path, "disposition": disposition, "sha256": item["sha256"]})
    table = pd.DataFrame(dispositions)
    write_frame(processed / "source_disposition.parquet", provenance(table, table.path.astype("string"), manifest))
    return {"tables": reports, "mirrors": mirror_records,
            "registered_raw_files": len(dispositions), "all_sources_have_disposition": True}
