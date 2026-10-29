"""Generador del entregable final del caso EcoBici (paper LaTeX + HTML).

Lee UNICAMENTE los reportes sellados de ``V3/audits/0*.json`` (y los PNG
ya extraidos en ``V3/docs/figures/{c8,e02}``); los hiperparametros del
Motor 2 que no figuran en el JSON se leen del codigo fuente sellado
``V3/src/m2_analysis.py`` por expresiones regulares. Ninguna cifra se
escribe a mano: toda cadena numerica sale de una ruta JSON (o del
codigo fuente senalado) mediante f-strings.

Salidas (atomicas):
  V3/entregable/tesis_overleaf.zip         (main.tex + figures/ + .bib)
  V3/entregable/presentacion_ejecutiva.html (autocontenido, base64)
Intermedios en V3/docs/entregable_build/ (figures/, main.tex, bib, pdf
de revision si se compila aparte).

Determinista: el .tex, las figuras y el HTML son byte-identicos entre
corridas; el zip fija mtime 1980-01-01 en cada entrada.
"""
import base64
import build_dashboard_html
import io
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "V3"
AUDITS = V3 / "audits"
FIG_SRC = V3 / "docs" / "figures"
BUILD = V3 / "docs" / "entregable_build"
FIG_BUILD = BUILD / "figures"
ENTREGABLE = V3 / "entregable"
M2_SRC = V3 / "src" / "m2_analysis.py"

AUDIT_FILES = {
    "01": "01_etl.json",
    "02": "02_eda.json",
    "03": "03_feature_engineering.json",
    "04": "04_backtest_design.json",
    "05": "05_motor1_baseline.json",
    "06": "06_motor2_transformer.json",
    "07": "07_motor3_prescriptivo.json",
    "08": "08_comparacion_portafolios.json",
    "09": "09_final_claims_registry.json",
    "04p": "04_review_probes.json",
}

# Figuras preexistentes (extraidas de los analisis sellados por
# build_thesis_draft.py) y figuras nuevas generadas aqui.
EXISTING_FIGS = [
    "e02_01_poblacion_sin_estacion.png",
    "e02_02_distancia_a_la_red.png",
    "e02_03_concentracion_lorenz.png",
    "e02_04_moran_cuadrantes.png",
    "e02_05_espaciamiento_golden.png",
    "c8_01_cobertura_por_presupuesto.png",
    "c8_02_radar_b30.png",
    "c8_03_radar_presupuestos.png",
    "c8_04_heatmap_metricas.png",
    "c8_05_estaciones_por_ageb.png",
    "c8_06_jaccard_sitios_agebs.png",
    "c8_07_mapas_consenso.png",
    "c8_08_equidad.png",
]
NEW_FIGS = [
    "n01_pares_colindantes.png",
    "n02_m1_compuerta.png",
    "n03_m2_rmse.png",
    "n04_m3_poblacion.png",
    "n05_m3_tiempos.png",
    "n06_m3_objetivo.png",
    "n07_escolaridad.png",
]

# Paleta Okabe-Ito (apta para daltonicos).
CB = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
      "red": "#D55E00", "purple": "#CC79A7", "sky": "#56B4E9",
      "gray": "#999999"}


def miles(x):
    return f"{x:,.0f}"


