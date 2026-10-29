"""Motor 3 autónomo: grafo geométrico + afinidad de saltos + greedy.

El Motor 3 resuelve la tarea común del contrato de despliegue del
cuaderno 04 —un portafolio de B sitios bajo reglas de red idénticas—
con su propio puntaje estructural: la afinidad determinista de cada
sitio al núcleo dorado, 1/(1+saltos a Golden) sobre el grafo geométrico
(estaciones existentes ∪ sitios candidatos, arista si distancia <=
enlace). NO lee salidas de los motores 05 ni 06: sus únicos insumos son
el contrato de despliegue del 04 (sitios, celdas, reglas, métricas), el
entorno de estaciones del 02, las AGEBs del 03 y los viajes del ETL
—estos últimos solo para un diagnóstico descriptivo de comunidades de
flujo que NO alimenta el optimizador—.

Desde v3-motor3-4:

- Node2Vec queda RETIRADO del pipeline (ver `node2vec_retired` en el
  reporte): la validación histórica publicada en v3-motor3-3 mostró que
  su afinidad estructural no ordenaba por cercanía al núcleo dorado.
- La afinidad es determinista y la prescripción PRINCIPAL es el greedy
  de ganancia marginal; el algoritmo genético se conserva como
  sensibilidad —heurística sin garantía de óptimo— y se reporta su
  brecha, su percentil frente a aleatorios y su tiempo de pared.
- Como la afinidad es función directa de los saltos a Golden, las
  métricas de cercanía a Golden del portafolio están optimizadas por
  construcción: NO son evidencia independiente a favor del Motor 3.
"""
import hashlib
import json
import platform
import random
import sys
import time
from pathlib import Path

import deap
import geopandas as gpd
import joblib
import networkx as nx
import numpy as np
import pandas as pd
import scipy
import sklearn
from deap import base, creator, tools
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.manifold import SpectralEmbedding

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import eda02_publication
from V3.src import engine_publication as ep
from V3.src import fe03_publication
from V3.src import fe04_publication
from V3.src import fe04_deployment as dep

VERSION = "v3-motor3-4"
CONFIG = {
    "metric_crs": dep.DEPLOY_CONFIG["metric_crs"],
    "link_distance_m": dep.DEPLOY_CONFIG["link_distance_m"],
    "coverage_radius_m": dep.DEPLOY_CONFIG["coverage_radius_m"],
    "min_spacing_m": dep.DEPLOY_CONFIG["min_spacing_m"],
    "site_grid_m": dep.DEPLOY_CONFIG["site_grid_m"],
    "max_reach_m": dep.DEPLOY_CONFIG["max_reach_m"],
    "pop_cell_m": dep.DEPLOY_CONFIG["pop_cell_m"],
    "budget": dep.DEPLOY_CONFIG["primary_budget"],
    "budget_sensitivity": dep.DEPLOY_CONFIG["budget_grid"],
    "weights": [0.0, 0.25, 0.5, 0.75, 1.0],
    "primary_weight": 0.5,
    "ga": {"population": 80, "generations": 120, "cxpb": 0.7,
           "mutpb": 0.3, "cx_indpb": 0.5, "mut_indpb": 0.05,
           "mut_sigma": 0.2, "tournament": 3, "elite": 2},
    "seeds_primary": [42, 43, 44, 45, 46],
    "seeds_other": [42, 43, 44],
    "n_random_portfolios": 300,
    "seed": 42,
    "embedding_dims": 8,
    "embedding_pairs": 20000,
}
MONTHS = [f"viajes_2025-{m:02}.parquet" for m in range(1, 13)]

UPSTREAM_ARTIFACTS = {
    "features": ["entorno_ageb_features.parquet"],
    "eda": ["station_environment.parquet"],
    "validation": ["universo_evaluacion.parquet",
                   "sitios_candidatos.parquet",
                   "celdas_poblacion.parquet",
                   "validation_harness.joblib"],
    "etl": MONTHS + ["station_aliases.parquet"],
}
POINTERS = {
    "eda": "audits/02_eda.json",
    "features": "audits/03_feature_engineering.json",
    "validation": "audits/04_backtest_design.json",
}


# ---------------------------------------------------------------------------
# Insumos verificados e identidad
# ---------------------------------------------------------------------------

def _etl_processed_record(audit, basename):
    """Registro único del ETL bajo data/processed/<contract>/.

    La auditoría registra los viajes mensuales dos veces (processed y
    quarantine); Motor 3 consume solo la rama processed.
    """
    prefix = f"data/processed/{audit['contract_id']}/"
    matches = [r for r in audit["outputs"]
               if r["path"].startswith(prefix)
               and r["path"].endswith(f"/{basename}")]
    if len(matches) != 1:
        raise ValueError(
            f"ETL processed artifact not unique: {basename}")
    return {key: matches[0][key] for key in ["path", "bytes", "sha256"]}


def _etl_artifact_path(v3, audit, basename):
    """Ruta verificada (bytes+hash) de un artefacto processed del ETL."""
    record = _etl_processed_record(audit, basename)
    path = Path(v3).resolve() / record["path"]
    if path.is_symlink() or not path.is_file() \
            or path.stat().st_size != record["bytes"] \
            or file_hash(path) != record["sha256"]:
        raise ValueError(
            f"ETL artifact failed byte/hash check: {basename}")
    return path


