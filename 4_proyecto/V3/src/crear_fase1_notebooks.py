"""Empaqueta los cuadernos 00/01; el contenido autorado vive en fase1_content.py."""
import platform
import sys
from pathlib import Path

import nbformat

try:
    from .fase1_content import NOTEBOOKS
except ImportError:
    # Ejecución directa: python V3/src/crear_fase1_notebooks.py
    project = next(folder for folder in Path(__file__).resolve().parents
                   if (folder / "V3/src").is_dir())
    sys.path.insert(0, str(project))
    from V3.src.fase1_content import NOTEBOOKS


def main():
    """Escribe los cuadernos 00/01 a partir de NOTEBOOKS."""
    out_dir = Path(__file__).resolve().parent.parent / "notebooks"
    for name, cells in NOTEBOOKS.items():
        notebook = nbformat.v4.new_notebook()
        notebook.metadata["kernelspec"] = {
            "display_name": "CM V3 ETL aislado", "language": "python",
            "name": "cm_v3etl",
        }
        notebook.metadata["language_info"] = {
            "name": "python", "version": platform.python_version(),
        }
        for kind, source in cells:
            notebook.cells.append(
                nbformat.v4.new_markdown_cell(source) if kind == "markdown"
                else nbformat.v4.new_code_cell(source))
        nbformat.validate(notebook)
        target = out_dir / name
        nbformat.write(notebook, target)
        print(f"Notebook generado: {target} "
              f"({sum(c.cell_type == 'code' for c in notebook.cells)} celdas de codigo)")


if __name__ == "__main__":
    main()
