"""Genera OMMS2070/1_presentacion/presentacion_ejecutiva_2.html (variante 2).

Arma D y fig_b64 igual que build_entregable.main(), enriquece D con los
datos de la variante 2 (scatter congelado, backtest del Motor 2, esquema
por grupos, sensibilidad PCA), llama build_html(variant=2), aplica el
mismo selfcheck del entregable y escribe con atomic_write.

Uso: conda run -n CM python V3/src/build_presentacion_2.py
"""
import base64
import json
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3 / "src"))

import build_entregable as be  # noqa: E402
import build_dashboard_html as bd  # noqa: E402
from validate_entregable import html_text  # noqa: E402

OUT = (V3.parent / "OMMS2070" / "1_presentacion"
       / "presentacion_ejecutiva_2.html")
SCATTER = V3 / "data" / "presentacion_v2" / "scatter_azar_b30.json"


def main():
    A = be.load_audits()
    D = be.collect_data(A)

    # Enriquecimiento para la variante 2 (todo derivado de sellados).
    sc = json.loads(SCATTER.read_text(encoding="utf-8"))
    D["v2_scatter"] = sc
    D["v2_m2_backtest"] = [r for r in A["08"]["backtest_context"]
                           if r["scheme"] == "fold_spatial_block"]
    D["v2_reg_groupkfold"] = [r for r in A["06"]["regression_means"]
                              if r["fold_scheme"] == "fold_groupkfold_ageb"]
    sens = {s["value"]: s["mean_precision@10"]
            for s in A["05"]["sensitivity"]
            if s.get("parameter") == "variance_target"}
    assert sens.get(0.7) == sens.get(0.9) == 0.38, \
        f"sensibilidad variance_target inesperada: {sens}"
    D["v2_m1_sens_p10"] = sens[0.7]

    fig_b64 = {}
    for name in be.EXISTING_FIGS:
        rel = name.split("_", 1)[0] + "/" + name
        fig_b64[rel] = base64.b64encode(
            (be.FIG_BUILD / rel).read_bytes()).decode()
    for name in be.NEW_FIGS:
        fig_b64[name] = base64.b64encode(
            (be.FIG_BUILD / name).read_bytes()).decode()

    html = bd.build_html(D, fig_b64, variant=2)
    be.selfcheck("html", html_text(html))
    be.atomic_write(OUT, html)
    print("escrito", OUT, len(html.encode("utf-8")), "bytes")


if __name__ == "__main__":
    sys.exit(main())
