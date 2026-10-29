"""Ejecuta los cuadernos 00 y 01 con kernel privado y caches bajo V3."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
for key, folder in {
    "IPYTHONDIR": ".ipython", "MPLCONFIGDIR": ".mplconfig",
    "JUPYTER_RUNTIME_DIR": ".runtime", "PYTHONPYCACHEPREFIX": ".bytecode",
}.items():
    path = V3 / folder
    path.mkdir(exist_ok=True)
    os.environ[key] = str(path)
os.environ["PYTHONHASHSEED"] = "42"
directory = V3 / ".jupyter/kernels/cm_v3etl"
directory.mkdir(parents=True, exist_ok=True)
(directory / "kernel.json").write_text(json.dumps({
    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
    "display_name": "CM V3 ETL aislado", "language": "python",
}))
os.environ["JUPYTER_PATH"] = str(V3 / ".jupyter")

import nbformat
from nbclient import NotebookClient

LOG = V3 / "audits/notebooks_ejecucion_v3.log"
LOG.parent.mkdir(exist_ok=True)
with LOG.open("w", encoding="utf-8", newline="\n") as log:
    for name in ["00_Manifest_y_Fuentes.ipynb", "01_ETL_Reproducible.ipynb"]:
        path = V3 / "notebooks" / name
        notebook = nbformat.read(path, as_version=4)
        NotebookClient(notebook, timeout=3600, kernel_name="cm_v3etl",
                       resources={"metadata": {"path": str(V3)}}).execute()
        nbformat.write(notebook, path)
        errors = [o for c in notebook.cells if c.cell_type == "code" for o in c.outputs
                  if o.output_type == "error"]
        assert not errors, name
        line = f"{name}: ejecutado completo, 0 errores"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
