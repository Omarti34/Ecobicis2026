"""Empaquetador fino de 06_Motor2_Transformer_Honesto.ipynb.

La receta vive en V3.src.m2_content y el cálculo en V3.src.m2_analysis;
este módulo solo la envuelve, la ejecuta en memoria con el kernel privado
cm_v3etl y publica el cuaderno de forma atómica tras una ejecución sin
errores. No crea directorios ni toca el entorno al importarse.
"""
import json
import os
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
if str(V3.parent) not in sys.path:
    sys.path.insert(0, str(V3.parent))

from V3.src.m2_analysis import VERSION  # noqa: E402
from V3.src.m2_content import get_notebook_cells  # noqa: E402,F401

TARGET = V3 / "notebooks/06_Motor2_Transformer_Honesto.ipynb"
ANALYSIS_VERSION = VERSION


def _prepare_private_environment():
    for key, folder in {
        "IPYTHONDIR": ".ipython", "MPLCONFIGDIR": ".mplconfig",
        "JUPYTER_RUNTIME_DIR": ".runtime", "PYTHONPYCACHEPREFIX": ".bytecode",
    }.items():
        path = V3 / folder
        path.mkdir(exist_ok=True)
        os.environ[key] = str(path)
    os.environ["PYTHONHASHSEED"] = "42"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"

    kernel_dir = V3 / ".jupyter/kernels/cm_v3etl"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (kernel_dir / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher",
                 "-f", "{connection_file}"],
        "display_name": "CM V3 ETL aislado", "language": "python",
    }))
    os.environ["JUPYTER_PATH"] = str(V3 / ".jupyter")


def _notebook_from_recipe():
    import nbformat
    notebook = nbformat.v4.new_notebook()
    notebook.metadata["kernelspec"] = {
        "display_name": "CM V3 ETL aislado", "language": "python",
        "name": "cm_v3etl",
    }
    notebook.metadata["language_info"] = {
        "name": "python", "version": platform.python_version(),
    }
    notebook.metadata["analysis_version"] = ANALYSIS_VERSION
    for cell in get_notebook_cells():
        kind, source = cell if isinstance(cell, tuple) \
            else (cell["cell_type"], cell["source"])
        notebook.cells.append(
            nbformat.v4.new_markdown_cell(source) if kind == "markdown"
            else nbformat.v4.new_code_cell(source))
    nbformat.validate(notebook)
    return notebook


def _report_marker(notebook):
    """Extrae el único marcador application/json de la última celda de código."""
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells:
        raise RuntimeError("06: el cuaderno no tiene celdas de código")
    markers = []
    for output in getattr(code_cells[-1], "outputs", []):
        data = getattr(output, "data", {}) or {}
        payload = data.get("application/json")
        if isinstance(payload, dict) and "m2_report_path" in payload:
            markers.append(payload["m2_report_path"])
    if len(markers) != 1:
        raise RuntimeError(
            f"06: se esperaba 1 marcador m2_report_path, hallados {len(markers)}")
    return markers[0]


def build_and_execute():
    """Construye, ejecuta en memoria y publica el cuaderno de forma atómica."""
    import nbformat
    from nbclient import NotebookClient

    from V3.src.m2_publication import activate_report, verify_report

    _prepare_private_environment()
    notebook = _notebook_from_recipe()
    client = NotebookClient(
        notebook,
        timeout=3600,
        kernel_name="cm_v3etl",
        resources={"metadata": {"path": str(V3)}},
    )
    client.execute()                       # falla -> no se escribe nada

    errors = [
        output for cell in notebook.cells if cell.cell_type == "code"
        for output in getattr(cell, "outputs", [])
        if output.output_type == "error"
    ]
    if errors:
        raise RuntimeError(
            f"06_Motor2_Transformer_Honesto.ipynb: {len(errors)} errores")

    report_marker = _report_marker(notebook)
    report = verify_report(V3, report_marker)
    notebook.metadata["m2_report_path"] = report_marker
    notebook.metadata["contract_id"] = report["contract_id"]
    notebook.metadata["analysis_id"] = report["analysis_id"]
    notebook.metadata["validation_analysis_id"] = report["upstream_refs"][
        "validation_analysis_id"]
    notebook.metadata["feature_analysis_id"] = report["upstream_refs"][
        "feature_analysis_id"]
    notebook.metadata["eda_analysis_id"] = report["upstream_refs"][
        "eda_analysis_id"]

    temp = TARGET.with_suffix(".tmp.ipynb")
    nbformat.write(notebook, temp)
    os.replace(temp, TARGET)               # reemplazo atómico del cuaderno
    activate_report(V3, report_marker)     # reemplazo atómico del puntero
    print(f"{TARGET.name}: ejecutado completo, 0 errores, "
          f"{len(notebook.cells)} celdas ({ANALYSIS_VERSION})")
    return notebook


if __name__ == "__main__":
    build_and_execute()
