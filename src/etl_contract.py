"""Immutable RAW contract and deterministic serialization for V3."""
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

POLICY = {
    "version": "v3-etl-3",
    "year": 2025,
    "calendar_days": 365,
    "trip_chunksize": 250000,
    "outlier_iqr_multiplier": 1.5,
    "metric_crs": "EPSG:32614",
    "ageb_default_declared_crs": "EPSG:6365",
    "dedup": "latest_valid_update_then_sha256_then_source_file_then_row",
    "processed_at": "UTC epoch pinned when the immutable manifest is created",
    "trip_cohort": "both endpoints valid 2025, known station identifiers, nullable integer age",
    "activity_cohort": "each valid 2025 endpoint independently; compound IDs share unit weight",
    "station_identity": "GBFS physical record; first short_name component is primary; all components are explicit aliases",
    "daily_activity": "(withdrawal_weight + arrival_weight) / (2 * 365)",
    "negative_trip_duration": "flag_only; no silent removal",
    "auxiliary_sources": "all registered datasets normalized; documents catalogued; mirrors verified once",
    "ignored_os_metadata": [".DS_Store"],
    "missing_values": "preserve legitimate nulls and suppression; never blanket fill/drop",
    "census": "all geographic levels retained; AGEB totals are a separate non-additive view",
    "denue": "snapshot 2026 retained and flagged; registration date is not an update timestamp",
    "gtfs": "optional nulls and times beyond24h allowed; foreign keys checked; service-year flag",
    "incidents": "2025 analytical cohort; historical/out-of-domain rows retained in quarantine",
    "cycling": "layers stay separate; total layer not concatenated with component layers",
    "ssc": "victim records retained; repeated labels flagged, not inferred to be duplicated events",
}
TRIP_COLUMNS = [
    "Genero_Usuario", "Edad_Usuario", "Bici", "Ciclo_Estacion_Retiro",
    "Fecha_Retiro", "Hora_Retiro", "Ciclo_EstacionArribo", "Fecha_Arribo", "Hora_Arribo",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_json(path, value):
    """Replace an owned output atomically; never use on RAW."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def inventory(v3):
    v3 = Path(v3).resolve()
    raw = v3 / "data/raw"
    if not raw.is_dir() or raw.is_symlink():
        raise ValueError("RAW must be a real directory")
    files = []
    for path in sorted(raw.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in RAW: {path}")
        if not path.is_file():
            continue
        if path.name in POLICY["ignored_os_metadata"]:
            continue
        relative = path.relative_to(v3).as_posix()
        core = (path.parent.name in {"ecobici_stations", "ecobici_trips"}
                or path.name in {"ageb_urbana_cdmx.geojson", "ageb_rural_cdmx.geojson"})
        mirror = ("data/raw/gtfs/gtfs/" in relative or "data/raw/inegi_ageb/denue_09_csv/" in relative)
        role = "verified_mirror" if mirror else ("core_etl" if core else "auxiliary_etl_or_document")
        files.append({"path": relative, "bytes": path.stat().st_size,
                      "sha256": sha256(path), "role": role})
    required = {
        "data/raw/ecobici_stations/station_information.json",
        "data/raw/inegi_ageb/ageb_urbana_cdmx.geojson",
        "data/raw/inegi_ageb/ageb_rural_cdmx.geojson",
        *[f"data/raw/ecobici_trips/2025-{month:02}.csv" for month in range(1, 13)],
        "data/raw/inegi_ageb/ageb_mza_urbana_09_cpv2020_csv.zip",
        "data/raw/inegi_ageb/denue_09_csv.zip",
        "data/raw/gtfs/gtfs.zip",
        *["data/raw/urban_environment/" + name for name in [
            "ciclovias.geojson", "ciclovias.zip", "ciclovias_semovi_2025.zip",
            "accidentes_viales_2025.geojson", "incidentes_viales_c5.csv",
            "ssc_semovi_2025_mapa.html", "ssc_semovi_2025_publicacion.html",
            "fuentes_diagnostico.json"]],
    }
    available = {row["path"] for row in files}
    if not required.issubset(available):
        raise ValueError(f"Missing core RAW files: {sorted(required - available)}")
    return files


def _build_manifest_locked(v3):
    v3 = Path(v3).resolve()
    files = inventory(v3)
    modules = ["etl_contract.py", "enterprise_etl.py", "auxiliary_etl.py", "artifact_reader.py"]
    code_hashes = {name: sha256(Path(__file__).parent / name) for name in modules}
    versions = {name: importlib.metadata.version(name) for name in
                ["pandas", "geopandas", "shapely", "pyproj", "pyarrow", "numpy",
                 "pyogrio", "beautifulsoup4"]}
    identity = {"files": files, "policy": POLICY, "code_hashes": code_hashes, "versions": versions}
    contract_id = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    target = v3 / "audits/00_manifest.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if previous["contract_id"] != contract_id or any(previous.get(k) != v for k, v in identity.items()):
            raise ValueError("Immutable contract changed: RAW, policy, code or versions differ; no overwrite permitted")
        pd.Timestamp(previous["processed_at"]).tz_convert("UTC")
        return previous
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {**identity, "contract_id": contract_id,
                "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "raw_root": "V3/data/raw", "timestamp_semantics": POLICY["processed_at"]}
    archive = v3 / "audits/contracts" / contract_id
    archive.mkdir(parents=True, exist_ok=True)
    for name in modules:
        source = Path(__file__).parent / name
        archived = archive / name
        if archived.exists() and sha256(archived) != code_hashes[name]:
            raise ValueError("Archived producer source differs; refusing overwrite")
        if not archived.exists():
            with archived.open("xb") as stream:
                stream.write(source.read_bytes())
    archived_manifest = archive / "00_manifest.json"
    if archived_manifest.exists():
        if json.loads(archived_manifest.read_text()) != manifest:
            raise ValueError("Archived contract differs")
    else:
        write_json(archived_manifest, manifest)
    write_json(target, manifest)
    return manifest


def build_manifest(v3):
    v3 = Path(v3).resolve()
    directory = v3 / "audits"
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".manifest.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        return _build_manifest_locked(v3)
    finally:
        lock.unlink()


def verify_manifest(v3):
    """Full content check, not merely an mtime check."""
    return build_manifest(v3)


def provenance(frame, source, manifest):
    result = frame.copy()
    result["_source_file"] = pd.Series(source, index=result.index, dtype="string")
    result["_processed_at"] = pd.Series(pd.Timestamp(manifest["processed_at"]),
                                         index=result.index, dtype="datetime64[ns, UTC]")
    return result


def get_processed_root(v3, verify=True):
    from .artifact_reader import get_processed_root as resolve
    return resolve(v3, verify=verify)


def get_quarantine_root(v3, verify=True):
    from .artifact_reader import get_quarantine_root as resolve
    return resolve(v3, verify=verify)


def upgrade_contract(v3, expected_parent_id):
    """Explicitly archive the current pointers before activating a new version."""
    v3 = Path(v3).resolve()
    lock = v3 / "audits/.etl.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        current = v3 / "audits/00_manifest.json"
        previous = json.loads(current.read_text(encoding="utf-8"))
        if previous["contract_id"] != expected_parent_id:
            raise ValueError("Active parent changed; upgrade not authorized for this contract")
        commit = json.loads((v3 / "audits/01_etl.json").read_text(encoding="utf-8"))
        if commit["contract_id"] != expected_parent_id:
            raise ValueError("Parent manifest and commit differ")
        for source in previous["files"]:
            if sha256(v3 / source["path"]) != source["sha256"]:
                raise ValueError("Original RAW content changed before the version upgrade")
        archive = v3 / "audits/contracts" / expected_parent_id
        archive.mkdir(parents=True, exist_ok=True)
        for name in ["00_manifest.json", "01_etl.json"]:
            source = v3 / "audits" / name
            destination = archive / ("active_before_v3_" + name)
            if destination.exists():
                raise ValueError("Upgrade archive already exists; refusing overwrite")
            source.rename(destination)
        activated = build_manifest(v3)
        write_json(v3 / "audits/contracts" / activated["contract_id"] / "upgrade.json", {
            "parent_contract_id": expected_parent_id,
            "child_contract_id": activated["contract_id"],
            "from_version": previous["policy"]["version"],
            "to_version": activated["policy"]["version"],
            "reason": "Complete source normalization and verified artifact resolution",
        })
        return activated
    finally:
        lock.unlink()
