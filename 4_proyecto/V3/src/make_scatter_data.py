"""Datos del scatter de equidad-cobertura (presentación v2).

Recalcula, con la semilla y el decodificador del Motor 3, los 300
portafolios aleatorios conectados y factibles a B=30, y de cada uno guarda
la población nueva y la escolaridad media de sus AGEBs anfitrionas. Verifica
que reproducen la media de f registrada en el reporte 07 (w=0.5, B=30).
También guarda la mediana de viajes diarios de las 677 estaciones.

Salida: V3/data/presentacion_v2/scatter_azar_b30.json
Uso: PYTHONPATH=. OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE \
     python V3/src/make_scatter_data.py
"""
import csv
import glob
import json
from pathlib import Path

import numpy as np

from V3.src import fe04_deployment as dep
from V3.src import m3_analysis as m3

V3 = Path("V3")
OUT = V3 / "data" / "presentacion_v2" / "scatter_azar_b30.json"
B = 30


def main():
    data = m3.load_inputs(V3)
    fr, cfg = data["frames"], m3.CONFIG
    crs = cfg["metric_crs"]
    st = fr["station_env"].to_crs(crs).reset_index(drop=True)
    sites = fr["sites"].to_crs(crs).reset_index(drop=True)
    cells = fr["cells"].to_crs(crs).reset_index(drop=True)
    sxy = np.c_[sites.x, sites.y]
    stxy = np.c_[st.geometry.x, st.geometry.y]
    ctx = dep.build_network_context(
        sites, cells, dep.site_cell_incidence(sxy, cells, cfg), st, cfg)
    neigh, in_comp, _ = m3.geometric_graph(stxy, sxy, cfg)
    golden = np.nonzero(st.is_golden.astype(bool).to_numpy())[0].tolist()
    hops = m3.hops_on_graph(neigh, golden, len(stxy), len(sxy))
    aff = m3.hop_affinity(hops, in_comp)
    esc = fr["features"].set_index("cvegeo") \
        .loc[sites.cvegeo, "grado_escolar_prom"].to_numpy()

    rng = np.random.default_rng(cfg["seed"])
    pts, fs = [], []
    for _ in range(cfg["n_random_portfolios"]):
        order = m3.decode(rng.uniform(0, 1, len(sxy)), ctx, B)["order"]
        pts.append([float(m3.new_pop(order, ctx)),
                    float(np.nanmean(esc[order])), len(order)])
        fs.append(m3.objective(order, ctx, aff, 0.5, B))
    pts = np.asarray(pts)

    run = next(r for p in glob.glob(
        str(V3 / "data/engines/07_motor3/*/3aa53121*/m3_runs.csv"))
        for r in csv.DictReader(open(p))
        if r["method"] == "random" and r["budget"] == "30"
        and r["weight"] == "0.5")
    f_audit = float(run["f"])
    if abs(float(np.mean(fs)) - f_audit) > 1e-9:
        raise SystemExit(f"No reproduce f_mean: {np.mean(fs)} vs {f_audit}")

    official = {}
    p8 = glob.glob(str(
        V3 / "data/engines/08_comparacion/*/fdba0469*/c8_metricas.csv"))[0]
    for r in csv.DictReader(open(p8)):
        if r["tier"] == "oficial" and r["budget"] == "30":
            official[r["motor"]] = {
                "new_pop": float(r["new_pop"]),
                "esc": float(r["mean_grado_escolar_prom_selected"])}
            universe = float(r["mean_grado_escolar_prom_all_sites"])

    sweep, base_set = {}, None
    for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
        o = m3.greedy_fgain(ctx, aff, w, B)["order"]
        if w == 0.5:
            base_set = set(o)
        sweep[str(w)] = {"new_pop": float(m3.new_pop(o, ctx)),
                         "esc": float(np.nanmean(esc[o])),
                         "mean_affinity": float(aff[o].mean()),
                         "n_selected": len(o), "sites": sorted(set(o))}
    for v in sweep.values():
        s = set(v.pop("sites"))
        v["jaccard_vs_w05"] = len(s & base_set) / len(s | base_set)
    run_pops = {}
    for r in csv.DictReader(open(glob.glob(str(
            V3 / "data/engines/07_motor3/*/3aa53121*/m3_runs.csv"))[0])):
        if r["method"] == "greedy" and r["budget"] == "30":
            run_pops[r["weight"]] = float(r["new_pop"])
    for k, v in sweep.items():
        if abs(run_pops[str(float(k))] - v["new_pop"]) > 1e-6:
            raise SystemExit(f"w={k}: no reproduce m3_runs.csv")
    e = pts[:, 1]
    res = {
        "w_sweep": sweep,
        "p_norm": float(dep.P_norm(ctx, B)),
        "budget": B, "n_random": len(pts), "seed": cfg["seed"],
        "f_mean_reproduced": float(np.mean(fs)), "f_mean_audit": f_audit,
        "universe_esc": universe,
        "points": [[round(a, 1), round(b, 4)] for a, b, _ in pts],
        "n_selected_min": int(pts[:, 2].min()),
        "cloud": {"pop_mean": float(pts[:, 0].mean()),
                  "pop_sd": float(pts[:, 0].std()),
                  "pop_max": float(pts[:, 0].max()),
                  "esc_mean": float(e.mean()), "esc_sd": float(e.std())},
        "official": official,
        "rank": {m: {"share_random_esc_le": float((e <= v["esc"]).mean()),
                     "share_random_esc_ge": float((e >= v["esc"]).mean()),
                     "share_random_pop_ge": float(
                         (pts[:, 0] >= v["new_pop"]).mean())}
                 for m, v in official.items()},
        "median_viajes_diarios_red": float(
            np.median(st.viajes_diarios_prom.to_numpy())),
        "n_estaciones": int(len(st)),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in res.items() if k != "points"},
                     indent=1))


if __name__ == "__main__":
    main()
