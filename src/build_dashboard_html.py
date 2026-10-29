"""Genera la presentación ejecutiva HTML autocontenida del caso EcoBici.

Reutiliza el lenguaje visual de la presentación de referencia (paleta
verde/slate/dorado, tipografías Plus Jakarta Sans + JetBrains Mono,
tarjetas glass-panel, badges, pestañas y simulador), pero alimentado
exclusivamente por los reportes y portafolios sellados del análisis.

Expone ``build_html(D, fig_b64)``, que ``build_entregable.py`` invoca en
lugar de su antiguo generador de HTML.
"""

import base64
import json
import math
import re
from pathlib import Path

import pandas as pd
from shapely import wkb
from shapely.ops import unary_union
import pyproj

V3 = Path(__file__).resolve().parent.parent
FIG_BUILD = V3 / "docs" / "entregable_build" / "figures"
FONTS_DIR = V3 / "assets" / "fonts"

CONTRACT = "6e586b3d9a0bd8b844d9cf5bc714f0e583fc2a6936f8cd5ca89de9cdb26afd93"
A05 = "879ae45d46b56fc5504c9817be154eee0e78ab0e13ddfdcef4435a58d32de29d"
A06 = "4027385dff30ab79689dfdeb3c468260176080e83b1abd21f5c605efcce30a8f"
A07 = "3aa53121add31f2ea2381259d0b44fa7f603fa758b4a731dcc08fd143b074b87"
EDA02 = "d77ab12f05e9025f438921b34e8688e1a75628262964277af62250cdbafa8e67"
FEA03 = "7565adda3bc4eb91514247d2a1213f0b1c934821e762ac9d3aae010031dbb05c"


def miles(x):
    return f"{x:,.0f}"


# ---------------------------------------------------------------------------
# Datos geográficos / tablas para el JS embebido (solo artefactos sellados)
# ---------------------------------------------------------------------------
_TO_4326 = pyproj.Transformer.from_crs(32614, 4326, always_xy=True).transform
_TO_32614 = pyproj.Transformer.from_crs(4326, 32614, always_xy=True).transform


def _portfolios():
    """Sitios seleccionados por motor y presupuesto (portafolios oficiales)."""
    base = V3 / "data" / "engines"
    frames = {
        "m1": pd.read_parquet(
            base / "05_motor1" / CONTRACT / A05 / "m1_portafolios.parquet"),
        "m2": pd.read_parquet(
            base / "06_motor2" / CONTRACT / A06 / "m2_portafolios.parquet"),
        "m3": pd.read_parquet(
            base / "07_motor3" / CONTRACT / A07 / "m3_portafolios.parquet"),
    }
    out = {}
    for motor, df in frames.items():
        if motor == "m3":
            df = df[(df["method"] == "greedy") & (df["weight"] == 0.5)]
        per_b = {}
        for b, sub in df.groupby("budget"):
            sub = sub.sort_values("order")
            rows = []
            for _, r in sub.iterrows():
                lon, lat = _TO_4326(r["x"], r["y"])
                rows.append({
                    "o": int(r["order"]) if not math.isnan(r["order"]) else 0,
                    "id": r["site_id"], "mun": r["nom_mun"],
                    "ageb": r["cvegeo"],
                    "pop": int(round(r["marginal_new_pop"]))
                    if pd.notna(r["marginal_new_pop"]) else 0,
                    "dist": int(round(r["dist_to_network_m"])),
                    "lon": round(lon, 6), "lat": round(lat, 6)})
            per_b[int(b)] = rows
        out[motor] = per_b
    return out


def _stations():
    """Estaciones vigentes y pertenencia al grupo de alta actividad."""
    p = (V3 / "data" / "eda" / CONTRACT / EDA02
         / "station_environment.parquet")
    df = pd.read_parquet(p)
    rows = [{"lon": round(r["lon"], 6), "lat": round(r["lat"], 6),
             "g": 1 if r["is_golden"] else 0}
            for _, r in df.iterrows()]
    return rows


def _boundary():
    """Contorno simplificado de la ciudad (unión de las AGEBs urbanas)."""
    df = pd.read_parquet(
        V3 / "data" / "processed" / CONTRACT / "agebs.parquet",
        columns=["geometry"])
    geoms = [wkb.loads(g) for g in df["geometry"]]
    u = unary_union(geoms).simplify(0.002, preserve_topology=True)
    geoms2 = [u] if u.geom_type == "Polygon" else list(u.geoms)
    paths = []
    for poly in geoms2:
        rings = [poly.exterior] + list(poly.interiors)
        for ring in rings:
            pts = [(round(x, 5), round(y, 5)) for x, y in ring.coords]
            d = "M" + " L".join(f"{x} {y}" for x, y in pts) + " Z"
            paths.append(d)
    return paths, [round(v, 6) for v in u.bounds]


def _line_path(geom, tol):
    """Trazo SVG (lon/lat) de una geometría lineal simplificada."""
    g = geom.simplify(tol, preserve_topology=False)
    parts = [g] if g.geom_type == "LineString" else [
        p for p in getattr(g, "geoms", []) if p.geom_type == "LineString"]
    return "".join(
        "M" + " L".join(f"{c[0]:.5f} {c[1]:.5f}" for c in p.coords)
        for p in parts if len(p.coords) > 1)


def _transit_layers(bounds):
    """Líneas de Metro, Metrobús (GTFS) y red ciclista en operación (SEMOVI)."""
    import geopandas as gpd
    from shapely.geometry import LineString, box
    pad = 0.06
    clip = box(bounds[0] - pad, bounds[1] - pad,
               bounds[2] + pad, bounds[3] + pad)
    g = V3 / "data" / "raw" / "gtfs" / "gtfs"
    routes = pd.read_csv(g / "routes.txt", dtype=str)
    routes = routes[routes["agency_id"].isin(["METRO", "MB"])]
    trips = pd.read_csv(g / "trips.txt", dtype=str)
    trips = trips[trips["route_id"].isin(routes["route_id"])]
    shapes = pd.read_csv(g / "shapes.txt")
    shapes = shapes.sort_values(["shape_id", "shape_pt_sequence"])
    lines = {sid: LineString(zip(d["shape_pt_lon"], d["shape_pt_lat"]))
             for sid, d in shapes.groupby("shape_id") if len(d) > 1}
    out = {"metro": [], "mb": []}
    for _, r in routes.sort_values("route_short_name").iterrows():
        sids = trips.loc[trips["route_id"] == r["route_id"], "shape_id"]
        geoms = [lines[s] for s in sids.unique() if s in lines]
        if not geoms:
            continue
        u = unary_union(geoms).intersection(clip)
        if u.is_empty:
            continue
        color = r["route_color"] if isinstance(r["route_color"], str) \
            and r["route_color"] else "116633"
        key = "metro" if r["agency_id"] == "METRO" else "mb"
        name = r["route_short_name"]
        out[key].append({"n": name if key == "mb" else "L" + name.lstrip("L"),
                         "c": "#" + color, "d": _line_path(u, 0.0003)})
    zpath = V3 / "data" / "raw" / "urban_environment" / \
        "ciclovias_semovi_2025.zip"
    lay = gpd.read_file(
        "/vsizip/" + str(zpath.resolve())
        + "/infraestructura_vial_ciclista/Infraestructura ciclista total.shp")
    lay = lay[lay["ESTADO"] == "En operacion"].to_crs(4326)
    u = unary_union(list(lay.geometry)).intersection(clip)
    km = float(lay["LONG_KM"].sum())
    out["bici"] = {"d": _line_path(u, 0.0003), "n": int(len(lay)),
                   "km": round(km)}
    return out


def _catalog(a03_contract):
    return [{"name": f["name"], "source": f["source"],
             "unit": f["unit"], "transform": f["transform"],
             "formula": f'{f["numerator"]}'
             + (f' / {f["denominator"]}' if f["denominator"] else "")}
            for f in a03_contract]


def _loadings():
    df = pd.read_parquet(
        V3 / "data" / "features" / CONTRACT / FEA03
        / "pca_loadings.parquet")
    rows = []
    for name, r in df.iterrows():
        rows.append({"feature": name,
                     **{f"PC{i}": round(float(r[f"PC{i}"]), 4)
                        for i in range(1, 9)}})
    return rows


# ---------------------------------------------------------------------------
# CSS: tomado de la presentación de referencia (mismo lenguaje visual)
# ---------------------------------------------------------------------------
CSS = """
    :root {
      --primary: #004d40;
      --primary-light: #00695c;
      --primary-dark: #00382e;
      --primary-subtle: #e0f2f1;
      --accent-gold: #b45309;
      --accent-gold-light: #fef3c7;
      --accent-blue: #0284c7;
      --accent-purple: #7e22ce;
      --slate-900: #0f172a;
      --slate-800: #1e293b;
      --slate-700: #334155;
      --slate-600: #475569;
      --slate-500: #64748b;
      --slate-400: #94a3b8;
      --slate-300: #cbd5e1;
      --slate-200: #e2e8f0;
      --slate-100: #f1f5f9;
      --slate-50: #f8fafc;
      --bg-canvas: #fbfbfd;
      --card-bg: rgba(255, 255, 255, 0.95);
      --card-border: rgba(15, 23, 42, 0.08);
      --card-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-xl: 28px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-canvas);
      color: var(--slate-900);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    code, pre, .font-mono { font-family: 'JetBrains Mono', monospace; }
    a:focus-visible, button:focus-visible {
      outline: 3px solid var(--accent-blue); outline-offset: 2px;
    }
    .glass-panel {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-lg);
      box-shadow: var(--card-shadow);
      transition: all 0.25s ease;
    }
    .glass-panel:hover {
      border-color: rgba(0, 77, 64, 0.2);
      box-shadow: 0 10px 30px -4px rgba(15, 23, 42, 0.08);
    }
    .badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 10px; border-radius: 9999px;
      font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em;
    }
    .badge-primary {
      background-color: var(--primary-subtle); color: var(--primary);
      border: 1px solid rgba(0, 77, 64, 0.15);
    }
    .badge-gold {
      background-color: var(--accent-gold-light); color: var(--accent-gold);
      border: 1px solid rgba(180, 83, 9, 0.2);
    }
    .badge-blue {
      background-color: #e0f2fe; color: #0369a1;
      border: 1px solid rgba(2, 132, 199, 0.2);
    }
    .badge-purple {
      background-color: #f3e8ff; color: #7e22ce;
      border: 1px solid rgba(126, 34, 206, 0.2);
    }
    .badge-neutral {
      background-color: var(--slate-100); color: var(--slate-700);
      border: 1px solid var(--slate-200);
    }
    .badge-verified {
      background-color: #ecfdf5; color: #047857;
      border: 1px solid rgba(16, 185, 129, 0.2);
    }
    .btn {
      display: inline-flex; align-items: center; justify-content: center;
      gap: 8px; padding: 8px 16px; border-radius: 9999px;
      font-size: 0.85rem; font-weight: 600; cursor: pointer;
      transition: all 0.2s ease; text-decoration: none; border: none;
    }
    .btn-primary { background-color: var(--primary); color: white; }
    .btn-primary:hover { background-color: var(--primary-light); transform: translateY(-1px); }
    .btn-secondary {
      background-color: var(--slate-100); color: var(--slate-700);
      border: 1px solid var(--slate-200);
    }
    .btn-secondary:hover { background-color: var(--slate-200); }
    .btn-segmented {
      padding: 6px 14px; font-size: 0.8rem; border-radius: 9999px;
      background: transparent; color: var(--slate-600);
      border: 1px solid transparent;
    }
    .btn-segmented.active {
      background: white; color: var(--primary); font-weight: 700;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      border: 1px solid var(--slate-200);
    }
    .nav-pill {
      font-size: 0.78rem; font-weight: 600; color: var(--slate-500);
      text-decoration: none; padding: 5px 12px; border-radius: 9999px;
      transition: all 0.2s ease; white-space: nowrap;
    }
    .nav-pill:hover, .nav-pill.active {
      background: var(--slate-100); color: var(--primary);
    }
    #map-svg {
      width: 100%; height: 520px; border-radius: var(--radius-md);
      background: var(--slate-50); border: 1px solid var(--slate-200);
    }
    .data-table {
      width: 100%; border-collapse: collapse; font-size: 0.82rem;
      text-align: left;
    }
    .data-table th {
      padding: 10px 12px; background: var(--slate-50); color: var(--slate-600);
      font-weight: 700; border-bottom: 2px solid var(--slate-200);
      position: sticky; top: 0; z-index: 2;
    }
    .data-table td {
      padding: 8px 12px; border-bottom: 1px solid var(--slate-100);
      color: var(--slate-800);
    }
    .data-table tr:hover { background-color: rgba(241, 245, 249, 0.6); }
    .table-wrap { overflow-x: auto; }
    .loading-cell {
      font-family: 'JetBrains Mono', monospace; font-weight: 600;
      text-align: right; padding: 6px 10px !important; border-radius: 4px;
    }
    .loading-pos-high { background-color: #d1fae5; color: #065f46; font-weight: 700; }
    .loading-pos-med { background-color: #ecfdf5; color: #047857; }
    .loading-neutral { color: #64748b; }
    .loading-neg-med { background-color: #fff1f2; color: #be123c; }
    .loading-neg-high { background-color: #ffe4e6; color: #9f1239; font-weight: 700; }
    .callout-box {
      background: #f8fafc; border-left: 4px solid var(--primary);
      padding: 16px 20px; border-radius: 0 var(--radius-md) var(--radius-md) 0;
      font-size: 0.9rem; color: var(--slate-700); margin: 12px 0;
    }
    .callout-gold {
      background: #fffbeb; border-left: 4px solid var(--accent-gold);
      color: #92400e;
    }
    .callout-danger {
      background: #fef2f2; border-left: 4px solid #dc2626; color: #991b1b;
    }
    .tab-btn {
      padding: 8px 18px; border-radius: 9999px; font-size: 0.84rem;
      font-weight: 600; background: var(--slate-100); color: var(--slate-600);
      border: 1px solid var(--slate-200); cursor: pointer;
      transition: all 0.2s ease;
    }
    .tab-btn.active {
      background: var(--primary); color: white; border-color: var(--primary);
    }
    .pane { display: none; }
    .pane.on { display: flex; flex-direction: column; gap: 18px; }
    figure { margin: 0; }
    figure img {
      max-width: 100%; height: auto; border-radius: var(--radius-md);
      border: 1px solid var(--slate-200); background: white;
    }
    figcaption {
      font-size: 0.8rem; color: var(--slate-500); margin-top: 8px;
      line-height: 1.5;
    }
    figcaption .fnum {
      font-weight: 800; color: var(--primary); margin-right: 6px;
    }
    .fig-grid {
      display: grid; gap: 20px;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    }
    .kpi-num { font-size: 2.2rem; font-weight: 800; margin-top: 4px; }
    @media (max-width: 768px) {
      #map-svg { height: 360px; }
      .hide-mobile { display: none !important; }
    }
    @media print {
      header { position: static !important; }
      .btn, .nav-pill, .tab-btn, .btn-segmented { display: none !important; }
      .glass-panel { box-shadow: none; border: 1px solid #ccc; }
      figure, .glass-panel { page-break-inside: avoid; }
      .pane { display: block !important; }
    }
"""