def _upstream_context(v3):
    """Verifica ETL + punteros 02/03/04; Motor 3 no usa 05 ni 06."""
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    reports = {
        "eda": ep.pointer_verified_report(
            v3, POINTERS["eda"], eda02_publication.verify_report,
            eda02_publication.EDA_ROOT),
        "features": ep.pointer_verified_report(
            v3, POINTERS["features"], fe03_publication.verify_report,
            fe03_publication.FEATURES_ROOT),
        "validation": ep.pointer_verified_report(
            v3, POINTERS["validation"], fe04_publication.verify_report,
            fe04_publication.VALIDATION_ROOT),
    }
    for name, report in reports.items():
        if report["contract_id"] != contract:
            raise ValueError(f"Upstream {name} report belongs to another contract")
    input_artifacts = {}
    for stage, basenames in UPSTREAM_ARTIFACTS.items():
        if stage == "etl":
            records = {b: _etl_processed_record(audit, b)
                       for b in basenames}
        else:
            records = ep.artifact_records(reports[stage], basenames)
        for basename, record in records.items():
            input_artifacts[f"{stage}/{basename}"] = record
    upstream_refs = {
        "etl_audit_sha256": file_hash(v3 / "audits/01_etl.json"),
        "eda_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["eda"]).read_bytes()).hexdigest(),
        "feature_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["features"]).read_bytes()).hexdigest(),
        "validation_audit_sha256": hashlib.sha256(
            (v3 / POINTERS["validation"]).read_bytes()).hexdigest(),
        "eda_analysis_id": reports["eda"]["analysis_id"],
        "feature_analysis_id": reports["features"]["analysis_id"],
        "validation_analysis_id": reports["validation"]["analysis_id"],
        "motor1_motor2_not_inputs": True,
    }
    return {"audit": audit, "reports": reports,
            "input_artifacts": input_artifacts,
            "upstream_refs": upstream_refs}


def analysis_identity(v3, context):
    identity = {
        "schema_version": VERSION,
        "contract_id": context["audit"]["contract_id"],
        "configuration": CONFIG,
        "input_artifacts": context["input_artifacts"],
        "upstream_refs": context["upstream_refs"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "m3_analysis.py", "m3_content.py", "m3_publication.py",
                "build_notebook_07.py", "engine_publication.py",
                "fe04_deployment.py", "fe04_publication.py",
                "fe03_publication.py", "eda02_publication.py",
            ]
        },
        "versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "geopandas": gpd.__version__,
            "scipy": scipy.__version__, "sklearn": sklearn.__version__,
            "joblib": joblib.__version__, "networkx": nx.__version__,
            "deap": deap.__version__,
        },
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), identity


def _verified_frame(v3, report, basename, geodataframe=False):
    path = ep.verified_artifact_path(v3, report, basename)
    return (gpd.read_parquet if geodataframe else pd.read_parquet)(path)


def load_inputs(v3):
    """Carga insumos verificados: ETL, 02, 03 y el contrato del 04."""
    context = _upstream_context(v3)
    reports = context["reports"]
    audit = context["audit"]
    harness = fe04_publication.load_validation_harness(v3)
    deploy = harness["deployment"]
    for name in ["is_feasible", "greedy_coverage", "new_pop",
                 "portfolio_metrics", "P_norm", "build_network_context"]:
        if deploy["callables"].get(name) is not getattr(dep, name):
            raise ValueError(f"Deployment callable drifted: {name}")
    if deploy["config"] != dep.DEPLOY_CONFIG:
        raise ValueError("Deployment config drifted from fe04_deployment")
    frames = {
        "features": _verified_frame(v3, reports["features"],
                                    "entorno_ageb_features.parquet",
                                    geodataframe=True),
        "station_env": _verified_frame(v3, reports["eda"],
                                       "station_environment.parquet",
                                       geodataframe=True),
        "sites": _verified_frame(v3, reports["validation"],
                                 "sitios_candidatos.parquet",
                                 geodataframe=True),
        "cells": _verified_frame(v3, reports["validation"],
                                 "celdas_poblacion.parquet",
                                 geodataframe=True),
        "universe04": _verified_frame(v3, reports["validation"],
                                      "universo_evaluacion.parquet"),
        "aliases": pd.read_parquet(
            _etl_artifact_path(v3, audit, "station_aliases.parquet")),
    }
    trip_paths = {m: _etl_artifact_path(v3, audit, m)
                  for m in MONTHS}
    data = {**context, "v3": Path(v3).resolve(), "frames": frames,
            "trip_paths": trip_paths, "harness": harness}
    data["analysis_id"], data["analysis_identity"] = \
        analysis_identity(v3, context)
    return data


# ---------------------------------------------------------------------------
# 1. Grafo geométrico y afinidad determinista de saltos
# ---------------------------------------------------------------------------

def geometric_graph(stations_xy, sites_xy, cfg):
    """G no ponderado: estaciones ∪ sitios, arista si dist <= enlace.

    Devuelve la lista de vecinos por nodo y la máscara de sitios en el
    componente que contiene a las estaciones existentes.
    """
    n_st = len(stations_xy)
    pts = np.r_[stations_xy, sites_xy]
    pairs = cKDTree(pts).query_pairs(cfg["link_distance_m"],
                                     output_type="ndarray")
    graph = nx.Graph()
    graph.add_nodes_from(range(len(pts)))
    if len(pairs):
        graph.add_edges_from(pairs.tolist())
    neighbors = [np.array(sorted(graph.neighbors(i)), dtype=np.int64)
                 for i in range(len(pts))]
    seen = np.zeros(len(pts), bool)
    stack = list(range(n_st))
    seen[:n_st] = True
    while stack:
        for nxt in neighbors[stack.pop()]:
            if not seen[nxt]:
                seen[nxt] = True
                stack.append(nxt)
    return neighbors, seen[n_st:], graph