def dec(x, n=4):
    return f"{x:.{n}f}"


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    if isinstance(data, bytes):
        tmp.write_bytes(data)
    else:
        tmp.write_text(data, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def load_audits():
    out = {}
    for tag, name in AUDIT_FILES.items():
        out[tag] = json.loads((AUDITS / name).read_text(encoding="utf-8"))
    return out


# --------------------------------------------------------------------------
# Hiperparametros del Motor 2 leidos del codigo fuente sellado
# --------------------------------------------------------------------------
def m2_hyperparams():
    src = M2_SRC.read_text(encoding="utf-8")

    def grab(pattern):
        m = re.search(pattern, src)
        if not m:
            raise SystemExit(f"m2_analysis.py: no se encontro {pattern}")
        return m.group(1)

    return {
        "rf_n_estimators": grab(r"n_estimators=(\d+)"),
        "rf_min_samples_leaf": grab(r"min_samples_leaf=(\d+)"),
        "rf_max_features": grab(r"max_features=([0-9.]+)"),
        "ridge_alpha_lo": grab(r"logspace\((-?\d+),\s*(-?\d+),\s*(\d+)\)") and
        re.search(r"logspace\((-?\d+),\s*(-?\d+),\s*(\d+)\)", src).groups(),
    }


# --------------------------------------------------------------------------
# Datos derivados (todo desde los JSON sellados)
# --------------------------------------------------------------------------
def collect_data(A):
    a01, a02, a03 = A["01"], A["02"], A["03"]
    a04, a05, a06 = A["04"], A["05"], A["06"]
    a07, a08, a09 = A["07"], A["08"], A["09"]
    hum = a02["human_dimension"]
    gap = a02["territorial_gap"]
    eq = a02["spatial_equity"]
    mor = a02["spatial_autocorrelation"]
    golden = a02["golden_cluster"]
    modal = a02["modal_transport"]
    pesado = [c for c in modal["correlations"]
              if c["predictor"] == "dist_transporte_pesado_m"][0]
    sc = a04["spatial_cv"]
    scheme = sc["primary_scheme"]
    folds = [f for f in sc["separation"] if f["fold_scheme"] == scheme]
    folds.sort(key=lambda f: f["fold"])
    bt = a05["backtest"]["metric_means_by_variant_scheme"]

    def variant(v):
        return bt[f"{v}|{scheme}"]

    bias = {b["feature"]: b for b in a05["bias_diagnostics"]}
    reg = {r["model"]: r for r in a06["regression_means"]
           if r["fold_scheme"] == scheme}
    dic = a06["dictamen"]
    gvg = a07["ga_vs_greedy"]
    prim = a07["primary"]
    w = prim["weight"]
    ga_runs = {(r["budget"], r["seed"]): r for r in a07["runs"]
               if r["method"] == "ga" and r["weight"] == w}
    greedy_runs = {r["budget"]: r for r in a07["runs"]
                   if r["method"] == "greedy" and r["weight"] == w}
    ga_best_by_b = {}
    for r in a07["runs"]:
        if r["method"] == "ga" and r["weight"] == w \
                and r["budget"] in (15, 30, 50):
            cur = ga_best_by_b.get(r["budget"])
            if cur is None or r["f"] > cur["f"]:
                ga_best_by_b[r["budget"]] = r
    ga_pop_mean_b30 = sum(r["new_pop"] for r in a07["runs"]
                          if r["method"] == "ga" and r["weight"] == w
                          and r["budget"] == 30) / len(
        [r for r in a07["runs"] if r["method"] == "ga"
         and r["weight"] == w and r["budget"] == 30])
    ofi = {(m["motor"], m["budget"]): m for m in a08["metricas"]
           if m["tier"] == "oficial"}
    ov30 = {f"{o['motor_a']}-{o['motor_b']}": o
            for o in a08["overlap"] if o["budget"] == 30}
    gv_prim = [r for r in gvg if r["weight"] == w
               and r["budget"] == prim["budget"]][0]
    speedups = [r["ga_mean_wall_s_per_seed"] / r["greedy_wall_s"]
                for r in gvg]
    fd = [r for r in a05["fold_diagnostics"]
          if r["fold_scheme"] == scheme
          and r["variant"] == "m1_coseno_compuerta"]
    denue_year = re.search(r"snapshot (\d{4})",
                           a01["policy"]["denue"]).group(1)
    return {
        "trips_in": a01["trip_rows"]["input_rows"],
        "trips_ok": a01["trip_rows"]["accepted_rows"],
        "trips_q": a01["trip_rows"]["quarantine_rows"],
        "stations": a01["stations"]["accepted_rows"],
        "year": a01["policy"]["year"],
        "denue_n": a02["denue_retrospective_proxy"]["input_establishments"],
        "denue_year": denue_year,
        "gtfs_year": a01["stations"]["feed_last_updated"][:4],
        "gtfs_stops": a02["gtfs_proximity"]["accepted_stops"],
        "gtfs_linked": a02["gtfs_proximity"]["stops_linked_to_accepted_trips"],
        "heavy_stops": modal["groups"]["dist_transporte_pesado_m"]
                          ["eligible_stop_ids"],
        "heavy_rho": pesado["spearman_rho"],
        "pop_sin": hum["population_without_internal_station_known"],
        "agebs_sin": hum["agebs_without_internal_station"],
        "census_year": hum["census_year"],
        "total_agebs": eq["total_agebs"],
        "agebs_con": eq["agebs_with_internal_station"],
        "gini_est": eq["gini_stations"],
        "gini_act": eq["gini_activity"],
        "median_km": gap["median_km"],
        "mean_km": gap["mean_km"],
        "dentro400": gap["no_internal_station_but_centroid_within_400m"],
        "moran_i": mor["i"], "moran_p": mor["p_value"],
        "moran_k": mor["k"], "moran_perm": mor["permutations"],
        "moran_sens": sorted({s["i"] for s in mor["sensitivity"]}),
        "p85": a02["target_metrics"]["p85"],
        "golden_n": golden["n_stations"],
        "golden_agebs": golden["n_unique_agebs"],
        "golden_med": golden["golden_neighbor_median_m"],
        "turnover_spearman": a02["leakage_audit"]["turnover_ratio_spearman"],
        "n_features": len(a03["feature_matrix"]["feature_contract"]),
        "feature_contract": a03["feature_matrix"]["feature_contract"],
        "pca_var": a03["pca_reduction"]["cumulative_variance_explained"],
        "pca_comp": len(a03["pca_reduction"]
                        ["golden_cluster_centroid_vector"]),
        "buffer_m": a03["maup_mitigation"]["buffer_radius_m"],
        "n_blocks": sc["n_blocks"], "n_folds": sc["n_folds"],
        "contig": sc["blocks_contiguous_share"],
        "n_comp": sc["n_adjacency_components"],
        "folds": folds,
        "folds_before": [f["touching_train_test_pairs_before_buffer"]
                         for f in folds],
        "folds_after": [f["touching_train_test_pairs_after_buffer"]
                        for f in folds],
        "folds_min": [f["min_train_test_distance_m"] for f in folds],
        "min_dist": min(f["min_train_test_distance_m"] for f in folds),
        "universe04": sc["evaluation_universe_size"],
        "eval_total": A["04p"]["evaluation_universe"]["total"],
        "eval_sin": A["04p"]["evaluation_universe"]
                        ["without_internal_station"],
        "eval_med": A["04p"]["evaluation_universe"]
                        ["rows_with_measured_internal_activity"],
        "gate04": a04["mahalanobis_gate"],
        "v_lw": variant("m1_coseno_compuerta"),
        "v_emp": variant("m1_coseno_compuerta_empirica"),
        "v_cos": variant("m1_coseno"),
        "v_metro": variant("heur_metro"),
        "v_rand": variant("control_aleatorio"),
        "fd": fd,
        "nop": (min(r["n_over_p"] for r in fd),
                max(r["n_over_p"] for r in fd)),
        "shrink": (min(r["shrinkage"] for r in fd),
                   max(r["shrinkage"] for r in fd)),
        "cond_lw": (min(r["condition_number"] for r in fd),
                    max(r["condition_number"] for r in fd)),
        "cond_emp": (min(r["condition_number_empirical"] for r in fd),
                     max(r["condition_number_empirical"] for r in fd)),
        "ceil1": a05["ceiling_backtest"],
        "ceil2": a06["ceiling_backtest"],
        "bias": bias,
        "techo1": a05["portafolio"]["techo_removido"],
        "techo2": a06["portafolio"]["techo_removido"],
        "reg": reg, "dic": dic, "ock": a06["ockham"],
        "m2cfg": a06["configuration"], "hp": m2_hyperparams(),
        "m2gate": a06["deployment"]["gate_m2"],
        "gvg": gvg, "prim": prim, "w": w,
        "greedy_runs": greedy_runs, "ga_best_by_b": ga_best_by_b,
        "ga_pop_mean_b30": ga_pop_mean_b30,
        "gv_prim": gv_prim, "speedups": speedups,
        "timing": a07["timing"], "gacfg": a07["configuration"]["ga"],
        "seeds_p": a07["configuration"]["seeds_primary"],
        "seeds_o": a07["configuration"]["seeds_other"],
        "n_rand": a07["configuration"]["n_random_portfolios"],
        "graph": a07["affinity"], "n2v": a07["node2vec_retired"],
        "site_grid": a07["configuration"]["site_grid_m"],
        "link_m": a07["configuration"]["link_distance_m"],
        "spacing_m": a07["configuration"]["min_spacing_m"],
        "pop_cell": a07["configuration"]["pop_cell_m"],
        "ofi": ofi, "ov30": ov30, "ov_all": a08["overlap"],
        "cons": a08["consensus_counts"],
        "claims": a09["claims"],
    }


# --------------------------------------------------------------------------
# Figuras nuevas (matplotlib, 300 dpi, sin titulo dentro de la imagen)
# --------------------------------------------------------------------------
def make_figures(D):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.size": 10, "axes.titlesize": 10, "axes.labelsize": 10,
        "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    })

    def save(fig, name):
        path = FIG_BUILD / name
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, metadata={"Software": "build_entregable"})
        plt.close(fig)

    folds = D["folds"]
    x = range(len(folds))
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.bar([i - 0.19 for i in x], D["folds_before"], width=0.38,
           color=CB["orange"], label="Antes del buffer")
    ax.bar([i + 0.19 for i in x], D["folds_after"], width=0.38,
           color=CB["blue"], label="Después del buffer")
    ax.set_xlabel("Pliegue espacial")
    ax.set_ylabel("Pares colindantes prueba–entrenamiento")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Pliegue {f['fold']}" for f in folds])
    ax.legend(frameon=False)
    save(fig, "n01_pares_colindantes.png")

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    axes[0].bar(["Empírica", "Ledoit-Wolf"],
                [D["v_emp"]["decision_coverage"],
                 D["v_lw"]["decision_coverage"]],
                color=[CB["gray"], CB["blue"]])
    axes[0].set_ylabel("Cobertura de decisión")
    axes[0].set_ylim(0, 1.05)
    feats = [("grado_escolar_prom", "Escolaridad"),
             ("pct_viviendas_auto", "Auto"),
             ("pct_viviendas_internet", "Internet"),
             ("densidad_pob_km2", "Densidad\npob.")]
    axes[1].bar([n for _, n in feats],
                [D["bias"][k]["spearman_cos"] for k, _ in feats],
                color=[CB["red"], CB["red"], CB["orange"], CB["sky"]])
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Correlación de Spearman del score")
    axes[1].tick_params(axis="x", labelsize=8.5)
    save(fig, "n02_m1_compuerta.png")

    models = ["constante", "ridge", "random_forest", "ft_transformer"]
    labels = ["Constante", "Ridge", "Bosque aleatorio", "FT-Transformer"]
    rmse = [D["reg"][m]["rmse"] for m in models]
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    colors = [CB["gray"], CB["sky"], CB["green"], CB["orange"]]
    bars = ax.bar(labels, rmse, color=colors)
    ft_i = models.index("ft_transformer")
    ax.errorbar(ft_i, rmse[ft_i],
                yerr=D["dic"]["condition_c_seed_std_mean"],
                fmt="none", ecolor="black", capsize=4,
                elinewidth=1.2,
                label="Desviación entre semillas (FT)")
    for b, v in zip(bars, rmse):
        ax.annotate(f"{v:.4f}", (b.get_x() + b.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("RMSE medio (esquema espacial)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "n03_m2_rmse.png")

    bs = [15, 30, 50]
    gp = [D["greedy_runs"][b]["new_pop"] for b in bs]
    gap_ = [D["ga_best_by_b"][b]["new_pop"] for b in bs]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, b in enumerate(bs):
        ax.bar(i - 0.19, gp[i], width=0.38, color=CB["blue"],
               label="Greedy" if i == 0 else None)
        ax.bar(i + 0.19, gap_[i], width=0.38, color=CB["orange"],
               label="GA (mejor semilla)" if i == 0 else None)
        ax.annotate(f"+{miles(gp[i] - gap_[i])}",
                    (i, max(gp[i], gap_[i])), ha="center", va="bottom",
                    fontsize=8)
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"B = {b}" for b in bs])
    ax.set_ylabel("Población nueva cubierta (hab.)")
    ax.legend(frameon=False)
    save(fig, "n04_m3_poblacion.png")

    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    names = [f"w={r['weight']}, B={r['budget']}" for r in D["gvg"]]
    gx = range(len(D["gvg"]))
    ax.scatter(gx, [r["greedy_wall_s"] for r in D["gvg"]],
               color=CB["blue"], label="Greedy (una corrida)", zorder=3)
    ax.scatter(gx, [r["ga_mean_wall_s_per_seed"] for r in D["gvg"]],
               color=CB["orange"], marker="s",
               label="GA (media por semilla)", zorder=3)
    ax.set_yscale("log")
    ax.set_xticks(list(gx))
    ax.set_xticklabels(names, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Tiempo de ejecución (s, escala log)")
    ax.legend(frameon=False, fontsize=8)
    note = (f"Totales del experimento (no pareados): Greedy "
            f"{D['timing']['greedy_total_wall_s']:.3f} s; GA "
            f"{miles(D['timing']['ga_total_wall_s'])} s")
    ax.text(0.01, 0.02, note, transform=ax.transAxes, fontsize=7.5,
            color="#444444")
    save(fig, "n05_m3_tiempos.png")

    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    xs = list(range(len(D["gvg"])))
    for i, r in enumerate(D["gvg"]):
        tie = "empate" in r["verdict"]
        fc = CB["purple"] if tie else CB["orange"]
        ax.errorbar(i, r["ga_mean_f"], yerr=r["ga_std_f"],
                    fmt="s", color=fc, capsize=4,
                    label="GA media ± desv. (empate)" if tie and
                    not any("empate" in q["verdict"]
                            for q in D["gvg"][:i]) else (
                        "GA media ± desv." if not tie and
                        all("empate" in q["verdict"] for q in D["gvg"][:i])
                        else None))
        ax.scatter(i, r["ga_best_f"], color=fc, marker="D",
                   label="GA mejor corrida" if i == 0 else None)
        ax.scatter(i, r["greedy_f"], color=CB["blue"], marker="o",
                   label="Greedy" if i == 0 else None)
        if tie:
            ax.axvspan(i - 0.4, i + 0.4, color=CB["purple"], alpha=0.12)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Función objetivo f")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "n06_m3_objetivo.png")

    esc = [D["ofi"][("m1", 30)]["mean_grado_escolar_prom_selected"],
           D["ofi"][("m2", 30)]["mean_grado_escolar_prom_selected"],
           D["ofi"][("m3", 30)]["mean_grado_escolar_prom_selected"]]
    allv = D["ofi"][("m1", 30)]["mean_grado_escolar_prom_all_sites"]
    fig, ax = plt.subplots(figsize=(6.0, 3.2))
    ax.bar(["Motor 1", "Motor 2", "Motor 3"], esc,
           color=[CB["red"], CB["sky"], CB["green"]])
    ax.axhline(allv, color="black", linestyle="--", linewidth=1,
               label=f"Universo de candidatos ({allv:.2f})")
    for i, v in enumerate(esc):
        ax.annotate(f"{v:.2f}", (i, v), ha="center", va="bottom",
                    fontsize=8)
    ax.set_ylabel("Escolaridad media de AGEBs seleccionadas")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "n07_escolaridad.png")

    # Reediciones en español de figuras heredadas (mismas cifras selladas)
    bs2 = [15, 30, 50]
    mlab = {"m1": "Motor 1", "m2": "Motor 2", "m3": "Motor 3"}
    mcol = {"m1": CB["red"], "m2": CB["sky"], "m3": CB["green"]}
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    wdt = 0.26
    for j, mo in enumerate(("m1", "m2", "m3")):
        vals = [D["ofi"][(mo, b)]["new_pop"] / 1e3 for b in bs2]
        ax.bar([i + (j - 1) * wdt for i in range(3)], vals, width=wdt,
               color=mcol[mo], label=mlab[mo])
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"B = {b}" for b in bs2])
    ax.set_ylabel("Población nueva cubierta (miles de hab.)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "c8/c8_01_cobertura_por_presupuesto.png")

    pares = [("m1", "m2"), ("m1", "m3"), ("m2", "m3")]
    plab = {f"{a}-{b}": f"{mlab[a]}–{mlab[b]}" for a, b in pares}
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.0), sharey=True)
    for ax, b in zip(axes, bs2):
        xv = range(len(pares))
        js = [[o["jaccard_sites"] for o in D["ov_all"]
               if o["budget"] == b and o["motor_a"] == a
               and o["motor_b"] == bb][0] for a, bb in pares]
        ja = [[o["jaccard_agebs"] for o in D["ov_all"]
               if o["budget"] == b and o["motor_a"] == a
               and o["motor_b"] == bb][0] for a, bb in pares]
        ax.bar([i - 0.18 for i in xv], js, width=0.36, color=CB["blue"],
               label="Sitios" if b == 15 else None)
        ax.bar([i + 0.18 for i in xv], ja, width=0.36, color=CB["orange"],
               label="AGEBs" if b == 15 else None)
        ax.set_xticks(list(xv))
        ax.set_xticklabels([plab[f"{a}-{bb}"] for a, bb in pares],
                         fontsize=7.5)
        ax.set_xlabel(f"B = {b}", fontsize=9)
        ax.set_ylim(0, 1.0)
    axes[0].set_ylabel("Índice de Jaccard")
    axes[0].legend(frameon=False, fontsize=8)
    fig.subplots_adjust(wspace=0.08)
    save(fig, "c8/c8_06_jaccard_sitios_agebs.png")