# Reglas adicionales solo para la variante 2 (scatter SVG, piloto, inputs).
V2_CSS = """
    circle.cloud { fill: #94a3b8; fill-opacity: 0.45; }
    svg.scatter-svg { width: 100%; height: auto; display: block;
      border-radius: var(--radius-md); border: 1px solid var(--slate-200);
      background: white; }
    .scatter-wrap { overflow-x: auto; }
    @media (max-width: 768px) {
      svg.scatter-svg { min-width: 660px; }
    }
    .cost-input {
      width: 120px; padding: 8px 10px; border: 1px solid var(--slate-300);
      border-radius: var(--radius-sm); font: inherit; font-size: 0.9rem;
      font-family: 'JetBrains Mono', monospace; }
    .eq-box {
      border-left: 4px solid var(--accent-gold); background: #fffbeb;
      border-radius: 0 var(--radius-md) var(--radius-md) 0;
      padding: 14px 18px; margin: 12px 0; overflow-x: auto;
      text-align: center; }
    .eq {
      display: inline-flex; align-items: center; gap: 7px;
      white-space: nowrap; color: var(--slate-900); font-size: 1.08rem;
      font-family: "Cambria Math", "STIX Two Math", "Latin Modern Math",
        Georgia, serif; }
    .eq var, .eq i { font-style: italic; }
    .eq-max, .eq-sum {
      display: inline-flex; flex-direction: column; align-items: center;
      line-height: 1.05; }
    .eq-sub { font-size: 0.6em; font-style: normal;
      color: var(--slate-700); }
    .eq-frac {
      display: inline-flex; flex-direction: column; align-items: center;
      line-height: 1.15; margin: 0 3px; }
    .eq-frac > span:first-child {
      border-bottom: 1.4px solid var(--slate-900); padding: 0 5px; }
    .eq-frac > span:last-child { padding: 0 5px; }
    .eq-legend {
      font-size: 0.78rem; color: var(--slate-600); line-height: 1.6;
      margin-top: 8px; text-align: left; }
    @media print { .cost-input { border: none; padding: 0; }
      svg.scatter-svg { min-width: 0; } .scatter-wrap { overflow: visible; } }
"""


def _font_faces():
    """Fuentes embebidas en base64 desde la caché local del repo."""
    rules = []
    for f in sorted(FONTS_DIR.glob("*.woff2")):
        m = re.match(r"(PlusJakartaSans|JetBrainsMono)-(\d+)\.woff2",
                     f.name)
        if not m:
            continue
        fam = "Plus Jakarta Sans" if "Jakarta" in m.group(1) \
            else "JetBrains Mono"
        wt = m.group(2)
        b64 = base64.b64encode(f.read_bytes()).decode()
        rules.append(
            "@font-face{font-family:'" + fam + "';font-style:normal;"
            "font-weight:" + wt + ";font-display:swap;"
            "src:url(data:font/woff2;base64," + b64 + ") "
            "format('woff2');}")
    return "\n".join(rules)


def _scatter_svg(sc):
    """Figura 20 (variante 2): nube de 300 portafolios aleatorios
    conectados frente a los portafolios oficiales, como SVG inline."""
    pts = sc["points"]
    off = sc["official"]
    cloud = sc["cloud"]
    x0, x1 = 40000.0, 340000.0
    y0, y1 = 10.6, 13.6
    L, R, T, B = 80, 30, 24, 62
    W, Hh = 1000, 520
    iw, ih = W - L - R, Hh - T - B

    def X(v):
        return L + (v - x0) / (x1 - x0) * iw

    def Y(v):
        return T + (1 - (v - y0) / (y1 - y0)) * ih

    parts = [
        f'<svg class="scatter-svg" viewBox="0 0 {W} {Hh}" role="img" '
        'aria-label="Dispersión: 300 portafolios aleatorios conectados y '
        'los tres portafolios oficiales en población nueva cubierta y '
        'escolaridad media, a B igual a 30">']
    parts.append(
        f'<rect x="{L}" y="{T}" width="{iw}" height="{ih}" fill="#f8fafc"/>')
    for v in range(50000, 340001, 50000):
        x = X(v)
        parts.append(
            f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{T + ih}" '
            'stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{T + ih + 20}" font-size="14" '
            'fill="#64748b" text-anchor="middle" font-family="inherit">'
            f'{v:,.0f}</text>')
    for v in (11.0, 11.5, 12.0, 12.5, 13.0, 13.5):
        y = Y(v)
        parts.append(
            f'<line x1="{L}" y1="{y:.1f}" x2="{L + iw}" y2="{y:.1f}" '
            'stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(
            f'<text x="{L - 8}" y="{y + 4:.1f}" font-size="14" '
            'fill="#64748b" text-anchor="end" font-family="inherit">'
            f'{v:.1f}</text>')
    parts.append(
        f'<text x="{L + iw / 2:.1f}" y="{Hh - 12}" font-size="15" '
        'fill="#334155" text-anchor="middle" font-weight="600" '
        'font-family="inherit">Población nueva cubierta (hab.)</text>')
    parts.append(
        f'<text transform="rotate(-90 16 {T + ih / 2:.1f})" x="16" '
        f'y="{T + ih / 2:.1f}" font-size="15" fill="#334155" '
        'text-anchor="middle" font-weight="600" font-family="inherit">'
        'Escolaridad media (años)</text>')
    for p in pts:
        parts.append(
            f'<circle class="cloud" cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" '
            'r="3.5"/>')
    uy = Y(sc["universe_esc"])
    parts.append(
        f'<line x1="{L}" y1="{uy:.1f}" x2="{L + iw}" y2="{uy:.1f}" '
        'stroke="#0f172a" stroke-width="1.4" stroke-dasharray="7 5"/>')
    parts.append(
        f'<text x="{L + iw - 6:.1f}" y="{uy - 7:.1f}" font-size="14" '
        'fill="#0f172a" text-anchor="end" font-weight="600" '
        'font-family="inherit">Universo candidato '
        f'{sc["universe_esc"]:.2f}</text>')
    cx_, cy_ = X(cloud["pop_mean"]), Y(cloud["esc_mean"])
    parts.append(
        f'<g><line x1="{cx_ - 9:.1f}" y1="{cy_:.1f}" x2="{cx_ + 9:.1f}" '
        f'y2="{cy_:.1f}" stroke="#475569" stroke-width="2"/>'
        f'<line x1="{cx_:.1f}" y1="{cy_ - 9:.1f}" x2="{cx_:.1f}" '
        f'y2="{cy_ + 9:.1f}" stroke="#475569" stroke-width="2"/>'
        f'<title>Media del azar conectado: '
        f'{cloud["pop_mean"]:,.0f} hab. · escolaridad '
        f'{cloud["esc_mean"]:.2f}</title></g>')
    parts.append(
        f'<text x="{cx_ + 12:.1f}" y="{cy_ - 8:.1f}" font-size="14" '
        'fill="#475569" font-weight="600" font-family="inherit">'
        f'Media del azar conectado {cloud["esc_mean"]:.2f}</text>')
    motors = [
        ("m1", "#7e22ce", "Motor 1 · Similitud", (14, -14)),
        ("m2", "#0284c7", "Motor 2 · Predictivo", (-15, -17)),
        ("m3", "#b45309", "Motor 3 · Greedy", (-17, 5))]
    for key, color, name, (dx, dy) in motors:
        m = off[key]
        x, y = X(m["new_pop"]), Y(m["esc"])
        anchor = "end" if dx < 0 else "start"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{color}" '
            'stroke="#ffffff" stroke-width="2.5">'
            f'<title>{name}: {m["new_pop"]:,.0f} hab. nuevos · '
            f'escolaridad {m["esc"]:.2f}</title></circle>')
        parts.append(
            f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" font-size="15" '
            f'fill="{color}" font-weight="700" text-anchor="{anchor}" '
            f'font-family="inherit">{name}</text>')
    parts.append('</svg>')
    return "".join(parts)


REPO_URL = "https://github.com/Omarti34/Ecobicis2026"


def _qr_repo():
    """QR real del repositorio GitHub (segno, SVG embebido sin recursos
    externos). Matriz de módulos pintada como rectángulos."""
    import segno
    qr = segno.make(REPO_URL, error="m")
    M, Q = 8, 14  # px por módulo y zona silenciosa
    N = qr.symbol_size(scale=1, border=0)[0]
    W = Q * 2 + N * M
    cells = "".join(
        f'<rect x="{Q + i * M}" y="{Q + j * M}" width="{M}" '
        f'height="{M}" fill="#0f172a"/>'
        for j, row in enumerate(qr.matrix)
        for i, v in enumerate(row) if v)
    return (
        f'<svg id="qr-slot" width="{W}" height="{W}" '
        f'viewBox="0 0 {W} {W}" role="img" '
        f'aria-label="Código QR del repositorio: {REPO_URL}">'
        f'<rect x="0" y="0" width="{W}" height="{W}" fill="#ffffff"/>'
        + cells + '</svg>')


