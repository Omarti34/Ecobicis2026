"""Contrato de despliegue común del cuaderno 04: sitios, reglas y métricas.

Los tres motores (05, 06 y 07) resuelven la MISMA tarea de formas
distintas: con un presupuesto B fijo elegido por el usuario, seleccionar
un portafolio de B SITIOS candidatos (coordenadas) —no AGEBs— que crece
de forma contigua desde la red existente. Para que sus respuestas sean
comparables, el 04 congela aquí las piezas compartidas:

- la rejilla de sitios candidatos (una sola, publicada una sola vez);
- la superficie poblacional y la cobertura existente;
- la distancia de enlace y las reglas de factibilidad;
- el constructor de contexto de red, la función new_pop, la cota P_norm;
- el verificador independiente is_feasible (con techo por AGEB opcional);
- el greedy de cobertura ponderado por puntaje del motor;
- las métricas de portafolio idénticas para los tres motores.

Nada en este módulo conoce el puntaje de ningún motor: site_score es un
vector arbitrario que cada motor aporta según su propio método.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree
from shapely.geometry import box

DEPLOY_CONFIG = {
    "metric_crs": "EPSG:32614",
    "link_distance_m": 500,
    "link_grid": [300, 400, 500, 600, 700, 800],
    "coverage_radius_m": 500,
    "min_spacing_m": 300,
    "site_grid_m": 250,
    "max_reach_m": 3000,
    "pop_cell_m": 200,
    "budget_grid": [15, 30, 50],
    "primary_budget": 30,
    "nn_quantiles": [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99],
}

STOP_BUDGET = "budget"
STOP_NO_FEASIBLE = "no_feasible"
STOP_NO_POSITIVE = "no_positive_value"


# ---------------------------------------------------------------------------
# 1. Distancia de enlace y justificación
# ---------------------------------------------------------------------------

def link_distance_analysis(stations_xy, is_golden, grid):
    """Componentes del grafo geométrico por distancia de enlace."""
    tree = cKDTree(stations_xy)
    rows = []
    for d in grid:
        pairs = tree.query_pairs(d, output_type="ndarray")
        graph = nx.Graph()
        graph.add_nodes_from(range(len(stations_xy)))
        if len(pairs):
            graph.add_edges_from(pairs.tolist())
        comps = list(nx.connected_components(graph))
        largest = max(comps, key=len)
        rows.append({"link_distance_m": d,
                     "n_components": len(comps),
                     "largest_component": len(largest),
                     "golden_in_largest":
                         int(is_golden[list(largest)].sum())})
    return pd.DataFrame(rows)


def check_link_distance(link_table, cfg):
    """Afirma que link_distance_m es la mínima distancia con 1 componente."""
    table = link_table.sort_values("link_distance_m")
    single = table.loc[table.n_components == 1, "link_distance_m"]
    if not len(single) or int(single.min()) != cfg["link_distance_m"]:
        raise ValueError(
            "Configured link distance is not the smallest tested distance "
            "producing a single component")
    below = table.loc[table.link_distance_m < cfg["link_distance_m"]]
    if (below.n_components <= 1).any():
        raise ValueError("A smaller tested distance already connects "
                         "the network")


def nearest_neighbor_quantiles(stations_xy, quantiles):
    tree = cKDTree(stations_xy)
    dist, _ = tree.query(stations_xy, k=2)
    nn = dist[:, 1]
    return {f"P{int(q * 100):02d}": float(np.quantile(nn, q))
            for q in quantiles}


# ---------------------------------------------------------------------------
# 2. Sitios candidatos (neutrales: sin puntaje de motor)
# ---------------------------------------------------------------------------

def build_sites(candidates, stations_xy, cfg):
    """Rejilla de sitios dentro de AGEBs candidatas proyectables.

    Punto cada site_grid_m contenido en el polígono, a >= min_spacing_m
    de toda estación y a <= max_reach_m de la red; site_id estable por
    orden (y, x). Las candidatas no proyectables no generan sitios: sin
    perfil de entorno (y población rural desconocida) no hay insumo
    honesto para evaluarlas. Las columnas son neutras: ningún puntaje de
    motor vive aquí.
    """
    metric = cfg["metric_crs"]
    polys = candidates[["cvegeo", "nom_mun", "geometry"]].to_crs(metric)
    bounds = polys.total_bounds
    step = cfg["site_grid_m"]
    xs = np.arange(np.floor(bounds[0] / step) * step, bounds[2], step)
    ys = np.arange(np.floor(bounds[1] / step) * step, bounds[3], step)
    grid = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(np.tile(xs, len(ys)),
                                    np.repeat(ys, len(xs))),
        crs=metric)
    joined = gpd.sjoin(grid, polys[["cvegeo", "nom_mun", "geometry"]],
                       how="inner", predicate="within").drop(
        columns="index_right")
    xy = np.c_[joined.geometry.x, joined.geometry.y]
    dist = cKDTree(stations_xy).query(xy)[0]
    keep = (dist >= cfg["min_spacing_m"]) & (dist <= cfg["max_reach_m"])
    sites = joined.loc[keep].copy()
    sites["dist_to_network_m"] = dist[keep]
    sites["x"] = sites.geometry.x
    sites["y"] = sites.geometry.y
    sites = sites.sort_values(["y", "x"]).reset_index(drop=True)
    sites["site_id"] = [f"S{i:05d}" for i in range(len(sites))]
    return sites[["site_id", "x", "y", "cvegeo", "nom_mun",
                  "dist_to_network_m", "geometry"]]


# ---------------------------------------------------------------------------
# 3. Superficie de población e incidencia sitio→celda
# ---------------------------------------------------------------------------

def population_surface(agebs, stations_xy, cfg):
    """Celdas cuadradas con población interpolada por área.

    Densidad uniforme dentro de cada AGEB (supuesto declarado); POBTOT
    desconocido aporta 0 y su fracción de área queda marcada como
    unknown_share. covered_existing = centroide a <= coverage_radius_m
    de una estación; solo las celdas descubiertas alimentan new_pop.
    """
    metric = cfg["metric_crs"]
    geo = agebs[["cvegeo", "POBTOT", "geometry"]].to_crs(metric)
    cell = cfg["pop_cell_m"]
    bounds = geo.total_bounds
    xs = np.arange(np.floor(bounds[0] / cell) * cell, bounds[2], cell)
    ys = np.arange(np.floor(bounds[1] / cell) * cell, bounds[3], cell)
    cells = gpd.GeoDataFrame(
        {"cell_id": [f"C{i:05d}" for i in range(len(xs) * len(ys))]},
        geometry=[box(x, y, x + cell, y + cell)
                  for y in ys for x in xs],
        crs=metric)
    geo = geo.assign(ageb_area=geo.geometry.area)
    inter = gpd.overlay(
        cells, geo[["cvegeo", "POBTOT", "ageb_area", "geometry"]],
        how="intersection")
    # share pondera población (conserva POBTOT); cell_share reparte área
    inter["share"] = inter.geometry.area / inter.ageb_area
    inter["cell_share"] = inter.geometry.area / cell ** 2
    pop = inter.assign(w=inter.POBTOT.fillna(0) * inter.share) \
        .groupby("cell_id").w.sum()
    unknown = inter.loc[inter.POBTOT.isna()].groupby("cell_id") \
        .cell_share.sum()
    cells["pop"] = cells.cell_id.map(pop).fillna(0.0)
    cells["unknown_share"] = cells.cell_id.map(unknown).fillna(0.0)
    centroids = cells.geometry.centroid
    dist = cKDTree(stations_xy).query(
        np.c_[centroids.x, centroids.y])[0]
    cells["covered_existing"] = dist <= cfg["coverage_radius_m"]
    return cells


def site_cell_incidence(sites_xy, cells, cfg):
    """CSR sitio→celdas no cubiertas a coverage_radius_m del centroide."""
    uncovered = cells.loc[~cells.covered_existing].reset_index(drop=True)
    cent = uncovered.geometry.centroid
    hits = cKDTree(sites_xy).query_ball_point(
        np.c_[cent.x, cent.y], r=cfg["coverage_radius_m"])
    rows = np.array([s for ss in hits for s in ss], dtype=np.int64)
    cols = np.array([c for c, ss in enumerate(hits)
                     for _ in ss], dtype=np.int64)
    inc = csr_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)),
                     shape=(len(sites_xy), len(uncovered)))
    return inc, uncovered


# ---------------------------------------------------------------------------
# 4. Contexto de red, objetivo de cobertura y factibilidad
# ---------------------------------------------------------------------------

def build_network_context(sites, cells, incidence, stations, cfg):
    """Contexto precalculado de reglas compartidas (sin puntaje de motor)."""
    inc, uncovered = incidence
    xy = np.c_[sites.x, sites.y]
    tree = cKDTree(xy)

    def adjacency(dist):
        pairs = tree.query_pairs(dist, output_type="ndarray")
        if not len(pairs):
            return csr_matrix((len(sites), len(sites)), dtype=np.int8)
        rows = np.r_[pairs[:, 0], pairs[:, 1]]
        cols = np.r_[pairs[:, 1], pairs[:, 0]]
        return csr_matrix(
            (np.ones(len(rows), dtype=np.int8), (rows, cols)),
            shape=(len(sites), len(sites)))

    pop = uncovered["pop"].to_numpy(float)
    single = np.asarray(
        (inc.astype(bool).T.multiply(pop.reshape(-1, 1)))
        .sum(axis=1)).ravel()
    stations_xy = np.c_[stations.geometry.x, stations.geometry.y]
    return {
        "xy": xy,
        "link": adjacency(cfg["link_distance_m"]),
        "spacing": adjacency(cfg["min_spacing_m"]),
        "initial_connected":
            sites.dist_to_network_m.to_numpy()
            <= cfg["link_distance_m"],
        "incidence": inc, "uncovered_pop": pop,
        "single_pop": single,
        "uncovered_total_pop": float(pop.sum()),
        "dist_to_network": sites.dist_to_network_m.to_numpy(),
        "stations_xy": stations_xy,
        "stations_tree": cKDTree(stations_xy),
        "station_ids": stations.station_id.astype(str).to_numpy(),
        "station_ce": stations.ce_id.astype(str).to_numpy(),
        "station_is_golden": stations.is_golden.astype(bool).to_numpy(),
        "site_ids": sites.site_id.to_numpy(),
        "site_cvegeo": sites.cvegeo.astype(str).to_numpy(),
        "config": dict(cfg),
    }


def new_pop(selected, ctx):
    """Población nueva cubierta: unión de celdas descubiertas."""
    if not len(selected):
        return 0.0
    mask = np.asarray(ctx["incidence"][list(selected)]
                      .sum(axis=0)).ravel() > 0
    return float(ctx["uncovered_pop"][mask].sum())


def P_norm(ctx, budget):
    """Cota submodular: suma de las B mayores coberturas individuales."""
    if budget <= 0 or not len(ctx["single_pop"]):
        return 0.0
    top = np.sort(ctx["single_pop"])[-budget:]
    return float(top.sum())


def _neighbors(adjacency, i):
    return adjacency.indices[adjacency.indptr[i]:adjacency.indptr[i + 1]]


def _attach_node(site, prior, ctx):
    """Estación existente o sitio previo más cercano a <= link_distance.

    Devuelve ("station", pos) o ("site", pos); el candidato siempre está
    conectado, así que al menos una opción existe dentro del enlace.
    """
    d_net, j = ctx["stations_tree"].query(ctx["xy"][site])
    best_kind, best_idx, best_d = "station", int(j), float(d_net)
    for p in prior:
        d = float(np.hypot(*(ctx["xy"][site] - ctx["xy"][p])))
        if d < best_d:
            best_kind, best_idx, best_d = "site", p, d
    return best_kind, best_idx


def attach_name(attach, ctx):
    kind, idx = attach
    if kind == "station":
        return f"est:{ctx['station_ids'][idx]}"
    return ctx["site_ids"][idx]


def _attach_communities(p_sol, ctx, community_of):
    """Comunidad de flujo de la estación raíz de cada anclaje.

    El anclaje puede ser una estación o un sitio previo; en el segundo
    caso se sigue la cadena de anclajes hasta la estación que conectó
    ese sitio a la red.
    """
    order, attaches = p_sol["order"], p_sol["attach"]
    order_pos = {site: i for i, site in enumerate(order)}
    communities = []
    for i, (kind, idx) in enumerate(attaches):
        seen = set()
        cur = (kind, idx)
        station = None
        while True:
            if cur[0] == "station":
                station = str(ctx["station_ce"][cur[1]])
                break
            pos = order_pos.get(cur[1])
            if pos is None or pos in seen:
                break
            seen.add(pos)
            cur = attaches[pos]
        communities.append(community_of.get(station) if station else None)
    return communities


def is_feasible(selected, ctx, budget, ceilings=None, site_cvegeo=None):
    """Verificador independiente del portafolio.

    |S|<=B; separación por parejas >= min_spacing_m; todo sitio alcanza
    la red existente por saltos <= link_distance_m a través de sitios
    seleccionados (BFS desde las estaciones). Si ceilings/site_cvegeo se
    dan, ninguna AGEB puede exceder su techo.
    """
    sel = list(selected)
    if len(sel) > budget or len(sel) != len(set(sel)):
        return False
    cfg = ctx["config"]
    xy = ctx["xy"][sel]
    if len(sel) > 1:
        d = np.sqrt(((xy[:, 0][:, None] - xy[:, 0]) ** 2)
                    + ((xy[:, 1][:, None] - xy[:, 1]) ** 2))
        np.fill_diagonal(d, np.inf)
        if d.min() < cfg["min_spacing_m"] - 1e-9:
            return False
    if ceilings is not None:
        cve = np.asarray(site_cvegeo)[sel] \
            if site_cvegeo is not None else ctx["site_cvegeo"][sel]
        for key, cap in ceilings.items():
            if int(np.sum(cve == key)) > cap:
                return False
    n_st = len(ctx["stations_xy"])
    points = np.r_[ctx["stations_xy"], ctx["xy"][sel]]
    pairs = cKDTree(points).query_pairs(cfg["link_distance_m"],
                                        output_type="ndarray")
    adjacency = [[] for _ in range(len(points))]
    for a, b in pairs:
        adjacency[a].append(b)
        adjacency[b].append(a)
    seen = np.zeros(len(points), bool)
    seen[:n_st] = True
    stack = list(range(n_st))
    while stack:
        for nxt in adjacency[stack.pop()]:
            if not seen[nxt]:
                seen[nxt] = True
                stack.append(nxt)
    return bool(seen[n_st:].all())


# ---------------------------------------------------------------------------
# 5. Greedy de cobertura ponderado por puntaje del motor
# ---------------------------------------------------------------------------

def greedy_coverage(site_score, ctx, budget, ceilings=None,
                    site_cvegeo=None):
    """Greedy de cobertura: valor_s = site_score_s x ganancia poblacional.

    Crece contiguo desde la red: cada paso elige, entre sitios
    conectados, no bloqueados ni seleccionados (y sin exceder el techo
    de su AGEB si se da), el de mayor valor_s = score_s * población de
    celdas descubiertas que s cubriría y S aún no. Empate por site_id
    ascendente (orden de índice). Razón de parada:
    "budget" | "no_feasible" | "no_positive_value".
    """
    score = np.asarray(site_score, dtype=float)
    n = len(ctx["xy"])
    selected = np.zeros(n, bool)
    blocked = np.zeros(n, bool)
    connected = ctx["initial_connected"].copy()
    inc = ctx["incidence"].tocsr()
    covered = np.zeros(inc.shape[1], bool)
    cve = np.asarray(site_cvegeo) if site_cvegeo is not None \
        else ctx["site_cvegeo"]
    counts = {}
    order, attaches = [], []
    stop = STOP_BUDGET
    for _ in range(budget):
        cand = np.where(connected & ~blocked & ~selected)[0]
        if ceilings is not None:
            cand = np.asarray([
                i for i in cand
                if counts.get(cve[i], 0)
                < ceilings.get(cve[i], np.inf)])
        if not len(cand):
            stop = STOP_NO_FEASIBLE
            break
        remaining = ctx["uncovered_pop"] * ~covered
        gains = np.asarray(inc[cand].dot(remaining)).ravel() \
            * score[cand]
        best = int(np.argmax(gains))
        if gains[best] <= 0:
            stop = STOP_NO_POSITIVE
            break
        i = int(cand[best])
        selected[i] = True
        order.append(i)
        attaches.append(_attach_node(i, order[:-1], ctx))
        counts[cve[i]] = counts.get(cve[i], 0) + 1
        covered[inc.indices[inc.indptr[i]:inc.indptr[i + 1]]] = True
        connected[_neighbors(ctx["link"], i)] = True
        blocked[_neighbors(ctx["spacing"], i)] = True
    return {"order": order, "attach": attaches, "stop_reason": stop}


# ---------------------------------------------------------------------------
# 6. Saltos a la red y a la estación dorada más cercana
# ---------------------------------------------------------------------------

def hops(order, sites, stations, cfg):
    """Saltos a la red y a la dorada más cercana (aristas <= link)."""
    sel_xy = sites[["x", "y"]].iloc[list(order)].to_numpy()
    st_xy = np.c_[stations.geometry.x, stations.geometry.y]
    pts = np.r_[st_xy, sel_xy]
    pairs = cKDTree(pts).query_pairs(cfg["link_distance_m"],
                                     output_type="ndarray")
    graph = nx.Graph()
    graph.add_nodes_from(range(len(pts)))
    graph.add_edges_from(pairs.tolist())
    n_st = len(st_xy)
    dist_net = nx.multi_source_dijkstra_path_length(
        graph, list(range(n_st)))
    golden_idx = [i for i, g in enumerate(
        stations.is_golden.astype(bool)) if g]
    dist_gold = nx.multi_source_dijkstra_path_length(graph, golden_idx)
    return (np.array([dist_net.get(n_st + k, -1)
                      for k in range(len(order))]),
            np.array([dist_gold.get(n_st + k, -1)
                      for k in range(len(order))]))


def portfolio_marginals(order, ctx):
    """Ganancia poblacional de cada sitio en su orden de inserción."""
    covered = np.zeros(ctx["incidence"].shape[1], bool)
    deltas = []
    inc = ctx["incidence"].tocsr()
    for i in order:
        cells_idx = inc.indices[inc.indptr[i]:inc.indptr[i + 1]]
        new_cells = cells_idx[~covered[cells_idx]]
        deltas.append(float(ctx["uncovered_pop"][new_cells].sum()))
        covered[cells_idx] = True
    return deltas


def portfolio_frame(order, attaches, sites, ctx):
    """Tabla del portafolio: filas de sitio + orden, anclaje, ganancia."""
    frame = sites.iloc[list(order)].copy()
    frame["order"] = np.arange(1, len(order) + 1)
    frame["attach"] = [attach_name(a, ctx) for a in attaches]
    frame["marginal_new_pop"] = portfolio_marginals(order, ctx)
    return frame


# ---------------------------------------------------------------------------
# 7. Métricas de portafolio compartidas por los tres motores
# ---------------------------------------------------------------------------

def portfolio_metrics(order, ctx, sites, features, universe04):
    """Métricas idénticas para los tres motores.

    Cobertura nueva y su fracción del total descubierto, redundancia
    (población cubierta por >=2 sitios), estructura por AGEB, saltos a
    la red y a la dorada más cercana, distancia media a la red, medias
    ponderadas por sitio de escolaridad/auto frente a todos los sitios
    y fracción de sitios en AGEBs fuera del dominio global del 04.
    """
    sel = list(order)
    inc = ctx["incidence"].tocsr()
    pop = ctx["uncovered_pop"]
    npop = new_pop(sel, ctx)
    if sel:
        counts = np.asarray(inc[sel].sum(axis=0)).ravel()
        covered_mask = counts > 0
        redundancy = float(pop[(counts >= 2) & covered_mask].sum()
                           / npop) if npop > 0 else 0.0
    else:
        redundancy = 0.0
    site_rows = sites.iloc[sel]
    per_ageb = site_rows.cvegeo.value_counts()
    stations_per_ageb = {
        "1": int((per_ageb == 1).sum()),
        "2": int((per_ageb == 2).sum()),
        "3+": int((per_ageb >= 3).sum()),
    }
    hops_net, hops_gold = hops(sel, sites, _stations_frame(ctx),
                               ctx["config"])
    feat = features.set_index("cvegeo") \
        if "cvegeo" in features.columns else features
    host = feat.loc[site_rows.cvegeo]
    all_sites = feat.loc[sites.cvegeo]
    equity = {}
    for col in ["grado_escolar_prom", "pct_viviendas_auto"]:
        sel_mean = float(host[col].mean()) if len(host) else float("nan")
        equity[f"mean_{col}_selected"] = sel_mean
        equity[f"mean_{col}_all_sites"] = float(all_sites[col].mean())
    dom = universe04.set_index("cvegeo").domain_status \
        if "cvegeo" in universe04.columns else None
    out_share = float(np.mean(
        dom.reindex(site_rows.cvegeo).to_numpy() == "out_of_domain")) \
        if dom is not None and len(site_rows) else float("nan")
    return {
        "n_selected": len(sel),
        "new_pop": npop,
        "new_pop_share": npop / ctx["uncovered_total_pop"]
        if ctx["uncovered_total_pop"] > 0 else 0.0,
        "redundancy": redundancy,
        "n_agebs": int(per_ageb.size),
        "stations_per_ageb": stations_per_ageb,
        "max_hops_network": int(hops_net.max()) if len(hops_net) else 0,
        "median_hops_golden": float(np.median(hops_gold))
        if len(hops_gold) else float("nan"),
        "max_hops_golden": int(hops_gold.max()) if len(hops_gold) else 0,
        "mean_dist_to_network_m": float(
            site_rows.dist_to_network_m.mean()) if sel else float("nan"),
        **equity,
        "out_of_domain_04_share": out_share,
    }


def _stations_frame(ctx):
    """GeoDataFrame mínimo de estaciones reconstruido desde el ctx."""
    return gpd.GeoDataFrame(
        {"is_golden": ctx["station_is_golden"]},
        geometry=gpd.points_from_xy(ctx["stations_xy"][:, 0],
                                    ctx["stations_xy"][:, 1]),
        crs=ctx["config"]["metric_crs"])