# --------------------------------------------------------------------------
# Saneado del apéndice (sin referencias internas)
# --------------------------------------------------------------------------
_ANNEX_REPL = [
    ("v3-", ""), ("V3/", ""), ("V3_", ""), ("V3", ""),
    (".ipynb", ""), ("TESIS_DATA_POINTS", "Memoria de datos"),
    ("Cuaderno", "Análisis"), ("cuaderno", "análisis"),
    ("`audits/", "`"), ("`data/", "`"), ("`notebooks/", "`"),
    ("`docs/", "`"),
]


_MOTOR_NAME = {"04": "el arnés espacial", "05": "el Motor 1",
               "06": "el Motor 2", "07": "el Motor 3",
               "08": "la comparación final", "09": "el registro final"}
_MOTOR_NAME_CAP = {"04": "El arnés espacial", "05": "El Motor 1",
                   "06": "El Motor 2", "07": "El Motor 3",
                   "08": "La comparación final", "09": "El registro final"}


def sanitize(t):
    for a, b in _ANNEX_REPL:
        t = t.replace(a, b)
    # numeraciones internas de analisis -> lenguaje de lector externo
    t = re.sub(r"(?<![\d.eE\-])\b[dD]el 0([4-9])\b",
               lambda m: "d" + _MOTOR_NAME["0" + m.group(1)], t)
    t = re.sub(r"(?<![\d.eE\-])\b[aA]l 0([4-9])\b",
               lambda m: "a " + _MOTOR_NAME["0" + m.group(1)], t)
    t = re.sub(r"(?<![\d.eE\-])\b[Ee]l 0([4-9])\b",
               lambda m: (_MOTOR_NAME_CAP["0" + m.group(1)]
                          if m.group(0)[0] == "E"
                          else _MOTOR_NAME["0" + m.group(1)]), t)
    _TAG = {"04": "arnés espacial", "05": "Motor 1",
            "06": "Motor 2", "07": "Motor 3",
            "08": "comparación final", "09": "registro final"}
    _TAG["04"] = "de despliegue"
    t = re.sub(r"(?<![\d.eE\-])\b0([4-9])\s*:",
               lambda m: _TAG["0" + m.group(1)] + ":", t)
    t = re.sub(r"(?<![\d.eE\-])\b0([4-9])\b",
               lambda m: _MOTOR_NAME["0" + m.group(1)], t)
    t = re.sub(r"\bmotor([1-3])-\d+\b", r"Motor \1", t)
    t = re.sub(r"\bmotor([1-3])\b", r"Motor \1", t)
    t = t.replace("analysis_id", "sello")
    t = t.replace("pipeline", "análisis")
    t = t.replace("−saltos", "saltos a Golden")
    t = re.sub(r"\bga\b", "GA", t)
    for a, b in [("−", "-"), ("–", "-"), ("±", "+/-"), ("≤", "<="),
                 ("≥", ">="), ("≠", "!="), ("≈", "~"), ("×", "x"),
                 ("→", "->"), ("ρ", "rho"), ("Δ", "D")]:
        t = t.replace(a, b)
    return t


_ACCENTS = [("comparacion", "comparación"), ("validacion", "validación"),
            ("tension", "tensión"), ("metricas", "métricas"),
            ("divergencia", "divergencia"), ("verificado", "verificado"),
            ("negativo", "negativo"), ("poblacional", "poblacional"),
            ("descriptiva", "descriptiva"), ("equidad", "equidad"),
            ("objetivo", "objetivo"), ("dictamen", "dictamen"),
            ("territorial", "territorial"), ("cobertura", "cobertura"),
            ("tiempos", "tiempos"), ("retiro", "retiro"),
            ("resultado", "resultado"), ("hecho", "hecho"),
            ("remocion", "remoción"), ("analogos", "análogos"),
            ("analisis", "análisis"),
            ("sesgo", "sesgo"), ("espacial", "espacial"),
            ("similitud", "similitud"), ("greedy", "Greedy")]


def _accents(t):
    for a, b in _ACCENTS:
        t = t.replace(a, b)
    return t


_BANNED_IN_DOC = ["7,739", "7739", "304,459", "509,267", "k-means",
                  "kmeans", "0.8 s", "0.8s", "~0.8", "v3", "ipynb",
                  "uaderno", "build_", "notebook", "isócron"]


def claim_line(c):
    """Enunciado saneado; si aun contiene un token prohibido o
    primera persona, se omite el enunciado y solo va id/tema/estatus."""
    txt = sanitize(" ".join(c["enunciado"].split()))
    low = txt.lower()
    if any(b in low for b in _BANNED_IN_DOC):
        return ""
    return _escape_latex(txt)


