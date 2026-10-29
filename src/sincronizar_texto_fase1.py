"""Sincroniza solo el texto Markdown de 00/01 con la receta NOTEBOOKS vigente.

Conserva las celdas de código ejecutadas (fuente, outputs y execution_count)
sin reejecutar el ETL. Anota en 01 el contrato al que pertenecen los hallazgos.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
if str(V3.parent) not in sys.path:
    sys.path.insert(0, str(V3.parent))

import nbformat

from V3.src.fase1_content import NOTEBOOKS

NOTEBOOKS_DIR = V3 / "notebooks"
FINDINGS_CONTRACT = "6e586b3d9a0bd8b844d9cf5bc714f0e583fc2a6936f8cd5ca89de9cdb26afd93"
FINDINGS_SOURCE = "V3/audits/01_findings_v3.json"
FINDINGS_NOTEBOOKS = {"01_ETL_Reproducible.ipynb"}


def sync_cells(name: str) -> tuple[bool, list[str]]:
    """Reconstruye la secuencia de celdas segun NOTEBOOKS.

    Devuelve (cambio, mensajes); no escribe si la tupla (tipo, fuente) ya
    coincide con la receta y no falta metadata de hallazgos.
    """
    path = NOTEBOOKS_DIR / name
    nb = nbformat.read(path, as_version=4)
    executed_code = [cell for cell in nb.cells if cell.cell_type == "code"]
    recipe = NOTEBOOKS[name]

    new_cells = []
    cursor = 0
    for cell_type, source in recipe:
        if cell_type == "code":
            assert cursor < len(executed_code), f"{name}: faltan celdas ejecutadas"
            cell = executed_code[cursor]
            cursor += 1
            assert cell.source == source, f"{name}: fuente de código distinta a la receta"
            new_cells.append(cell)
        else:
            new_cells.append(nbformat.v4.new_markdown_cell(source))
    assert cursor == len(executed_code), f"{name}: celdas ejecutadas de más"

    changed = [(c.cell_type, c.source) for c in nb.cells] != [
        (c.cell_type, c.source) for c in new_cells
    ]
    nb.cells = new_cells

    messages = []
    if name in FINDINGS_NOTEBOOKS:
        meta = nb.metadata
        if meta.get("findings_contract_id") != FINDINGS_CONTRACT or meta.get(
            "findings_source"
        ) != FINDINGS_SOURCE:
            meta["findings_contract_id"] = FINDINGS_CONTRACT
            meta["findings_source"] = FINDINGS_SOURCE
            changed = True
        messages.append("metadata de hallazgos anotada")

    if not changed:
        return False, ["ya coincide con la receta"]
    nbformat.validate(nb)
    nbformat.write(nb, path)
    return True, messages


def main() -> int:
    for name in NOTEBOOKS:
        changed, messages = sync_cells(name)
        estado = "actualizado" if changed else "sin cambios"
        detalle = "; ".join(messages)
        print(f"{name}: {estado} ({detalle})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
