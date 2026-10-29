"""Presentación de diapositivas 16:9 autocontenida (variante slides).

Escenario fijo de 1920x1080 escalado por CSS transform al viewport, sin
scroll de documento ni de diapositiva. Reutiliza de build_dashboard_html
las fuentes embebidas, la paleta, el scatter SVG, el QR del repositorio y los
datos geograficos del simulador. Toda cifra sale de D/JSON, como en v2.
"""
import json
import math
import re
from pathlib import Path

import build_dashboard_html as bd

miles = bd.miles

SLIDES_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; overflow: hidden; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      background: #0b1220; color: var(--slate-900);
      -webkit-font-smoothing: antialiased; }
    #letterbox { position: fixed; inset: 0; background: #0b1220; }
    #stage {
      position: absolute; left: 50%; top: 50%; width: 1920px; height: 1080px;
      transform-origin: center center; background: var(--bg-canvas); }
    .slide {
      position: absolute; inset: 0; padding: 50px 72px;
      display: none; flex-direction: column; gap: 20px;
      background: var(--bg-canvas); overflow: hidden; }
    .slide.cur { display: flex; }
    @media (prefers-reduced-motion: no-preference) {
      .slide { transition: opacity .22s ease; opacity: 0; }
      .slide.cur { opacity: 1; }
    }
    .shead h2 { font-size: 52px; font-weight: 800; letter-spacing: -0.02em;
      line-height: 1.08; color: var(--slate-900); }
    .shead .sec-chip { font-size: 20px; font-weight: 700; color: var(--slate-400);
      text-transform: uppercase; letter-spacing: .08em; margin-bottom: 6px; }
    .cols { display: flex; gap: 40px; flex: 1; min-height: 0;
      align-items: center; }
    .figcol { display: flex; flex-direction: column; min-width: 0;
      justify-content: center; }
    .bandrow { display: grid; gap: 18px; width: 100%;
      align-items: stretch; }
    .bandrow .cifra { font-size: 86px; }
    .figcol figure { flex: 1; min-height: 0; display: flex;
      flex-direction: column; }
    .figcol img { width: 100%; max-height: 820px; object-fit: contain;
      border-radius: var(--radius-md); border: 1px solid var(--slate-200);
      background: #fff; }
    .txtcol { display: flex; flex-direction: column; gap: 18px;
      justify-content: center; min-height: 0; min-width: 0; }
    .bl { list-style: none; display: flex; flex-direction: column; gap: 18px; }
    .bl li { font-size: 36px; line-height: 1.38; color: var(--slate-700);
      padding-left: 36px; position: relative; }
    .bl li::before { content: ""; position: absolute; left: 0; top: .45em;
      width: 14px; height: 14px; border-radius: 3px; background: var(--primary); }
    .bl li b, .lead b { color: var(--slate-900); }
    .lead { font-size: 36px; line-height: 1.45; color: var(--slate-700); }
    .small { font-size: 24px; color: var(--slate-500); line-height: 1.5; }
    .bignum { font-size: 64px; font-weight: 800; color: var(--primary);
      line-height: 1.05; }
    .bignum span { display: block; font-size: 24px; font-weight: 600;
      color: var(--slate-500); margin-top: 6px; }
    .cifra { font-size: 112px; font-weight: 800; color: var(--primary);
      line-height: 1.02; }
    .cifra small { display: block; font-size: 26px; font-weight: 600;
      color: var(--slate-500); margin-top: 8px; }
    .kgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .card { padding: 26px 30px; display: flex; flex-direction: column;
      justify-content: center; }
    .card h3 { font-size: 40px; font-weight: 700; margin-bottom: 10px; }
    .card p, .card li { font-size: 32px; line-height: 1.48;
      color: var(--slate-700); }
    .chips { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip { font-size: 22px; font-weight: 600; padding: 7px 16px;
      border-radius: 999px; background: var(--slate-100);
      color: var(--slate-700); border: 1px solid var(--slate-200); }
    .chip.mono { font-family: 'JetBrains Mono', monospace; font-size: 22px; }
    table.data-table { font-size: 26px; }
    .data-table th { padding: 12px 16px; font-size: 26px; }
    .data-table td { padding: 12px 16px; font-size: 26px; }
    table.loadings td { padding: 2px 6px; font-size: 18px;
      text-align: center; min-width: 78px; }
    table.loadings td:first-child { font-size: 20px; font-weight: 700;
      text-align: left; }
    .bigtable td { font-size: 28px; padding: 18px 16px; }
    .bigtable .badge { font-size: 24px; }
    .vertfill { flex: 1; display: flex; flex-direction: column;
      justify-content: center; min-height: 0; }
    .eq-tiles { display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 12px; margin-top: 14px; text-align: left; }
    .eq-tile { background: rgba(255,255,255,.7); border: 1px solid var(--slate-200);
      border-radius: var(--radius-sm); padding: 10px 14px; }
    .eq-tile b { display: block; font-size: 26px; color: var(--slate-900);
      font-family: "Cambria Math","STIX Two Math",Georgia,serif;
      font-style: italic; margin-bottom: 3px; }
    .eq-tile span { font-size: 19px; color: var(--slate-600);
      line-height: 1.3; font-family: 'Plus Jakarta Sans', sans-serif; }
    figcaption { font-size: 22px; color: var(--slate-500); margin-top: 10px;
      line-height: 1.4; }
    figcaption .fnum { font-weight: 800; color: var(--primary);
      margin-right: 6px; }
    .callout-box { font-size: 32px; padding: 22px 26px; }
    .eq-box { font-size: 30px; }
    .eq { font-size: 60px; }
    .eq-legend { font-size: 26px; margin-top: 14px; }
    #hud { position: fixed; left: 0; right: 0; bottom: 0; z-index: 50;
      display: flex; align-items: center; justify-content: center;
      gap: 14px; padding: 10px 18px;
      color: #cbd5e1; font-size: 13px; font-family: 'JetBrains Mono', monospace;
      pointer-events: none; opacity: 0; transition: opacity .3s ease; }
    #hud.on { opacity: 1; }
    #hud.on .hbtn { pointer-events: auto; }
    #hud .hbtn { pointer-events: none; cursor: pointer; background: #1e293b;
      border: 1px solid #334155; color: #cbd5e1; border-radius: 8px;
      padding: 5px 12px; font: inherit; }
    #hud .hbtn:hover { background: #334155; }
    #prog { position: fixed; top: 0; left: 0; height: 4px; width: 0;
      background: var(--accent-gold); z-index: 60; transition: width .2s; }
    #sec-ind { margin-right: auto; opacity: .8; }
    #counter { position: fixed; right: 18px; bottom: 8px; z-index: 50;
      color: #94a3b8; font-size: 13px; font-family: 'JetBrains Mono', monospace;
      opacity: .8; pointer-events: none; }
    #idx { position: fixed; inset: 0; z-index: 80; background: rgba(11,18,32,.94);
      display: none; overflow-y: auto; padding: 40px 8vw; }
    #idx.on { display: block; }
    #idx h2 { color: #e2e8f0; font-size: 26px; margin-bottom: 18px; }
    #idx .ig { margin-bottom: 14px; }
    #idx .ig h3 { color: var(--accent-gold); font-size: 15px;
      text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
    #idx a { display: inline-block; color: #cbd5e1; text-decoration: none;
      font-size: 15px; padding: 5px 10px; margin: 2px; border-radius: 6px;
      border: 1px solid #334155; }
    #idx a:hover { background: #1e293b; color: #fff; }
    #idx a .n { color: #64748b; margin-right: 6px; font-size: 12px; }
    .edge { position: fixed; top: 0; bottom: 44px; width: 8vw; z-index: 40;
      cursor: pointer; }
    #edge-l { left: 0; } #edge-r { right: 0; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
    .sim-map { border-radius: var(--radius-md); border: 1px solid var(--slate-200);
      background: var(--slate-50); }
    .tab-btn { font-size: 22px; padding: 10px 22px; }
    .btn, .btn-segmented { font-size: 22px; padding: 10px 24px; }
    #portfolio-table-body td, #portfolio-table-body ~ * { }
    .sim-tbl th, .sim-tbl td { font-size: 21px !important; padding: 8px 10px !important;
      white-space: nowrap; }
    .data-table .badge { font-size: 22px !important; padding: 5px 14px !important; }
    .data-table td small, .data-table td .small { font-size: 22px !important; }
    .cost-input { width: 170px; font-size: 28px; height: 52px; }
    @page { size: 1920px 1080px; margin: 0; }
    @media print {
      html, body { height: auto; overflow: visible; background: #fff; }
      #letterbox { position: static; }
      #stage { position: static; transform: none !important;
        width: auto; height: auto; background: #fff; }
      .slide { position: relative; display: flex !important;
        width: 1920px; height: 1080px; overflow: hidden;
        page-break-after: always; opacity: 1 !important;
        transition: none !important; }
      #hud, #idx, .edge, #prog, #counter { display: none !important; }
      .btn, .nav-pill, .tab-btn, .btn-segmented { display: none !important; }
      .pane { display: block !important; }
      figure, .glass-panel { page-break-inside: avoid; }
      .cost-input { border: none; padding: 0; }
      svg.scatter-svg { min-width: 0; }
      .scatter-wrap { overflow: visible; }
    }
"""


def _fig_img(fig_b64, name, num, caption, style="", img_style=""):
    return (f'<figure style="{style}"><img src="data:image/png;base64,'
            f'{fig_b64[name]}" alt="{caption}" style="{img_style}">'
            f'<figcaption><span class="fnum">Figura {num}.</span>'
            f'{caption}</figcaption></figure>')


def _eq_block(pnorm_s):
    return (
        '<div class="eq-box" role="math" aria-label="máximo sobre S '
        'subconjunto de C con cardinal B, de w por Pob de S entre Pob '
        'estrella sub B, más uno menos w por un B-ésimo por la suma sobre '
        'j en S de uno entre uno más h sub j">'
        '<div class="eq">'
        '<span class="eq-max">max'
        '<span class="eq-sub"><var>S</var> ⊆ <var>C</var>, '
        '|<var>S</var>| = <var>B</var></span></span>'
        '<span>[</span><var>w</var> · '
        '<span class="eq-frac"><span>Pob(<var>S</var>)</span>'
        '<span>Pob*<sub><var>B</var></sub></span></span>'
        ' + (1 − <var>w</var>) · '
        '<span class="eq-frac"><span>1</span><span><var>B</var></span></span>'
        ' · <span class="eq-sum">'
        '<span style="font-size:1.5em;line-height:1">Σ</span>'
        '<span class="eq-sub"><var>j</var> ∈ <var>S</var></span></span>'
        '<span class="eq-frac"><span>1</span>'
        '<span>1 + <var>h</var><sub><var>j</var></sub></span></span>'
        '<span>]</span></div>'
        '<div class="eq-tiles">'
        '<div class="eq-tile"><b>S</b><span>portafolio de B sitios'
        '</span></div>'
        '<div class="eq-tile"><b>C</b><span>candidatos factibles '
        '(enlace ≤ 500 m, separación ≥ 300 m, crecimiento contiguo)'
        '</span></div>'
        '<div class="eq-tile"><b>Pob(S)</b><span>población nueva por la '
        'unión de capturas de 500 m en celdas de 200 m, sin doble conteo'
        '</span></div>'
        '<div class="eq-tile"><b>Pob*<sub>B</sub></b><span>suma de las B '
        f'mayores coberturas individuales ({pnorm_s} hab. a B = 30)'
        '</span></div>'
        '<div class="eq-tile"><b>h<sub>j</sub></b><span>saltos a la '
        'estación Golden más cercana en el grafo</span></div>'
        '<div class="eq-tile"><b>w = 0.5</b><span>coeficiente de '
        'ponderación, con normalización de variables</span></div>'
        '</div></div>')


def build_slides(D, fig_b64):
    """Devuelve la presentación de diapositivas como un solo HTML."""
    sc = D["v2_scatter"]
    bt2 = {r["subject"]: r for r in D["v2_m2_backtest"]}
    reg = D["reg"]
    reg_g = {r["model"]: r for r in D["v2_reg_groupkfold"]}
    ofi = D["ofi"]
    cons3 = D['cons']['30']['selected_by_3']
    cons2 = D['cons']['30']['selected_by_2plus']
    ws = sc["w_sweep"]
    n_rand = sc["n_random"]
    esc_uni = sc["universe_esc"]
    cov = []
    for (motor, b), m in sorted(ofi.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        cov.append({"motor": motor, "b": b, "pop_s": miles(m["new_pop"]),
                    "agebs": int(m["n_agebs"]),
                    "pct": round(m["new_pop_share"] * 100, 2),
                    "esc": round(m["mean_grado_escolar_prom_selected"], 2),
                    "dist": int(round(m["mean_dist_to_network_m"]))})

    geo_ports = bd._portfolios()
    stations = bd._stations()
    boundary, bbounds = bd._boundary()
    transit = bd._transit_layers(bbounds)
    catalog = bd._catalog(D["feature_contract"])
    loadings = bd._loadings()

    S = []

    def slide(sec, inner):
        S.append(f'<section class="slide" data-sec="{sec}">{inner}</section>')

    def head(t):
        return f'<div class="shead"><div class="sec-chip">{t[0]}</div><h2>{t[1]}</h2></div>'

    def bl(items):
        return '<ul class="bl">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>"

    def figside(sec, t, fig_html, txt_html, fw=58):
        inner = (head((sec, t)) + '<div class="cols">'
                 + f'<div class="figcol" style="flex:0 0 {fw}%">{fig_html}</div>'
                 + f'<div class="txtcol" style="flex:1">{txt_html}</div></div>')
        slide(sec, inner)

    def cifra(v, lab=""):
        lab_html = f"<small>{lab}</small>" if lab else ""
        return f'<div class="cifra">{v}{lab_html}</div>'

    BAND_FIGS = {
        "e02/e02_01_poblacion_sin_estacion.png",
        "e02/e02_02_distancia_a_la_red.png",
        "e02/e02_03_concentracion_lorenz.png",
        "e02/e02_04_moran_cuadrantes.png",
        "e02/e02_05_espaciamiento_golden.png",
        "c8/c8_06_jaccard_sitios_agebs.png",
        "c8/c8_07_mapas_consenso.png",
        "c8/c8_08_equidad.png",
        "c8/c8_03_radar_presupuestos.png",
        "c8/c8_04_heatmap_metricas.png"}

    def figband(sec, t, name, num, caption, bullets,
                num_val=None, num_lab=""):
        tiles = []
        if num_val is not None:
            tiles.append(
                '<div class="glass-panel" style="padding:16px 24px;'
                'display:flex;align-items:center;min-width:0">'
                + cifra(num_val, num_lab) + "</div>")
        for b in bullets:
            tiles.append(
                '<div class="glass-panel" style="padding:14px 20px;'
                'font-size:28px;line-height:1.38;color:var(--slate-700);'
                f'display:flex;align-items:center;min-width:0"><div>{b}</div></div>')
        inner = (
            head((sec, t))
            + '<div class="vertfill" style="align-items:center;gap:16px">'
            + '<figure style="margin:0;width:100%;max-width:1500px">'
            + f'<img src="data:image/png;base64,{fig_b64[name]}" '
            f'alt="{caption}" style="width:100%;max-height:540px;'
            'object-fit:contain;border-radius:var(--radius-md);'
            'border:1px solid var(--slate-200);background:#fff">'
            f'<figcaption><span class="fnum">Figura {num}.</span>'
            f'{caption}</figcaption></figure>'
            + f'<div class="bandrow" style="grid-template-columns:'
              f'repeat({len(tiles)},minmax(0,1fr))">{"".join(tiles)}</div>'
            + "</div>")
        slide(sec, inner)

    def fig_slide(sec, t, name, num, caption, bullets, extra="", fw=66,
                  num_val=None, num_lab=""):
        if name in BAND_FIGS:
            figband(sec, t, name, num, caption, bullets,
                    num_val, num_lab)
            return
        txt = ((cifra(num_val, num_lab) if num_val is not None else "")
               + bl(bullets) + extra)
        figside(sec, t, _fig_img(fig_b64, name, num, caption), txt, fw)

    def kpi(v, lab, color=""):
        st = f' style="color:{color}"' if color else ""
        return f'<div class="bignum"{st}>{v}<span>{lab}</span></div>'

    def card(t, body, accent=""):
        top = f"border-top:5px solid {accent};" if accent else ""
        return (f'<div class="glass-panel card" style="{top}">'
                f'<h3>{t}</h3>{body}</div>')

    # ------------------------------------------------------------- portada
    slide("Portada", f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:30px;">
  <span class="badge badge-primary" style="font-size:22px;padding:8px 18px;width:max-content;">Caso de negocio</span>
  <h1 style="font-size:76px;font-weight:800;letter-spacing:-0.03em;line-height:1.05;max-width:1500px;">
    Expansión justa de EcoBici mediante <span style="color:var(--primary)">tres motores analíticos</span> auditados bajo un mismo contrato</h1>
  <p class="lead" style="max-width:1400px;">Similitud estadística, modelo predictivo y optimización prescriptiva sobre grafos. La comparación es descriptiva: no se declara un ganador agregado.</p>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:14px;">
    <div class="glass-panel card">{kpi(miles(D['pop_sin']), "residentes en AGEBs sin estación interna", "#dc2626")}</div>
    <div class="glass-panel card">{kpi(miles(D['agebs_sin']), f"de {miles(D['total_agebs'])} AGEBs urbanas sin estación")}</div>
    <div class="glass-panel card">{kpi(miles(ofi[('m3',30)]['new_pop']), "cobertura M3 a B = 30 (hab. nuevos)", "var(--primary)")}</div>
    <div class="glass-panel card">{kpi(cons3, "sitios de consenso triple", "var(--accent-gold)")}</div>
  </div>
  <div class="chips"><span class="chip">✓ {miles(D['trips_ok'])} viajes auditados</span><span class="chip">Gini {D['gini_est']:.4f}</span><span class="chip">Ward + buffer {D['buffer_m']:.0f} m</span></div>
</div>""")

    # ------------------------------------------------------------- Contexto
    slide("Contexto",
          head(("Contexto", "El sistema y la decisión de expansión"))
          + '<div style="flex:1;display:flex;flex-direction:column;'
          'justify-content:center;gap:26px">'
          + '<div style="display:grid;grid-template-columns:repeat(3,1fr);'
          'gap:20px">'
          + f'<div class="glass-panel card">{kpi(miles(D["stations"]), "estaciones físicas")}</div>'
          + f'<div class="glass-panel card">{kpi(miles(D["trips_ok"]), f"viajes aceptados en {D[chr(121)+chr(101)+chr(97)+chr(114)]}")}</div>'
          + f'<div class="glass-panel card">{kpi(miles(D["trips_q"]), "viajes en cuarentena", "#dc2626")}</div>'
          + '</div>'
          + '<div class="glass-panel card">'
          + bl(["<b>Dónde expandir la red</b> cubriendo más población sin "
                "replicar sesgos históricos",
                "Tres métodos independientes bajo <b>un mismo contrato</b> "
                "de despliegue",
                "Arnés de validación espacial con separación certificada"])
          + '</div></div>')

    fig_slide("Contexto", "La brecha cubre la parte mayoritaria del territorio",
              "e02/e02_01_poblacion_sin_estacion.png", 1,
              "Población residente en AGEBs sin estación interna.",
              [f"Solo <b>{miles(D['agebs_con'])}</b> AGEBs albergan estación",
               f"<b>{miles(D['agebs_sin'])}</b> AGEBs, con <b>{miles(D['pop_sin'])}</b> residentes, no contienen ninguna (Figura 1)"],
              num_val=miles(D['pop_sin']), num_lab="residentes sin estación")

    fig_slide("Contexto", "La red pasa junto a población que no captura",
              "e02/e02_02_distancia_a_la_red.png", 2,
              "Distancia del centroide de cada AGEB sin estación a la red.",
              [f"Mediana <b>{D['median_km']:.1f} km</b>, media <b>{D['mean_km']:.1f} km</b> del centroide a la estación más cercana",
               f"<b>{D['dentro400']} AGEBs</b> sin estación están a menos de 400 m de una (Figura 2)"],
              num_val=f"{D['median_km']:.1f} km", num_lab="mediana a la red")

    fig_slide("Contexto", "Oferta y actividad muy concentradas",
              "e02/e02_03_concentracion_lorenz.png", 3,
              "Curva de Lorenz de estaciones y actividad entre AGEBs.",
              [f"Gini de estaciones <b>{D['gini_est']:.4f}</b> y de actividad <b>{D['gini_act']:.4f}</b>",
               "La concentración territorial es el punto de partida del problema (Figura 3)"],
              num_val=f"{D['gini_est']:.4f}", num_lab="Gini de estaciones")

    fig_slide("Contexto", "La concentración tiene estructura espacial",
              "e02/e02_04_moran_cuadrantes.png", 4,
              "Cuadrantes del I de Moran local: núcleo alta-alta y bolsas bajas.",
              [f"I de Moran global <b>{D['moran_i']:.4f}</b> (p ≤ 0.001, calculado por permutaciones; sensibilidad k = 4, 8, 12)",
               "Núcleo alta-alta con bolsas contiguas de baja actividad (Figura 4)"],
              num_val=f"{D['moran_i']:.4f}", num_lab="I de Moran global")

    # ------------------------------------------------- Pregunta e hipótesis
    slide("Pregunta e hipótesis",
          head(("Pregunta e hipótesis", "Una pregunta, una hipótesis general"))
          + '<div class="two-col" style="flex:1">'
          + card("Pregunta de investigación",
                 '<p class="lead">¿Puede un enfoque de ciencia de datos diseñar una expansión justa y conectada sin replicar el sesgo histórico?</p>',
                 "var(--primary)")
          + card("Hipótesis general",
                 '<p class="lead">A igual presupuesto, un diseño que optimiza directamente la población nueva cubierta bajo crecimiento contiguo desde la red cubre más población nueva que uno basado solo en la similitud con las zonas históricamente exitosas, sin desviarse hacia zonas de mayor escolaridad que el azar conectado.</p>',
                 "var(--accent-blue)")
          + "</div>")

    def hspec(tag, enun, crit):
        return (f'<div class="glass-panel card" style="padding:28px 32px">'
                f'<div style="display:flex;gap:10px;align-items:center;margin-bottom:12px">'
                f'<span class="badge badge-neutral" style="font-size:24px;padding:6px 16px">{tag}</span></div>'
                f'<p style="font-size:34px;color:var(--slate-800);line-height:1.4">{enun}</p>'
                f'<p style="font-size:30px;color:var(--slate-500);margin-top:10px"><b>Criterio:</b> {crit}</p></div>')
    slide("Pregunta e hipótesis",
          head(("Pregunta e hipótesis", "Cuatro hipótesis específicas"))
          + '<div class="two-col" style="flex:1;align-content:center">'
          + hspec("H1 · Concentración",
                  "La oferta y la actividad de EcoBici están concentradas en pocas AGEBs y agrupadas en el espacio.",
                  "Gini > 0.9 e I de Moran > 0 con p ≤ 0.001.")
          + hspec("H2 · Sesgo de similitud",
                  "El puntaje de similitud del Motor 1 se asocia con el nivel socioeconómico y desplaza su portafolio hacia mayor escolaridad que el azar conectado.",
                  f"Spearman > 0.5 y escolaridad en percentil ≥ 95 de {n_rand} portafolios aleatorios conectados.")
          + hspec("H3 · Cobertura",
                  "A igual presupuesto, el Motor 3 cubre más población nueva que el Motor 1.",
                  "Mayor cobertura en B = 15, 30 y 50.")
          + hspec("H4 · Equidad sin desvío",
                  "El portafolio del Motor 3 no se ubica por encima del azar conectado en escolaridad.",
                  "Escolaridad por debajo del percentil 95 de la nube.")
          + "</div>")

    slide("Pregunta e hipótesis",
          head(("Pregunta e hipótesis", "Principios de diseño"))
          + '<div class="two-col" style="flex:1;grid-template-columns:1fr 1fr 1fr">'
          + card("Principio 1 · Cero fuga de datos",
                 f"<p>Variables derivadas de los viajes vetadas por circularidad: el flujo de rotación alcanzó Spearman <b>{D['turnover_spearman']:.3f}</b> con el objetivo.</p>")
          + card("Principio 2 · Demanda honesta",
                 f"<p>Las <b>{miles(D['agebs_sin'])}</b> AGEBs sin estación se trataron como no etiquetadas, no como demanda cero: entrenar contra eso aprendería el mapa de cobertura, no el de demanda.</p>",
                 "var(--accent-blue)")
          + card("Principio 3 · Tensión declarada",
                 "<p>Similitud con zonas exitosas empuja hacia mayor escolaridad; cobertura poblacional empuja en sentido contrario. Documentada, sin imponer resolución única.</p>",
                 "var(--accent-gold)")
          + "</div>")

    # ------------------------------------------------- Datos y validación
    slide("Datos y validación",
          head(("Datos y validación", "Datos y tratamiento"))
          + '<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">'
          + '<div class="chips"><span class="chip mono">' + miles(D['trips_in']) + ' registros crudos</span>'
          + '<span class="chip mono" style="color:var(--primary)">→ ' + miles(D['trips_ok']) + ' aceptados</span>'
          + '<span class="chip mono" style="color:#dc2626">' + miles(D['trips_q']) + ' cuarentena</span></div></div>'
          + '<div class="two-col" style="flex:1;grid-template-columns:1fr 1fr 1fr">'
          + card(f"Censo {D['census_year']}",
                 f"<p>Población y atributos sociodemográficos por AGEB; soporte territorial fijo del análisis.</p>")
          + card(f"DENUE {D['denue_year']}",
                 f"<p><b>{miles(D['denue_n'])}</b> establecimientos como proxy retrospectivo de actividad económica.</p>",
                 "var(--accent-blue)")
          + card(f"GTFS {D['gtfs_year']}",
                 f"<p><b>{miles(D['gtfs_stops'])}</b> paradas aceptadas; <b>{D['heavy_stops']}</b> de Metro y Metrobús elegibles.</p>",
                 "var(--accent-gold)")
          + "</div>")

    SRC_LABEL = {"censo": "Censo 2020", "denue": "DENUE", "gtfs": "GTFS"}

    def src_group(src):
        s = src.lower()
        for k, v in SRC_LABEL.items():
            if k in s:
                return v
        return "Infraestructura ciclista"

    groups = {}
    for f in catalog:
        groups.setdefault(src_group(f["source"]), []).append(f["name"])
    gchips = "".join(
        f'<div class="glass-panel card" style="padding:18px 22px">'
        f'<h3>{g}</h3><div class="chips">'
        + "".join(f'<span class="chip mono">{n}</span>' for n in names)
        + '</div></div>' for g, names in groups.items())
    slide("Datos y validación",
          head(("Datos y validación", "Contrato de 18 variables"))
          + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;flex:1;align-content:start">'
          + gchips + "</div>"
          + '<p class="small">Ninguna variable deriva de los viajes ni del objetivo a predecir; el contrato fija numerador, denominador, fuente y transformación.</p>')

    slide("Datos y validación",
          head(("Datos y validación", "Espacio factorial ortogonal (PCA)"))
          + '<div class="cols">'
          + '<div class="figcol" style="flex:0 0 62%;justify-content:center">'
          + '<div class="glass-panel" style="padding:12px">'
          + '<table class="data-table loadings" style="font-size:18px;width:100%">'
          + '<thead><tr><th>Variable</th>' + "".join(f"<th>PC{i}</th>" for i in range(1, 9)) + '</tr></thead>'
          + '<tbody id="pca-loadings-body"></tbody></table></div>'
          + '<figcaption style="margin-top:8px">Matriz de cargas: verdes, cargas positivas fuertes; rojas, negativas.</figcaption></div>'
          + '<div class="txtcol" style="flex:1">'
          + bl([f"18 variables → <b>{D['pca_comp']} componentes</b> ({D['pca_var']*100:.2f} % de varianza)",
                f"Umbral del 80 % fijado <b>antes de evaluar</b>; con 0.70 y 0.90 la Precisión@10 del Motor 1 se mantuvo en {D['v2_m1_sens_p10']:.2f}",
                "El problema de unidad areal modificable se mitiga —sin resolverse— midiendo cobertura sobre celdas de 200 m con zonas de captura de 500 m"])
          + "</div></div>")

    fig_slide("Datos y validación", "Grupo de referencia de alta actividad",
              "e02/e02_05_espaciamiento_golden.png", 5,
              "Espaciamiento entre estaciones Golden y la red completa.",
              [f"<b>{D['golden_n']}</b> estaciones en <b>{D['golden_agebs']}</b> AGEBs (percentil 85; umbral {D['p85']:.1f} viajes/día)",
               f"Espaciamiento mediano <b>{D['golden_med']:.0f} m</b> (Figura 5); referencia de éxito para los motores 1 y 3"],
              num_val=D['golden_n'], num_lab="estaciones Golden")

    fig_slide("Datos y validación", "Arnés de validación espacial",
              "n01_pares_colindantes.png", 6,
              "Pares colindantes prueba–entrenamiento antes y después del buffer.",
              [f"<b>{D['n_blocks']}</b> bloques Ward con adyacencia, <b>{D['n_folds']}</b> pliegues, buffer de {D['buffer_m']:.0f} m, universo de <b>{D['eval_med']}</b> AGEBs",
               f"Pares colindantes {D['folds_before']} → {D['folds_after']}; distancia mínima retenida <b>{D['min_dist']:.1f} m</b> (Figura 6)",
               "Certifica adyacencia y buffer; no descarta autocorrelación a mayores distancias"],
              num_val=f"{D['min_dist']:.1f} m", num_lab="distancia mínima retenida")

    # -------------------------------------------------------- Los motores
    slide("Los tres motores",
          head(("Los tres motores", "Arquitectura paralela desacoplada"))
          + '<div class="two-col" style="flex:1;grid-template-columns:1fr 1fr 1fr">'
          + card("Motor 1 · Similitud",
                 "<p>No supervisado: puntúa sitios por parecido con el perfil de zonas exitosas en el espacio factorial.</p>",
                 "var(--accent-blue)")
          + card("Motor 2 · Predictivo",
                 "<p>Supervisado: predice actividad por estación para ordenar candidatos; se despliega por parsimonia.</p>",
                 "var(--accent-purple)")
          + card("Motor 3 · Prescriptivo",
                 "<p>Diseño: maximiza cobertura + afinidad sobre un grafo de enlaces factibles.</p>",
                 "var(--primary)")
          + "</div>"
          + '<p class="lead" style="text-align:center">Mismas reglas y mismo contrato de despliegue; <b>ninguno lee las salidas de otro</b>.</p>')

    v = D["v_lw"]
    fig_slide("Los tres motores", "Motor 1: similitud con compuerta de dominio",
              "n02_m1_compuerta.png", 7,
              "Cobertura de decisión de la compuerta y correlaciones del score.",
              [f"Coseno al centroide Golden + compuerta Mahalanobis (corte cuantil <b>0.9973</b>)",
               f"Ledoit-Wolf: condición <b>{D['cond_emp'][0]:.1f}–{D['cond_emp'][1]:.1f}</b> → <b>{D['cond_lw'][0]:.2f}–{D['cond_lw'][1]:.2f}</b>; cobertura de decisión <b>{D['v_emp']['decision_coverage']:.3f}</b> → <b>{v['decision_coverage']:.3f}</b>, NDCG@10 {v['ndcg@10']:.3f} (Figura 7)",
               f"Sesgo declarado: Spearman <b>{D['bias']['grado_escolar_prom']['spearman_cos']:.2f}</b> escolaridad, <b>{D['bias']['pct_viviendas_auto']['spearman_cos']:.2f}</b> automóvil"],
              num_val=f"{v['decision_coverage']:.3f}", num_lab="cobertura de decisión Ledoit-Wolf")

    m1rows = "".join(
        f"<tr><td>{n}</td><td class='font-mono'>{r['precision@10']:.2f}</td>"
        f"<td class='font-mono'>{r['ndcg@10']:.3f}</td>"
        f"<td class='font-mono'>{r['decision_coverage']:.3f}</td></tr>"
        for n, r in [("Coseno + compuerta Ledoit-Wolf", v),
                     ("Coseno + compuerta empírica", D["v_emp"]),
                     ("Coseno sin compuerta", D["v_cos"]),
                     ("Heurística cercanía transporte pesado", D["v_metro"]),
                     ("Control aleatorio", D["v_rand"])])
    slide("Los tres motores",
          head(("Los tres motores", "Motor 1: desempeño de ranking (esquema espacial)"))
          + '<div class="vertfill"><div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table"><thead><tr><th>Variante</th><th>P@10</th><th>NDCG@10</th><th>Cobertura decisión</th></tr></thead><tbody>'
          + m1rows + '</tbody></table></div>'
          + '<p class="small">El techo por análogos —densidad histórica de planeación, no demanda— no superó a una densidad constante mediana en MAE y se retiró del despliegue.</p></div>')

    rf_ndcg = bt2["random_forest"]["ndcg_at_10"]
    rand_ndcg = bt2["control_aleatorio"]["ndcg_at_10"]
    fig_slide("Los tres motores", "Motor 2: ordenar candidatos, no predecir niveles",
              "n03_m2_rmse.png", 8,
              "RMSE medio por modelo en el esquema espacial.",
              [f"Bosque aleatorio: Spearman <b>{reg['random_forest']['spearman']:.3f}</b>, NDCG@10 <b>{rf_ndcg:.3f}</b> (control aleatorio: {rand_ndcg:.3f}), R² {reg['random_forest']['r2']:.3f}",
               f"Sin geografía el Spearman sube a <b>{reg_g['random_forest']['spearman']:.3f}</b>: el optimismo de la validación no espacial",
               f"RMSE: {reg['constante']['rmse']:.4f} constante · {reg['ridge']['rmse']:.4f} Ridge · {reg['random_forest']['rmse']:.4f} bosque · {reg['ft_transformer']['rmse']:.4f} FT (Figura 8)",
               "La diferencia de error es menor a la variación entre semillas; se despliega el bosque por estabilidad y simplicidad"],
              num_val=f"{reg['random_forest']['spearman']:.3f}", num_lab="Spearman espacial (bosque aleatorio)")

    def _f3(v):
        return "—" if v is None else f"{v:.3f}"
    m2rows = "".join(
        f"<tr><td>{n}</td><td class='font-mono'>{h}</td>"
        f"<td class='font-mono'>{r['rmse']:.4f}</td>"
        f"<td class='font-mono'>{_f3(r['r2'])}</td>"
        f"<td class='font-mono'>{_f3(r['spearman'])}</td></tr>"
        for n, h, r in [("Constante", "mediana por pliegue", reg["constante"]),
                        ("Ridge", "RidgeCV, logspace(−3,3,13), CV 5", reg["ridge"]),
                        ("Bosque aleatorio", "500 árboles, min_leaf 5, max_features 0.5", reg["random_forest"]),
                        ("FT-Transformer", "d_token 32, 2 capas, 4 cabezas, ff 64, dropout 0.1, 5 semillas", reg["ft_transformer"])])
    slide("Los tres motores",
          head(("Los tres motores", "Motor 2: parsimonia dictada a priori"))
          + '<div class="vertfill"><div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table"><thead><tr><th>Modelo</th><th>Hiperparámetros</th><th>RMSE</th><th>R²</th><th>Spearman</th></tr></thead><tbody>'
          + m2rows + '</tbody></table></div>'
          + f'<div class="callout-box"><b>Dictamen preespecificado.</b> El Transformer sale del despliegue: su diferencia de RMSE frente a Ridge (+{abs(reg["ft_transformer"]["rmse"]-reg["ridge"]["rmse"]):.4f}) es {abs(D["dic"]["condition_c_improvement"])/D["dic"]["condition_c_seed_std_mean"]:.3f} veces la variación entre semillas ({D["dic"]["condition_c_seed_std_mean"]:.4f}); el R² espacial máximo es {max(r["r2"] for r in reg.values()):.3f}: el valor del modelo está en el orden de los candidatos, no en la predicción del nivel.</div></div>')

    g = D["graph"]
    slide("Los tres motores",
          head(("Los tres motores", "Motor 3: optimización prescriptiva sobre grafos"))
          + '<div style="display:flex;flex-direction:column;gap:18px;flex:1;justify-content:center">'
          + _eq_block(miles(sc["p_norm"]))
          + '<div class="two-col" style="grid-template-columns:1fr 1fr">'
          + card("El grafo de factibilidad",
                 f"<p>Malla de sitios de {D['site_grid']:.0f} m, aristas de enlace ≤ {D['link_m']:.0f} m, separación ≥ {D['spacing_m']:.0f} m, crecimiento contiguo desde la red: <b>{miles(g['n_graph_nodes'])}</b> nodos, <b>{miles(g['n_graph_edges'])}</b> aristas, <b>{miles(g['n_sites'])}</b> sitios.</p>")
          + card("Matiz honesto",
                 f"<p>La afinidad solo modifica el portafolio con w ≤ 0.25; con w ≥ 0.5 coincide con maximizar solo cobertura (Jaccard {ws['1.0']['jaccard_vs_w05']:.1f}). La cercanía a Golden está optimizada por construcción.</p>",
                 "var(--accent-gold)")
          + "</div></div>")

    fig_slide("Los tres motores", "Motor 3: Greedy frente a algoritmo genético",
              "n06_m3_objetivo.png", 9,
              "Función objetivo por configuración: Greedy vs mejor corrida del GA.",
              ["En las <b>7 configuraciones</b> el Greedy iguala o supera a la mejor corrida del GA",
               "En w = 0.25 y 0.75 la diferencia cae dentro de la variación entre semillas (Figura 9)",
               "La garantía (1−1/e) submodular no aplica formalmente bajo contigüidad y espaciamiento"])

    gav_t = "".join(
        f"<tr><td class='font-mono'>{b}</td>"
        f"<td class='font-mono' style='font-weight:700;color:var(--primary)'>{miles(D['greedy_runs'][b]['new_pop'])}</td>"
        f"<td class='font-mono'>{miles(D['ga_best_by_b'][b]['new_pop'])}</td></tr>"
        for b in (15, 30, 50))
    slide("Los tres motores",
          head(("Los tres motores", "Motor 3: cobertura y tiempo de ejecución"))
          + '<div class="cols">'
          + '<div class="figcol" style="flex:0 0 68%;display:flex;flex-direction:row;gap:18px;min-height:0">'
          + '<div style="flex:1;min-width:0;display:flex">' + _fig_img(fig_b64, "n04_m3_poblacion.png", 10, "Población nueva por presupuesto: Greedy vs mejor semilla del GA.", style="flex:1;min-height:0", img_style="max-height:640px") + '</div>'
          + '<div style="flex:1;min-width:0;display:flex">' + _fig_img(fig_b64, "n05_m3_tiempos.png", 11, "Tiempo de ejecución por configuración (escala log).", style="flex:1;min-height:0", img_style="max-height:640px") + '</div>'
          + '</div>'
          + '<div class="txtcol" style="flex:1">'
          + '<div class="table-wrap"><table class="data-table"><thead><tr><th>B</th><th>Greedy</th><th>GA mejor</th></tr></thead><tbody>'
          + gav_t + '</tbody></table></div>'
          + f'<p class="small">Una ejecución del Greedy toma <b>{D["gv_prim"]["greedy_wall_s"]:.3f} s</b> frente a <b>{D["gv_prim"]["ga_mean_wall_s_per_seed"]:.1f} s</b> por semilla del GA (3,193×; los totales del experimento no son pareados). Población en la Figura 10, tiempos en la Figura 11.</p>'
          + "</div></div>")

    # --------------------------------------------------------- Simulador
    slide("Simulador y resultados", """
<div class="shead"><div class="sec-chip">Simulador y resultados</div><h2>Simulador interactivo de portafolios</h2></div>
<div class="cols" style="align-items:stretch">
  <div class="figcol" style="flex:0 0 60%">
    <div class="glass-panel" style="padding:14px;position:relative;height:100%">
      <div style="position:absolute;top:24px;right:24px;z-index:5;background:rgba(255,255,255,.96);padding:10px 14px;border-radius:10px;border:1px solid var(--slate-200);font-size:16px;display:flex;flex-direction:column;gap:5px">
        <div style="font-weight:700">Capas</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#94a3b8;margin-right:6px"></span><span id="legend-st">Estaciones vigentes</span></div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#d97706;margin-right:6px"></span><span id="legend-g">Alta actividad</span></div>
        <div><span id="legend-new-dot" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#0284c7;margin-right:6px;border:2px solid #fff"></span><span id="legend-new">Sitios nuevos</span></div>
        <label style="cursor:pointer"><input type="checkbox" id="chk-metro" onchange="toggleLayer('metro',this.checked)"> Metro (<span id="n-metro"></span>)</label>
        <label style="cursor:pointer"><input type="checkbox" id="chk-mb" onchange="toggleLayer('mb',this.checked)"> Metrobús (<span id="n-mb"></span>)</label>
        <label style="cursor:pointer"><input type="checkbox" id="chk-bici" onchange="toggleLayer('bici',this.checked)"> Ciclovías (<span id="n-bici"></span> km)</label>
        <div style="font-size:12px;color:var(--slate-400)">Rueda: zoom · arrastre: pan · doble clic: encuadre</div>
      </div>
      <svg id="map-svg" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block" role="img" aria-label="Mapa de la ciudad con estaciones y sitios seleccionados"></svg>
    </div>
  </div>
  <div class="txtcol" style="flex:1;justify-content:flex-start;gap:14px">
    <div>
      <div class="sec-chip" style="font-size:16px">Motor</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button onclick="setStrategy('m1')" id="btn-m1" class="btn btn-segmented active">M1 · Similitud</button>
        <button onclick="setStrategy('m2')" id="btn-m2" class="btn btn-segmented">M2 · Predictivo</button>
        <button onclick="setStrategy('m3')" id="btn-m3" class="btn btn-segmented">M3 · Greedy</button>
      </div>
    </div>
    <div>
      <div class="sec-chip" style="font-size:16px">Presupuesto</div>
      <div style="display:flex;gap:8px">
        <button onclick="setBudget(15)" id="btn-b15" class="btn btn-segmented">B = 15</button>
        <button onclick="setBudget(30)" id="btn-b30" class="btn btn-segmented active">B = 30</button>
        <button onclick="setBudget(50)" id="btn-b50" class="btn btn-segmented">B = 50</button>
      </div>
    </div>
    <div class="kgrid">
      <div><div class="small">Población nueva</div><div id="kpi-pop" class="bignum" style="font-size:40px;color:var(--primary)">—</div></div>
      <div><div class="small">AGEBs</div><div id="kpi-agebs" class="bignum" style="font-size:40px">—</div></div>
      <div><div class="small">Escolaridad media</div><div id="kpi-esc" class="bignum" style="font-size:40px">—</div></div>
      <div><div class="small">Distancia a red</div><div id="kpi-dist" class="bignum" style="font-size:40px">—</div></div>
    </div>
    <div class="glass-panel" style="padding:12px;flex:1;min-height:0;display:flex;flex-direction:column">
      <div class="table-wrap" style="flex:1;min-height:0;overflow-y:auto">
        <table class="data-table sim-tbl" style="font-size:16px"><thead><tr><th>Orden</th><th>Sitio</th><th>Alcaldía</th><th>Pob.</th><th>Dist.</th></tr></thead><tbody id="portfolio-table-body"></tbody></table>
      </div>
      <div id="resumen" class="small" style="margin-top:6px"></div>
    </div>
  </div>
</div>""")

    covrows = "".join(
        f"<tr><td><span class='badge "
        f"{ {'m1':'badge-blue','m2':'badge-purple','m3':'badge-primary'}[r['motor']] }'>"
        f"{ {'m1':'M1','m2':'M2','m3':'M3'}[r['motor']] }</span></td>"
        f"<td class='font-mono'>{r['b']}</td><td class='font-mono' style='font-weight:700'>{r['pop_s']}</td>"
        f"<td class='font-mono'>{r['agebs']}</td><td class='font-mono'>{r['pct']:.2f}%</td>"
        f"<td class='font-mono'>{r['dist']} m</td><td class='font-mono'>{r['esc']:.2f}</td></tr>"
        for r in cov)
    slide("Simulador y resultados",
          head(("Simulador y resultados", "Los 9 portafolios oficiales"))
          + '<div class="vertfill"><div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table"><thead><tr><th>Motor</th><th>B</th><th>Población nueva</th><th>AGEBs</th><th>% población</th><th>Distancia a red</th><th>Escolaridad</th></tr></thead><tbody>'
          + covrows + '</tbody></table></div>'
          + '<p class="small">La población se calcula sobre celdas de 200 m cubiertas por la unión de zonas de captura de 500 m, contando cada celda una sola vez.</p></div>')

    fig_slide("Simulador y resultados", "Cobertura por motor y presupuesto",
              "c8/c8_01_cobertura_por_presupuesto.png", 12,
              "Población nueva cubierta por los portafolios oficiales.",
              [f"A B = 30: <b>{miles(ofi[('m3',30)]['new_pop'])}</b> (M3), {miles(ofi[('m2',30)]['new_pop'])} (M2), {miles(ofi[('m1',30)]['new_pop'])} (M1)",
               "El Motor 3 domina en cobertura a los tres presupuestos (Figura 12)"],
              num_val=miles(ofi[('m3',30)]['new_pop']), num_lab="hab. nuevos M3 a B = 30")

    fig_slide("Simulador y resultados", "Los motores seleccionan territorios distintos",
              "c8/c8_06_jaccard_sitios_agebs.png", 13,
              "Jaccard de sitios y AGEBs entre pares de motores.",
              [f"Jaccard de sitios a B = 30: M1–M2 <b>{D['ov30']['m1-m2']['jaccard_sites']:.3f}</b>, M1–M3 <b>{D['ov30']['m1-m3']['jaccard_sites']:.3f}</b>, M2–M3 <b>{D['ov30']['m2-m3']['jaccard_sites']:.3f}</b>",
               f"<b>{cons2}</b> sitios en ≥ 2 motores y <b>{cons3}</b> en los 3 (Figura 13; su consenso territorial en la Figura 14); divergencia descriptiva, los objetivos difieren por diseño"],
              num_val=f"{D['ov30']['m1-m3']['jaccard_sites']:.3f}",
              num_lab="Jaccard M1–M3 en sitios")

    fig_slide("Simulador y resultados", "Consenso territorial",
              "c8/c8_07_mapas_consenso.png", 14,
              "Universo evaluable y consenso territorial entre motores.",
              [f"<b>{cons2}</b> sitios elegidos por al menos dos motores y <b>{cons3}</b> por los tres (Figura 14)"],
              num_val=f"{cons2} + {cons3}", num_lab="sitios en ≥2 motores / en los 3")

    fig_slide("Simulador y resultados", "Radar de ejes fijos en B = 30",
              "c8/c8_02_radar_b30.png", 15,
              "Radar de ejes fijos por objetivo; el área no es un puntaje.",
              ["Cada eje codifica un objetivo distinto; <b>el área no es un puntaje</b> y no ordena a los motores (Figura 15)"])

    fig_slide("Simulador y resultados", "Tensión similitud–cobertura",
              "c8/c8_08_equidad.png", 19,
              "Perfil de equidad de los portafolios frente al universo.",
              [f"Escolaridad media a B = 30: <b>{ofi[('m1',30)]['mean_grado_escolar_prom_selected']:.2f}</b> (M1), {ofi[('m2',30)]['mean_grado_escolar_prom_selected']:.2f} (M2), {ofi[('m3',30)]['mean_grado_escolar_prom_selected']:.2f} (M3) frente a {esc_uni:.2f} del universo",
               "El Motor 1 premia el perfil exitoso; la menor escolaridad del Motor 3 es consecuencia observada, no objetivo programado (Figura 19)"],
              num_val=f"{ofi[('m1',30)]['mean_grado_escolar_prom_selected']:.2f}", num_lab="escolaridad media M1 (universo 12.23)")

    p_m1 = round(sc["rank"]["m1"]["share_random_esc_le"] * 100)
    figside("Simulador y resultados", "Equidad y cobertura frente al azar conectado",
            '<figure style="flex:1;min-height:0">'
            '<div class="scatter-wrap" style="height:100%">'
            + bd._scatter_svg(sc) + '</div>'
            '<figcaption><span class="fnum">Figura 20.</span>Población nueva '
            'y escolaridad media a B = 30: ' + str(n_rand) +
            ' portafolios aleatorios conectados y factibles frente a los '
            'portafolios oficiales; la línea punteada marca el universo.</figcaption></figure>',
            bl([f"Nube gris: <b>{n_rand} portafolios aleatorios conectados</b> (misma red y restricciones)",
                f"Motor 1 por encima del <b>{p_m1} %</b> de la nube en escolaridad",
                f"Motor 3 dentro de la nube en escolaridad pero con cobertura mayor que cualquiera de los {n_rand} (máx. <b>{miles(sc['cloud']['pop_max'])}</b>)",
                "La línea punteada marca el universo de candidatos (Figura 20)"]),
            fw=66)

    base_pop = sc["cloud"]["pop_mean"]

    def rx(pop):
        return f"{pop / base_pop:.2f}×"
    ref_rows = ""
    ref_data = [
        (f"Azar conectado (media de {n_rand} portafolios)", base_pop,
         sc["cloud"]["esc_mean"], None, "", False),
        ("Motor 1 · Similitud", sc["official"]["m1"]["new_pop"],
         sc["official"]["m1"]["esc"], "#7e22ce", "", False),
        ("Motor 2 · Predictivo", sc["official"]["m2"]["new_pop"],
         sc["official"]["m2"]["esc"], "#0284c7", "", False),
        ("Motor 3 (w = 0.5)", sc["official"]["m3"]["new_pop"],
         sc["official"]["m3"]["esc"], "#b45309", "", True),
        ("Solo población (Motor 3 con w = 1)", ws["1.0"]["new_pop"],
         ws["1.0"]["esc"], "#b45309",
         f"mismo conjunto de 30 sitios que w = 0.5 (Jaccard "
         f"{ws['1.0']['jaccard_vs_w05']:.1f}); heurística voraz, no un "
         "máximo demostrado", False),
        ("Solo afinidad al núcleo (Motor 3 con w = 0)", ws["0.0"]["new_pop"],
         ws["0.0"]["esc"], "#b45309", "", False)]
    for nombre, pop, esc, col, note, hl in ref_data:
        chip = (f'<span class="badge" style="background:{col}1A;color:{col};'
                f'border:1px solid {col}40">{nombre}</span>' if col else nombre)
        nota = (f'<div style="font-size:15px;color:var(--slate-500)">{note}</div>'
                if note else "")
        bg = ' style="background:#fef3c7"' if hl else ""
        ref_rows += (f"<tr{bg}><td>{chip}{nota}</td>"
                     f"<td class='font-mono' style='text-align:right'>{miles(pop)}</td>"
                     f"<td class='font-mono' style='text-align:right'>{esc:.2f}</td>"
                     f"<td class='font-mono' style='text-align:right'>{rx(pop)}</td></tr>")
    slide("Simulador y resultados",
          head(("Simulador y resultados", "Referencias simples a B = 30"))
          + '<div class="vertfill"><div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table"><thead><tr><th>Referencia</th><th style="text-align:right">Población nueva</th><th style="text-align:right">Escolaridad media</th><th style="text-align:right">Cobertura frente al azar</th></tr></thead><tbody>'
          + ref_rows + '</tbody></table></div>'
          + f'<p class="small">Azar conectado: aleatorios factibles de crecimiento contiguo (±{miles(sc["cloud"]["pop_sd"])} hab., ±{sc["cloud"]["esc_sd"]:.2f} años); ninguno alcanza al Motor 3 (máx. {miles(sc["cloud"]["pop_max"])}). Los motores superan al azar en cobertura; el sesgo de escolaridad es del Motor 1.</p></div>')

    # -------------------------------------------------------- Conclusiones
    esc_bias = D['bias']['grado_escolar_prom']['spearman_cos']
    p_m3 = round(sc["rank"]["m3"]["share_random_esc_le"] * 100)
    hyp_rows = "".join(
        f"<tr><td><span class='badge badge-neutral'>{t}</span></td>"
        f"<td>{r}</td><td><span class='badge badge-verified'>Sostenida</span></td></tr>"
        for t, r in [
            ("H1 · Concentración",
             f"Gini {D['gini_est']:.4f} / {D['gini_act']:.4f}; I = {D['moran_i']:.4f}"),
            ("H2 · Sesgo de similitud",
             f"ρ = {esc_bias:.2f}; {sc['official']['m1']['esc']:.2f} (percentil {p_m1})"),
            ("H3 · Cobertura",
             f"{miles(ofi[('m3',30)]['new_pop'])} > {miles(ofi[('m1',30)]['new_pop'])} a B = 30; también en 15 y 50"),
            ("H4 · Equidad sin desvío",
             f"{sc['official']['m3']['esc']:.2f} (percentil {p_m3}; universo {esc_uni:.2f})")])
    slide("Conclusiones",
          head(("Conclusiones", "Respuesta a las hipótesis"))
          + '<div class="vertfill">'
          + '<div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table bigtable"><thead><tr><th>Hipótesis</th><th>Resultado</th><th>Veredicto</th></tr></thead><tbody>'
          + hyp_rows + '</tbody></table></div>'
          + f'<div class="callout-box" style="margin-top:20px">La hipótesis general se sostiene en el diseño retrospectivo. La afinidad por saltos a Golden solo modifica el portafolio con w ≤ 0.25: con w ≥ 0.5 coincide con maximizar solo cobertura (Jaccard {ws["1.0"]["jaccard_vs_w05"]:.1f}); la conectividad se debe a la restricción de crecimiento contiguo, común a los tres motores.</div></div>')

    icons = "".join(
        f'<circle cx="{26 + i * 58}" cy="28" r="24" '
        f'fill="{"#b45309" if i < cons3 else "#004d40"}" stroke="#fff" stroke-width="3"/>'
        for i in range(cons2))
    mediana_red = sc["median_viajes_diarios_red"]
    n_est = sc["n_estaciones"]
    slide("Conclusiones",
          head(("Conclusiones", "Recomendación y despliegue del piloto"))
          + f'<p class="lead">Piloto sobre los <b>{cons2} sitios</b> elegidos por al menos dos motores a B = 30 (<b>{cons3}</b> por los tres y <b>{cons2 - cons3}</b> por exactamente dos), sujeto a levantamiento de campo, costos y red caminable; Motor 3 como generador de portafolio y Motor 1 como control de similitud.</p>'
          + '<div class="two-col" style="grid-template-columns:1fr 1fr;flex:1;align-items:stretch">'
          + '<div class="glass-panel card">'
          + f'<svg viewBox="0 0 {26 + cons2 * 58} 56" role="img" aria-label="{cons2} estaciones del piloto" style="display:block;width:100%;height:auto">{icons}</svg>'
          + f'<div class="chips" style="margin:12px 0"><span class="chip"><span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:#b45309;margin-right:6px"></span>{cons3} consenso triple</span><span class="chip"><span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:#004d40;margin-right:6px"></span>{cons2 - cons3} consenso doble</span></div>'
          + '<h3>Costo paramétrico</h3>'
          + '<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:26px;color:var(--slate-700)">'
          + '<label>Estaciones <input type="number" id="piloto-n" class="cost-input" value="18" min="1" step="1"></label>'
          + '<label>Costo unitario <input type="number" id="piloto-u" class="cost-input" value="450000" min="0" step="10000"></label></div>'
          + '<div id="piloto-total" style="font-size:84px;font-weight:800;color:var(--primary);margin-top:10px;line-height:1.05;white-space:nowrap">$8,100,000 MXN</div>'
          + '<p class="small">Supuesto paramétrico editable; no es una estimación de campo. Valor inicial: 450,000 MXN por estación.</p></div>'
          + card("Métrica de éxito en campo",
                 cifra(f"{mediana_red:.1f}", "viajes/día · mediana de la red")
                 + f"<p>Viajes diarios promedio por estación piloto frente a la mediana de la red ({D['year']}, {n_est} estaciones), evaluados a los <b>3 y 6 meses</b> de operación.</p>")
          + "</div>")

    sup_rows = [
        ("Captura por distancia euclidiana de 500 m",
         "Vías rápidas, ríos y pendientes alargan el trayecto real; el círculo sobreestima la población alcanzable",
         "Áreas de servicio de caminata sobre la red peatonal equivalentes a 500 m, comparadas con el círculo"),
        ("Población del Censo 2020 como población presente",
         "Cambio demográfico y urbano entre 2020 y 2025; la población flotante no está censada",
         "Conteo o encuesta de residentes y población flotante en el entorno del piloto"),
        ("Actividad existente como indicador de demanda",
         "La demanda latente de zonas sin servicio no se observa; la actividad refleja también la oferta",
         "Viajes diarios por estación del piloto frente a la mediana de la red, a 3 y 6 meses"),
        ("Retícula de candidatos cada 250 m",
         "Predios, banquetas o permisos pueden impedir instalar en el nodo exacto",
         "Levantamiento físico del sitio y ajuste a la ubicación factible más cercana"),
        ("Cobertura de población equivale a beneficio",
         "La población en la zona de captura no es necesariamente usuaria",
         "Registro de usuarios nuevos o muestreo en el área de captura"),
        ("Enlace de 500 m como continuidad de red",
         "La ruta real entre estaciones puede ser insegura o no ciclable",
         "Recorrido en bicicleta entre estaciones vecinas midiendo tiempo y seguridad percibida")]
    sup_html = "".join(
        f"<tr><td style='font-weight:600'>{a}</td><td>{b}</td><td>{c}</td></tr>"
        for a, b, c in sup_rows)
    slide("Conclusiones",
          head(("Conclusiones", "Supuestos del modelo frente a la realidad"))
          + '<div class="vertfill"><div class="glass-panel card" style="flex:0 0 auto">'
          + '<table class="data-table" style="font-size:20px"><thead><tr><th>Qué supone el modelo</th><th>Dónde falla en la realidad</th><th>Cómo se mediría en campo</th></tr></thead><tbody>'
          + sup_html + '</tbody></table></div></div>')

    slide("Conclusiones",
          head(("Conclusiones", "Límites y trabajo futuro"))
          + '<div class="two-col" style="flex:1">'
          + card("Límites de la investigación",
                 bl(["Cobertura = población en zonas de captura, no demanda observada",
                     f"Desajuste temporal: Censo {D['census_year']}, viajes {D['year']}, DENUE {D['denue_year']}",
                     "La abstención de la compuerta no implica sitios malos",
                     "Una sola ciudad; sin inferencia causal; afinidad del Motor 3 optimizada por construcción"]),
                 "#dc2626")
          + card("Trabajo futuro",
                 bl(["Costos y restricciones operativas del despliegue",
                     "Medición de demanda real tras el piloto (3 y 6 meses)",
                     "Red caminable en lugar de distancia euclidiana",
                     "Sensibilidad temporal y réplica del arnés en otras ciudades"]))
          + "</div>")

    slide("Conclusiones", f"""
{head(("Conclusiones", "Transparencia y reproducibilidad"))}
<div class="cols" style="align-items:center">
  <div style="flex:0 0 auto">
    {bd._qr_repo().replace('<svg id="qr-slot"',
        '<svg id="qr-slot" style="width:456px;height:456px;display:block"')}
    <div style="font-size:26px;color:var(--slate-600);margin-top:10px">Repositorio en GitHub con código fuente</div>
    <div style="font-size:26px;color:var(--slate-800);margin-top:4px;font-weight:600">github.com/Omarti34/Ecobicis2026</div>
  </div>
  <div class="txtcol" style="flex:1;gap:16px">
    <div class="glass-panel" style="padding:22px 26px">
      <h3 style="font-size:34px;font-weight:700;margin-bottom:8px">Reproducibilidad</h3>
      <ul style="font-size:26px;color:var(--slate-700);padding-left:26px;display:flex;flex-direction:column;gap:9px;line-height:1.4">
        <li>Cada cifra se traza a un reporte sellado con identificador de análisis y huella SHA-256.</li>
        <li>Datos crudos inmutables y contrato de datos con identificador único.</li>
        <li>Semillas fijas: los {n_rand} portafolios aleatorios de la Figura 20 se reproducen con la semilla {sc['seed']} y coinciden con el reporte del Motor 3.</li>
        <li>Simulador autocontenido: un solo archivo, sin conexión a internet.</li>
      </ul>
    </div>
    <div class="glass-panel" style="padding:22px 26px;border-top:4px solid var(--accent-gold)">
      <h3 style="font-size:34px;font-weight:700;margin-bottom:8px">Nota sobre el uso de IA generativa</h3>
      <p style="font-size:26px;color:var(--slate-700);line-height:1.45">Se emplearon modelos de lenguaje (LLMs) como asistentes para la refactorización de código —incluido el simulador y los procesos de construcción— y para la corrección de estilo del documento, validando de forma humana la lógica deductiva.</p>
    </div>
  </div>
</div>""")

    biblio = "".join(
        f"<li>{x}</li>" for x in [
            f"SEMOVI / EcoBici — Datos abiertos de viajes del sistema, {D['year']}",
            f"INEGI — Censo de Población y Vivienda, {D['census_year']}",
            f"INEGI — Marco Geoestadístico, {D['census_year']}",
            f"INEGI — Directorio Estadístico Nacional de Unidades Económicas (DENUE), {D['denue_year']}",
            f"Movilidad CDMX / operadores — Especificación GTFS, {D['gtfs_year']}"])
    slide("Conclusiones",
          head(("Conclusiones", "Bibliografía"))
          + f'<div class="vertfill"><div class="glass-panel card"><ol style="font-size:30px;color:var(--slate-700);padding-left:38px;display:flex;flex-direction:column;gap:20px;line-height:1.45">{biblio}</ol></div></div>')

    # --------------------------------------------------------------- Anexo
    fig_slide("Anexo", "Radar por presupuesto para cada motor",
              "c8/c8_03_radar_presupuestos.png", 16,
              "Radar de ejes fijos por presupuesto y motor.",
              ["Mismo criterio de ejes fijos que el radar de B = 30 (Figura 16)"])
    fig_slide("Anexo", "Matriz de métricas oficiales",
              "c8/c8_04_heatmap_metricas.png", 17,
              "Métricas oficiales por motor y presupuesto, recomputadas.",
              ["Resumen tabular de las métricas recomputadas desde los portafolios publicados (Figura 17)"])
    fig_slide("Anexo", "Estaciones seleccionadas por AGEB",
              "c8/c8_05_estaciones_por_ageb.png", 18,
              "Distribución de estaciones por AGEB en cada portafolio.",
              ["Cuántas estaciones concentra cada motor por AGEB (1, 2 o 3+) en cada portafolio oficial (Figura 18)"])

    slides_html = "\n".join(S)
    n_slides = len(S)

    # ----------------------------------------------------------- payload JS
    gav = []
    for b in (15, 30, 50):
        gr = D["greedy_runs"][b]["new_pop"]
        ga = D["ga_best_by_b"][b]["new_pop"]
        gav.append({"b": b, "greedy_s": miles(gr), "ga_s": miles(ga),
                    "dif_s": miles(gr - ga)})
    payload = {"cov": cov, "gav": gav, "ports": geo_ports,
               "stations": stations, "boundary": boundary,
               "bounds": bbounds, "transit": transit,
               "catalog": catalog, "loadings": loadings}
    payload_json = json.dumps(payload, ensure_ascii=False,
                              separators=(",", ":"))
    secs = []
    for i, s in enumerate(S):
        sec = re.search(r'data-sec="([^"]+)"', s).group(1)
        m = re.search(r"<h2>([^<]+)</h2>|<h1[^>]*>(.*?)</h1>", s, re.S)
        t = re.sub(r"<[^>]+>", " ", m.group(2) or m.group(1)) if m else sec
        t = re.sub(r"\s+", " ", t).strip()
        secs.append({"n": i + 1, "sec": sec, "t": t})

    idx_items = json.dumps(secs, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EcoBici · Presentación de diapositivas</title>
<style>
{bd._font_faces()}
{bd.CSS}
{bd.V2_CSS}
{SLIDES_CSS}
</style>
</head>
<body>
<div id="letterbox"><div id="stage">
{slides_html}
</div></div>
<div id="prog"></div>
<div id="counter"></div>
<div id="hud"><button class="hbtn" id="b-idx">Índice (G)</button><button class="hbtn" id="b-prev">←</button><button class="hbtn" id="b-next">→</button><button class="hbtn" id="b-fs">Pantalla completa (F)</button></div>
<div class="edge" id="edge-l" aria-hidden="true"></div>
<div class="edge" id="edge-r" aria-hidden="true"></div>
<div id="idx"><h2>Índice — pulsa para saltar · Esc para cerrar</h2><div id="idx-body"></div></div>
<script>
"use strict";
var slides=[].slice.call(document.querySelectorAll(".slide"));
var N=slides.length, cur=0;
var stage=document.getElementById("stage");
function fit(){{
 var s=Math.min(innerWidth/1920,innerHeight/1080);
 stage.style.transform="translate(-50%,-50%) scale("+s+")";
}}
addEventListener("resize",fit);fit();
function go(n){{
 n=Math.max(0,Math.min(N-1,n));
 slides[cur].classList.remove("cur");cur=n;
 slides[cur].classList.add("cur");
 document.getElementById("counter").textContent=(cur+1)+" / "+N;
 var si=document.getElementById("sec-ind");if(si)si.textContent=slides[cur].dataset.sec;
 document.getElementById("prog").style.width=((cur+1)/N*100)+"%";
 history.replaceState(null,"","#"+(cur+1));
}}
function isForm(t){{return t&&(t.tagName==="INPUT"||t.tagName==="SELECT"||t.tagName==="TEXTAREA"||t.isContentEditable);}}
document.addEventListener("keydown",function(e){{
 if(isForm(e.target))return;
 var k=e.key;
 if(k==="ArrowRight"||k==="ArrowDown"||k===" "||k==="PageDown"){{e.preventDefault();go(cur+1);}}
 else if(k==="ArrowLeft"||k==="ArrowUp"||k==="PageUp"){{e.preventDefault();go(cur-1);}}
 else if(k==="Home")go(0);
 else if(k==="End")go(N-1);
 else if(k==="f"||k==="F")toggleFS();
 else if(k==="g"||k==="G")idxToggle();
 else if(k==="Escape")document.getElementById("idx").classList.remove("on");
}});
function toggleFS(){{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen();}}
document.getElementById("b-fs").onclick=toggleFS;
document.getElementById("b-next").onclick=function(){{go(cur+1)}};
document.getElementById("b-prev").onclick=function(){{go(cur-1)}};
document.getElementById("b-idx").onclick=function(){{idxToggle()}};
function idxToggle(){{document.getElementById("idx").classList.toggle("on");}}
var hud=document.getElementById("hud"),hudT=null;
function hudShow(){{hud.classList.add("on");
 if(hudT)clearTimeout(hudT);
 hudT=setTimeout(function(){{hud.classList.remove("on")}},2500);}}
document.addEventListener("mousemove",hudShow);
document.addEventListener("touchstart",hudShow,{{passive:true}});
hudShow();
document.getElementById("edge-l").onclick=function(){{go(cur-1)}};
document.getElementById("edge-r").onclick=function(){{go(cur+1)}};
var tx0=0,ty0=0;
document.addEventListener("touchstart",function(e){{
 if(e.target.closest("#map-svg")||isForm(e.target))return;
 tx0=e.touches[0].clientX;ty0=e.touches[0].clientY;}},{{passive:true}});
document.addEventListener("touchend",function(e){{
 if(!tx0)return;var dx=e.changedTouches[0].clientX-tx0;var dy=e.changedTouches[0].clientY-ty0;tx0=0;
 if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy))go(cur+(dx<0?1:-1));}},{{passive:true}});