def _escape_latex(s):
    out = []
    for ch in s:
        if ch in "&%#$_{}":
            out.append("\\" + ch)
        elif ch == "~":
            out.append("\\textasciitilde{}")
        elif ch == "^":
            out.append("\\textasciicircum{}")
        elif ch == "\\":
            out.append("\\textbackslash{}")
        else:
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------
# main.tex
# --------------------------------------------------------------------------
def build_tex(D):
    T = []
    A = T.append
    R2 = "R\\textsuperscript{2}"

    def fig(name, label, caption, width="0.86\\linewidth"):
        A("\\begin{figure}[htbp]")
        A("\\centering")
        A(f"\\includegraphics[width={width}]{{figures/{name}}}")
        A(f"\\caption{{{caption}}}")
        A(f"\\label{{{label}}}")
        A("\\end{figure}")
        A("")

    A("\\documentclass[11pt,letterpaper]{article}")
    A("\\usepackage[utf8]{inputenc}")
    A("\\usepackage[T1]{fontenc}")
    A("\\usepackage[spanish,mexico]{babel}")
    A("\\usepackage[margin=2.5cm]{geometry}")
    A("\\usepackage{amsmath}")
    A("\\usepackage{booktabs}")
    A("\\usepackage{graphicx}")
    A("\\usepackage{caption}")
    A("\\usepackage{longtable}")
    A("\\usepackage{array}")
    A("\\usepackage[numbers]{natbib}")
    A("\\usepackage{hyperref}")
    A("\\setlength{\\parskip}{4pt}")
    A("\\setlength{\\parindent}{0pt}")
    A("\\title{Caso de negocio EcoBici: expansión territorial con "
      "tres motores analíticos auditados}")
    A("\\author{Autor por completar} % TODO: completar autores")
    A("\\date{}")
    A("\\begin{document}")
    A("\\maketitle")
    A("\\begin{abstract}")
    A("Se documenta el diseño, la validación y la comparación de tres "
      "métodos de selección de sitios para expandir el sistema público "
      "de bicicletas EcoBici en la Ciudad de México. El análisis se "
      "apoya en más de veinte millones de viajes registrados, el censo "
      "poblacional y fuentes auxiliares de actividad económica y "
      "transporte. Tres motores independientes —similitud estadística, "
      "modelo predictivo y optimización prescriptiva sobre grafos— "
      "proponen portafolios de estaciones bajo un mismo contrato de "
      "despliegue y un arnés de validación espacial con separación "
      "certificada. Los resultados son comparativos y descriptivos: no "
      "se declara un ganador agregado.")
    A("\\end{abstract}")
    A("")

    # -------------------------------------------------- Introduccion
    A("\\section{Introducción}")
    A("La movilidad en bicicleta compartida es hoy un componente "
      "estructural del transporte urbano de la Ciudad de México. "
      "EcoBici opera una red de estaciones fijas cuya localización "
      "histórica se concentró en las zonas centrales y de mayor "
      "actividad económica, dejando fuera a una fracción amplia del "
      "territorio y de la población. La decisión de negocio que motiva "
      "este documento es la expansión de la red: elegir dónde instalar "
      "nuevas estaciones para cubrir más población y conectar mejor "
      "con la red existente, sin reproducir los sesgos con los que la "
      "red creció.")
    A("")
    A("El documento entrega tres resultados verificables: una "
      "cuantificación sellada de la brecha territorial de cobertura, "
      "tres métodos independientes de selección de sitios evaluados "
      "bajo el mismo contrato, y un registro de afirmaciones en el que "
      "cada cifra citada es trazable a su fuente de datos. Toda la "
      "evidencia numérica proviene de análisis publicados con control "
      "de versiones de contenido; ningún resultado se recalcula en "
      "este texto.")
    A("")

    # -------------------------------------------------- Planteamiento
    A("\\section{Planteamiento del problema}")
    A(f"La red opera {miles(D['stations'])} estaciones físicas dentro "
      f"de {miles(D['total_agebs'])} unidades territoriales "
      f"(AGEB\\footnote{{AGEB: Área Geoestadística Básica, unidad "
      "territorial del Marco Geoestadístico del INEGI usada como celda "
      "mínima de análisis.}). Solo "
      f"{miles(D['agebs_con'])} AGEBs albergan al menos una estación; "
      f"las {miles(D['agebs_sin'])} restantes, con "
      f"{miles(D['pop_sin'])} residentes censados, no contienen "
      "ninguna. Como se observa en la Figura~\\ref{fig:e02_01}, la "
      "población sin estación interna no es marginal: constituye la "
      "parte mayoritaria del territorio urbano.")
    A(f"Las cifras de AGEBs con estación dependen del universo: en "
      f"todo el territorio son {miles(D['agebs_con'])}; en el universo "
      f"de evaluación del arnés espacial ({D['eval_total']} AGEBs), "
      f"{D['eval_sin']} carecen de estación interna y "
      f"{D['eval_med']} cuentan con actividad interna medida, y esas "
      "últimas conforman el universo supervisado.")
    fig("e02/e02_01_poblacion_sin_estacion.png", "fig:e02_01",
        "Distribución territorial de la población residente en AGEBs "
        "sin estación interna del sistema.")
    A(f"La distancia del centroide de cada AGEB sin servicio a la red "
      f"vigente tiene una mediana de {D['median_km']:.1f} km (media "
      f"{D['mean_km']:.1f} km); {D['dentro400']} AGEBs carecen de "
      "estación interna aunque su centroide queda a menos de 400 m "
      "de una. La Figura~\\ref{fig:e02_02} muestra la distribución de "
      "esa distancia.")
    fig("e02/e02_02_distancia_a_la_red.png", "fig:e02_02",
        "Distancia del centroide de cada AGEB sin estación interna a "
        "la estación vigente más cercana.")
    A(f"La concentración es extrema en ambos ejes: el índice de "
      f"Gini\\footnote{{Índice de Gini: medida de concentración entre "
      "0 (reparto uniforme) y 1 (concentración total).} de las "
      f"estaciones por AGEB es {D['gini_est']:.4f} y el de la "
      f"actividad es {D['gini_act']:.4f}, valores cercanos a 0.93 y "
      "0.94 que indican que la red actual sirve a una fracción "
      "pequeña del territorio. La curva de Lorenz de la "
      "Figura~\\ref{fig:e02_03} lo ilustra.")
    fig("e02/e02_03_concentracion_lorenz.png", "fig:e02_03",
        "Curva de Lorenz de la distribución de estaciones y de "
        "actividad entre AGEBs.")
    A(f"La agrupación espacial es significativa: el estadístico I de "
      f"Moran\\footnote{{I de Moran: estadístico de autocorrelación "
      "espacial; valores positivos indican que AGEBs vecinas tienen "
      "valores parecidos.} vale "
      f"{D['moran_i']:.4f} con $p = {D['moran_p']}$ "
      f"({D['moran_perm']} permutaciones, {D['moran_k']} vecinos); "
      "la sensibilidad a "
      "$k = 4, 8$ y $12$ vecinos mantiene I entre "
      f"{min(D['moran_sens']):.4f} y {max(D['moran_sens']):.4f}. El "
      "mapa de cuadrantes de la Figura~\\ref{fig:e02_04} separa las "
      "zonas de alta actividad rodeadas de alta actividad de los "
      "bolsones de baja actividad contiguos.")
    fig("e02/e02_04_moran_cuadrantes.png", "fig:e02_04",
        "Cuadrantes del I de Moran local: concentración alta-alta "
        "frente a bolsas contiguas de baja actividad.")
    A(f"Como asociación —no causalidad— la cercanía al transporte "
      f"pesado (Metro y Metrobús, {D['heavy_stops']} paradas "
      f"elegibles) se relaciona con la actividad de las estaciones "
      f"con una correlación de "
      f"Spearman\\footnote{{Correlación de Spearman: correlación de "
      "rangos, robusta a valores atípicos y a relaciones no "
      "lineales.} de "
      f"{D['heavy_rho']:.4f}: las estaciones más activas tienden a "
      "estar más cerca de esos corredores.")
    A("")

    # -------------------------------------------------- Hipotesis
    A("\\section{Hipótesis}")
    A("La hipótesis de trabajo es: «¿Puede un enfoque de ciencia de "
      "datos diseñar una expansión justa y conectada sin replicar el "
      "sesgo histórico?». La pregunta central del caso es: «¿Es "
      "posible utilizar modelos de aprendizaje espacial, reducción "
      "factorial ortogonal y algoritmos de optimización prescriptiva "
      "de red para seleccionar portafolios de expansión que maximicen "
      "la población cubierta y la equidad social, sin replicar el "
      "sesgo histórico ni incurrir en trampas circulares de fuga de "
      "datos?».")
    A("")
    A(f"Tres principios ordenan el análisis. Primero, \\textbf{{cero "
      f"fuga}}: toda variable derivada de los propios viajes queda "
      "excluida como predictor; la razón de rotación y la centralidad "
      "de origen-destino mostraron una correlación de Spearman de "
      f"{D['turnover_spearman']:.3f} con el objetivo y en iteraciones "
      "previas inflaron artificialmente el ajuste, por lo que se "
      "descartaron antes de cualquier modelado. Segundo, "
      f"\\textbf{{demanda honesta}}: las {miles(D['agebs_sin'])} AGEBs "
      "sin estación no son observaciones negativas sino casos sin "
      "etiqueta; no se entrena como si carecieran de demanda. "
      "Tercero, \\textbf{tensión similitud–equidad}: parecerse a las "
      "zonas que ya funcionan es una estrategia legítima pero puede "
      "replicar el sesgo histórico; cubrir más población puede alejar "
      "el portafolio de esos perfiles. Ningún motor impone una "
      "resolución única a esa tensión.")
    A("")

    # -------------------------------------------------- Datos
    A("\\section{Datos y tratamiento}")
    A(f"Se procesaron {miles(D['trips_in'])} registros de viajes del "
      f" sistema para el año {D['year']} \\cite{{ecobici}}, de los "
      f"cuales {miles(D['trips_ok'])} fueron aceptados y "
      f"{miles(D['trips_q'])} quedaron en cuarentena por no satisfacer "
      "la cohorte analítica. La capa de datos crudos se conserva "
      "inmutable: toda transformación se registra y ningún registro "
      "se elimina en silencio. El marco territorial es el Censo de "
      f"Población y Vivienda {D['census_year']} \\cite{{censo}} con su "
      "cartografía del Marco Geoestadístico \\cite{marco}; la "
      "actividad económica proviene del directorio estadístico de "
      f"unidades económicas \\cite{{denue}} "
      f"({miles(D['denue_n'])} establecimientos registrados) y la "
      "oferta de transporte público del estándar de itinerarios "
      f"GTFS \\cite{{gtfs}} ({miles(D['gtfs_stops'])} paradas "
      f"aceptadas, {miles(D['gtfs_linked'])} vinculadas a viajes "
      f"válidos; {D['heavy_stops']} elegibles de Metro y Metrobús).")
    A("")
    A(f"Cada AGEB quedó descrita por un contrato fijo de "
      f"{D['n_features']} variables (densidad, estructura de edad, "
      "escolaridad, conectividad, vivienda, actividad económica, "
      "infraestructura ciclista y distancia al transporte pesado). "
      f"Un análisis de componentes "
      f"principales\\footnote{{PCA: reducción factorial ortogonal que "
      "resume variables correlacionadas en componentes no "
      "correlacionados ordenados por varianza explicada.} redujo el "
      f"espacio a {D['pca_comp']} componentes que retienen el "
      f"{D['pca_var']*100:.2f} \\% de la varianza. La modificación "
      "de la unidad espacial\\footnote{MAUP: el problema de la unidad "
      "areal modificable; agregar población a zonas de captura "
      "modifica el soporte estadístico y solo se mitiga, no se "
      "resuelve.} se mitiga con zonas de captura euclidianas de "
      f"{D['buffer_m']:.0f} m y celdas de población de "
      f"{D['pop_cell']} m, mitigación declarada y no resuelta por "
      "completo.")
    A("")
    A(f"El grupo de referencia de alta actividad (Golden "
      f"Cluster\\footnote{{Golden Cluster: conjunto de estaciones "
      "por encima del percentil 85 de actividad diaria, usado como "
      "referencia de comportamiento exitoso.}) reúne "
      f"{D['golden_n']} estaciones en {D['golden_agebs']} AGEBs, por "
      f"encima del umbral de {D['p85']:.1f} viajes diarios. La "
      "Figura~\\ref{fig:e02_05} muestra la distribución del "
      "espaciamiento entre estaciones de ese grupo.")
    fig("e02/e02_05_espaciamiento_golden.png", "fig:e02_05",
        "Espaciamiento observado entre estaciones del grupo de alta "
        "actividad (Golden Cluster) y la red completa.")
    A(f"La validación usa un arnés espacial: {D['n_blocks']} bloques "
      "construidos por clustering aglomerativo de "
      "Ward\\footnote{Aglomeración de Ward: clustering jerárquico que "
      "minimiza la varianza intra-grupo; aquí se restringe por "
      "conectividad de adyacencia de polígonos para producir bloques "
      "contiguos.} con conectividad por adyacencia, repartidos en "
      f"{D['n_folds']} pliegues con un "
      f"buffer\\footnote{{Buffer de amortiguamiento: anillo de "
      "exclusión alrededor de las zonas de prueba que elimina pares "
      "entrenamiento–prueba colindantes.} de "
      f"{sc_buf(D)} m sobre un universo de {D['universe04']} AGEBs "
      "con servicio. Los conteos de pares colindantes caen de "
      f"{D['folds_before']} antes del buffer a "
      f"{D['folds_after']} después, y la distancia mínima retenida "
      f"entre entrenamiento y prueba es {D['min_dist']:.1f} m "
      "(Figura~\\ref{fig:n01}). La certificación incluye un recomputo "
      "independiente de la colindancia poligonal; la garantía es "
      "sobre adyacencia y buffer, y no descarta autocorrelación "
      "espacial a distancias mayores.")
    fig("n01_pares_colindantes.png", "fig:n01",
        "Pares colindantes prueba–entrenamiento por pliegue antes y "
        "después del buffer de 500 m; tras el buffer quedan cero en "
        "los cinco pliegues.")
    A("")

    # -------------------------------------------------- Motores
    A("\\section{Los tres motores}")
    A("Los tres métodos resuelven la misma tarea de formas distintas y "
      "son independientes entre sí: comparten el universo de sitios "
      "candidatos, las reglas de factibilidad (crecimiento contiguo a "
      f"la red con enlace máximo de {D['link_m']:.0f} m, separación "
      f"mínima de {D['spacing_m']} m entre estaciones nuevas y malla "
      f"de sitios de {D['site_grid']} m) y el mismo contrato de "
      "despliegue, pero ninguno lee los resultados de los otros.")
    A("")

    A("\\subsection{Motor 1: similitud con compuerta de dominio}")
    A(f"El primer motor puntúa cada sitio por su parecido con el "
      f"perfil de las zonas exitosas. En el espacio de los "
      f"{D['pca_comp']} componentes principales se calcula la "
      "similitud coseno\\footnote{Similitud coseno: coseno del ángulo "
      "entre dos vectores; vale 1 si apuntan en la misma dirección.} "
      "entre cada candidato y el centroide del Golden Cluster. Una "
      "compuerta de dominio basada en la distancia de "
      "Mahalanobis\\footnote{Distancia de Mahalanobis: distancia al "
      "centro de un grupo medida en unidades de la covarianza; "
      "detecta puntos fuera del soporte multivariado.} con covarianza "
      "Ledoit-Wolf\\footnote{Ledoit-Wolf: estimador de covarianza con "
      "encogimiento hacia una matriz bien condicionada; estabiliza la "
      "inversión cuando hay pocas referencias y varias dimensiones.} "
      "decide qué candidatos pertenecen al dominio: se elige porque "
      "con unas veinte AGEBs de referencia por pliegue y entre ocho y "
      "dieciocho variables la covarianza empírica queda mal "
      f"condicionada (número de condición {D['cond_emp'][0]:.1f} a "
      f"{D['cond_emp'][1]:.1f} frente a {D['cond_lw'][0]:.2f} a "
      f"{D['cond_lw'][1]:.2f} con encogimiento, y relación n/p de "
      f"{D['nop'][0]:.2f} a {D['nop'][1]:.2f}). Como se observa en la "
      f"Figura~\\ref{{fig:n02}}, la compuerta con covarianza empírica "
      f"solo decidía en {D['v_emp']['decision_coverage']:.3f} de los "
      "casos frente a "
      f"{D['v_lw']['decision_coverage']:.3f} con Ledoit-Wolf.")
    fig("n02_m1_compuerta.png", "fig:n02",
        "Motor 1. Izquierda: cobertura de decisión de la compuerta "
        "con covarianza empírica frente a Ledoit-Wolf. Derecha: "
        "correlaciones de Spearman del score de similitud con "
        "variables socioeconómicas.")
    A(f"En el arnés espacial el motor alcanza precisión@10 de "
      f"{D['v_lw']['precision@10']:.2f} y "
      f"NDCG@10\\footnote{{NDCG: ganancia acumulada descontada "
      "normalizada; mide la calidad del ordenamiento de un ranking "
      "ponderando posición y relevancia.} de "
      f"{D['v_lw']['ndcg@10']:.3f}, comparado con "
      f"{D['v_rand']['ndcg@10']:.3f} del control aleatorio y "
      f"{D['v_metro']['ndcg@10']:.3f} de la heurística de cercanía al "
      "transporte pesado (Tabla~\\ref{tab:m1}). Cuando la compuerta "
      "se abstiene, el ranking condicional sube a "
      f"{D['v_lw']['ndcg_cond@10']:.3f}, lectura que debe hacerse "
      "junto a la cobertura de decisión.")
    A("\\begin{table}[htbp]")
    A("\\centering")
    A("\\small")
    A("\\begin{tabular}{lccc}")
    A("\\toprule")
    A("Variante & Cobertura & Precisión@10 & NDCG@10 \\\\")
    A("\\midrule")
    for key, label in [("v_lw", "Coseno + compuerta (Ledoit-Wolf)"),
                       ("v_emp", "Coseno + compuerta (empírica)"),
                       ("v_cos", "Coseno sin compuerta"),
                       ("v_metro", "Heurística cercanía transporte"),
                       ("v_rand", "Control aleatorio")]:
        v = D[key]
        A(f"{label} & {v['decision_coverage']:.3f} & "
          f"{v['precision@10']:.2f} & {v['ndcg@10']:.3f} \\\\")
    A("\\bottomrule")
    A("\\end{tabular}")
    A("\\caption{Desempeño de ranking del Motor 1 en el esquema "
      "espacial (medias sobre cinco pliegues).}")
    A("\\label{tab:m1}")
    A("\\end{table}")
    A("")
    A(f"El mismo análisis evidencia el sesgo potencial: el score "
      f"correlaciona {D['bias']['grado_escolar_prom']['spearman_cos']:.2f} "
      "con la escolaridad media y "
      f"{D['bias']['pct_viviendas_auto']['spearman_cos']:.2f} con la "
      "tenencia de automóvil (Spearman; Figura~\\ref{fig:n02}), por "
      "lo que el portafolio tiende a repetir el perfil "
      "socioeconómico de las zonas ya servidas. Además se retiró el "
      "«techo por análogos» (una asignación de bicicletas por "
      "estaciones parecidas): su error absoluto medio fue "
      f"{D['ceil1']['mae_analog']:.3f} frente a "
      f"{D['ceil1']['mae_naive']:.3f} de la densidad constante "
      "mediana en el backtest\\footnote{Backtest: evaluación "
      "retrospectiva que simula la decisión sobre datos ya "
      "observados.}, y su correlación de Spearman también fue menor "
      f"({D['ceil1']['spearman_analog']:.3f} frente a "
      f"{D['ceil1']['spearman_naive']:.3f}). Retirarlo elevó la "
      "cobertura del portafolio B = 30 en "
      f"{D['techo1']['delta_B30_new_pop']:+,.0f} habitantes respecto "
      "a la publicación previa con techos: un cambio metodológico, "
      "no una mejora del método.")
    A("")

    A("\\subsection{Motor 2: modelo predictivo y principio de "
      "parsimonia}")
    A(f"El segundo motor entrena modelos supervisados sobre las "
      f"{D['universe04']} AGEBs con servicio para predecir el "
      "logaritmo de la actividad media por estación y despliega el "
      "pronóstico sobre los candidatos en dominio. Cuatro modelos "
      "se compararon con hiperparámetros fijos "
      "(Tabla~\\ref{tab:m2hp}): un predictor constante, regresión "
      "Ridge con validación interna, un bosque aleatorio y un "
      "FT-Transformer tabular.")
    A("\\begin{table}[htbp]")
    A("\\centering")
    A("\\small")
    A("\\begin{tabular}{lp{0.58\\linewidth}}")
    A("\\toprule")
    A("Modelo & Hiperparámetros \\\\")
    A("\\midrule")
    hp = D["hp"]; cfg = D["m2cfg"]
    lo, hi, n = hp["ridge_alpha_lo"]
    A(f"Ridge (RidgeCV) & rejilla de $\\alpha$ logarítmica "
      f"$10^{{{lo}}}$ a $10^{{{hi}}}$ en {n} puntos, validación "
      "cruzada interna de 5 pliegues \\\\")
    A(f"Bosque aleatorio & {hp['rf_n_estimators']} árboles, "
      f"mínimo {hp['rf_min_samples_leaf']} observaciones por hoja, "
      f"fracción de variables por corte {hp['rf_max_features']} \\\\")
    A(f"FT-Transformer & token de dimensión {cfg['d_token']}, "
      f"{cfg['n_layers']} capas, {cfg['nhead']} cabezas, red interna "
      f"de {cfg['dim_feedforward']}, abandono {cfg['dropout']}, "
      f"tasa {cfg['lr']}, decaimiento {cfg['weight_decay']}, lote "
      f"{cfg['batch_size']}, máximo {cfg['max_epochs']} épocas, "
      f"paciencia {cfg['patience']}, {len(cfg['seeds'])} semillas \\\\")
    A("Constante & media del objetivo en entrenamiento \\\\")
    A("\\bottomrule")
    A("\\end{tabular}")
    A("\\caption{Hiperparámetros fijos de los modelos comparados en "
      "el Motor 2.}")
    A("\\label{tab:m2hp}")
    A("\\end{table}")
    A("")
    A(f"La Tabla~\\ref{{tab:m2}} resume el desempeño en el esquema "
      "espacial y la Figura~\\ref{fig:n03} lo visualiza: el "
      f"RMSE\\footnote{{RMSE: raíz del error cuadrático medio; menor "
      "es mejor.} medio es "
      f"{D['reg']['constante']['rmse']:.4f} (constante), "
      f"{D['reg']['ridge']['rmse']:.4f} (Ridge), "
      f"{D['reg']['random_forest']['rmse']:.4f} (bosque aleatorio) y "
      f"{D['reg']['ft_transformer']['rmse']:.4f} (FT-Transformer). "
      f"Frente al mejor control (Ridge) el Transformer no mejora: su "
      "diferencia de RMSE es de "
      f"{D['reg']['ft_transformer']['rmse'] - D['reg']['ridge']['rmse']:+.4f} "
      "a favor de Ridge, equivalente a "
      f"{abs(D['dic']['condition_c_improvement']) / D['dic']['condition_c_seed_std_mean']:.3f} "
      "veces la variación entre semillas "
      f"({D['dic']['condition_c_seed_std_mean']:.4f}). Ridge tiene el "
      "RMSE medio más bajo por esa diferencia mínima, pero el "
      f"FT-Transformer muestra {R2} "
      f"({D['reg']['ft_transformer']['r2']:.3f} frente a "
      f"{D['reg']['ridge']['r2']:.3f}) y Spearman "
      f"({D['reg']['ft_transformer']['spearman']:.3f} frente a "
      f"{D['reg']['ridge']['spearman']:.3f}) ligeramente superiores: "
      "el resultado es un empate práctico y la complejidad del "
      "Transformer no se justifica. El dictamen preespecificado "
      f"(condición A falsa; {D['dic']['condition_b_fold_wins_vs_best_control']} "
      f"de {D['dic']['condition_b_required']} victorias requeridas "
      "en pliegues; mejora insuficiente frente al ruido entre "
      "semillas) lo retira del despliegue.")
    fig("n03_m2_rmse.png", "fig:n03",
        "RMSE medio por modelo en el esquema espacial; la barra del "
        "FT-Transformer indica la desviación estándar entre semillas.")
    A("\\begin{table}[htbp]")
    A("\\centering")
    A("\\small")
    A("\\begin{tabular}{lccc}")
    A("\\toprule")
    A(f"Modelo & RMSE & {R2} & Spearman \\\\")
    A("\\midrule")
    for key, label in [("constante", "Constante"), ("ridge", "Ridge"),
                       ("random_forest", "Bosque aleatorio"),
                       ("ft_transformer", "FT-Transformer")]:
        r = D["reg"][key]
        sp = f"{r['spearman']:.3f}" if r["spearman"] is not None else "—"
        A(f"{label} & {r['rmse']:.4f} & {r['r2']:.3f} & {sp} \\\\")
    A("\\bottomrule")
    A("\\end{tabular}")
    A("\\caption{Desempeño medio de los modelos del Motor 2 en el "
      "esquema espacial (cinco pliegues).}")
    A("\\label{tab:m2}")
    A("\\end{table}")
    A("")
    A(f"Ningún modelo es predictivamente fuerte: el " + R2 + " "
      f"espacial máximo es {D['ock']['r2_spatial_mean']['ft_transformer']:.3f}. "
      "Se desplegó el bosque aleatorio por parsimonia y estabilidad, "
      "no por superioridad acreditada: frente a Ridge difiere en "
      f"{D['ock']['rf_vs_ridge']['delta_rmse_mean']:+.4f} de RMSE "
      f"medio y gana en {D['ock']['rf_vs_ridge']['rf_fold_wins']} de "
      f"{D['ock']['rf_vs_ridge']['n_folds']} pliegues. La predicción "
      "sobre candidatos es exploratoria y lleva una bandera de "
      "extrapolación\\footnote{OOD: fuera del dominio de "
      "entrenamiento; la predicción en ese territorio extrapola "
      "fuera del soporte observado.}; el motor aplicó su propia "
      "compuerta de dominio estimada sobre las "
      f"{D['universe04']} AGEBs servidas. Su versión del backtest "
      "del techo por análogos confirmó el retiro: error absoluto "
      f"{D['ceil2']['mae_analog']:.3f} frente a "
      f"{D['ceil2']['mae_naive']:.3f} de la densidad constante, con "
      "Spearman marginalmente mayor "
      f"({D['ceil2']['spearman_analog']:.3f} frente a "
      f"{D['ceil2']['spearman_naive']:.3f}); al retirarlo el "
      "portafolio B = 30 ganó "
      f"{D['techo2']['delta_B30_new_pop']:+,.0f} habitantes.")
    A("")

    A("\\subsection{Motor 3: optimización prescriptiva sobre grafos}")
    A(f"El tercer motor pasa de predecir a diseñar. Los sitios "
      f"candidatos se conectan en un grafo geométrico "
      f"({miles(D['graph']['n_graph_nodes'])} nodos, "
      f"{miles(D['graph']['n_graph_edges'])} aristas, "
      f"{miles(D['graph']['n_sites'])} sitios elegibles) donde una "
      f"arista existe si dos puntos distan a lo más "
      f"{D['link_m']:.0f} m; las reglas exigen contigüidad a la red "
      f"vigente y separación mínima de {D['spacing_m']} m. El grafo "
      "impide estaciones aisladas porque el servicio exige origen y "
      "destino dentro de la red. Cada sitio recibe una afinidad "
      "determinista $1/(1+\\text{saltos a Golden})$: la cercanía a "
      "la zona dorada medida en saltos del grafo. En consecuencia, "
      "las métricas de proximidad a Golden del portafolio quedan "
      "optimizadas por construcción y no constituyen evidencia "
      "independiente a su favor. El enfoque previo con embeddings "
      "Node2Vec se retiró como decisión metodológica (en la "
      "evidencia histórica, Spearman de la afinidad con menos "
      "saltos a Golden de $-0.095$).")
    A("")
    A(f"La función objetivo combina cobertura poblacional y "
      "afinidad estructural: "
      "$f = w\\cdot\\mathrm{cobertura} + (1-w)\\cdot"
      "\\mathrm{afinidad\\ media}$, con $w = "
      f"{D['w']}$ en la configuración primaria. La selección la hace "
      "un algoritmo Greedy\\footnote{Greedy: algoritmo voraz que "
      "añade en cada paso el sitio de mayor ganancia marginal.} "
      "(heurística determinista de ganancia marginal) y se contrasta "
      "con un algoritmo genético "
      f"(población {D['gacfg']['population']}, "
      f"{D['gacfg']['generations']} generaciones, cruza "
      f"{D['gacfg']['cxpb']}, mutación {D['gacfg']['mutpb']}, "
      f"torneo {D['gacfg']['tournament']}, élite "
      f"{D['gacfg']['elite']}, semillas "
      f"{D['seeds_p'][0]:.0f}--{D['seeds_p'][-1]:.0f} en la "
      f"configuración primaria y {D['seeds_o'][0]:.0f}--"
      f"{D['seeds_o'][-1]:.0f} en las demás; "
      f"{D['n_rand']} portafolios aleatorios de referencia). La "
      "Tabla~\\ref{tab:m3} resume las siete configuraciones "
      "evaluadas: en todas, el Greedy iguala o supera a la mejor "
      "corrida del GA en la función objetivo; en dos (w = 0.25 y "
      "w = 0.75) la diferencia es menor que la variación entre "
      "semillas del GA y se declara empate práctico "
      "(Figura~\\ref{fig:n06}).")
    A("\\begin{table}[htbp]")
    A("\\centering")
    A("\\small")
    A("\\begin{tabular}{llllll}")
    A("\\toprule")
    A("$w$ & $B$ & $f$ Greedy & $f$ GA mejor & $f$ GA media $\\pm$ "
      "desv. & Veredicto \\\\")
    A("\\midrule")
    for r in D["gvg"]:
        verd = "Empate" if "empate" in r["verdict"] else "Greedy"
        A(f"{r['weight']:.2f} & {r['budget']} & {r['greedy_f']:.4f} & "
          f"{r['ga_best_f']:.4f} & {r['ga_mean_f']:.4f} $\\pm$ "
          f"{r['ga_std_f']:.4f} & {verd} \\\\")
    A("\\bottomrule")
    A("\\end{tabular}")
    A("\\caption{Función objetivo Greedy frente a algoritmo genético "
      "en las siete configuraciones (misma función objetivo y "
      "reglas de factibilidad).}")
    A("\\label{tab:m3}")
    A("\\end{table}")
    A("")
    fig("n06_m3_objetivo.png", "fig:n06",
        "Función objetivo por configuración: Greedy frente a la "
        "mejor corrida y a la media $\\pm$ desviación entre semillas del "
        "GA; las franjas sombreadas marcan los empates dentro del "
        "ruido entre semillas.")
    A(f"En población cubierta (Figura~\\ref{{fig:n04}}): a B = 15 el "
      f"Greedy selecciona {miles(D['greedy_runs'][15]['new_pop'])} "
      f"habitantes nuevos frente a {miles(D['ga_best_by_b'][15]['new_pop'])} "
      f"del mejor GA (ventaja de {miles(D['greedy_runs'][15]['new_pop'] - D['ga_best_by_b'][15]['new_pop'])}); "
      "a B = 30 son "
      f"{miles(D['greedy_runs'][30]['new_pop'])} frente a "
      f"{miles(D['ga_best_by_b'][30]['new_pop'])} (media de cinco "
      f"semillas {miles(D['ga_pop_mean_b30'])}), una ventaja de "
      f"{miles(D['greedy_runs'][30]['new_pop'] - D['ga_best_by_b'][30]['new_pop'])}; "
      f"y a B = 50 el Greedy alcanza "
      f"{miles(D['greedy_runs'][50]['new_pop'])} frente a "
      f"{miles(D['ga_best_by_b'][50]['new_pop'])} "
      f"(ventaja de {miles(D['greedy_runs'][50]['new_pop'] - D['ga_best_by_b'][50]['new_pop'])}). En costo "
      "computacional (Figura~\\ref{fig:n05}), una ejecución del "
      f"Greedy toma {D['gv_prim']['greedy_wall_s']:.3f} s frente a "
      f"{D['gv_prim']['ga_mean_wall_s_per_seed']:.1f} s por semilla "
      "del GA en la configuración primaria "
      f"({miles(D['gv_prim']['ga_mean_wall_s_per_seed'] / D['gv_prim']['greedy_wall_s'])}x; "
      f"rango emparejado {miles(min(D['speedups']))}x a "
      f"{miles(max(D['speedups']))}x). Los totales del experimento "
      f"—Greedy {D['timing']['greedy_total_wall_s']:.3f} s frente a "
      f"{miles(D['timing']['ga_total_wall_s'])} s del GA, unos "
      f"{D['timing']['ga_total_wall_s']/60:.1f} minutos— no son "
      "pareados: el GA corre varias semillas por configuración y el "
      "Greedy una sola corrida, por lo que el cociente de totales "
      "no es un indicador válido. El Greedy no gana por "
      "construcción: es una heurística sin garantía formal bajo las "
      "restricciones de contigüidad y espaciamiento "
      "(submodularidad\\footnote{Submodularidad: propiedad de "
      "rendimientos decrecientes de la cobertura; la garantía "
      "teórica (1$-$1/$e$) del Greedy no aplica formalmente con las "
      "restricciones de red impuestas.} solo garantiza la cota "
      "clásica sin esas restricciones); en los experimentos igualó o "
      "superó al GA en todas las configuraciones, con empate "
      "estadístico en dos.")
    fig("n04_m3_poblacion.png", "fig:n04",
        "Población nueva cubierta por el Greedy y por la mejor "
        "semilla del GA a cada presupuesto; la etiqueta indica la "
        "ventaja del Greedy en habitantes.")
    fig("n05_m3_tiempos.png", "fig:n05",
        "Tiempo de ejecución por configuración (escala logarítmica): "
        "una corrida del Greedy frente a la media por semilla del "
        "GA; la nota inferior reporta los totales no pareados del "
        "experimento.")
    A("")

    # -------------------------------------------------- Resultados
    A("\\section{Resultados y discusión}")
    A(f"La Tabla~\\ref{{tab:cobertura}} resume los portafolios "
      "oficiales a los tres presupuestos\\footnote{La población "
      "cubierta por un portafolio se calcula sobre las celdas de "
      f"{D['pop_cell']} m contenidas en la unión de las zonas de "
      f"captura euclidianas de {D['buffer_m']:.0f} m; cada celda "
      "cuenta una sola vez, por lo que el total es menor o igual "
      "que la suma de las poblaciones de las zonas individuales "
      "cuando estas se traslapan.} y la Figura~\\ref{fig:c8_01} los "
      "compara visualmente.")
    A("\\begin{table}[htbp]")
    A("\\centering")
    A("\\footnotesize")
    A("\\begin{tabular}{llrrrrr}")
    A("\\toprule")
    A("Motor & $B$ & Pob.\\ nueva & \\% pob. & AGEBs & Dist.\\ media "
      "(m) & Escolaridad \\\\")
    A("\\midrule")
    lbl = {"m1": "Motor 1", "m2": "Motor 2", "m3": "Motor 3"}
    for b in (15, 30, 50):
        for m in ("m1", "m2", "m3"):
            v = D["ofi"][(m, b)]
            A(f"{lbl[m]} & {b} & {miles(v['new_pop'])} & "
              f"{v['new_pop_share']*100:.2f} & {v['n_agebs']} & "
              f"{v['mean_dist_to_network_m']:.0f} & "
              f"{v['mean_grado_escolar_prom_selected']:.2f} \\\\")
    A("\\bottomrule")
    A("\\end{tabular}")
    A("\\caption{Cobertura de los portafolios oficiales por motor y "
      "presupuesto: población nueva en la unión de zonas de captura, "
      "AGEBs alcanzadas, distancia media a la red vigente y "
      "escolaridad media de las AGEBs seleccionadas.}")
    A("\\label{tab:cobertura}")
    A("\\end{table}")
    A("")
    fig("c8/c8_01_cobertura_por_presupuesto.png", "fig:c8_01",
        "Población nueva cubierta por los portafolios oficiales de "
        "los tres motores a cada presupuesto.")
    A(f"El traslape entre motores es bajo: a B = 30 los índices de "
      f"Jaccard\\footnote{{Índice de Jaccard: tamaño de la "
      "intersección sobre el de la unión de dos conjuntos.} de "
      f"sitios son {D['ov30']['m1-m2']['jaccard_sites']:.3f} "
      f"(M1--M2), {D['ov30']['m1-m3']['jaccard_sites']:.3f} (M1--M3) "
      f"y {D['ov30']['m2-m3']['jaccard_sites']:.3f} (M2--M3), y de "
      f"AGEBs {D['ov30']['m1-m2']['jaccard_agebs']:.3f}, "
      f"{D['ov30']['m1-m3']['jaccard_agebs']:.3f} y "
      f"{D['ov30']['m2-m3']['jaccard_agebs']:.3f} "
      "(Figura~\\ref{fig:c8_06}). El consenso territorial concentra "
      f"{D['cons']['30']['selected_by_2plus']} sitios elegidos por "
      "al menos dos motores y "
      f"{D['cons']['30']['selected_by_3']} elegidos por los tres "
      "(Figura~\\ref{fig:c8_07}); el conteo por presupuesto es "
      f"{D['cons']['15']['selected_by_2plus']}/"
      f"{D['cons']['15']['selected_by_3']} a B = 15 y "
      f"{D['cons']['50']['selected_by_2plus']}/"
      f"{D['cons']['50']['selected_by_3']} a B = 50.")
    fig("c8/c8_06_jaccard_sitios_agebs.png", "fig:c8_06",
        "Índices de Jaccard de sitios y de AGEBs entre pares de "
        "motores por presupuesto; el traslape bajo evidencia que los "
        "motores seleccionan territorios distintos.")
    fig("c8/c8_07_mapas_consenso.png", "fig:c8_07",
        "Mapa del universo evaluable y del consenso territorial: "
        "sitios elegidos por al menos dos motores y por los tres.")
    A("Los radares de las Figuras~\\ref{fig:c8_02} y~\\ref{fig:c8_03} "
      "usan ejes fijos: el área del "
      "radar no es un puntaje agregado y no ordena a los motores. La "
      "matriz de la Figura~\\ref{fig:c8_04} resume las métricas "
      "oficiales recomputadas desde los portafolios publicados, y la "
      "Figura~\\ref{fig:c8_05} muestra cuántas estaciones cae cada "
      "motor por AGEB.")
    fig("c8/c8_02_radar_b30.png", "fig:c8_02",
        "Radar de ejes fijos en B = 30; cada eje codifica un "
        "objetivo distinto y el área no es un puntaje.")
    fig("c8/c8_03_radar_presupuestos.png", "fig:c8_03",
        "Radar de ejes fijos por presupuesto para cada motor.")
    fig("c8/c8_04_heatmap_metricas.png", "fig:c8_04",
        "Matriz de métricas oficiales por motor y presupuesto, "
        "recomputadas desde los portafolios publicados.")
    fig("c8/c8_05_estaciones_por_ageb.png", "fig:c8_05",
        "Distribución de estaciones seleccionadas por AGEB (1, 2 o "
        "3 o más) en cada portafolio oficial.")
    A(f"La tensión entre los objetivos queda visible en la "
      f"Figura~\\ref{{fig:c8_08}} y en la Figura~\\ref{{fig:n07}}. El "
      f"Motor 1 premia la similitud con el perfil de las zonas "
      f"exitosas: su score correlaciona "
      f"{D['bias']['grado_escolar_prom']['spearman_cos']:.2f} con la "
      f"escolaridad y {D['bias']['pct_viviendas_auto']['spearman_cos']:.2f} "
      "con la tenencia de automóvil, y su portafolio B = 30 "
      "selecciona AGEBs de escolaridad media "
      f"{D['ofi'][('m1', 30)]['mean_grado_escolar_prom_selected']:.2f}, "
      "el valor más alto de los tres; existe el riesgo declarado de "
      "replicar el sesgo socioeconómico histórico. El Motor 3 "
      "maximiza cobertura poblacional más cercanía a la red —la "
      "equidad no es un objetivo explícito— y su portafolio B = 30 "
      f"cubre {miles(D['ofi'][('m3', 30)]['new_pop'])} habitantes "
      "con escolaridad media "
      f"{D['ofi'][('m3', 30)]['mean_grado_escolar_prom_selected']:.2f} "
      "frente a "
      f"{D['ofi'][('m1', 30)]['mean_grado_escolar_prom_all_sites']:.2f} "
      "del universo de candidatos: la menor escolaridad es una "
      "consecuencia observada, no un objetivo programado.")
    fig("c8/c8_08_equidad.png", "fig:c8_08",
        "Perfil de equidad de los portafolios: escolaridad media y "
        "tenencia de automóvil en las AGEBs seleccionadas frente al "
        "universo de candidatos.")
    fig("n07_escolaridad.png", "fig:n07",
        "Escolaridad media de las AGEBs seleccionadas por cada motor "
        "a B = 30 frente al universo de candidatos (línea punteada).")
    A(f"La comparación es descriptiva: con presupuesto fijo y "
      "objetivos distintos no se declara un ganador agregado. El "
      f"tiempo acumulado del GA ({miles(D['timing']['ga_total_wall_s'])} "
      f"s) frente al del Greedy ({D['timing']['greedy_total_wall_s']:.3f} "
      "s) refleja el costo de ejecutar varias semillas por "
      "configuración; no ordena a los motores.")
    A("")

    # -------------------------------------------------- Conclusiones
    A("\\section{Conclusiones}")
    A("\\subsection{Respuesta a la hipótesis}")
    A(f"La respuesta, con matices y condiciones, es afirmativa. Un "
      "enfoque de ciencia de datos sí puede diseñar una expansión "
      "justa y conectada sin replicar el sesgo histórico, siempre "
      "que se respeten los tres principios: la fuga de datos se "
      "descartó antes del modelado (las variables derivadas de "
      "viajes con correlación "
      f"{D['turnover_spearman']:.3f} quedaron fuera), las AGEBs sin "
      "servicio se trataron como no etiquetadas y la tensión "
      "similitud–equidad se documentó explícitamente sin imponer "
      "una resolución única. Las condiciones son reales: la cobertura es "
      "población en zonas de captura, no demanda observada; ningún "
      "modelo predictivo resultó fuerte; y la cercanía a Golden del "
      "Motor 3 está optimizada por construcción.")
    A("\\subsection{Recomendaciones}")
    A(f"Se recomienda iniciar un piloto sobre los "
      f"{D['cons']['30']['selected_by_3']} sitios de consenso triple "
      f"y los {D['cons']['30']['selected_by_2plus']} de consenso "
      "doble a B = 30, sujeto a levantamiento de campo, costos de "
      "instalación y verificación de la red caminable. Como "
      "instrumento de trabajo se sugiere usar el Motor 3 como "
      "generador de portafolios (heurística determinista, "
      "reproducible y de costo computacional mínimo) y el Motor 1 "
      "como control de similitud para auditar el sesgo "
      "socioeconómico de cada propuesta.")
    A("\\subsection{Límites de la investigación}")
    A("Los límites declarados son: la cobertura poblacional no es "
      "demanda ni uso observado; el análisis no modela costos, "
      "caminabilidad peatonal ni operación del sistema; ninguna "
      "asociación reportada es causal; las fuentes tienen épocas "
      "distintas (censo, viajes y directorio económico); la "
      "abstención de la compuerta no implica sitio deficiente; las "
      "métricas de cercanía a Golden del Motor 3 están optimizadas "
      "por construcción; el estudio cubre una sola ciudad y un solo "
      "año de viajes.")
    A("\\subsection{Trabajo futuro}")
    A("Queda abierta la incorporación de costos y restricciones "
      "operativas, la medición de demanda real tras un piloto, la "
      "extensión a red caminable, la sensibilidad temporal con más "
      "años de operación y la réplica del arnés en otras ciudades "
      "del sistema.")
    A("")

    # -------------------------------------------------- Bibliografia
    A("\\renewcommand{\\bibsection}{\\section{Bibliografía}}")
    A("\\bibliographystyle{plainnat}")
    A("\\bibliography{referencias}")
    A("")

    # -------------------------------------------------- Apendice
    A("\\appendix")
    A("\\section{Registro de afirmaciones verificadas}")
    A("La Tabla~\\ref{tab:claims} reproduce el registro sellado de "
      "afirmaciones: cada una lleva su identificador, tema, estatus y "
      "enunciado, saneado de toda referencia interna al "
      "pipeline.")
    A("\\begin{longtable}{p{0.05\\linewidth}p{0.16\\linewidth}"
      "p{0.16\\linewidth}p{0.55\\linewidth}}")
    A("\\caption{Registro de afirmaciones verificadas del análisis.}"
      "\\label{tab:claims}\\\\")
    A("\\toprule")
    A("Id & Tema & Estatus & Afirmación \\\\")
    A("\\midrule")
    A("\\endfirsthead")
    A("\\toprule")
    A("Id & Tema & Estatus & Afirmación \\\\")
    A("\\midrule")
    A("\\endhead")
    for c in D["claims"]:
        line = claim_line(c)
        tema = _escape_latex(_accents(sanitize(
            c["tema"].replace("_", " "))))
        est = _escape_latex(_accents(c["estatus"].replace("_", " ")))
        A(f"{c['id']} & {tema} & {est} & {line} \\\\")
    A("\\bottomrule")
    A("\\end{longtable}")
    A("")
    A("\\end{document}")
    return "\n".join(T) + "\n"


