"""Read-only resolution of committed, verified V3 generations."""
import hashlib
import json
import re
from pathlib import Path


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(v3, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise ValueError("Noncanonical artifact path")
    result = v3 / path
    for component in [result, *result.parents]:
        if component == v3.parent:
            break
        if component.is_symlink():
            raise ValueError("Artifact symlinks are not allowed")
    result.resolve().relative_to(v3)
    return result


def load_committed_audit(v3, verify=True):
    v3 = Path(v3).resolve()
    manifest_path = v3 / "audits/00_manifest.json"
    audit_path = v3 / "audits/01_etl.json"
    manifest_bytes = manifest_path.read_bytes()
    audit_bytes = audit_path.read_bytes()
    manifest, audit = json.loads(manifest_bytes), json.loads(audit_bytes)
    contract_id = manifest["contract_id"]
    if not re.fullmatch(r"[0-9a-f]{64}", contract_id) or audit["contract_id"] != contract_id:
        raise ValueError("Generation is not committed under the active manifest")
    identity = {key: manifest[key] for key in ["files", "policy", "code_hashes", "versions"]}
    calculated = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if calculated != contract_id:
        raise ValueError("Manifest identity is invalid")
    roots = {f"data/processed/{contract_id}", f"data/quarantine/{contract_id}"}
    if set(audit["generation_directories"]) != roots:
        raise ValueError("Unexpected generation directories")
    for root in roots:
        if not _inside(v3, root).is_dir():
            raise ValueError("Missing committed generation")
    expected = set()
    for artifact in audit["outputs"]:
        relative = artifact["path"]
        if not any(relative.startswith(root + "/") for root in roots) or relative in expected:
            raise ValueError("Unregistered/duplicate output path")
        expected.add(relative)
        path = _inside(v3, relative)
        if not path.is_file():
            raise ValueError(f"Missing artifact: {relative}")
        if verify and (path.stat().st_size != artifact["bytes"] or _hash(path) != artifact["sha256"]):
            raise ValueError(f"Altered artifact: {relative}")
    actual = {path.relative_to(v3).as_posix() for root in roots
              for path in _inside(v3, root).rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("Unexpected files in the active generation")
    if manifest_path.read_bytes() != manifest_bytes or audit_path.read_bytes() != audit_bytes:
        raise ValueError("Active generation changed during verification; retry the read")
    return audit


def get_processed_root(v3, verify=True):
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=verify)
    return v3 / "data/processed" / audit["contract_id"]


def get_quarantine_root(v3, verify=True):
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=verify)
    return v3 / "data/quarantine" / audit["contract_id"]