// indice
var SECS={idx_items};
(function(){{
 var body=document.getElementById("idx-body"),g="",sec="";
 SECS.forEach(function(s){{
  if(s.sec!==sec){{sec=s.sec;if(g)body.appendChild(g);
   g=document.createElement("div");g.className="ig";
   var h=document.createElement("h3");h.textContent=sec;g.appendChild(h);}}
  var a=document.createElement("a");a.href="#"+s.n;
  a.innerHTML='<span class="n">'+s.n+'</span>'+s.t;
  a.onclick=function(ev){{ev.preventDefault();go(s.n-1);document.getElementById("idx").classList.remove("on");}};
  g.appendChild(a);}});
 if(g)body.appendChild(g);}})();
// --- datos del simulador / tablas ---
const DATA={payload_json};
const MOTOR_COLOR={{m1:"#0284c7",m2:"#7e22ce",m3:"#004d40"}};
const MOTOR_NAME={{m1:"Motor 1 · Similitud",m2:"Motor 2 · Predictivo",m3:"Motor 3 · Greedy"}};
let curM="m1",curB=30;
function fmt(v){{return v.toLocaleString("en-US");}}
const _pts=DATA.stations.slice();
Object.values(DATA.ports).forEach(o=>Object.values(o).forEach(a=>a.forEach(q=>_pts.push(q))));
const _lo=_pts.map(q=>q.lon),_la=_pts.map(q=>q.lat),_pd=0.03;
const minLon=Math.min(..._lo)-_pd,maxLon=Math.max(..._lo)+_pd,
      minLat=Math.min(..._la)-_pd,maxLat=Math.max(..._la)+_pd;