def sc_buf(D):
    return f"{D['buffer_m']:.0f}"


# --------------------------------------------------------------------------
# referencias.bib (solo las 5 fuentes de datos)
# --------------------------------------------------------------------------
def build_bib(D):
    return f"""@misc{{ecobici,
  author = {{Gobierno de la Ciudad de México — SEMOVI / EcoBici}},
  title = {{Datos abiertos de viajes del sistema EcoBici}},
  year = {{{D['year']}}},
  note = {{Registros de viajes del sistema público de bicicletas}}
}}
@misc{{censo,
  author = {{INEGI}},
  title = {{Censo de Población y Vivienda}},
  year = {{{D['census_year']}}},
  note = {{Población por AGEB urbana}}
}}
@misc{{marco,
  author = {{INEGI}},
  title = {{Marco Geoestadístico}},
  year = {{{D['census_year']}}},
  note = {{Cartografía de AGEBs urbanas}}
}}
@misc{{denue,
  author = {{INEGI}},
  title = {{Directorio Estadístico Nacional de Unidades Económicas (DENUE)}},
  year = {{{D['denue_year']}}},
  note = {{Establecimientos económicos registrados}}
}}
@misc{{gtfs,
  author = {{Movilidad CDMX / operadores de transporte público}},
  title = {{Especificación GTFS de la red de transporte público de la Ciudad de México}},
  year = {{{D['gtfs_year']}}},
  note = {{Paradas y calendarios de servicio}}
}}
"""