def build_html(D, fig_b64, variant=1):
    """Devuelve la presentación ejecutiva como un solo archivo HTML."""
    v2 = (variant == 2)
    if v2:
        sc = D["v2_scatter"]
        bt2 = {r["subject"]: r for r in D["v2_m2_backtest"]}
        reg_g = {r["model"]: r for r in D["v2_reg_groupkfold"]}
        esc_uni = sc["universe_esc"]
        p_m1 = round(sc["rank"]["m1"]["share_random_esc_le"] * 100)
        p_m3 = round(sc["rank"]["m3"]["share_random_esc_le"] * 100)
        cloud_max = sc["cloud"]["pop_max"]
        n_rand = sc["n_random"]
        mediana_red = sc["median_viajes_diarios_red"]
        n_est = sc["n_estaciones"]
        cons3 = D['cons']['30']['selected_by_3']
        cons2 = D['cons']['30']['selected_by_2plus']
    H = []

    def A(x):
        H.append(x)

    def fig(name, num, caption):
        return (f'<figure><img src="data:image/png;base64,{fig_b64[name]}" '
                f'alt="{caption}">'
                f'<figcaption><span class="fnum">Figura {num}.</span>'
                f'{caption}</figcaption></figure>')

    geo_ports = _portfolios()
    stations = _stations()
    boundary, bbounds = _boundary()
    transit = _transit_layers(bbounds)
    catalog = _catalog(D["feature_contract"])
    loadings = _loadings()

    # Cobertura oficial (mismas cifras que la tabla del paper)
    cov = []
    for (motor, b), m in sorted(D["ofi"].items(),
                                key=lambda kv: (kv[0][1], kv[0][0])):
        cov.append({"motor": motor, "b": b,
                    "pop": int(round(m["new_pop"])),
                    "pop_s": miles(m["new_pop"]),
                    "agebs": int(m["n_agebs"]),
                    "pct": round(m["new_pop_share"] * 100, 2),
                    "esc": round(m["mean_grado_escolar_prom_selected"], 2),
                    "dist": int(round(m["mean_dist_to_network_m"]))})
    esc_universe = [m["mean_grado_escolar_prom_all_sites"]
                    for m in D["ofi"].values()][0]

    # Greedy vs GA por presupuesto (configuración primaria)
    gav = []
    for b in (15, 30, 50):
        g = D["greedy_runs"][b]["new_pop"]
        ga = D["ga_best_by_b"][b]["new_pop"]
        gav.append({"b": b, "greedy": int(round(g)),
                    "greedy_s": miles(g), "ga": int(round(ga)),
                    "ga_s": miles(ga), "dif_s": miles(g - ga)})

    payload = {
        "cov": cov, "gav": gav, "ports": geo_ports,
        "stations": stations, "boundary": boundary,
        "bounds": bbounds, "transit": transit,
        "catalog": catalog, "loadings": loadings,
    }
    payload_json = json.dumps(payload, ensure_ascii=False,
                              separators=(",", ":"))

    # ------------------------------------------------------------------ head
    A("""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Expansión territorial de EcoBici · Tres motores analíticos auditados</title>
<style>
""" + _font_faces() + CSS + (V2_CSS if v2 else "") + """
</style>
</head>
<body>
""")

    # ---------------------------------------------------------------- header
    A(f"""
<header style="position: sticky; top: 0; z-index: 1000; background: rgba(255,255,255,0.96); backdrop-filter: blur(18px); border-bottom: 1px solid var(--slate-200); padding: 12px 24px;">
  <div style="max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
    <div style="display: flex; align-items: center; gap: 12px;">
      <div style="width: 36px; height: 36px; border-radius: 10px; background: var(--primary); display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 15px; box-shadow: 0 4px 12px rgba(0,77,64,0.25);">EB</div>
      <div>
        <div style="font-weight: 800; font-size: 1.02rem; color: var(--slate-900); line-height: 1.2;">
          EcoBici <span style="color: var(--primary);">· Expansión Territorial</span>
        </div>
        <div style="font-size: 0.72rem; color: var(--slate-500); font-family: 'JetBrains Mono', monospace;">
          Tres motores analíticos · mismo contrato de despliegue
        </div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 8px;" class="hide-mobile">
      <span class="badge badge-verified">✓ {miles(D['trips_ok'])} viajes auditados</span>
      <span class="badge badge-gold">Gini: {D['gini_est']:.4f}</span>
      <span class="badge badge-primary">Ward + buffer {D['buffer_m']:.0f} m</span>
    </div>
    <nav style="display: flex; gap: 4px; overflow-x: auto; max-width: 100%; padding: 2px 0;">
      <a href="#intro" class="nav-pill">01 Introducción</a>
      <a href="#problema" class="nav-pill">02 Problema</a>
      <a href="#hipotesis" class="nav-pill">03 Hipótesis</a>
      <a href="#datos" class="nav-pill">04 Datos</a>
      <a href="#motores" class="nav-pill">05 Motores</a>
      <a href="#simulador" class="nav-pill">06 Simulador</a>
      <a href="#resultados" class="nav-pill">07 Resultados</a>
      <a href="#conclusiones" class="nav-pill">08 Conclusiones</a>
      <a href="#biblio" class="nav-pill">09 Bibliografía</a>
    </nav>
  </div>
</header>
""")

    A("""<main style="max-width: 1400px; margin: 0 auto; padding: 32px 24px; display: flex; flex-direction: column; gap: 56px;">""")

    # ------------------------------------------------------------------ hero
    A(f"""
<section style="text-align: center; display: flex; flex-direction: column; gap: 16px; padding: 36px 0 16px 0;">
  <div style="display: inline-flex; justify-content: center; margin: 0 auto;">
    <span class="badge badge-primary" style="font-weight: 800; letter-spacing: 0.08em; padding: 4px 14px; font-size: 0.85rem;">Caso de negocio</span>
  </div>
  <h1 style="font-size: clamp(2.3rem, 4.8vw, 4.1rem); font-weight: 800; letter-spacing: -0.03em; line-height: 1.12; color: var(--slate-900); max-width: 1100px; margin: 0 auto;">
    Expansión justa de EcoBici mediante <span style="color: var(--primary);">tres motores analíticos</span> auditados bajo un mismo contrato
  </h1>
  <p style="max-width: 780px; margin: 0 auto; color: var(--slate-600); font-size: 1.02rem;">
    Similitud estadística, modelo predictivo y optimización prescriptiva sobre grafos proponen portafolios de estaciones validados con un arnés espacial de separación certificada. La comparación es descriptiva: no se declara un ganador agregado.
  </p>
  <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 10px;">
    <a href="#simulador" class="btn btn-primary" style="padding: 10px 22px; font-size: 0.95rem;"><span>Abrir simulador de portafolios</span><span>→</span></a>
    <a href="#motores" class="btn btn-secondary" style="padding: 10px 20px; font-size: 0.95rem;"><span>Ver los tres motores</span></a>
    <a href="#datos" class="btn btn-secondary" style="padding: 10px 20px; font-size: 0.95rem;"><span>Ver datos y validación</span></a>
  </div>
  <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 28px;">
    <div class="glass-panel" style="padding: 22px; text-align: left;">
      <div style="font-size: 0.72rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Brecha de acceso</div>
      <div class="kpi-num" style="color: #dc2626;">{miles(D['pop_sin'])}</div>
      <div style="font-size: 0.8rem; color: var(--slate-500);">residentes en AGEBs sin estación interna</div>
    </div>
    <div class="glass-panel" style="padding: 22px; text-align: left;">
      <div style="font-size: 0.72rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Territorio sin servicio</div>
      <div class="kpi-num" style="color: var(--slate-900);">{miles(D['agebs_sin'])}</div>
      <div style="font-size: 0.8rem; color: var(--slate-500);">de {miles(D['total_agebs'])} AGEBs urbanas</div>
    </div>
    <div class="glass-panel" style="padding: 22px; text-align: left;">
      <div style="font-size: 0.72rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Cobertura M3 · B=30</div>
      <div class="kpi-num" style="color: var(--primary);">{miles(D['ofi'][('m3',30)]['new_pop'])}</div>
      <div style="font-size: 0.8rem; color: var(--slate-500);">habitantes nuevos en zonas de captura</div>
    </div>
    <div class="glass-panel" style="padding: 22px; text-align: left;">
      <div style="font-size: 0.72rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Consenso triple</div>
      <div class="kpi-num" style="color: var(--accent-gold);">{D['cons']['30']['selected_by_3']}</div>
      <div style="font-size: 0.8rem; color: var(--slate-500);">sitios elegidos por los tres motores</div>
    </div>
  </div>
</section>
""")

    def chap(num, title, extra=""):
        return (f'<section style="display: flex; flex-direction: column; '
                f'gap: 20px;">'
                f'<div style="display: flex; align-items: center; gap: 10px; '
                f'flex-wrap: wrap;">'
                f'<span class="badge badge-primary">Capítulo {num}</span>'
                f'<h2 style="font-size: 1.85rem; font-weight: 800; '
                f'letter-spacing: -0.02em;">{title}</h2>{extra}</div>')

    def card(title, body, accent=None):
        top = (f'border-top: 4px solid {accent};' if accent else '')
        return (f'<div class="glass-panel" style="padding: 26px; {top}">'
                f'<h3 style="font-size: 1.12rem; font-weight: 700; '
                f'margin-bottom: 12px; color: var(--slate-900);">{title}</h3>'
                f'{body}</div>')

    def p_(txt):
        return (f'<p style="color: var(--slate-600); font-size: 0.92rem; '
                f'line-height: 1.65;">{txt}</p>')

    grid2 = ('<div style="display: grid; grid-template-columns: '
             'repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">')

    # ------------------------------------------------------- 01 Introducción
    A('<div id="intro">')
    A(chap("01", "Introducción"))
    A(grid2)
    A(card("El sistema y su decisión de expansión",
           p_(f"EcoBici operó {miles(D['stations'])} estaciones físicas y "
              f"registró {miles(D['trips_ok'])} viajes aceptados en "
              f"{D['year']}, tras descartar {miles(D['trips_q'])} registros "
              "en cuarentena sobre una capa de datos crudos inmutable. La "
              "decisión de negocio evaluada es hacia dónde expandir la red "
              "cubriendo más población y conectando mejor con el transporte "
              "masivo, sin replicar los sesgos históricos del sistema.")))
    A(card("Qué entrega este documento",
           p_("Tres métodos independientes de selección de sitios —similitud "
              "estadística, predicción supervisada y optimización prescriptiva "
              "sobre un grafo— evaluados bajo un mismo contrato de despliegue "
              "y un arnés de validación espacial con separación certificada. "
              "Los resultados se comparan de forma descriptiva y cada afirmación "
              "queda trazada a un reporte verificado."), accent="var(--primary)"))
    A("</div></div>")

    # ------------------------------------------------------- 02 Problema
    A('<div id="problema">')
    A(chap("02", "Planteamiento del problema"))
    A(f"""<div class="callout-box callout-danger">
      <strong>Brecha territorial.</strong> Solo {miles(D['agebs_con'])} AGEBs
      albergan al menos una estación; las {miles(D['agebs_sin'])} restantes,
      con {miles(D['pop_sin'])} residentes censados, no contienen ninguna. En
      el universo de evaluación del arnés espacial ({D['eval_total']} AGEBs),
      {D['eval_sin']} carecen de estación interna y {D['eval_med']} cuentan con
      actividad interna medida; esas últimas conforman el universo supervisado.
    </div>""")
    A(grid2)
    A(card("La población sin estación no es marginal",
           p_(f"Como se observa en la Figura 1, la brecha cubre la parte "
              f"mayoritaria del territorio urbano. La mediana de distancia del "
              f"centroide a la red es {D['median_km']:.1f} km "
              f"(media {D['mean_km']:.1f} km) y {D['dentro400']} AGEBs sin "
              "estación están a menos de 400 m de una: la frontera de la red "
              "pasa junto a una población que no captura (Figura 2).")))
    ksens = ', '.join(str(int(k)) for k in [4, 8, 12])
    moran_par = (f"(p ≤ 0.001, calculado por permutaciones; sensibilidad "
                 f"k = {ksens})" if v2 else
                 f"(p = {D['moran_p']}, {miles(D['moran_perm'])} "
                 f"permutaciones; sensibilidad k = {ksens})")
    A(card("Concentración y estructura espacial",
           p_(f"La curva de Lorenz de la Figura 3 cuantifica la "
              f"concentración: Gini de estaciones {D['gini_est']:.4f} y de "
              f"actividad {D['gini_act']:.4f}, ambos cercanos a 0.93. El I de "
              f"Moran global es {D['moran_i']:.4f} {moran_par}, y la "
              "Figura 4 muestra que la actividad se concentra en un núcleo "
              "alta-alta con bolsas contiguas de baja actividad."),
           accent="#dc2626"))
    A("</div>")
    A('<div class="fig-grid">'
      + fig("e02/e02_01_poblacion_sin_estacion.png", 1,
            "Distribución territorial de la población residente en AGEBs "
            "sin estación interna del sistema.")
      + fig("e02/e02_02_distancia_a_la_red.png", 2,
            "Distancia del centroide de cada AGEB sin estación interna a "
            "la estación vigente más cercana.")
      + "</div>")
    A('<div class="fig-grid">'
      + fig("e02/e02_03_concentracion_lorenz.png", 3,
            "Curva de Lorenz de la distribución de estaciones y de "
            "actividad entre AGEBs.")
      + fig("e02/e02_04_moran_cuadrantes.png", 4,
            "Cuadrantes del I de Moran local: concentración alta-alta "
            "frente a bolsas contiguas de baja actividad.")
      + "</div>")
    A(p_(f"La cercanía al transporte pesado (Metro y Metrobús, "
         f"{D['heavy_stops']} paradas elegibles) se asocia a la actividad "
         f"por estación con Spearman {D['heavy_rho']:.4f}: una asociación "
         "descriptiva, no una relación causal."))
    A("</div>")

    # ------------------------------------------------------- 03 Hipótesis
    principles = [
        grid2,
        card("Principio 1 · Cero fuga de datos",
             p_(f"Toda variable derivada de los viajes quedó descartada del "
                f"modelado cuando su asociación con el objetivo era "
                f"circular: el flujo de rotación alcanzó Spearman "
                f"{D['turnover_spearman']:.3f} con la actividad que se "
                "busca predecir, por lo que se vetó junto con el resto de "
                "métricas derivadas del fenómeno.")),
        card("Principio 2 · Demanda honesta",
             p_(f"Las {miles(D['agebs_sin'])} AGEBs sin estación se "
                "trataron como unidades no etiquetadas, no como ejemplos "
                "negativos con demanda cero: un modelo entrenado contra "
                "esa suposición aprendería el mapa de la cobertura, no el "
                "de la demanda."), accent="var(--accent-blue)"),
        card("Principio 3 · Tensión declarada",
             p_("La similitud con las zonas de mayor actividad empuja los "
                "portafolios hacia perfiles de mayor escolaridad; "
                "maximizar cobertura poblacional los empuja en sentido "
                "contrario. La tensión se documentó explícitamente sin "
                "imponer una resolución única."),
             accent="var(--accent-gold)")]
    A('<div id="hipotesis">')
    if v2:
        A(chap("03", "Pregunta e hipótesis"))
        esc_bias = D['bias']['grado_escolar_prom']['spearman_cos']
        A(grid2)
        A(card("Pregunta de investigación",
               p_("¿Puede un enfoque de ciencia de datos diseñar una "
                  "expansión justa y conectada sin replicar el sesgo "
                  "histórico?"), accent="var(--primary)"))
        A(card("Hipótesis general",
               p_("A igual presupuesto, un diseño que optimiza directamente "
                  "la población nueva cubierta bajo crecimiento contiguo "
                  "desde la red cubre más población nueva que uno basado "
                  "solo en la similitud con las zonas históricamente "
                  "exitosas, sin desviarse hacia zonas de mayor escolaridad "
                  "que el azar conectado."), accent="var(--accent-blue)"))
        A("</div>")

        def hcard(tag, enun, criterio, resultado):
            return (
                f'<div class="glass-panel" style="padding: 20px;">'
                f'<div style="display: flex; align-items: center; gap: 8px; '
                f'margin-bottom: 8px;"><span class="badge badge-neutral">'
                f'{tag}</span>'
                f'<span class="badge badge-verified" '
                f'style="margin-left:auto;">Sostenida</span></div>'
                f'<p style="font-size: 0.88rem; color: var(--slate-800); '
                f'line-height: 1.55; margin-bottom: 8px;">{enun}</p>'
                f'<p style="font-size: 0.78rem; color: var(--slate-500); '
                f'margin-bottom: 6px;"><strong>Criterio:</strong> '
                f'{criterio}</p>'
                f'<p style="font-size: 0.82rem; color: var(--slate-700);">'
                f'<strong>Resultado:</strong> {resultado}</p></div>')

        A(grid2.replace("minmax(320px, 1fr)", "minmax(270px, 1fr)"))
        A(hcard("H1 · Concentración",
                "La oferta y la actividad de EcoBici están concentradas en "
                "pocas AGEBs y agrupadas en el espacio.",
                "Gini &gt; 0.9 e I de Moran &gt; 0 con p ≤ 0.001.",
                f"Gini {D['gini_est']:.4f} (estaciones) y "
                f"{D['gini_act']:.4f} (actividad); I = {D['moran_i']:.4f}."))
        A(hcard("H2 · Sesgo de similitud",
                "El puntaje de similitud del Motor 1 se asocia con el nivel "
                "socioeconómico y desplaza su portafolio hacia mayor "
                "escolaridad que el azar conectado.",
                f"Spearman con escolaridad &gt; 0.5 y escolaridad del "
                f"portafolio en el percentil ≥ 95 de {n_rand} portafolios "
                "aleatorios conectados.",
                f"ρ = {esc_bias:.2f}; {sc['official']['m1']['esc']:.2f} "
                f"(percentil {p_m1})."))
        A(hcard("H3 · Cobertura",
                "A igual presupuesto, el Motor 3 cubre más población nueva "
                "que el Motor 1.",
                "Mayor cobertura en B = 15, 30 y 50.",
                f"{miles(D['ofi'][('m3', 15)]['new_pop'])} &gt; "
                f"{miles(D['ofi'][('m1', 15)]['new_pop'])}; "
                f"{miles(D['ofi'][('m3', 30)]['new_pop'])} &gt; "
                f"{miles(D['ofi'][('m1', 30)]['new_pop'])}; "
                f"{miles(D['ofi'][('m3', 50)]['new_pop'])} &gt; "
                f"{miles(D['ofi'][('m1', 50)]['new_pop'])}; a B = 30 ningún "
                "portafolio aleatorio conectado lo alcanza."))
        A(hcard("H4 · Equidad sin desvío",
                "El portafolio del Motor 3 no se ubica por encima del azar "
                "conectado en escolaridad.",
                "Escolaridad por debajo del percentil 95 de la nube.",
                f"{sc['official']['m3']['esc']:.2f} (percentil {p_m3}; "
                f"universo candidato {esc_uni:.2f}); no implica que el "
                "Motor 3 favorezca zonas de menor escolaridad que el azar."))
        A("</div>")
        A('<h3 style="font-size: 1.05rem; font-weight: 700; '
          'color: var(--slate-900);">Principios de diseño</h3>')
        for c in principles:
            A(c)
        A("</div>")
        A(p_("La evidencia es retrospectiva sobre portafolios; no mide uso "
             "real tras construir las estaciones."))
        A("</div>")
    else:
        A(chap("03", "Hipótesis"))
        A(f"""<div class="callout-box">
      <strong>Pregunta central.</strong> ¿Es posible utilizar modelos de
      Machine Learning espacial, reducción factorial ortogonal y algoritmos de
      optimización prescriptiva de red para seleccionar portafolios de
      expansión de EcoBici que maximicen la población cubierta y la equidad
      social, sin replicar el sesgo histórico de clase media-alta ni incurrir
      en trampas circulares de fuga de datos?
    </div>""")
        for c in principles:
            A(c)
        A("</div></div>")

    # ------------------------------------------------------- 04 Datos
    A('<div id="datos">')
    A(chap("04", "Datos y tratamiento"))
    A(grid2)
    A(card("Viajes y limpieza",
           p_(f"Se procesaron {miles(D['trips_in'])} registros de viajes de "
              f"{D['year']}; {miles(D['trips_ok'])} fueron aceptados y "
              f"{miles(D['trips_q'])} quedaron en cuarentena con su razón de "
              "descarte documentada, sobre una capa cruda inmutable que no se "
              "modifica en ningún paso.")))
    A(card("Fuentes auxiliares",
           p_(f"El contexto urbano proviene del Censo {D['census_year']} "
              f"(población por AGEB), del DENUE {D['denue_year']} "
              f"({miles(D['denue_n'])} establecimientos como proxy "
              "retrospectivo de actividad económica) y del feed GTFS "
              f"{D['gtfs_year']} ({miles(D['gtfs_stops'])} paradas aceptadas, "
              f"{miles(D['gtfs_linked'])} vinculadas a viajes), con "
              f"{D['heavy_stops']} paradas de Metro y Metrobús elegibles "
              "como red de transporte pesado."),
           accent="var(--accent-blue)"))
    A("</div>")
    A("""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Catálogo de las 18 variables del contrato</h3>
      <p style="font-size: 0.85rem; color: var(--slate-600); margin-bottom: 12px;">
        El contrato de variables fija numerador, denominador, fuente y transformación de cada rasgo; ninguna variable deriva de los viajes ni del objetivo a predecir.</p>
      <div style="display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap;" class="hide-mobile">
        <button class="tab-btn active" id="btn-cat-all" onclick="filterCatalog('all')">Todas</button>
        <button class="tab-btn" id="btn-cat-censo" onclick="filterCatalog('censo')">Censo</button>
        <button class="tab-btn" id="btn-cat-denue" onclick="filterCatalog('denue')">DENUE</button>
        <button class="tab-btn" id="btn-cat-gtfs" onclick="filterCatalog('gtfs')">GTFS</button>
      </div>
      <div class="table-wrap" style="max-height: 320px; overflow-y: auto;">
        <table class="data-table">
          <thead><tr><th>Variable</th><th>Fuente</th><th>Unidad</th><th>Construcción</th><th>Transformación</th></tr></thead>
          <tbody id="catalog-table-body"></tbody>
        </table>
      </div>
    </div>""")
    pca_seg = (f"de la varianza. El umbral del 80 % se fijó antes de "
               f"evaluar resultados; con umbrales de 0.70 y 0.90 la "
               f"Precisión@10 del Motor 1 se mantuvo en "
               f"{D['v2_m1_sens_p10']:.2f}. El problema de unidad areal "
               f"modificable se mitiga —sin resolverse— midiendo la "
               f"cobertura sobre una retícula de celdas de 200 m con zonas "
               f"de captura de 500 m, no con la población total de la AGEB."
               if v2 else
               "de la varianza, mitigando —\n        sin resolver — el "
               "problema de unidad areal modificable.")
    A(f"""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Espacio factorial ortogonal (PCA)</h3>
      <p style="font-size: 0.85rem; color: var(--slate-600); margin-bottom: 12px;">
        Las 18 variables se redujeron a {D['pca_comp']} componentes principales
        que retienen el {D['pca_var']*100:.2f}% {pca_seg} La matriz de
        cargas completa se muestra abajo; las celdas verdes son cargas
        positivas fuertes y las rojas, negativas.</p>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Variable</th><th>PC1</th><th>PC2</th><th>PC3</th><th>PC4</th><th>PC5</th><th>PC6</th><th>PC7</th><th>PC8</th></tr></thead>
          <tbody id="pca-loadings-body"></tbody>
        </table>
      </div>
    </div>""")
    A(grid2)
    A(card("Grupo de referencia de alta actividad",
           p_(f"El Golden Cluster reúne las {D['golden_n']} estaciones del "
              f"percentil 85 de actividad (umbral {D['p85']:.1f} viajes "
              f"diarios) repartidas en {D['golden_agebs']} AGEBs; su "
              f"espaciamiento mediano es {D['golden_med']:.0f} m (Figura 5). "
              "Sirve de referencia de comportamiento exitoso para los motores "
              "1 y 3."), accent="var(--accent-gold)"))
    A(card("Arnés de validación espacial",
           p_(f"{D['n_blocks']} bloques construidos por clustering "
              "aglomerativo de Ward con conectividad por adyacencia de "
              f"polígonos, repartidos en {D['n_folds']} pliegues con buffer "
              f"de {D['buffer_m']:.0f} m sobre un universo de "
              f"{D['eval_med']} AGEBs con servicio. Los pares colindantes "
              f"prueba–entrenamiento caen de "
              f"{D['folds_before']} antes del buffer a "
              f"{D['folds_after']} después, con distancia mínima retenida de "
              f"{D['min_dist']:.1f} m (Figura 6). La certificación cubre "
              "adyacencia y buffer; no descarta autocorrelación a mayores "
              "distancias.")))
    A("</div>")
    A('<div class="fig-grid">'
      + fig("e02/e02_05_espaciamiento_golden.png", 5,
            "Espaciamiento observado entre estaciones del grupo de alta "
            "actividad (Golden Cluster) y la red completa.")
      + fig("n01_pares_colindantes.png", 6,
            "Pares colindantes prueba–entrenamiento por pliegue antes y "
            "después del buffer de 500 m; tras el buffer quedan cero en "
            "los cinco pliegues.")
      + "</div>")
    A("</div>")

    # ------------------------------------------------------- 05 Motores
    A('<div id="motores">')
    A(chap("05", "Los tres motores",
           '<span class="badge badge-neutral" style="margin-left:auto;">'
           'Arquitectura paralela desacoplada</span>'))
    A(p_("Los tres motores resuelven la misma tarea —seleccionar portafolios "
         "de sitios nuevos bajo el mismo universo de candidatos, las mismas "
         "reglas de factibilidad y el mismo contrato de despliegue— con "
         "métodos independientes: ninguno lee las salidas de otro."))
    A("""<div style="display: flex; gap: 8px; flex-wrap: wrap;">
      <button class="tab-btn active" data-motor="m1">Motor 1 · Similitud</button>
      <button class="tab-btn" data-motor="m2">Motor 2 · Predictivo</button>
      <button class="tab-btn" data-motor="m3">Motor 3 · Prescriptivo</button>
    </div>""")

    # ---- Motor 1
    v = D["v_lw"]
    A(f"""<div class="pane on" id="pane-m1">
    <div class="glass-panel" style="padding: 26px; border-top: 4px solid var(--accent-blue);">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
        <span class="badge badge-blue">Motor 1</span>
        <span style="font-size: 0.72rem; color: var(--slate-400); font-weight: 600;">No supervisado · similitud</span>
      </div>
      <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 8px;">Similitud coseno con compuerta de dominio</h3>
      {p_('Puntúa cada sitio por su parecido con el perfil de las zonas exitosas: '
          f'en el espacio de los {D["pca_comp"]} componentes principales se calcula la '
          'similitud coseno al centroide del Golden Cluster y se aplica una compuerta '
          'de Mahalanobis que se abstiene en los sitios demasiado atípicos, con corte '
          'en el cuantil 0.9973 de la chi-cuadrada.')}
      {p_(f'Con ~20 referencias por pliegue frente a 8–18 variables, la covarianza '
          f'empírica queda mal condicionada (número de condición '
          f'{D["cond_emp"][0]:.1f}–{D["cond_emp"][1]:.1f}); el encogimiento '
          f'Ledoit-Wolf ({D["shrink"][0]:.2f}–{D["shrink"][1]:.2f}) la estabiliza '
          f'({D["cond_lw"][0]:.2f}–{D["cond_lw"][1]:.2f}) y sube la cobertura de '
          f'decisión de {D["v_emp"]["decision_coverage"]:.3f} a '
          f'{v["decision_coverage"]:.3f} sin cambiar el NDCG@10 '
          f'({v["ndcg@10"]:.3f}). Como se observa en la Figura 7.')}
      <div class="callout-box callout-gold" style="margin-top: 12px;">
        <strong>Sesgo declarado.</strong> El score correlaciona con escolaridad
        (Spearman {D["bias"]["grado_escolar_prom"]["spearman_cos"]:.2f}) y tenencia de
        automóvil ({D["bias"]["pct_viviendas_auto"]["spearman_cos"]:.2f}): premia el
        perfil histórico de clase media-alta; la tensión se documenta
        explícitamente en Resultados sin imponer una corrección única.
      </div>
    </div>
    <div class="fig-grid">""" +
     fig("n02_m1_compuerta.png", 7,
         "Motor 1. Izquierda: cobertura de decisión de la compuerta con "
         "covarianza empírica frente a Ledoit-Wolf. Derecha: correlaciones "
         "de Spearman del score de similitud con variables socioeconómicas.")
     + f"""<div class="glass-panel" style="padding: 24px;">
      <h4 style="font-size: 0.95rem; font-weight: 700; margin-bottom: 8px;">Desempeño de ranking (esquema espacial)</h4>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Variante</th><th>P@10</th><th>NDCG@10</th><th>Cobertura decisión</th></tr></thead>
        <tbody>
          <tr><td>Coseno + compuerta Ledoit-Wolf</td><td>{v['precision@10']:.2f}</td><td>{v['ndcg@10']:.3f}</td><td>{v['decision_coverage']:.3f}</td></tr>
          <tr><td>Coseno + compuerta empírica</td><td>{D['v_emp']['precision@10']:.2f}</td><td>{D['v_emp']['ndcg@10']:.3f}</td><td>{D['v_emp']['decision_coverage']:.3f}</td></tr>
          <tr><td>Coseno sin compuerta</td><td>{D['v_cos']['precision@10']:.2f}</td><td>{D['v_cos']['ndcg@10']:.3f}</td><td>{D['v_cos']['decision_coverage']:.3f}</td></tr>
          <tr><td>Heurística cercanía transporte pesado</td><td>{D['v_metro']['precision@10']:.2f}</td><td>{D['v_metro']['ndcg@10']:.3f}</td><td>{D['v_metro']['decision_coverage']:.3f}</td></tr>
          <tr><td>Control aleatorio</td><td>{D['v_rand']['precision@10']:.2f}</td><td>{D['v_rand']['ndcg@10']:.3f}</td><td>{D['v_rand']['decision_coverage']:.3f}</td></tr>
        </tbody></table></div>
    </div></div>
    {p_('El techo por análogos —densidad histórica de planeación, no demanda— '
        'no superó a una densidad constante mediana en MAE y se retiró del '
        'despliegue.')}
    </div>""")

    # ---- Motor 2
    reg = D["reg"]
    if v2:
        rf_ndcg = bt2["random_forest"]["ndcg_at_10"]
        rand_ndcg = bt2["control_aleatorio"]["ndcg_at_10"]
        m2_txt = (
            f'Entrena sobre las {D["eval_med"]} AGEBs con actividad medida '
            'para predecir el logaritmo de la actividad media por estación. '
            'Su función es ordenar candidatos, no predecir niveles exactos: '
            'en el esquema espacial el bosque aleatorio alcanza Spearman '
            f'{reg["random_forest"]["spearman"]:.3f} y NDCG@10 '
            f'{rf_ndcg:.3f} (control aleatorio: {rand_ndcg:.3f}), con R² de '
            f'{reg["random_forest"]["r2"]:.3f}; el R² mide el ajuste del '
            'nivel, mientras que la decisión depende del orden. Con un '
            'esquema que ignora la geografía el Spearman sube a '
            f'{reg_g["random_forest"]["spearman"]:.3f}, lo que cuantifica '
            'el optimismo de la validación no espacial. El RMSE medio en el '
            f'esquema espacial es {reg["constante"]["rmse"]:.4f} '
            f'(constante), {reg["ridge"]["rmse"]:.4f} (Ridge), '
            f'{reg["random_forest"]["rmse"]:.4f} (bosque aleatorio) y '
            f'{reg["ft_transformer"]["rmse"]:.4f} (FT-Transformer); la '
            'Figura 8 lo resume. Ridge tiene el RMSE ligeramente menor y el '
            f'FT-Transformer muestra R² ({reg["ft_transformer"]["r2"]:.3f} '
            f'frente a {reg["ridge"]["r2"]:.3f}) y Spearman '
            f'({reg["ft_transformer"]["spearman"]:.3f} frente a '
            f'{reg["ridge"]["spearman"]:.3f}) ligeramente superiores, pero '
            'la diferencia de error es menor a la variación entre semillas '
            'y la complejidad no se justifica. Se despliega el bosque '
            'aleatorio por estabilidad y simplicidad.')
    else:
        m2_txt = (
            f'Entrena sobre las {D["eval_med"]} AGEBs con actividad medida '
            'para predecir el logaritmo de la actividad media por estación '
            'y despliega bosque aleatorio por estabilidad y simplicidad. El '
            'RMSE medio en el esquema espacial es '
            f'{reg["constante"]["rmse"]:.4f} '
            f'(constante), {reg["ridge"]["rmse"]:.4f} (Ridge), '
            f'{reg["random_forest"]["rmse"]:.4f} (bosque aleatorio) y '
            f'{reg["ft_transformer"]["rmse"]:.4f} (FT-Transformer); la '
            'Figura 8 lo resume. Ridge tiene el RMSE ligeramente menor, '
            f'pero el FT-Transformer muestra R² '
            f'({reg["ft_transformer"]["r2"]:.3f} frente a '
            f'{reg["ridge"]["r2"]:.3f}) y Spearman '
            f'({reg["ft_transformer"]["spearman"]:.3f} frente a '
            f'{reg["ridge"]["spearman"]:.3f}) ligeramente superiores: '
            'empate práctico, no dominancia, y la complejidad no se '
            'justifica porque la diferencia de RMSE es una fracción de la '
            'variación entre semillas.')
    dic_cierre = (": el valor del modelo está en el orden de los "
                  "candidatos,\n        no en la predicción del nivel."
                  if v2 else
                  ", así que ningún modelo\n        predice con solidez.")
    A(f"""<div class="pane" id="pane-m2">
    <div class="glass-panel" style="padding: 26px; border-top: 4px solid var(--accent-purple);">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
        <span class="badge badge-purple">Motor 2</span>
        <span style="font-size: 0.72rem; color: var(--slate-400); font-weight: 600;">Supervisado · parsimonia</span>
      </div>
      <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 8px;">Modelo predictivo y principio de parsimonia</h3>
      {p_(m2_txt)}
      <div class="table-wrap"><table class="data-table" style="margin-top:10px;">
        <thead><tr><th>Modelo</th><th>Hiperparámetros</th><th>RMSE</th><th>R²</th><th>Spearman</th></tr></thead>
        <tbody>
          <tr><td>Constante</td><td class="font-mono">mediana por pliegue</td><td>{reg['constante']['rmse']:.4f}</td><td>—</td><td>—</td></tr>
          <tr><td>Ridge</td><td class="font-mono">RidgeCV, alphas logspace(-3,3,13), CV 5</td><td>{reg['ridge']['rmse']:.4f}</td><td>{reg['ridge']['r2']:.3f}</td><td>{reg['ridge']['spearman']:.3f}</td></tr>
          <tr><td>Bosque aleatorio</td><td class="font-mono">500 árboles, min_leaf 5, max_features 0.5</td><td>{reg['random_forest']['rmse']:.4f}</td><td>{reg['random_forest']['r2']:.3f}</td><td>{reg['random_forest']['spearman']:.3f}</td></tr>
          <tr><td>FT-Transformer</td><td class="font-mono">d_token 32, 2 capas, 4 cabezas, ff 64, dropout 0.1, lr 1e-3, wd 1e-4, batch 32, 400 épocas, paciencia 40, 5 semillas</td><td>{reg['ft_transformer']['rmse']:.4f}</td><td>{reg['ft_transformer']['r2']:.3f}</td><td>{reg['ft_transformer']['spearman']:.3f}</td></tr>
        </tbody></table></div>
      <div class="callout-box" style="margin-top: 12px;">
        <strong>Dictamen preespecificado.</strong> El Transformer sale del
        despliegue: su diferencia de RMSE frente a Ridge
        (+{abs(reg['ft_transformer']['rmse']-reg['ridge']['rmse']):.4f}) es
        {abs(D['dic']['condition_c_improvement'])/D['dic']['condition_c_seed_std_mean']:.3f}
        veces la variación entre semillas
        ({D['dic']['condition_c_seed_std_mean']:.4f}); el R² espacial máximo es
        {max(r['r2'] for r in reg.values()):.3f}{dic_cierre}
      </div>
    </div>
    <div class="fig-grid">""" +
     fig("n03_m2_rmse.png", 8,
         "RMSE medio por modelo en el esquema espacial; la barra del "
         "FT-Transformer indica la desviación estándar entre semillas.")
     + "</div></div>")

    # ---- Motor 3
    g = D["graph"]
    w_txt = ("con coeficiente w = 0.5 y normalización de variables (la "
             "cobertura se divide por la cota submodular, suma de las B "
             "mayores coberturas individuales, y la afinidad se promedia "
             "sobre B, de modo que ambos términos quedan en escala "
             "comparable)." if v2 else
             "con w = 0.5 en la configuración primaria.")
    gaclose_txt = ("la diferencia cae dentro de la variación entre "
                   "semillas (Figura 9)." if v2 else
                   "la diferencia cae dentro del ruido entre semillas "
                   "(empate práctico, Figura 9).")
    if v2:
        pnorm_s = miles(sc["p_norm"])
        eq_html = (
            '<div class="eq-box" role="math" aria-label="máximo sobre S '
            'subconjunto de C con cardinal B, de w por Pob de S entre Pob '
            'estrella sub B, más uno menos w por un B-ésimo por la suma '
            'sobre j en S de uno entre uno más h sub j">'
            '<div class="eq">'
            '<span class="eq-max">max'
            '<span class="eq-sub"><var>S</var> ⊆ <var>C</var>, '
            '|<var>S</var>| = <var>B</var></span></span>'
            '<span>[</span><var>w</var> · '
            '<span class="eq-frac"><span>Pob(<var>S</var>)</span>'
            '<span>Pob*<sub><var>B</var></sub></span></span>'
            ' + (1 − <var>w</var>) · '
            '<span class="eq-frac"><span>1</span>'
            '<span><var>B</var></span></span>'
            ' · <span class="eq-sum">'
            '<span style="font-size:1.5em;line-height:1">Σ</span>'
            '<span class="eq-sub"><var>j</var> ∈ <var>S</var></span>'
            '</span>'
            '<span class="eq-frac"><span>1</span>'
            '<span>1 + <var>h</var><sub><var>j</var></sub></span></span>'
            '<span>]</span></div>'
            '<div class="eq-legend">'
            '<var>S</var>: portafolio de <var>B</var> sitios; '
            '<var>C</var>: sitios candidatos factibles (enlace ≤ 500 m, '
            'separación ≥ 300 m, crecimiento contiguo desde la red). '
            'Pob(<var>S</var>): población nueva cubierta por la unión de '
            'zonas de captura de 500 m sobre celdas de 200 m, sin doble '
            'conteo. Pob*<sub>B</sub>: constante de normalización, suma de '
            f'las B mayores coberturas individuales ({pnorm_s} habitantes '
            f'con B = 30). <var>h</var><sub>j</sub>: saltos desde el sitio '
            'j hasta la estación Golden más cercana en el grafo de '
            'enlaces. <var>w</var> = 0.5: coeficiente de ponderación.'
            '</div></div>')
    else:
        eq_html = ""
    matiz_extra = (" El barrido de pesos a B = 30 muestra que con w ≥ 0.5 "
                   "el portafolio coincide con el de maximizar solo "
                   "cobertura; la afinidad solo lo modifica con w ≤ 0.25."
                   if v2 else "")
    A(f"""<div class="pane" id="pane-m3">
    <div class="glass-panel" style="padding: 26px; border-top: 4px solid var(--primary);">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
        <span class="badge badge-primary">Motor 3</span>
        <span style="font-size: 0.72rem; color: var(--slate-400); font-weight: 600;">Prescriptivo · grafo</span>
      </div>
      <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 8px;">Optimización prescriptiva sobre grafos</h3>
      {p_(f'Pasa de predecir a diseñar: un grafo geométrico con malla de sitios '
          f'de {D["site_grid"]:.0f} m, aristas de enlace de hasta '
          f'{D["link_m"]:.0f} m, separación mínima de {D["spacing_m"]:.0f} m '
          f'entre estaciones nuevas y crecimiento contiguo desde la red '
          f'({miles(g["n_graph_nodes"])} nodos, {miles(g["n_graph_edges"])} aristas, '
          f'{miles(g["n_sites"])} sitios candidatos). La afinidad '
          'de un sitio es determinista: 1/(1+saltos a Golden). Un grafo evita '
          'estaciones aisladas porque el servicio exige origen y destino en la '
          'red; a diferencia del Motor 1, que mide similitud en el espacio de '
          'características, aquí la cercanía se mide en saltos sobre la '
          'estructura de red.')}
      {p_(f'La función objetivo combina cobertura y afinidad: '
          'f = w·cobertura + (1−w)·afinidad media, ' + w_txt +
          ' La selección la hace un algoritmo Greedy '
          'determinista contrastado con un algoritmo genético (población 80, '
          '120 generaciones, cruza 0.7, mutación 0.3, torneo 3, élite 2, '
          'semillas 42–46 en la primaria y 42–44 en las demás; '
          f'{D["n_rand"]} portafolios aleatorios de referencia). En las 7 '
          'configuraciones el Greedy iguala o supera a la mejor corrida del '
          'GA; en w = 0.25 y w = 0.75 ' + gaclose_txt)}{eq_html}
      <div class="callout-box callout-gold" style="margin-top: 8px;">
        <strong>Matiz honesto.</strong> La ventaja del Greedy es empírica: la
        garantía (1−1/e) de cobertura submodular no aplica formalmente bajo
        las restricciones de contigüidad y espaciamiento, y el GA es una
        heurística sin garantía de optimalidad. La cercanía a Golden está
        optimizada por construcción.{matiz_extra}
      </div>
      {p_('Los embeddings de grafo (Node2Vec) se evaluaron en una iteración '
          'previa y se retiraron por decisión metodológica: su afinidad no '
          'ordenaba por cercanía al núcleo.')}
    </div>
    <div class="fig-grid">""" +
     fig("n06_m3_objetivo.png", 9,
         "Función objetivo por configuración: Greedy frente a la mejor "
         "corrida y a la media ± desviación entre semillas del GA; las "
         "franjas sombreadas marcan los empates dentro del ruido entre "
         "semillas.")
     + fig("n04_m3_poblacion.png", 10,
           "Población nueva cubierta por el Greedy y por la mejor semilla "
           "del GA a cada presupuesto; la etiqueta indica la ventaja del "
           "Greedy en habitantes.")
     + fig("n05_m3_tiempos.png", 11,
           "Tiempo de ejecución por configuración (escala logarítmica): "
           "una corrida del Greedy frente a la media por semilla del GA; "
           "la nota inferior reporta los totales no pareados del "
           "experimento.")
     + "</div>")
    A("</div></div>")

    # ------------------------------------------------------- 06 Simulador
    A('<div id="simulador">')
    A(chap("06", "Simulador interactivo de portafolios",
           f'<span class="badge badge-neutral" style="margin-left:auto;">'
           f'{miles(g["n_sites"])} sitios viables</span>'))
    A("""<div class="glass-panel" style="padding: 24px;">
      <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 20px;">
        <div>
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 8px;">Motor:</div>
          <div style="display: flex; gap: 6px; background: var(--slate-100); padding: 4px; border-radius: 9999px; flex-wrap: wrap;">
            <button onclick="setStrategy('m1')" id="btn-m1" class="btn btn-segmented active">M1 · Similitud</button>
            <button onclick="setStrategy('m2')" id="btn-m2" class="btn btn-segmented">M2 · Predictivo RF</button>
            <button onclick="setStrategy('m3')" id="btn-m3" class="btn btn-segmented">M3 · Greedy</button>
          </div>
        </div>
        <div>
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 8px;">Presupuesto (B):</div>
          <div style="display: flex; gap: 6px; background: var(--slate-100); padding: 4px; border-radius: 9999px;">
            <button onclick="setBudget(15)" id="btn-b15" class="btn btn-segmented">B = 15</button>
            <button onclick="setBudget(30)" id="btn-b30" class="btn btn-segmented active">B = 30</button>
            <button onclick="setBudget(50)" id="btn-b50" class="btn btn-segmented">B = 50</button>
          </div>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--slate-200);">
        <div><div style="font-size: 0.72rem; color: var(--slate-500); font-weight: 600;">Población nueva cubierta</div>
          <div id="kpi-pop" style="font-size: 1.6rem; font-weight: 800; color: var(--primary);">—</div></div>
        <div><div style="font-size: 0.72rem; color: var(--slate-500); font-weight: 600;">AGEBs beneficiadas</div>
          <div id="kpi-agebs" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">—</div></div>
        <div><div style="font-size: 0.72rem; color: var(--slate-500); font-weight: 600;">Escolaridad media</div>
          <div id="kpi-esc" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">—</div></div>
        <div><div style="font-size: 0.72rem; color: var(--slate-500); font-weight: 600;">Distancia media a la red</div>
          <div id="kpi-dist" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">—</div></div>
      </div>
    </div>""")
    A("""<div class="glass-panel" style="padding: 16px; position: relative;">
      <div style="position: absolute; top: 28px; right: 28px; z-index: 500; background: rgba(255,255,255,0.96); backdrop-filter: blur(10px); padding: 12px 16px; border-radius: var(--radius-md); border: 1px solid var(--slate-200); box-shadow: var(--card-shadow); font-size: 0.78rem; display: flex; flex-direction: column; gap: 6px;">
        <div style="font-weight: 700; color: var(--slate-900); margin-bottom: 2px;">Capas</div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="width: 10px; height: 10px; border-radius: 50%; background: #94a3b8; display: inline-block;"></span>
          <span id="legend-st">Estaciones vigentes</span></div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="width: 10px; height: 10px; border-radius: 50%; background: #d97706; display: inline-block;"></span>
          <span id="legend-g">Grupo de alta actividad</span></div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span id="legend-new-dot" style="width: 12px; height: 12px; border-radius: 50%; background: #0284c7; display: inline-block; border: 2px solid white;"></span>
          <span id="legend-new">Sitios nuevos seleccionados</span></div>
        <div style="font-weight: 700; color: var(--slate-900); margin: 6px 0 2px; padding-top: 8px; border-top: 1px solid var(--slate-200);">Transporte y ciclovías</div>
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
          <input type="checkbox" id="chk-metro" onchange="toggleLayer('metro',this.checked)">
          <span style="width: 18px; height: 0; border-top: 3px solid #D81E05; display: inline-block;"></span>
          <span>Metro (<span id="n-metro"></span> líneas)</span></label>
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
          <input type="checkbox" id="chk-mb" onchange="toggleLayer('mb',this.checked)">
          <span style="width: 18px; height: 0; border-top: 3px dashed #D40D0D; display: inline-block;"></span>
          <span>Metrobús (<span id="n-mb"></span> líneas)</span></label>
        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
          <input type="checkbox" id="chk-bici" onchange="toggleLayer('bici',this.checked)">
          <span style="width: 18px; height: 0; border-top: 2px solid #16a34a; display: inline-block;"></span>
          <span>Ciclovías en operación (<span id="n-bici"></span> km)</span></label>
      </div>
      <svg id="map-svg" preserveAspectRatio="xMidYMid meet" style="width:100%;height:560px;display:block;" role="img" aria-label="Mapa de la ciudad con estaciones vigentes y sitios seleccionados del portafolio"></svg>
    </div>""")
    A("""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 12px;">Sitios del portafolio activo</h3>
      <div class="table-wrap" style="max-height: 420px; overflow-y: auto;">
        <table class="data-table">
          <thead><tr><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">Orden</th><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">Sitio</th><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">Alcaldía</th><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">AGEB</th><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">Pob. nueva aportada</th><th style="position:sticky;top:0;background:var(--slate-50);z-index:5">Distancia a red</th></tr></thead>
          <tbody id="portfolio-table-body"></tbody>
        </table>
      </div>
      <div id="resumen" style="font-size: 0.8rem; color: var(--slate-500); margin-top: 10px;"></div>
    </div>""")
    A("</div>")

    # ------------------------------------------------------- 07 Resultados
    A('<div id="resultados">')
    A(chap("07", "Resultados y discusión"))
    A("""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Cobertura por motor y presupuesto (portafolios oficiales)</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Motor</th><th>B</th><th>Población nueva</th><th>AGEBs</th><th>% población</th><th>Distancia media a red</th><th>Escolaridad media</th></tr></thead>
        <tbody>""" + "".join(
        f"<tr><td><span class='badge "
        f"{ {'m1':'badge-blue','m2':'badge-purple','m3':'badge-primary'}[r['motor']] }'>"
        f"{ {'m1':'M1 · Similitud','m2':'M2 · Predictivo','m3':'M3 · Greedy'}[r['motor']] }</span></td>"
        f"<td class='font-mono'>{r['b']}</td>"
        f"<td style='font-weight:700'>{r['pop_s']}</td>"
        f"<td>{r['agebs']}</td><td>{r['pct']:.2f}%</td>"
        f"<td>{r['dist']} m</td><td>{r['esc']:.2f}</td></tr>"
        for r in cov) + """</tbody>
      </table></div>
      <p style="font-size: 0.8rem; color: var(--slate-500); margin-top: 10px;">
        La población de cada portafolio se calcula sobre celdas de 200 m
        cubiertas por la unión de las zonas de captura euclidianas de 500 m,
        contando cada celda una sola vez; por eso es menor o igual a la suma
        de las poblaciones de las zonas individuales cuando estas se traslapan.
      </p>
    </div>""")
    A("""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Greedy frente a algoritmo genético (configuración primaria, w = 0.5)</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>B</th><th>Greedy</th><th>GA mejor semilla</th><th>Ventaja Greedy</th></tr></thead>
        <tbody>""" + "".join(
        f"<tr><td class='font-mono'>{r['b']}</td>"
        f"<td style='font-weight:700;color:var(--primary)'>{r['greedy_s']}</td>"
        f"<td>{r['ga_s']}</td>"
        f"<td><span class='badge badge-verified'>+{r['dif_s']}</span></td></tr>"
        for r in gav) + """</tbody>
      </table></div>
      <p style="font-size: 0.85rem; color: var(--slate-600); margin-top: 10px;">
        En costo computacional, una ejecución del Greedy toma 0.016 s frente
        a 51.4 s por semilla del GA en la configuración primaria (3,193x;
        rango emparejado 2,786x–4,422x). Los totales del experimento —0.123 s
        del Greedy frente a 1,303 s del GA, unos 21.7 minutos— no son
        pareados: el GA corre varias semillas por configuración y el Greedy
        una sola corrida, por lo que el cociente de totales no es un
        indicador válido.
      </p>
    </div>""")
    A(grid2)
    A(card("Divergencia territorial",
           p_(f"A B = 30 el Jaccard de sitios es "
              f"{D['ov30']['m1-m2']['jaccard_sites']:.3f} (M1–M2), "
              f"{D['ov30']['m1-m3']['jaccard_sites']:.3f} (M1–M3) y "
              f"{D['ov30']['m2-m3']['jaccard_sites']:.3f} (M2–M3); "
              f"{D['cons']['30']['selected_by_2plus']} sitios aparecen en al "
              f"menos 2 motores y {D['cons']['30']['selected_by_3']} en los "
              "3 (Figuras 13 y 14). La divergencia es descriptiva: los "
              "objetivos difieren por diseño."), accent="var(--accent-blue)"))
    tension_txt = (
        f"A B = 30 la escolaridad media de las AGEBs seleccionadas es "
        f"{D['ofi'][('m1',30)]['mean_grado_escolar_prom_selected']:.2f} "
        f"(M1), "
        f"{D['ofi'][('m2',30)]['mean_grado_escolar_prom_selected']:.2f} "
        f"(M2) y "
        f"{D['ofi'][('m3',30)]['mean_grado_escolar_prom_selected']:.2f} "
        f"(M3) frente a {esc_universe:.2f} del universo de candidatos "
        "(Figuras 19 y 20). El Motor 1 premia la similitud con el "
        "perfil exitoso; el Motor 3 maximiza cobertura más cercanía a "
        "la red —la menor escolaridad es consecuencia observada, no "
        "objetivo programado—."
        + (" El Motor 1 queda por encima del " + str(p_m1) +
           " % de la nube en escolaridad; el Motor 3 "
           "permanece dentro de la nube en escolaridad pero con cobertura "
           "mayor que la de cualquiera de los " + str(n_rand) +
           " portafolios aleatorios conectados (máximo " +
           miles(cloud_max) + ")." if v2 else ""))
    A(card("Tensión similitud–cobertura",
           p_(tension_txt), accent="var(--accent-gold)"))
    A("</div>")
    A('<div class="fig-grid">'
      + fig("c8/c8_01_cobertura_por_presupuesto.png", 12,
            "Población nueva cubierta por los portafolios oficiales de "
            "los tres motores a cada presupuesto.")
      + fig("c8/c8_06_jaccard_sitios_agebs.png", 13,
            "Índices de Jaccard de sitios y de AGEBs entre pares de "
            "motores por presupuesto; el traslape bajo evidencia que los "
            "motores seleccionan territorios distintos.")
      + "</div>")
    A('<div class="fig-grid">'
      + fig("c8/c8_07_mapas_consenso.png", 14,
            "Mapa del universo evaluable y del consenso territorial: "
            "sitios elegidos por al menos dos motores y por los tres.")
      + fig("c8/c8_02_radar_b30.png", 15,
            "Radar de ejes fijos en B = 30; cada eje codifica un objetivo "
            "distinto y el área no es un puntaje.")
      + "</div>")
    A('<div class="fig-grid">'
      + fig("c8/c8_03_radar_presupuestos.png", 16,
            "Radar de ejes fijos por presupuesto para cada motor.")
      + fig("c8/c8_04_heatmap_metricas.png", 17,
            "Matriz de métricas oficiales por motor y presupuesto, "
            "recomputadas desde los portafolios publicados.")
      + "</div>")
    if v2:
        A('<div class="fig-grid">'
          + fig("c8/c8_05_estaciones_por_ageb.png", 18,
                "Distribución de estaciones seleccionadas por AGEB (1, 2 "
                "o 3 o más) en cada portafolio oficial.")
          + fig("c8/c8_08_equidad.png", 19,
                "Perfil de equidad de los portafolios: escolaridad media "
                "y tenencia de automóvil en las AGEBs seleccionadas "
                "frente al universo de candidatos.")
          + "</div>")
        A('<figure><div class="scatter-wrap">' + _scatter_svg(sc) +
          '</div>'
          '<figcaption><span class="fnum">Figura 20.</span>'
          'Población nueva cubierta y escolaridad media a B = 30: '
          + str(n_rand) +
          ' portafolios aleatorios conectados y factibles (misma '
          'red y mismas restricciones) frente a los portafolios '
          'oficiales de los tres motores; la línea punteada marca el '
          'universo de candidatos.</figcaption></figure>')
        # Tabla C: referencias simples a B = 30 (cifras del JSON congelado)
        ws = sc["w_sweep"]
        base_pop = sc["cloud"]["pop_mean"]

        def rx(pop):
            return f"{pop / base_pop:.2f}×"

        MCOLOR = {"m1": "#7e22ce", "m2": "#0284c7", "m3": "#b45309"}

        def ref_row(nombre, pop, esc, badge=None, note="", hl=False):
            chip = (f'<span class="badge" style="background:{badge}1A;'
                    f'color:{badge};border:1px solid {badge}40;">'
                    f'{nombre}</span>' if badge else nombre)
            nota = (f'<div style="font-size:0.72rem;color:var(--slate-500);'
                    f'margin-top:4px;">{note}</div>' if note else "")
            bg = ' style="background:#fef3c7;"' if hl else ""
            return (f"<tr{bg}><td>{chip}{nota}</td>"
                    f'<td class="font-mono" style="text-align:right">'
                    f'{miles(pop)}</td>'
                    f'<td class="font-mono" style="text-align:right">'
                    f'{esc:.2f}</td>'
                    f'<td class="font-mono" style="text-align:right">'
                    f'{rx(pop)}</td></tr>')

        jac10 = ws["1.0"]["jaccard_vs_w05"]
        ref_rows = "".join([
            ref_row(f"Azar conectado (media de {n_rand} portafolios)",
                    base_pop, sc["cloud"]["esc_mean"]),
            ref_row("Motor 1 · Similitud", sc["official"]["m1"]["new_pop"],
                    sc["official"]["m1"]["esc"], MCOLOR["m1"]),
            ref_row("Motor 2 · Predictivo", sc["official"]["m2"]["new_pop"],
                    sc["official"]["m2"]["esc"], MCOLOR["m2"]),
            ref_row("Motor 3 (w = 0.5)", sc["official"]["m3"]["new_pop"],
                    sc["official"]["m3"]["esc"], MCOLOR["m3"], hl=True),
            ref_row("Solo población (Motor 3 con w = 1)",
                    ws["1.0"]["new_pop"], ws["1.0"]["esc"], MCOLOR["m3"],
                    note=f"mismo conjunto de 30 sitios que w = 0.5 "
                         f"(Jaccard {jac10:.1f}); heurística voraz, no un "
                         "máximo demostrado"),
            ref_row("Solo afinidad al núcleo (Motor 3 con w = 0)",
                    ws["0.0"]["new_pop"], ws["0.0"]["esc"], MCOLOR["m3"])])
        A(f"""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Referencias simples a B = 30</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Referencia</th><th style="text-align:right">Población nueva</th><th style="text-align:right">Escolaridad media</th><th style="text-align:right">Cobertura frente al azar</th></tr></thead>
        <tbody>{ref_rows}</tbody>
      </table></div>
      <p style="font-size: 0.8rem; color: var(--slate-500); margin-top: 10px;">
        Azar conectado: portafolios aleatorios factibles que crecen de forma
        contigua desde la red (misma red y mismas restricciones; desviación
        entre portafolios: ±{miles(sc['cloud']['pop_sd'])} habitantes y
        ±{sc['cloud']['esc_sd']:.2f} años). Ningún portafolio aleatorio
        alcanza la cobertura del Motor 3 (máximo aleatorio:
        {miles(sc['cloud']['pop_max'])}).
      </p>
    </div>""")
    else:
        A('<div class="fig-grid">'
          + fig("c8/c8_05_estaciones_por_ageb.png", 18,
                "Distribución de estaciones seleccionadas por AGEB (1, 2 "
                "o 3 o más) en cada portafolio oficial.")
          + fig("c8/c8_08_equidad.png", 19,
                "Perfil de equidad de los portafolios: escolaridad media "
                "y tenencia de automóvil en las AGEBs seleccionadas "
                "frente al universo de candidatos.")
          + fig("n07_escolaridad.png", 20,
                "Escolaridad media de las AGEBs seleccionadas por cada "
                "motor a B = 30 frente al universo de candidatos (línea "
                "punteada).")
          + "</div>")
    A(p_("Los radares de las Figuras 15 y 16 usan ejes fijos: el área del "
         "radar no es un puntaje agregado y no ordena a los motores. La "
         "matriz de la Figura 17 resume las métricas oficiales recomputadas "
         "desde los portafolios publicados, y la Figura 18 muestra cuántas "
         "estaciones cae cada motor por AGEB."))
    A("</div>")

    # ------------------------------------------------------- 08 Conclusiones
    A('<div id="conclusiones">')
    A(chap("08", "Conclusiones"))
    if v2:
        def p_mt(t):
            return p_(t).replace('<p style="',
                                 '<p style="margin-top: 14px; ', 1)
        hyp_rows = "".join(
            f"<tr><td><span class='badge badge-neutral'>{t}</span></td>"
            f"<td>{r}</td>"
            f"<td><span class='badge badge-verified'>Sostenida</span></td>"
            f"</tr>"
            for t, r in [
                ("H1 · Concentración",
                 f"Gini {D['gini_est']:.4f} (estaciones) y "
                 f"{D['gini_act']:.4f} (actividad); "
                 f"I = {D['moran_i']:.4f}."),
                ("H2 · Sesgo de similitud",
                 f"ρ = {esc_bias:.2f}; "
                 f"{sc['official']['m1']['esc']:.2f} "
                 f"(percentil {p_m1})."),
                ("H3 · Cobertura",
                 f"{miles(D['ofi'][('m3', 30)]['new_pop'])} &gt; "
                 f"{miles(D['ofi'][('m1', 30)]['new_pop'])} a B = 30; "
                 "ventaja también en B = 15 y 50."),
                ("H4 · Equidad sin desvío",
                 f"{sc['official']['m3']['esc']:.2f} "
                 f"(percentil {p_m3}; universo {esc_uni:.2f}).")])
        A(card("Respuesta a las hipótesis",
               '<div class="table-wrap"><table class="data-table">'
               '<thead><tr><th>Hipótesis</th><th>Resultado</th>'
               '<th>Veredicto</th></tr></thead><tbody>' + hyp_rows +
               '</tbody></table></div>'
               + p_mt(f"En el diseño retrospectivo la hipótesis general se "
                    "sostiene: el Motor 3 cubre más población nueva que el "
                    "Motor 1 y no se desvía en escolaridad respecto del "
                    "azar conectado, mientras que el Motor 1 sí se desvía "
                    "hacia mayor escolaridad. H4 no establece que el "
                    "Motor 3 favorezca zonas de menor escolaridad: su "
                    f"valor ({sc['official']['m3']['esc']:.2f}) se ubica en "
                    f"el percentil {p_m3} de la nube aleatoria. Las "
                    "condiciones son reales: la cobertura es población en "
                    "zonas de captura, no demanda observada; ningún modelo "
                    "predictivo resultó fuerte en nivel; y la cercanía a "
                    "Golden del Motor 3 está optimizada por construcción. "
                    "La afinidad por saltos a Golden solo modifica el "
                    "portafolio con pesos w ≤ 0.25: con w ≥ 0.5 coincide "
                    "con el que maximiza únicamente la cobertura (Jaccard "
                    f"{sc['w_sweep']['1.0']['jaccard_vs_w05']:.1f}), de "
                    "modo que la conectividad se debe a la restricción de "
                    "crecimiento contiguo, común a los tres motores."),
               accent="var(--primary)"))
        A(card("Recomendaciones",
               p_(f"Iniciar un piloto sobre los {cons2} sitios elegidos por "
                  f"al menos dos motores a B = 30 ({cons3} por los tres "
                  f"motores y {cons2 - cons3} por exactamente dos), sujeto "
                  "a levantamiento de campo, costos y red caminable; usar "
                  "el Motor 3 como generador de portafolio y el Motor 1 "
                  "como control de similitud.")))
        icons = "".join(
            f'<circle cx="{13 + i * 26}" cy="13" r="10" '
            f'fill="{"#b45309" if i < cons3 else "#004d40"}" '
            'stroke="#ffffff" stroke-width="2"/>'
            for i in range(cons2))
        A(f"""<div class="glass-panel" style="padding: 24px;">
      <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 10px;">Despliegue del piloto</h3>
      <svg width="{cons2 * 26}" height="26" role="img"
        aria-label="{cons2} estaciones del piloto: {cons3} de consenso triple y {cons2 - cons3} de consenso doble"
        style="display:block;max-width:100%;height:auto;">{icons}</svg>
      <div style="display: flex; gap: 18px; flex-wrap: wrap; font-size: 0.8rem; color: var(--slate-600); margin: 6px 0 14px;">
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#b45309;margin-right:5px;"></span>{cons3} sitios de consenso triple</span>
        <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#004d40;margin-right:5px;"></span>{cons2 - cons3} sitios de consenso doble</span>
      </div>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px;">
        <div style="border: 1px solid var(--slate-200); border-radius: var(--radius-md); padding: 16px;">
          <div style="font-size: 0.78rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 10px;">Costo paramétrico</div>
          <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center; font-size: 0.85rem; color: var(--slate-700);">
            <label>Estaciones <input type="number" id="piloto-n" class="cost-input" value="18" min="1" step="1"></label>
            <label>Costo unitario (MXN) <input type="number" id="piloto-u" class="cost-input" value="450000" min="0" step="10000"></label>
          </div>
          <div id="piloto-total" style="font-size: 1.4rem; font-weight: 800; color: var(--primary); margin-top: 10px;">$8,100,000 MXN</div>
          <div style="font-size: 0.75rem; color: var(--slate-500); margin-top: 6px;">Supuesto paramétrico editable; no es una estimación de campo. Valor inicial: 450,000 MXN por estación.</div>
        </div>
        <div style="border: 1px solid var(--slate-200); border-radius: var(--radius-md); padding: 16px;">
          <div style="font-size: 0.78rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 10px;">Métrica de éxito en campo</div>
          <p style="font-size: 0.85rem; color: var(--slate-700); line-height: 1.6;">Viajes diarios promedio por estación piloto frente a la mediana de la red ({mediana_red:.1f} viajes por día en {D['year']}, {n_est} estaciones), evaluados a los 3 y 6 meses de operación.</p>
        </div>
      </div>
    </div>""")
        sup_rows = [
            ("Captura por distancia euclidiana de 500 m",
             "Vías rápidas, ríos y pendientes alargan el trayecto real; "
             "el círculo sobreestima la población alcanzable",
             "Áreas de servicio de caminata sobre la red peatonal "
             "equivalentes a 500 m, comparadas con el círculo."),
            ("Población del Censo 2020 como población presente",
             "Cambio demográfico y urbano entre 2020 y 2025; la población "
             "flotante no está censada",
             "Conteo o encuesta de residentes y población flotante en el "
             "entorno de cada sitio piloto."),
            ("Actividad de estaciones existentes como indicador de demanda",
             "La demanda latente de zonas sin servicio no se observa; la "
             "actividad refleja también la oferta",
             "Viajes diarios por estación del piloto frente a la mediana "
             "de la red, a 3 y 6 meses."),
            ("Retícula de candidatos cada 250 m",
             "Predios, banquetas o permisos pueden impedir instalar en el "
             "nodo exacto",
             "Levantamiento físico del sitio y ajuste a la ubicación "
             "factible más cercana."),
            ("Cobertura de población equivale a beneficio",
             "La población en la zona de captura no es necesariamente "
             "usuaria",
             "Registro de usuarios nuevos o muestreo en el área de "
             "captura."),
            ("Enlace de 500 m entre estaciones como continuidad de la red",
             "La ruta real entre estaciones puede ser insegura o no "
             "ciclable",
             "Recorrido en bicicleta entre estaciones vecinas con medición "
             "de tiempo y seguridad percibida.")]
        sup_html = "".join(
            f"<tr><td style='font-weight:600'>{a}</td><td>{b}</td>"
            f"<td>{c}</td></tr>" for a, b, c in sup_rows)
        A(card("Límites de la investigación",
               p_("Se omiten costos, caminabilidad, demanda observada (la "
                  "cobertura es población en captura), operación e "
                  "inferencia causal; el análisis cubre una sola ciudad y "
                  "está acotado por el tiempo y los datos disponibles. La "
                  "tabla confronta los supuestos del modelo con su "
                  "contraste en campo.")
               + '<h4 style="font-size: 0.95rem; font-weight: 700; '
                 'margin: 14px 0 8px;">Supuestos del modelo frente a la '
                 'realidad</h4>'
               + '<div class="table-wrap"><table class="data-table">'
                 '<thead><tr><th>Qué supone el modelo</th>'
                 '<th>Dónde falla en la realidad</th>'
                 '<th>Cómo se mediría en campo</th></tr></thead><tbody>'
               + sup_html + '</tbody></table></div>'
               + p_mt(f"El desajuste temporal entre Censo {D['census_year']}, "
                    f"viajes {D['year']} y DENUE {D['denue_year']}, la "
                    "abstención de la compuerta (que no implica sitios "
                    "malos), el alcance de una sola ciudad y la ausencia "
                    "de inferencia causal acotan las conclusiones."),
               accent="#dc2626"))
        A(grid2)
    else:
        A(grid2)
        A(card("Respuesta a la hipótesis",
               p_("Afirmativa con matices y condiciones: un enfoque de "
                  "ciencia de datos sí puede diseñar una expansión justa y "
                  "conectada si se respetan los tres principios —la fuga se "
                  "descartó antes del modelado, las AGEBs sin servicio se "
                  "trataron como no etiquetadas y la tensión "
                  "similitud–equidad se documentó explícitamente—. Las "
                  "condiciones son reales: la cobertura es población en "
                  "zonas de captura, no demanda observada; ningún modelo "
                  "predictivo resultó fuerte; y la cercanía a Golden del "
                  "Motor 3 está optimizada por construcción."),
               accent="var(--primary)"))
        A(card("Recomendaciones",
               p_(f"Iniciar un piloto sobre los "
                  f"{D['cons']['30']['selected_by_3']} sitios de consenso "
                  f"triple y los {D['cons']['30']['selected_by_2plus']} de "
                  "consenso doble, sujeto a levantamiento de campo, costos "
                  "y red caminable; usar el Motor 3 como generador de "
                  "portafolio y el Motor 1 como control de similitud.")))
        A("</div>")
        A(grid2)
        A(card("Límites de la investigación",
               p_(f"Se omiten costos, caminabilidad, demanda observada (la "
                  "cobertura es población en captura), operación, "
                  "inferencia causal y el desajuste temporal entre Censo "
                  f"{D['census_year']}, viajes {D['year']} y DENUE "
                  f"{D['denue_year']}. La abstención de la compuerta no "
                  "implica sitios malos; el análisis cubre una sola ciudad "
                  "y está acotado por el tiempo y los datos disponibles."),
               accent="#dc2626"))
    A(card("Trabajo futuro",
           p_("Queda abierta la incorporación de costos y restricciones "
              "operativas, la medición de demanda real tras un piloto, la "
              "extensión a red caminable, la sensibilidad temporal con más "
              "años de operación y la réplica del arnés en otras ciudades "
              "del sistema.")))
    A("</div></div>")

    # ------------------------------------------------------- 09 Bibliografía
    A('<div id="biblio">')
    A(chap("09", "Bibliografía"))
    A(f"""<div class="glass-panel" style="padding: 24px;">
      <ol style="font-size: 0.88rem; color: var(--slate-700); padding-left: 20px; display: flex; flex-direction: column; gap: 8px;">
        <li>Gobierno de la Ciudad de México — SEMOVI / EcoBici. Datos
          abiertos de viajes del sistema EcoBici, {D['year']}.</li>
        <li>INEGI. Censo de Población y Vivienda, {D['census_year']}.</li>
        <li>INEGI. Marco Geoestadístico, {D['census_year']}.</li>
        <li>INEGI. Directorio Estadístico Nacional de Unidades Económicas
          (DENUE), {D['denue_year']}.</li>
        <li>Movilidad CDMX / operadores. Especificación GTFS de la red de
          transporte público, {D['gtfs_year']}.</li>
      </ol>
    </div>""")
    A("</div>")
    if v2:
        A(f"""<div id="transparencia" style="display: flex; flex-direction: column; gap: 20px;">
<div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
  <span class="badge badge-neutral">Anexo</span>
  <h2 style="font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em;">Transparencia y reproducibilidad</h2>
</div>
<div class="glass-panel" style="padding: 26px; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 32px; align-items: start;">
  <div>
    {_qr_repo()}
    <div style="font-size: 0.82rem; color: var(--slate-600); margin-top: 10px; max-width: 240px;">Repositorio en GitHub con código fuente<br/><span style="font-weight:600;">github.com/Omarti34/Ecobicis2026</span></div>
  </div>
  <div>
    <h3 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 10px;">Reproducibilidad</h3>
    <ul style="font-size: 0.88rem; color: var(--slate-700); padding-left: 18px; display: flex; flex-direction: column; gap: 7px; line-height: 1.55;">
      <li>Cada cifra se traza a un reporte sellado con identificador de análisis y huella SHA-256.</li>
      <li>Datos crudos inmutables y contrato de datos con identificador único.</li>
      <li>Semillas fijas: los {n_rand} portafolios aleatorios de la Figura 20 se reproducen con la semilla {sc['seed']} y coinciden con el reporte del Motor 3.</li>
      <li>Simulador autocontenido: un solo archivo, sin conexión a internet.</li>
    </ul>
    <h3 style="font-size: 1.05rem; font-weight: 700; margin: 18px 0 8px;">Nota sobre el uso de IA generativa</h3>
    <p style="font-size: 0.88rem; color: var(--slate-700); line-height: 1.6;">Se emplearon modelos de lenguaje (LLMs) como asistentes para la refactorización de código —incluido el simulador y los procesos de construcción— y para la corrección de estilo del documento, validando de forma humana la lógica deductiva.</p>
  </div>
</div>
</div>""")
    A("</main>")

    # ------------------------------------------------------------- JS inline
    A("""<script>
const DATA = """ + payload_json + """;
const MOTOR_COLOR = {m1:"#0284c7", m2:"#7e22ce", m3:"#004d40"};
const MOTOR_NAME = {m1:"Motor 1 · Similitud", m2:"Motor 2 · Predictivo", m3:"Motor 3 · Greedy"};
let curM = "m1", curB = 30;

function fmt(v){return v.toLocaleString("en-US");}

// --- geometria lon/lat -> svg ---
const _pts=DATA.stations.slice();
Object.values(DATA.ports).forEach(o=>Object.values(o).forEach(a=>a.forEach(q=>_pts.push(q))));
const _lo=_pts.map(q=>q.lon), _la=_pts.map(q=>q.lat), _pd=0.03;
const minLon=Math.min(..._lo)-_pd, maxLon=Math.max(..._lo)+_pd,
      minLat=Math.min(..._la)-_pd, maxLat=Math.max(..._la)+_pd;
const kx=0.94;  // correccion de latitud ~cos(19.4)
const W=1000, pad=18;
const scale=(W-2*pad)/((maxLon-minLon)*kx);
const VH=Math.round((maxLat-minLat)*scale+2*pad);
const cx0=(minLon+maxLon)/2, cy0=(maxLat+minLat)/2;
function X(lon){return W/2+(lon-cx0)*kx*scale;}
function Yc(lat){return VH/2-(lat-cy0)*scale;}
function mapTransform(){
  return "translate("+W/2+" "+VH/2+") scale("+(scale*kx)+" "+(-scale)+") translate("+(-cx0)+" "+(-cy0)+")";
}

function renderCatalog(cat){
  const tbody=document.getElementById("catalog-table-body");
  tbody.innerHTML="";
  DATA.catalog.filter(i=>{
    if(cat==="all")return true;
    const s=i.source.toLowerCase();
    if(cat==="censo")return s.includes("censo");
    if(cat==="denue")return s.includes("denue");
    if(cat==="gtfs")return s.includes("gtfs");
    return true;
  }).forEach(i=>{
    const badge=i.source.toLowerCase().includes("censo")?"badge-primary":
      i.source.toLowerCase().includes("denue")?"badge-gold":
      i.source.toLowerCase().includes("gtfs")?"badge-blue":"badge-neutral";
    const tr=document.createElement("tr");
    tr.innerHTML="<td style='font-weight:700;font-family:monospace'>"+i.name+"</td>"+
      "<td><span class='badge "+badge+"'>"+i.source+"</span></td>"+
      "<td style='color:var(--slate-600)'>"+i.unit+"</td>"+
      "<td style='font-family:monospace;font-size:0.78rem;color:var(--slate-700)'>"+i.formula+"</td>"+
      "<td><span class='badge badge-neutral'>"+i.transform+"</span></td>";
    tbody.appendChild(tr);
  });
}
function filterCatalog(c){
  document.querySelectorAll("[id^=btn-cat-]").forEach(b=>b.classList.remove("active"));
  const el=document.getElementById("btn-cat-"+c); if(el)el.classList.add("active");
  renderCatalog(c);
}

function renderLoadings(){
  const tbody=document.getElementById("pca-loadings-body");
  tbody.innerHTML="";
  DATA.loadings.forEach(r=>{
    let h="<td style='font-weight:700;font-family:monospace'>"+r.feature+"</td>";
    for(let i=1;i<=8;i++){
      const v=r["PC"+i]||0;
      let c="loading-neutral";
      if(v>=0.3)c="loading-pos-high";else if(v>=0.1)c="loading-pos-med";
      else if(v<=-0.3)c="loading-neg-high";else if(v<=-0.1)c="loading-neg-med";
      h+="<td class='loading-cell "+c+"'>"+(v>=0?"+":"")+v.toFixed(4)+"</td>";
    }
    const tr=document.createElement("tr");tr.innerHTML=h;tbody.appendChild(tr);
  });
}

function renderCovTable(){}
function renderGavTable(){}

const svgNS="http://www.w3.org/2000/svg";
const gEl=document.createElementNS(svgNS,"g");
const layerOn={metro:false,mb:false,bici:false};
function toggleLayer(k,on){
  layerOn[k]=on;
  const g=document.getElementById("layer-"+k);
  if(g)g.style.display=on?"":"none";
}
function buildLayers(){
  const svg=document.getElementById("map-svg");
  svg.setAttribute("viewBox","0 0 "+W+" "+VH);
  svg.innerHTML="";
  svg.appendChild(gEl);
  gEl.innerHTML="";
  // contorno ciudad
  DATA.boundary.forEach(d=>{
    const p=document.createElementNS(svgNS,"path");
    p.setAttribute("d",d);
    p.setAttribute("fill","#eef2f7");
    p.setAttribute("stroke","#94a3b8");
    p.setAttribute("stroke-width","0.8");p.setAttribute("vector-effect","non-scaling-stroke");
    p.setAttribute("transform",mapTransform());
    gEl.appendChild(p);
  });
  // capas de transporte y ciclovías (activables)
  const mkPath=(d,color,w,dash,op)=>{
    const p=document.createElementNS(svgNS,"path");
    p.setAttribute("d",d);p.setAttribute("fill","none");
    p.setAttribute("stroke",color);p.setAttribute("stroke-width",w);
    p.setAttribute("stroke-linecap","round");p.setAttribute("stroke-linejoin","round");
    if(dash)p.setAttribute("stroke-dasharray",dash);
    if(op)p.setAttribute("stroke-opacity",op);
    p.setAttribute("vector-effect","non-scaling-stroke");
    p.setAttribute("transform",mapTransform());
    return p;
  };
  const mkLayer=(k)=>{
    const g=document.createElementNS(svgNS,"g");
    g.setAttribute("id","layer-"+k);
    g.style.display=layerOn[k]?"":"none";
    gEl.appendChild(g);return g;
  };
  const gb=mkLayer("bici");
  gb.appendChild(mkPath(DATA.transit.bici.d,"#16a34a",1.6,null,0.85));
  const gm=mkLayer("metro");
  DATA.transit.metro.forEach(l=>{
    const p=mkPath(l.d,l.c,3,null,0.95);
    const t=document.createElementNS(svgNS,"title");t.textContent="Metro "+l.n;p.appendChild(t);
    gm.appendChild(p);
  });
  const gx=mkLayer("mb");
  DATA.transit.mb.forEach(l=>{
    const p=mkPath(l.d,l.c,3,"7 4",0.95);
    const t=document.createElementNS(svgNS,"title");t.textContent="Metrobús "+l.n;p.appendChild(t);
    gx.appendChild(p);
  });
  // estaciones
  DATA.stations.forEach(s=>{
    const c=document.createElementNS(svgNS,"circle");
    c.setAttribute("cx",X(s.lon));c.setAttribute("cy",Yc(s.lat));
    c.setAttribute("r",s.g?4.6:2.4);
    c.setAttribute("fill",s.g?"#d97706":"#94a3b8");
    c.setAttribute("fill-opacity",s.g?0.95:0.5);
    gEl.appendChild(c);
  });
  // sitios del portafolio activo (halo blanco para resaltar)
  (DATA.ports[curM][curB]||[]).forEach(s=>{
    const halo=document.createElementNS(svgNS,"circle");
    halo.setAttribute("cx",X(s.lon));halo.setAttribute("cy",Yc(s.lat));
    halo.setAttribute("r",10.5);
    halo.setAttribute("fill","#fff");
    halo.setAttribute("fill-opacity","0.55");
    gEl.appendChild(halo);
    const c=document.createElementNS(svgNS,"circle");
    c.setAttribute("cx",X(s.lon));c.setAttribute("cy",Yc(s.lat));
    c.setAttribute("r",7);
    c.setAttribute("fill",MOTOR_COLOR[curM]);
    c.setAttribute("stroke","#fff");
    c.setAttribute("stroke-width","2");
    const t=document.createElementNS(svgNS,"title");
    t.textContent=s.id+" · "+s.mun+" · +"+fmt(s.pop)+" hab.";
    c.appendChild(t);
    gEl.appendChild(c);
  });
}
function renderPortfolio(){
  const rows=DATA.ports[curM][curB]||[];
  const tb=document.getElementById("portfolio-table-body");
  tb.innerHTML="";
  rows.forEach(s=>{
    const tr=document.createElement("tr");
    tr.innerHTML="<td class='font-mono'>"+s.o+"</td><td class='font-mono'>"+s.id+"</td>"+
      "<td>"+s.mun+"</td><td class='font-mono' style='font-size:0.75rem'>"+s.ageb+"</td>"+
      "<td style='font-weight:600'>+"+fmt(s.pop)+"</td><td>"+fmt(s.dist)+" m</td>";
    tb.appendChild(tr);
  });
  const m=DATA.cov.find(r=>r.motor===curM&&r.b===curB);
  if(m){
    document.getElementById("kpi-pop").textContent=m.pop_s+" hab.";
    document.getElementById("kpi-agebs").textContent=m.agebs+" AGEBs";
    document.getElementById("kpi-esc").textContent=m.esc.toFixed(2)+" años";
    document.getElementById("kpi-dist").textContent=m.dist+" m";
  }
  document.getElementById("resumen").textContent=
    MOTOR_NAME[curM]+" · B = "+curB+": "+rows.length+" sitios nuevos (portafolio oficial publicado).";
  document.getElementById("legend-st").textContent="Estaciones vigentes ("+DATA.stations.length+")";
  document.getElementById("legend-g").textContent="Grupo de alta actividad ("+DATA.stations.filter(s=>s.g).length+")";
  const nd=document.getElementById("legend-new-dot");
  if(nd)nd.style.background=MOTOR_COLOR[curM];
  document.getElementById("legend-new").textContent="Sitios nuevos ("+MOTOR_NAME[curM]+")";
}

function setStrategy(m){
  curM=m;
  ["m1","m2","m3"].forEach(k=>document.getElementById("btn-"+k).classList.toggle("active",k===m));
  buildLayers();renderPortfolio();
}
function setBudget(b){
  curB=b;
  [15,30,50].forEach(k=>document.getElementById("btn-b"+k).classList.toggle("active",k===b));
  buildLayers();renderPortfolio();
}

// pestañas de motores
document.querySelectorAll("[data-motor]").forEach(t=>{
  t.addEventListener("click",()=>{
    document.querySelectorAll("[data-motor]").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".pane").forEach(x=>x.classList.remove("on"));
    t.classList.add("active");
    document.getElementById("pane-"+t.dataset.motor).classList.add("on");
  });
});

document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("n-metro").textContent=DATA.transit.metro.length;
  document.getElementById("n-mb").textContent=DATA.transit.mb.length;
  document.getElementById("n-bici").textContent=fmt(DATA.transit.bici.km);
  renderCatalog("all");renderLoadings();renderCovTable();renderGavTable();
  buildLayers();
  const h=/[#&?]b=(\d+)/.exec(location.hash+location.search);
  if(h&&[15,30,50].includes(+h[1]))setBudget(+h[1]);else renderPortfolio();
});
""" + ("""
function _pilotoTotal(){
  var n=parseInt(document.getElementById("piloto-n").value)||0;
  var u=parseFloat(document.getElementById("piloto-u").value)||0;
  var t=document.getElementById("piloto-total");
  if(t)t.textContent="$"+(n*u).toLocaleString("en-US")+" MXN";
}
["piloto-n","piloto-u"].forEach(function(i){
  var e=document.getElementById(i);
  if(e)e.addEventListener("input",_pilotoTotal);
});
""" if v2 else "") + """</script>
</body>
</html>""")
    return "\n".join(H)