const kx=0.94;
const W=1000,pad=18;
const scale=(W-2*pad)/((maxLon-minLon)*kx);
const VH=Math.round((maxLat-minLat)*scale+2*pad);
const cx0=(minLon+maxLon)/2,cy0=(minLat+maxLat)/2;
function X(lon){{return W/2+(lon-cx0)*kx*scale;}}
function Yc(lat){{return VH/2-(lat-cy0)*scale;}}
function mapTransform(){{
 return "translate("+W/2+" "+VH/2+") scale("+(scale*kx)+" "+(-scale)+") translate("+(-cx0)+" "+(-cy0)+")";}}
function renderLoadings(){{
 var tb=document.getElementById("pca-loadings-body");if(!tb)return;tb.innerHTML="";
 DATA.loadings.forEach(r=>{{
  var h="<td style='font-weight:700;font-family:monospace'>"+r.feature+"</td>";
  for(var i=1;i<=8;i++){{var v=r["PC"+i]||0,c="loading-neutral";
   if(v>=0.3)c="loading-pos-high";else if(v>=0.1)c="loading-pos-med";
   else if(v<=-0.3)c="loading-neg-high";else if(v<=-0.1)c="loading-neg-med";
   h+="<td class='loading-cell "+c+"'>"+(v>=0?"+":"")+v.toFixed(2)+"</td>";}}
  var tr=document.createElement("tr");tr.innerHTML=h;tb.appendChild(tr);}});}}