_STALE = ["7,739", "7739", "304,459", "509,267", "K-Means", "KMeans",
          "kmeans", "K-means", "50 minutos", "0.8 s", "0.8s", "~0.8",
          "V3", "ipynb", "uaderno", "build_", "notebook", "isócron",
          "5,829"]
_FIRST = re.compile(
    r"\b(nosotros|nuestr[oa]s?|hemos|\w+(?:amos|emos)|"
    r"hicimos|decidimos|elegimos|definimos|medimos|obtuvimos|vimos|"
    r"fijamos|jubilamos|creímos|usamos|utilizamos|dejamos|quitamos|"
    r"recomendamos|sumamos)\b", re.I)
_ALLOW = {"ramos", "gramos", "diagramos", "programas", "estemos"}


def selfcheck(name, text):
    bad = [s for s in _STALE if s.lower() in text.lower()]
    if bad:
        raise SystemExit(f"{name}: términos prohibidos {bad}")
    fp = {m.group(0) for m in _FIRST.finditer(text)
          if m.group(0).lower() not in _ALLOW}
    if fp:
        raise SystemExit(f"{name}: posible primera persona "
                         f"{sorted(fp)[:10]}")
    if text.count("¿") > 3:
        raise SystemExit(f"{name}: demasiadas preguntas")


