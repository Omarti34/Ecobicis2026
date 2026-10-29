"""Genera OMMS2070/1_presentacion/presentacion_ejecutiva_slides.html.

Version en diapositivas 16:9 de la presentacion ejecutiva. Ensambla D y
fig_b64 igual que build_entregable.py main(), anade los datos v2 (scatter
congelado, backtest espacial, sensibilidad PCA), llama a
build_slides_html.build_slides, corre selfcheck("html", ...) y escribe de
forma atomica. NO ejecuta build_entregable.main() ni toca los HTML v1/v2.

Uso: PYTHONPATH=V3/src:. OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE \
     python V3/src/build_presentacion_slides.py
"""
import base64
import json
import sys
from pathlib import Path

import build_entregable as be
import build_dashboard_html  # noqa: F401  (reusado por build_slides_html)
import build_slides_html
from validate_entregable import html_text

ROOT = Path(__file__).resolve().parents[2]
SCATTER_JSON = ROOT / "V3" / "data" / "presentacion_v2" / \
    "scatter_azar_b30.json"
OUT = ROOT / "OMMS2070" / "1_presentacion" / \
    "presentacion_ejecutiva_slides.html"


def enrich(D, A):
    """Anade a D los datos v2 que consume el generador de diapositivas."""
    D["v2_scatter"] = json.loads(SCATTER_JSON.read_text())
    D["v2_m2_backtest"] = [
        r for r in A["08"]["backtest_context"]
        if r["scheme"] == "fold_spatial_block"]
    D["v2_reg_groupkfold"] = [
        r for r in A["06"]["regression_means"]
        if r["fold_scheme"] == "fold_groupkfold_ageb"]
    sens = A["05"]["sensitivity"]
    p = {r["mean_precision@10"] for r in sens
         if r["parameter"] == "variance_target"
         and r["value"] in (0.7, 0.9)}
    assert p == {0.38}, f"P@10 sensibilidad variance_target: {p}"
    D["v2_m1_sens_p10"] = 0.38


def main():
    A = be.load_audits()
    D = be.collect_data(A)
    fig_b64 = {}
    for name in be.EXISTING_FIGS:
        rel = name.split("_", 1)[0] + "/" + name
        fig_b64[rel] = base64.b64encode(
            (be.FIG_BUILD / rel).read_bytes()).decode()
    for name in be.NEW_FIGS:
        fig_b64[name] = base64.b64encode(
            (be.FIG_BUILD / name).read_bytes()).decode()
    enrich(D, A)
    html = build_slides_html.build_slides(D, fig_b64)
    texto = html_text(html)
    be.selfcheck("html", texto)
    be.atomic_write(OUT, html)
    print(f"escrito {OUT} {len(html.encode('utf-8'))} bytes")


if __name__ == "__main__":
    sys.exit(main())