const svgNS="http://www.w3.org/2000/svg";
const gEl=document.createElementNS(svgNS,"g");
const layerOn={{metro:false,mb:false,bici:false}};
function toggleLayer(k,on){{layerOn[k]=on;var g=document.getElementById("layer-"+k);if(g)g.style.display=on?"":"none";}}
function buildLayers(){{
 var svg=document.getElementById("map-svg");if(!svg)return;
 svg.setAttribute("viewBox",vbz.x+" "+vbz.y+" "+vbz.w+" "+vbz.h);
 svg.innerHTML="";svg.appendChild(gEl);gEl.innerHTML="";
 DATA.boundary.forEach(d=>{{var p=document.createElementNS(svgNS,"path");
  p.setAttribute("d",d);p.setAttribute("fill","#eef2f7");p.setAttribute("stroke","#94a3b8");
  p.setAttribute("stroke-width","0.8");p.setAttribute("vector-effect","non-scaling-stroke");
  p.setAttribute("transform",mapTransform());gEl.appendChild(p);}});
 var mkP=(d,c,w,dash,op)=>{{var p=document.createElementNS(svgNS,"path");
  p.setAttribute("d",d);p.setAttribute("fill","none");p.setAttribute("stroke",c);
  p.setAttribute("stroke-width",w);p.setAttribute("stroke-linecap","round");
  if(dash)p.setAttribute("stroke-dasharray",dash);if(op)p.setAttribute("stroke-opacity",op);
  p.setAttribute("vector-effect","non-scaling-stroke");p.setAttribute("transform",mapTransform());return p;}};
 var mkL=k=>{{var g=document.createElementNS(svgNS,"g");g.id="layer-"+k;
  g.style.display=layerOn[k]?"":"none";gEl.appendChild(g);return g;}};
 var gb=mkL("bici");gb.appendChild(mkP(DATA.transit.bici.d,"#16a34a",1.6,null,0.85));
 var gm=mkL("metro");DATA.transit.metro.forEach(l=>{{var p=mkP(l.d,l.c,3,null,0.95);
  var t=document.createElementNS(svgNS,"title");t.textContent="Metro "+l.n;p.appendChild(t);gm.appendChild(p);}});
 var gx=mkL("mb");DATA.transit.mb.forEach(l=>{{var p=mkP(l.d,l.c,3,"7 4",0.95);
  var t=document.createElementNS(svgNS,"title");t.textContent="Metrobús "+l.n;p.appendChild(t);gx.appendChild(p);}});
 DATA.stations.forEach(s=>{{var c=document.createElementNS(svgNS,"circle");
  c.setAttribute("cx",X(s.lon));c.setAttribute("cy",Yc(s.lat));
  c.setAttribute("r",s.g?4.6:2.4);c.setAttribute("fill",s.g?"#d97706":"#94a3b8");
  c.setAttribute("fill-opacity",s.g?0.95:0.5);gEl.appendChild(c);}});
 (DATA.ports[curM][curB]||[]).forEach(s=>{{
  var h2=document.createElementNS(svgNS,"circle");
  h2.setAttribute("cx",X(s.lon));h2.setAttribute("cy",Yc(s.lat));
  h2.setAttribute("r",10.5);h2.setAttribute("fill","#fff");h2.setAttribute("fill-opacity","0.55");gEl.appendChild(h2);
  var c=document.createElementNS(svgNS,"circle");
  c.setAttribute("cx",X(s.lon));c.setAttribute("cy",Yc(s.lat));c.setAttribute("r",7);
  c.setAttribute("fill",MOTOR_COLOR[curM]);c.setAttribute("stroke","#fff");c.setAttribute("stroke-width","2");
  var t=document.createElementNS(svgNS,"title");
  t.textContent=s.id+" · "+s.mun+" · +"+fmt(s.pop)+" hab.";c.appendChild(t);gEl.appendChild(c);}});
}}
function renderPortfolio(){{
 var rows=DATA.ports[curM][curB]||[];var tb=document.getElementById("portfolio-table-body");if(!tb)return;
 tb.innerHTML="";rows.forEach(s=>{{var tr=document.createElement("tr");
  tr.innerHTML="<td class='font-mono'>"+s.o+"</td><td class='font-mono'>"+s.id+"</td>"+
   "<td>"+s.mun+"</td><td style='font-weight:600'>+"+fmt(s.pop)+"</td><td>"+fmt(s.dist)+" m</td>";
  tb.appendChild(tr);}});
 var m=DATA.cov.find(r=>r.motor===curM&&r.b===curB);
 if(m){{document.getElementById("kpi-pop").textContent=m.pop_s+" hab.";
  document.getElementById("kpi-agebs").textContent=m.agebs+" AGEBs";
  document.getElementById("kpi-esc").textContent=m.esc.toFixed(2)+" años";
  document.getElementById("kpi-dist").textContent=m.dist+" m";}}
 document.getElementById("resumen").textContent=MOTOR_NAME[curM]+" · B = "+curB+": "+rows.length+" sitios nuevos (portafolio oficial).";
 document.getElementById("legend-st").textContent="Estaciones vigentes ("+DATA.stations.length+")";
 document.getElementById("legend-g").textContent="Alta actividad ("+DATA.stations.filter(s=>s.g).length+")";
 document.getElementById("legend-new-dot").style.background=MOTOR_COLOR[curM];
 document.getElementById("legend-new").textContent="Sitios nuevos ("+MOTOR_NAME[curM]+")";
}}
function setStrategy(m){{curM=m;["m1","m2","m3"].forEach(k=>document.getElementById("btn-"+k).classList.toggle("active",k===m));buildLayers();renderPortfolio();}}
function setBudget(b){{curB=b;[15,30,50].forEach(k=>document.getElementById("btn-b"+k).classList.toggle("active",k===b));buildLayers();renderPortfolio();}}
// pan/zoom del mapa en coordenadas viewBox
var vbz={{x:0,y:0,w:W,h:VH}};
function mapInit(){{
 var svg=document.getElementById("map-svg");if(!svg)return;
 svg.setAttribute("viewBox","0 0 "+W+" "+VH);
 svg.addEventListener("wheel",function(e){{e.preventDefault();
  var r=svg.getBoundingClientRect();
  var mx=vbz.x+(e.clientX-r.left)/r.width*vbz.w,my=vbz.y+(e.clientY-r.top)/r.height*vbz.h;
  var f=e.deltaY<0?0.82:1.22;var nw=Math.min(W*4,Math.max(W/10,vbz.w*f));
  var k=nw/vbz.w;vbz.x=mx-(mx-vbz.x)*k;vbz.y=my-(my-vbz.y)*k;
  vbz.w=nw;vbz.h=vbz.w*VH/W;
  svg.setAttribute("viewBox",vbz.x+" "+vbz.y+" "+vbz.w+" "+vbz.h);}},{{passive:false}});
 var drag=null;
 svg.addEventListener("pointerdown",function(e){{drag={{x:e.clientX,y:e.clientY,bx:vbz.x,by:vbz.y}};svg.setPointerCapture(e.pointerId);}});
 svg.addEventListener("pointermove",function(e){{if(!drag)return;
  var r=svg.getBoundingClientRect();
  vbz.x=drag.bx-(e.clientX-drag.x)/r.width*vbz.w;
  vbz.y=drag.by-(e.clientY-drag.y)/r.height*vbz.h;
  svg.setAttribute("viewBox",vbz.x+" "+vbz.y+" "+vbz.w+" "+vbz.h);}});
 svg.addEventListener("pointerup",function(){{drag=null;}});
 svg.addEventListener("dblclick",function(){{vbz={{x:0,y:0,w:W,h:VH}};svg.setAttribute("viewBox","0 0 "+W+" "+VH);}});
}}
// costo paramétrico del piloto
function _pilotoTotal(){{
 var n=parseInt(document.getElementById("piloto-n").value)||0;
 var u=parseFloat(document.getElementById("piloto-u").value)||0;
 var t=document.getElementById("piloto-total");
 if(t){{t.textContent="$"+(n*u).toLocaleString("en-US")+" MXN";
 t.style.fontSize=t.textContent.length>15?"60px":"84px";}}}}
["piloto-n","piloto-u"].forEach(function(i){{var e=document.getElementById(i);if(e)e.addEventListener("input",_pilotoTotal);}});
document.addEventListener("DOMContentLoaded",function(){{
 document.getElementById("n-metro").textContent=DATA.transit.metro.length;
 document.getElementById("n-mb").textContent=DATA.transit.mb.length;
 document.getElementById("n-bici").textContent=fmt(DATA.transit.bici.km);
 renderLoadings();mapInit();buildLayers();renderPortfolio();
 var h=parseInt((location.hash||"").replace("#",""));
 go(h>=1&&h<=N?h-1:0);}});
</script>
</body>
</html>"""