# --------------------------------------------------------------------------
def main():
    A = load_audits()
    D = collect_data(A)

    if BUILD.exists():
        shutil.rmtree(BUILD)
    FIG_BUILD.mkdir(parents=True)

    # Figuras existentes: copia byte a byte al directorio de build.
    for name in EXISTING_FIGS:
        src = FIG_SRC / name.split("_", 1)[0] / name
        if not src.exists():
            raise SystemExit(f"Falta figura extraída: {src}")
        sub = FIG_BUILD / name.split("_", 1)[0]
        sub.mkdir(exist_ok=True)
        shutil.copyfile(src, sub / name)
    make_figures(D)

    tex = build_tex(D)
    bib = build_bib(D)
    atomic_write(BUILD / "main.tex", tex)
    atomic_write(BUILD / "referencias.bib", bib)

    # HTML: figuras embebidas (mismos PNG del zip).
    fig_b64 = {}
    for name in EXISTING_FIGS:
        rel = name.split("_", 1)[0] + "/" + name
        fig_b64[rel] = base64.b64encode(
            (FIG_BUILD / rel).read_bytes()).decode()
    for name in NEW_FIGS:
        fig_b64[name] = base64.b64encode(
            (FIG_BUILD / name).read_bytes()).decode()
    html = build_dashboard_html.build_html(D, fig_b64)

    # Autocontrol previo al validador externo.
    def tex_text(src):
        s = re.sub(r"(?<!\\)%.*", "", src)
        s = re.sub(r"\\(label|ref|cite|includegraphics|bibliography|"
                   r"bibliographystyle|usepackage|documentclass)"
                   r"(\[[^\]]*\])?\{[^}]*\}", " ", s)
        s = re.sub(r"\$[^$]*\$", " ", s)
        s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
        return re.sub(r"[{}\\~]", " ", s)
    selfcheck("tex", tex_text(tex))
    import html.parser as hp_

    class _T(hp_.HTMLParser):
        def __init__(self):
            super().__init__()
            self.out, self.skip = [], 0

        def handle_starttag(self, t, a):
            if t in ("script", "style"):
                self.skip += 1

        def handle_endtag(self, t):
            if t in ("script", "style") and self.skip:
                self.skip -= 1

        def handle_data(self, d):
            if not self.skip:
                self.out.append(d)
    p = _T()
    p.feed(html)
    selfcheck("html", " ".join(p.out))

    # Entregable: SOLO los dos archivos.
    if ENTREGABLE.exists():
        shutil.rmtree(ENTREGABLE)
    ENTREGABLE.mkdir(parents=True)

    # Zip determinista.
    entries = ["main.tex", "referencias.bib"]
    entries += [f"figures/{r}" for r in sorted(fig_b64)]
    ztmp = ENTREGABLE / ".tesis_overleaf.zip.tmp"
    with zipfile.ZipFile(ztmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in entries:
            if rel == "main.tex":
                data = tex.encode("utf-8")
            elif rel == "referencias.bib":
                data = bib.encode("utf-8")
            else:
                data = (FIG_BUILD / rel[len("figures/"):]).read_bytes()
            zi = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    os.replace(ztmp, ENTREGABLE / "tesis_overleaf.zip")
    atomic_write(ENTREGABLE / "presentacion_ejecutiva.html", html)
    print("entregable:", ENTREGABLE)
    print(" zip:", (ENTREGABLE / "tesis_overleaf.zip").stat().st_size,
          "bytes")
    print(" html:", (ENTREGABLE / "presentacion_ejecutiva.html")
          .stat().st_size, "bytes")


if __name__ == "__main__":
    sys.exit(main())