def hops_on_graph(neighbors, sources, n_stations, n_sites):
    """BFS multi-fuente sobre la lista de vecinos: saltos por nodo."""
    dist = np.full(n_stations + n_sites, -1, dtype=np.int64)
    stack = list(sources)
    for s in sources:
        dist[s] = 0
    frontier = list(sources)
    while frontier:
        nxt = []
        for node in frontier:
            for nb in neighbors[node]:
                if dist[nb] < 0:
                    dist[nb] = dist[node] + 1
                    nxt.append(nb)
        frontier = nxt
    return dist[n_stations:]


# ---------------------------------------------------------------------------
# 2. Grafo de flujos OD (diagnóstico descriptivo; NO entra al optimizador)
# ---------------------------------------------------------------------------

def _station_lists(series):
    """Réplica exacta del ETL: '271-272' -> ['271','272'] o []."""
    normalized = series.astype("string").str.strip()
    valid = normalized.str.fullmatch(r"\d+(?:-\d+)*", na=False)
    mapping = {
        value: list(dict.fromkeys(
            str(int(part)).zfill(3) for part in value.split("-")))
        for value in normalized.loc[valid].unique()}
    return normalized.map(mapping).map(
        lambda v: v if isinstance(v, list) else [])


def flow_edges(month_frames, aliases, ce_ids):
    """Pesos OD agregados replicando el mapeo del ETL.

    Cada componente de un código compuesto pesa 1/len; el par (o,d)
    aporta w_o·w_d. Se reporta el peso mapeado a estaciones existentes;
    los auto-bucles se cuentan y se excluyen del grafo.
    """
    alias_map = dict(zip(aliases.station_code.astype("string"),
                         aliases.ce_id.astype("string")))
    ce_set = set(str(c) for c in ce_ids)
    edges = {}
    stats = {"rows": 0, "self_loops": 0.0,
             "mapped_weight": 0.0, "unmapped_weight": 0.0}
    for frame in month_frames:
        ok = (frame.is_valid_2025_retiros.fillna(False)
              & frame.is_valid_2025_arribos.fillna(False)
              & ~frame.is_negative_duration.fillna(False))
        sub = frame.loc[ok].reset_index(drop=True)
        stats["rows"] += len(sub)
        ends = {}
        for role, col in [("o", "Ciclo_Estacion_Retiro"),
                          ("d", "Ciclo_EstacionArribo")]:
            ids = _station_lists(sub[col])
            n = ids.map(len).to_numpy()
            events = pd.DataFrame({
                "row": np.repeat(np.arange(len(sub)), n),
                "code": [p for parts in ids for p in parts],
                "weight": 1.0 / np.repeat(n, n)})
            events["ce_id"] = events.code.map(alias_map) \
                .fillna(events.code).astype("string")
            ends[role] = events
        pairs = ends["o"].merge(ends["d"], on="row", suffixes=("_o", "_d"))
        pairs["w"] = pairs.weight_o * pairs.weight_d
        mapped_o = pairs.ce_id_o.isin(ce_set)
        mapped_d = pairs.ce_id_d.isin(ce_set)
        both = pairs.loc[mapped_o & mapped_d]
        stats["mapped_weight"] += float(both.w.sum())
        stats["unmapped_weight"] += float(
            pairs.loc[~(mapped_o & mapped_d), "w"].sum())
        loops = both.ce_id_o == both.ce_id_d
        stats["self_loops"] += float(both.loc[loops, "w"].sum())
        for (o, d), w in both.loc[~loops].groupby(
                ["ce_id_o", "ce_id_d"]).w.sum().items():
            key = (str(o), str(d))
            edges[key] = edges.get(key, 0.0) + float(w)
    return edges, stats


def flow_diagnostics(edges, stations, cfg):
    """Grafo OD no dirigido ponderado: Louvain + espectral descriptivo."""
    geo = stations.set_index("ce_id")
    graph = nx.Graph()
    graph.add_nodes_from(geo.index)
    for (o, d), w in edges.items():
        if o in geo.index and d in geo.index:
            if graph.has_edge(o, d):
                graph[o][d]["weight"] += w
            else:
                graph.add_edge(o, d, weight=w)
    communities = nx.community.louvain_communities(
        graph, weight="weight", resolution=1, seed=cfg["seed"])
    modularity = nx.community.modularity(
        graph, communities, weight="weight")
    comm_of = {node: i for i, comm in enumerate(communities)
               for node in comm}
    golden = set(geo.index[geo.is_golden.astype(bool)])
    golden_comm = max(range(len(communities)),
                      key=lambda i: len(communities[i] & golden))
    lcc_nodes = max(nx.connected_components(graph), key=len)
    sub = graph.subgraph(lcc_nodes)
    matrix = nx.to_numpy_array(sub, weight="weight")
    emb = SpectralEmbedding(n_components=cfg["embedding_dims"],
                            affinity="precomputed",
                            random_state=cfg["seed"]).fit_transform(matrix)
    nodes = list(sub.nodes)
    xy = np.c_[geo.loc[nodes].geometry.x, geo.loc[nodes].geometry.y]
    rng = np.random.default_rng(cfg["seed"])
    idx = rng.choice(len(nodes) * (len(nodes) - 1) // 2,
                     size=min(cfg["embedding_pairs"],
                              len(nodes) * (len(nodes) - 1) // 2),
                     replace=False)
    iu = np.triu_indices(len(nodes), 1)
    d_emb = np.sqrt(((emb[iu[0][idx]] - emb[iu[1][idx]]) ** 2).sum(1))
    d_geo = np.sqrt(((xy[iu[0][idx]] - xy[iu[1][idx]]) ** 2).sum(1))
    rho = float(spearmanr(d_emb, d_geo).statistic)
    intra = []
    comm_nodes = list(communities[golden_comm] & set(nodes))
    if len(comm_nodes) > 1:
        cxy = np.c_[geo.loc[comm_nodes].geometry.x,
                    geo.loc[comm_nodes].geometry.y]
        intra = pdist_condensed(cxy)
    frame = geo[["station_id", "is_golden"]].copy()
    frame["community"] = [comm_of.get(c) for c in frame.index]
    frame = frame.reset_index()
    for k in range(emb.shape[1]):
        col = {c: float("nan") for c in frame.ce_id}
        col.update({node: float(emb[i, k])
                    for i, node in enumerate(nodes)})
        frame[f"emb_{k}"] = frame.ce_id.map(col)
    return {
        "graph": graph, "community_of": comm_of,
        "n_communities": len(communities),
        "modularity": modularity,
        "golden_community": golden_comm,
        "golden_share": len(set(communities[golden_comm]) & golden)
        / max(len(golden), 1),
        "golden_intra_median_m": float(np.median(intra))
        if len(intra) else float("nan"),
        "lcc_size": len(lcc_nodes),
        "embedding_geo_spearman": rho,
        "frame": frame}


def pdist_condensed(xy):
    d = np.sqrt(((xy[:, 0][:, None] - xy[:, 0]) ** 2)
                + ((xy[:, 1][:, None] - xy[:, 1]) ** 2))
    return d[np.triu_indices(len(xy), 1)]


# ---------------------------------------------------------------------------
# 3. Objetivo, decodificador de llaves aleatorias y GA
# ---------------------------------------------------------------------------

def new_pop(selected, ctx):
    return dep.new_pop(selected, ctx)


def objective(selected, ctx, affinity, weight, budget):
    """f_w(S) = w·new_pop/P_norm + (1-w)·sum(affinity)/B."""
    pnorm = dep.P_norm(ctx, budget)
    gain = new_pop(selected, ctx) / pnorm if pnorm > 0 else 0.0
    aff = float(affinity[list(selected)].sum()) / budget \
        if len(selected) else 0.0
    return float(weight * gain + (1 - weight) * aff)


def decode(keys, ctx, budget):
    """Decodificador de llaves aleatorias: crece contiguo desde la red."""
    keys = np.asarray(keys, dtype=float)
    n = len(keys)
    selected = np.zeros(n, bool)
    blocked = np.zeros(n, bool)
    connected = ctx["initial_connected"].copy()
    order, attaches = [], []
    for _ in range(budget):
        cand = np.where(connected & ~blocked & ~selected)[0]
        if not len(cand):
            break
        i = int(cand[np.argmax(keys[cand])])
        selected[i] = True
        order.append(i)
        attaches.append(dep._attach_node(i, order[:-1], ctx))
        connected[dep._neighbors(ctx["link"], i)] = True
        blocked[dep._neighbors(ctx["spacing"], i)] = True
    return {"order": order, "attach": attaches}


def greedy_fgain(ctx, affinity, weight, budget):
    """Greedy de ganancia marginal de f_w (misma construcción factible)."""
    selected = np.zeros(len(ctx["xy"]), bool)
    blocked = np.zeros(len(ctx["xy"]), bool)
    connected = ctx["initial_connected"].copy()
    inc = ctx["incidence"].tocsr()
    covered = np.zeros(inc.shape[1], bool)
    pnorm = dep.P_norm(ctx, budget)
    order, attaches = [], []
    for _ in range(budget):
        cand = np.where(connected & ~blocked & ~selected)[0]
        if not len(cand):
            break
        remaining = ctx["uncovered_pop"] * ~covered
        gains_pop = np.asarray(inc[cand].dot(remaining)).ravel()
        gains = (weight * gains_pop / pnorm if pnorm > 0
                 else gains_pop * 0.0)
        gains = gains + (1 - weight) * affinity[cand] / budget
        i = int(cand[np.argmax(gains)])
        selected[i] = True
        order.append(i)
        attaches.append(dep._attach_node(i, order[:-1], ctx))
        covered[inc.indices[inc.indptr[i]:inc.indptr[i + 1]]] = True
        connected[dep._neighbors(ctx["link"], i)] = True
        blocked[dep._neighbors(ctx["spacing"], i)] = True
    return {"order": order, "attach": attaches}


def _mutate_clip(individual, sigma, indpb):
    for i in range(len(individual)):
        if random.random() < indpb:
            individual[i] = min(1.0, max(
                0.0, individual[i] + random.gauss(0, sigma)))
    return individual,


def _toolbox(ctx, affinity, weight, budget, cfg):
    """Caja DEAP con decodificador de llaves (registro único garantizado)."""
    ga = cfg["ga"]
    if not hasattr(creator, "FitnessMaxM3"):
        creator.create("FitnessMaxM3", base.Fitness, weights=(1.0,))
    if not hasattr(creator, "IndividualM3"):
        creator.create("IndividualM3", list,
                       fitness=creator.FitnessMaxM3)
    toolbox = base.Toolbox()
    toolbox.register("attr_float", random.random)
    toolbox.register("individual", tools.initRepeat,
                     creator.IndividualM3, toolbox.attr_float,
                     len(ctx["xy"]))
    toolbox.register("population", tools.initRepeat, list,
                     toolbox.individual)
    toolbox.register("evaluate", lambda ind: (
        objective(decode(np.asarray(ind), ctx, budget)["order"],
                  ctx, affinity, weight, budget),))
    toolbox.register("mate", tools.cxUniform, indpb=ga["cx_indpb"])
    toolbox.register("mutate", _mutate_clip, sigma=ga["mut_sigma"],
                     indpb=ga["mut_indpb"])
    toolbox.register("select", tools.selTournament,
                     tournsize=ga["tournament"])
    return toolbox


def run_ga(ctx, affinity, weight, budget, seed, cfg):
    """GA DEAP sobre llaves aleatorias; elitismo fijo; sin semilla greedy."""
    ga = cfg["ga"]
    random.seed(seed)
    np.random.seed(seed)
    toolbox = _toolbox(ctx, affinity, weight, budget, cfg)
    pop = toolbox.population(n=ga["population"])
    for ind in pop:
        ind.fitness.values = toolbox.evaluate(ind)
    history = [{"generation": -1,
                "best": float(max(i.fitness.values[0] for i in pop)),
                "mean": float(np.mean([i.fitness.values[0]
                                       for i in pop])),
                "std": float(np.std([i.fitness.values[0]
                                     for i in pop]))}]
    for gen in range(ga["generations"]):
        elite = list(map(toolbox.clone, tools.selBest(pop, ga["elite"])))
        offspring = list(map(toolbox.clone, toolbox.select(
            pop, len(pop) - ga["elite"])))
        for a, b in zip(offspring[::2], offspring[1::2]):
            if random.random() < ga["cxpb"]:
                toolbox.mate(a, b)
                del a.fitness.values, b.fitness.values
        for ind in offspring:
            if random.random() < ga["mutpb"]:
                toolbox.mutate(ind)
                del ind.fitness.values
        for ind in offspring:
            if not ind.fitness.valid:
                ind.fitness.values = toolbox.evaluate(ind)
        pop = elite + offspring
        fitnesses = [ind.fitness.values[0] for ind in pop]
        history.append({"generation": gen,
                        "best": float(max(fitnesses)),
                        "mean": float(np.mean(fitnesses)),
                        "std": float(np.std(fitnesses))})
    best = tools.selBest(pop, 1)[0]
    decoded = decode(np.asarray(best), ctx, budget)
    return {"keys": np.asarray(best), "history": history,
            "f": objective(decoded["order"], ctx, affinity,
                           weight, budget),
            "decoded": decoded}


def random_portfolios(ctx, affinity, weight, budget, n, seed):
    rng = np.random.default_rng(seed)
    return np.asarray([
        objective(decode(rng.uniform(0, 1, len(ctx["xy"])),
                         ctx, budget)["order"], ctx, affinity,
                  weight, budget)
        for _ in range(n)])


def _jaccard_mean(site_sets):
    pairs = [(a, b) for i, a in enumerate(site_sets)
             for b in site_sets[i + 1:]]
    if not pairs:
        return float("nan")
    return float(np.mean([
        len(a & b) / len(a | b) if a | b else 1.0
        for a, b in pairs]))


def _jaccard(a, b):
    a, b = set(a), set(b)
    return float(len(a & b) / len(a | b)) if a | b else 1.0


def _mean_aff(affinity, order):
    return float(affinity[list(order)].mean()) if len(order) else 0.0


def _finite(value):
    value = float(value)
    return value if np.isfinite(value) else None


def hop_affinity(hops_golden, in_component):
    """Afinidad determinista: 1/(1+saltos a Golden), 0 fuera del
    componente o sin camino a una estación dorada.

    Es función directa de los saltos a Golden: las métricas de cercanía
    a Golden de un portafolio optimizado con ella quedan optimizadas
    POR CONSTRUCCIÓN y no constituyen evidencia independiente.
    """
    hops = np.asarray(hops_golden, dtype=float)
    valid = np.asarray(in_component, dtype=bool) & (hops >= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(valid, 1.0 / (1.0 + hops), 0.0)


def _records(df):
    """Registros JSON-seguros: NaN/pd.NA -> None (campo no aplicable)."""
    return df.astype(object).where(pd.notna(df), None) \
        .to_dict(orient="records")


# ---------------------------------------------------------------------------
# Análisis completo
# ---------------------------------------------------------------------------

def analyze(data, verbose=False):
    started = time.perf_counter()

    def tick(label):
        if verbose:
            print(f"[m3] {label}: {time.perf_counter() - started:.1f}s",
                  file=sys.stderr, flush=True)

    frames = data["frames"]
    cfg = CONFIG
    metric = cfg["metric_crs"]
    stations = frames["station_env"].to_crs(metric).reset_index(drop=True)
    stations_xy = np.c_[stations.geometry.x, stations.geometry.y]
    is_golden = stations.is_golden.astype(bool).to_numpy()
    sites = frames["sites"].to_crs(metric).reset_index(drop=True)
    cells = frames["cells"].to_crs(metric).reset_index(drop=True)
    sites_xy = np.c_[sites.x, sites.y]

    # ---- Contexto del contrato de despliegue (04) --------------------------
    incidence = dep.site_cell_incidence(sites_xy, cells, cfg)
    ctx = dep.build_network_context(sites, cells, incidence,
                                    stations, cfg)
    tick("deployment_ctx")

    # ---- Grafo geométrico + afinidad determinista de saltos --------------
    neighbors, in_component, graph = geometric_graph(
        stations_xy, sites_xy, cfg)
    n_st = len(stations_xy)
    golden_nodes = np.nonzero(is_golden)[0].tolist()
    hops_gold_all = hops_on_graph(neighbors, golden_nodes, n_st,
                                  len(sites_xy))
    tick("graph+hops")

    # Afinidad primaria: 1/(1+saltos a Golden). Node2Vec quedó retirado
    # (ver `node2vec_retired` en el reporte): su afinidad no ordenaba por
    # cercanía al núcleo dorado en la validación histórica publicada.
    affinity = hop_affinity(hops_gold_all, in_component)
    tick("affinity")

    # ---- Grafo de flujos (descriptivo) -------------------------------------
    month_frames = [pd.read_parquet(data["trip_paths"][m],
                                    columns=["Ciclo_Estacion_Retiro",
                                             "Ciclo_EstacionArribo",
                                             "is_valid_2025_retiros",
                                             "is_valid_2025_arribos",
                                             "is_negative_duration"])
                    for m in MONTHS]
    edges, flow_stats = flow_edges(
        month_frames, frames["aliases"], stations.ce_id)
    flow = flow_diagnostics(edges, stations, cfg)
    tick("flow")

    # ---- Optimización: greedy (principal), GA y aleatorios ---------------
    # El greedy de ganancia marginal es el motor prescriptivo principal
    # —determinista y órdenes de magnitud más barato—. El GA se conserva
    # como sensibilidad con las mismas semillas/parámetros; por cada
    # (w, B) se reportan f greedy, f mejor/media del GA, brecha, percentil
    # frente a aleatorios, Jaccard GA–greedy y tiempos de pared.
    w_primary, b_primary = cfg["primary_weight"], cfg["budget"]
    runs, ga_histories, solutions, best_per = [], [], {}, {}
    ga_greedy_table = []
    for weight in cfg["weights"]:
        budgets = [b_primary] + ([b for b in cfg["budget_sensitivity"]
                                  if b != b_primary]
                                 if weight == w_primary else [])
        for budget_b in budgets:
            tick(f"opt w={weight} B={budget_b}")
            seeds = (cfg["seeds_primary"] if budget_b == b_primary
                     and weight == w_primary else cfg["seeds_other"])
            t0 = time.perf_counter()
            g_sol = greedy_fgain(ctx, affinity, weight, budget_b)
            g_wall = time.perf_counter() - t0
            g_f = objective(g_sol["order"], ctx, affinity,
                            weight, budget_b)
            runs.append({"weight": weight, "budget": budget_b,
                         "method": "greedy", "seed": None, "f": g_f,
                         "wall_s": g_wall,
                         "new_pop": new_pop(g_sol["order"], ctx),
                         "mean_affinity": _mean_aff(affinity,
                                                    g_sol["order"]),
                         "n_selected": len(g_sol["order"])})
            solutions[("greedy", weight, budget_b)] = g_sol
            ga_sols, ga_walls = {}, {}
            for seed in seeds:
                t0 = time.perf_counter()
                ga = run_ga(ctx, affinity, weight, budget_b, seed,
                            dict(cfg))
                ga_walls[seed] = time.perf_counter() - t0
                ga_sols[seed] = ga
                runs.append({"weight": weight, "budget": budget_b,
                             "method": "ga", "seed": seed, "f": ga["f"],
                             "wall_s": ga_walls[seed],
                             "new_pop": new_pop(ga["decoded"]["order"],
                                                ctx),
                             "mean_affinity": _mean_aff(
                                 affinity, ga["decoded"]["order"]),
                             "n_selected": len(ga["decoded"]["order"])})
                ga_histories.extend(
                    {"weight": weight, "budget": budget_b, "seed": seed,
                     **row} for row in ga["history"])
            best_seed = max(ga_sols, key=lambda s: ga_sols[s]["f"])
            best_per[(weight, budget_b)] = {
                "seed": best_seed, "sol": ga_sols[best_seed],
                "wall_s": ga_walls[best_seed]}
            rand = random_portfolios(ctx, affinity, weight, budget_b,
                                     cfg["n_random_portfolios"],
                                     cfg["seed"])
            ga_fs = [g["f"] for g in ga_sols.values()]
            std_ga = float(np.std(ga_fs))
            gap = float(max(ga_fs) - g_f)
            j_gg = _jaccard(
                ga_sols[best_seed]["decoded"]["order"],
                g_sol["order"])
            ga_total_wall = float(sum(ga_walls.values()))
            verdict = ("empate (|brecha| <= std entre semillas)"
                       if abs(gap) <= std_ga
                       else ("ga" if gap > 0 else "greedy"))
            ga_greedy_table.append({
                "weight": weight, "budget": budget_b,
                "greedy_f": g_f,
                "ga_best_f": float(max(ga_fs)),
                "ga_mean_f": float(np.mean(ga_fs)),
                "ga_std_f": std_ga,
                "ga_minus_greedy": gap,
                "ga_percentile_vs_random": float(
                    (rand < max(ga_fs)).mean()),
                "jaccard_ga_greedy": j_gg,
                "jaccard_ga_pairwise": _jaccard_mean(
                    [set(g["decoded"]["order"])
                     for g in ga_sols.values()]),
                "greedy_wall_s": g_wall,
                "ga_total_wall_s": ga_total_wall,
                "ga_mean_wall_s_per_seed": float(
                    np.mean(list(ga_walls.values()))),
                "verdict": verdict})
            runs.append({"weight": weight, "budget": budget_b,
                         "method": "random", "seed": cfg["seed"],
                         "f": float(rand.mean()),
                         "f_p95": float(np.quantile(rand, 0.95)),
                         "f_max": float(rand.max()),
                         "ga_percentile_vs_random": float(
                             (rand < max(ga_fs)).mean()),
                         "ga_minus_greedy": gap,
                         "jaccard_ga_greedy": j_gg,
                         "jaccard_ga": _jaccard_mean(
                             [set(g["decoded"]["order"])
                              for g in ga_sols.values()]),
                         "std_f_ga": std_ga,
                         "wall_s": None,
                         "n_selected": None})
    tick("optimize")

    runs_df = pd.DataFrame(runs)
    ga_history = pd.DataFrame(ga_histories)

    # ---- Portafolios publicados y métricas comunes --------------------------
    features = frames["features"]
    universe04 = frames["universe04"]

    def metrics_of(sol):
        return dep.portfolio_metrics(sol["order"], ctx, sites,
                                     features, universe04)

    portfolio_rows = []
    frames_out = {}

    def add_portfolio(tag, sol, method, weight, budget_b, score_vec):
        frame = dep.portfolio_frame(sol["order"], sol["attach"],
                                    sites, ctx)
        frame["method"] = method
        frame["weight"] = weight
        frame["budget"] = budget_b
        frame["score"] = score_vec[list(sol["order"])]
        frames_out[tag] = frame
        for _, row in frame.iterrows():
            portfolio_rows.append(row.to_dict())
        if not dep.is_feasible(sol["order"], ctx, budget_b):
            raise ValueError(f"published portfolio infeasible: {tag}")
        return frame

    # Portafolios publicados: el greedy es el motor principal —oficial en
    # cada presupuesto con el peso primario—; la mejor corrida del GA en
    # la configuración primaria entra como sensibilidad `ga_best`.
    for budget_b in cfg["budget_sensitivity"]:
        sol = solutions[("greedy", w_primary, budget_b)]
        add_portfolio(f"greedy_B{budget_b}", sol, "greedy", w_primary,
                      budget_b, affinity)
    primary_sol = solutions[("greedy", w_primary, b_primary)]
    ga_best = best_per[(w_primary, b_primary)]
    add_portfolio("ga_best", ga_best["sol"]["decoded"], "ga",
                  w_primary, b_primary, affinity)
    portafolios = gpd.GeoDataFrame(
        pd.DataFrame(portfolio_rows), geometry="geometry",
        crs=sites.crs)

    primary_metrics = metrics_of(primary_sol)
    metrics_by = {
        "primary": primary_metrics,
        "budget_sensitivity": {
            str(b): metrics_of(solutions[("greedy", w_primary, b)])
            for b in cfg["budget_sensitivity"]},
        "ga_best": metrics_of(ga_best["sol"]["decoded"]),
    }
    ga_best_jaccard = _jaccard(
        primary_sol["order"], ga_best["sol"]["decoded"]["order"])

    tradeoff = pd.DataFrame([
        {"weight": w, "budget": b_primary,
         "f": objective(
             solutions[("greedy", w, b_primary)]["order"], ctx,
             affinity, w, b_primary),
         "new_pop_norm":
             new_pop(solutions[("greedy", w, b_primary)]["order"],
                     ctx) / dep.P_norm(ctx, b_primary)
             if dep.P_norm(ctx, b_primary) > 0 else 0.0,
         "mean_affinity": _mean_aff(
             affinity,
             solutions[("greedy", w, b_primary)]["order"])}
        for w in cfg["weights"]])

    ga_row_primary = next(
        r for r in ga_greedy_table
        if r["weight"] == w_primary and r["budget"] == b_primary)
    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "notebook": "07_Motor3_Grafo_y_Genetico.ipynb",
        "scope": {
            "autonomous_no_motor1_motor2_inputs": True,
            "ageb_is_context_site_is_decision": True,
            "no_one_station_per_ageb": True,
            "contiguous_growth_from_network": True,
            "heuristic_not_proven_optimum": True,
            "greedy_is_primary_engine": True,
            "ga_is_sensitivity_not_deployment": True,
            "affinity_is_structural_not_demand": True,
            "affinity_is_function_of_hops_to_golden": True,
            "golden_proximity_optimized_by_construction": True,
            "flow_diagnostic_descriptive_only": True,
            "node2vec_retired_from_pipeline": True,
        },
        "configuration": CONFIG,
        "upstream": data["upstream_refs"],
        "affinity": {
            "definition": "1/(1+saltos a Golden) para sitios en el "
                          "componente conectado; 0 en otro caso",
            "deterministic": True,
            "n_sites": int(len(sites_xy)),
            "n_graph_nodes": int(n_st + len(sites_xy)),
            "n_graph_edges": int(graph.number_of_edges()),
            "sites_in_component_share": float(in_component.mean()),
            "n_golden_stations": int(len(golden_nodes)),
            "scope_warning": "la afinidad es función directa de los "
                "saltos a Golden: las métricas de cercanía a Golden del "
                "portafolio (saltos máximos y mediana) quedan optimizadas "
                "POR CONSTRUCCIÓN y NO constituyen evidencia "
                "independiente a favor del Motor 3",
        },
        "node2vec_retired": {
            "decision": "retirado del pipeline por decisión "
                        "metodológica",
            "historical_schema": "v3-motor3-3",
            "historical_analysis_id":
                "69a83e61b633b19f6b2914202c072d4b155a2cd59f397d4049"
                "e8cd90398e05e7",
            "historical_evidence_not_recomputed": {
                "spearman_affinity_vs_minus_hops_golden": {
                    "q_0.5": {"centroid": -0.095,
                              "nearest_golden": -0.095},
                    "q_1.0": {"centroid": -0.218,
                              "nearest_golden": -0.170},
                    "q_2.0": {"centroid": -0.101,
                              "nearest_golden": -0.008}},
                "centroid_norm_ratio": 0.735,
                "golden_pairwise_cosine": {"p10": 0.14, "p50": 0.56,
                                           "p90": 0.88}},
        },
        "flow": {
            "rows_used": flow_stats["rows"],
            "mapped_weight_share": flow_stats["mapped_weight"]
            / max(flow_stats["mapped_weight"]
                  + flow_stats["unmapped_weight"], 1e-12),
            "self_loop_weight": flow_stats["self_loops"],
            "n_communities": flow["n_communities"],
            "modularity": float(flow["modularity"]),
            "golden_community": flow["golden_community"],
            "golden_community_share": float(flow["golden_share"]),
            "golden_intra_median_m": flow["golden_intra_median_m"],
            "lcc_size": flow["lcc_size"],
            "embedding_geo_spearman": flow["embedding_geo_spearman"],
            "descriptive_only": True,
        },
        "runs": _records(runs_df),
        "ga_vs_greedy": ga_greedy_table,
        "timing": {
            "greedy_total_wall_s": float(
                sum(r["greedy_wall_s"] for r in ga_greedy_table)),
            "ga_total_wall_s": float(
                sum(r["ga_total_wall_s"] for r in ga_greedy_table)),
            "ga_mean_wall_s_per_seed": float(
                sum(r["ga_total_wall_s"] for r in ga_greedy_table)
                / max(len(ga_greedy_table), 1)),
        },
        "primary": {
            "weight": w_primary, "budget": b_primary,
            "method": "greedy",
            "f": ga_row_primary["greedy_f"],
            "metrics": primary_metrics,
            "ga_best": {
                "seed": ga_best["seed"],
                "f": ga_best["sol"]["f"],
                "jaccard_vs_greedy": ga_best_jaccard},
            "ga_better_than_greedy":
                bool(ga_row_primary["ga_minus_greedy"] > 0),
            "primary_change_vs_v3_motor3_3": {
                "previous_schema": "v3-motor3-3",
                "previous_engine": "GA primario con afinidad Node2Vec",
                "previous_B30": {
                    "new_pop": 304459.5365476905,
                    "n_agebs": 26,
                    "stations_per_ageb": {"1": 24, "2": 1, "3+": 1},
                    "max_hops_network": 13,
                    "median_hops_golden": 11.0,
                    "out_of_domain_04_share": 0.5333333333333333},
                "current_B30": primary_metrics},
        },
        "portfolios": metrics_by,
        "pending_validation": [
            "Affinity is a deterministic function of hops to the golden "
            "core: golden-proximity portfolio metrics are optimized by "
            "construction and are not independent evidence",
            "Structural affinity is proximity to the golden core, not "
            "observed demand",
            "Areal interpolation and 500 m catchments are assumptions, "
            "not observed demand",
            "No street network, cost, or field validation",
            "The GA is a heuristic without optimality guarantee; its "
            "best run is published only as a sensitivity portfolio",
        ],
    }

    outputs = [
        ("m3_flow_communities.csv", "csv", flow["frame"]),
        ("m3_flow_summary.csv", "csv", pd.DataFrame([{
            "rows_used": flow_stats["rows"],
            "mapped_weight": flow_stats["mapped_weight"],
            "unmapped_weight": flow_stats["unmapped_weight"],
            "self_loop_weight": flow_stats["self_loops"],
            "n_communities": flow["n_communities"],
            "modularity": float(flow["modularity"]),
            "golden_community": flow["golden_community"],
            "golden_share": float(flow["golden_share"]),
            "golden_intra_median_m": flow["golden_intra_median_m"],
            "lcc_size": flow["lcc_size"],
            "embedding_geo_spearman":
                flow["embedding_geo_spearman"]}])),
        ("m3_runs.csv", "csv", runs_df),
        ("m3_ga_history.csv", "csv", ga_history),
        ("m3_ga_greedy.csv", "csv", pd.DataFrame(ga_greedy_table)),
        ("m3_portafolios.parquet", "parquet", portafolios),
        ("m3_tradeoff.csv", "csv", tradeoff),
    ]
    return {"report": report, "outputs": outputs,
            "flow": flow, "runs": runs_df, "ga_history": ga_history,
            "ga_greedy_table": pd.DataFrame(ga_greedy_table),
            "portafolios": portafolios, "tradeoff": tradeoff,
            "ctx": ctx, "sites": sites, "cells": cells,
            "stations": stations, "affinity": affinity,
            "hops_golden": hops_gold_all,
            "in_component": in_component,
            "primary_sol": primary_sol,
            "ga_best_sol": ga_best["sol"]["decoded"],
            "metrics_by": metrics_by,
            "ga_best_seed": ga_best["seed"]}
