"""Receta del cuaderno 08: comparación de portafolios publicados.

Narrativa formal en español; ningún número se incrusta: todo se lee de
result/report. El 08 compara los portafolios YA PUBLICADOS y verificados
de los motores 05, 06 y 07 —jamás los reejecuta— sobre el contrato de
despliegue común del cuaderno 04.
"""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 08. Evaluación comparativa de portafolios

    Los motores 05, 06 y 07 resuelven **la misma tarea de despliegue**
    —un portafolio de $B$ sitios candidatos bajo reglas de red
    idénticas— con métodos distintos: similitud de entornos (Motor 1),
    predicción supervisada del bosque aleatorio (Motor 2) y afinidad
    determinista de saltos al núcleo dorado (Motor 3). Este cuaderno
    compara sus **portafolios ya publicados**: no reejecuta ningún
    motor, lee los artefactos verificados byte a byte y reconstruye las
    métricas del contrato del cuaderno 04 para comprobar que lo
    publicado es reproducible.

    La comparación es **descriptiva**: no se declara un ganador global.
    Los ejes del radar están en escalas fijas $[0,1]$ con semántica
    propia —su área **no** es un puntaje— y codifican objetivos en
    tensión (cobertura, equidad, similitud).
    """)
    code("""
    import sys
    from pathlib import Path
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from matplotlib.collections import LineCollection
    from IPython.display import display, Markdown, JSON

    BASE = Path.cwd().resolve()
    PROJECT = next(p for p in [BASE, *BASE.parents] if (p / "V3/data/raw").is_dir())
    V3_DIR = PROJECT / "V3"
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from V3.src.c8_analysis import CONFIG, RADAR_AXES, load_inputs, analyze
    from V3.src.c8_publication import stage_results
    from V3.src import fe04_deployment as dep

    GREEN, GRAY, BLUE, RED, GOLD = "#004731", "#546E7A", "#0D47A1", "#B03A2E", "#B8860B"
    MOTOR_COLOR = {"m1": GREEN, "m2": BLUE, "m3": GOLD}
    MOTOR_LABEL = {"m1": "Motor 1 · similitud",
                   "m2": "Motor 2 · bosque aleatorio",
                   "m3": "Motor 3 · afinidad de saltos"}
    plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 11})
    data = load_inputs(V3_DIR)
    result = analyze(data, verbose=True)
    report = result["report"]
    display(pd.DataFrame([{
        "contract_id": report["contract_id"],
        "analysis_version": report["schema_version"],
        "shared_validation_analysis_id":
            report["shared_validation_analysis_id"],
        "motor1": report["upstream"]["motor1_analysis_id"],
        "motor2": report["upstream"]["motor2_analysis_id"],
        "motor3": report["upstream"]["motor3_analysis_id"],
        "never_reruns_motors": report["scope"]["never_reruns_motors"],
    }]))
    """)
    md("""
    ## 1. Chequeo de consistencia

    Antes de comparar, el cuaderno reconstruye el contexto del contrato
    —sitios, celdas, adyacencias e incidencia— y **recalcula las
    métricas** de cada portafolio publicado: deben coincidir con lo que
    cada motor reportó (tolerancia $10^{-9}$) y pasar el verificador
    independiente `is_feasible` —ya sin techos por AGEB, retirados en
    las versiones vigentes de los motores 1 y 2—. Los tres motores
    deben referenciar el **mismo** analysis_id del cuaderno 04.
    Cualquier divergencia aborta la publicación.
    """)
    code("""
    cons = report["consistency"]
    display(pd.Series({
        "portafolios_verificados": cons["n_portfolios_checked"],
        "todos_factibles": cons["all_feasible"],
        "todas_metricas_reproducidas": cons["all_metrics_reproduced"],
        "rtol": cons["rtol"],
    }, name="valor").to_frame())
    display(pd.DataFrame(cons["checked"]))
    """)
    md(r"""
    ## 2. Contexto metodológico de esta versión

    Tres notas condicionan la lectura de toda la comparación:

    - **Los motores 1 y 2 ya no usan techos por AGEB.** El techo por
      análogos reproducía la densidad histórica de planeación —no la
      demanda— y su backtest perdía contra una densidad constante; sus
      portafolios **cambiaron** respecto a la versión previa (el cambio
      de $B=30$ se muestra abajo, leído de los campos publicados por
      cada motor).
    - **El Motor 3 optimiza directamente la cercanía a Golden.** Su
      afinidad es $1/(1+\text{saltos a Golden})$: los ejes de
      proximidad a la red o a Golden que lo favorecen están **por
      construcción** —no son evidencia independiente—.
    - **El prescriptor del Motor 3 es el greedy, no el GA.** La tabla
      abajo —leída del reporte del 07— muestra $f$, brecha y tiempos de
      pared medidos de ambos métodos por peso y presupuesto.
    """)
    code("""
    ctx8 = report["method_context"]
    display(Markdown("**Remoción del techo — cambio publicado a B=30**"))
    rows = []
    for mot, lab in [("m1_techo_removido", "Motor 1"),
                     ("m2_techo_removido", "Motor 2")]:
        tr = ctx8[mot]
        if tr:
            rows.append({"motor": lab,
                         "esquema_previo": tr["previous_schema"],
                         "new_pop_previo_B30":
                             tr["previous_B30"]["new_pop"],
                         "new_pop_actual_B30":
                             tr["current_B30"]["new_pop"],
                         "delta_new_pop": tr["delta_B30_new_pop"],
                         "delta_n_agebs": tr["delta_B30_n_agebs"]})
    display(pd.DataFrame(rows))
    display(Markdown("**Motor 3 — greedy vs GA** (leído del reporte "
                     "publicado del 07)"))
    gg = pd.DataFrame(ctx8["m3_ga_vs_greedy"])
    display(gg[["weight", "budget", "greedy_f", "ga_best_f",
                "ga_mean_f", "ga_minus_greedy", "jaccard_ga_greedy",
                "greedy_wall_s", "ga_total_wall_s", "verdict"]])
    display(Markdown(
        f"**Advertencia del Motor 3.** {ctx8['m3_affinity_scope_warning']}"))
    """)
    md("""
    ## 3. Cobertura y eficiencia

    Tabla completa de métricas del contrato por motor y presupuesto, y
    curva de población nueva cubierta contra la cota submodular
    $P_{\\text{norm}}$ —la misma referencia para los tres métodos—.
    """)
    code("""
    met = result["metricas"]
    of = met.loc[met.tier.eq("oficial")]
    display(pd.DataFrame(of).T)
    display(Markdown("**Filas de sensibilidad** (no oficiales)"))
    display(pd.DataFrame(met.loc[met.tier.eq("sensibilidad")]).T)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    pnorm = of.drop_duplicates("budget").set_index("budget").p_norm
    ax.plot(pnorm.index, pnorm.values, "--", color=GRAY,
            label="P_norm (cota submodular)")
    for m, g in of.groupby("motor"):
        g = g.sort_values("budget")
        ax.plot(g.budget, g.new_pop, "-o", color=MOTOR_COLOR[m],
                label=MOTOR_LABEL[m])
    ax.set(xlabel="presupuesto B", ylabel="new_pop (hab.)",
           title="Cobertura nueva vs presupuesto — portafolios oficiales")
    ax.legend(fontsize=8); plt.tight_layout(); plt.show()
    """)
    md(r"""
    ## 4. Radar y mapa de calor

    Seis ejes en escala fija $[0,1]$: **cobertura** ($new\_pop/P_{norm}$),
    **eficiencia** ($1-$redundancia), **proximidad a la red**
    ($1-\bar d_{red}/\text{alcanzable}$), **equidad** (fracción de sitios
    en AGEBs bajo la mediana de escolaridad de todos los sitios),
    **similitud al núcleo** ($1-$fracción fuera del dominio global del
    04) y **dispersión** ($n_{AGEB}/n_{sitios}$). El área del radar
    **no es un puntaje**: los ejes codifican objetivos distintos y en
    tensión, y es un dispositivo de presentación, no una evaluación.
    **El eje de proximidad a la red del Motor 3 es favorable por
    construcción** (su afinidad son los saltos a Golden).
    """)
    code("""
    radar = result["radar"].loc[lambda r: r.tier.eq("oficial")]
    angles = np.linspace(0, 2 * np.pi, len(RADAR_AXES), endpoint=False)
    angles = np.r_[angles, angles[:1]]
    def _radar(ax, budget):
        sub = radar.loc[radar.budget.eq(budget)]
        for m, g in sub.groupby("motor"):
            vals = g.set_index("axis").reindex(RADAR_AXES)["value"]
            v = np.r_[vals.to_numpy(float), vals.to_numpy(float)[:1]]
            ax.plot(angles, v, color=MOTOR_COLOR[m],
                    label=MOTOR_LABEL[m])
            ax.fill(angles, v, color=MOTOR_COLOR[m], alpha=0.08)
        ax.set_xticks(angles[:-1]); ax.set_xticklabels(RADAR_AXES,
                                                     fontsize=7)
        ax.set_ylim(0, 1); ax.set_title(f"B={budget}")
    b_grid = sorted(radar.budget.unique())
    b_main = CONFIG["primary_budget"]
    fig, ax = plt.subplots(figsize=(6.5, 6.5),
                           subplot_kw={"polar": True})
    _radar(ax, b_main); ax.legend(fontsize=8, loc="upper right",
                                 bbox_to_anchor=(1.45, 1.1))
    plt.suptitle(f"Radar de ejes fijos — B={b_main} (oficiales)")
    plt.tight_layout(); plt.show()
    fig, axes = plt.subplots(1, len(b_grid), figsize=(5 * len(b_grid), 5),
                             subplot_kw={"polar": True})
    for ax, b in zip(np.atleast_1d(axes), b_grid):
        _radar(ax, b)
    plt.suptitle("Radar por presupuesto")
    plt.tight_layout(); plt.show()
    """)
    code("""
    cols = ["new_pop", "new_pop_share", "redundancy", "n_agebs",
            "max_hops_network", "median_hops_golden",
            "out_of_domain_04_share"]
    pivot = of.set_index(["motor", "budget"])[cols].T
    fig, ax = plt.subplots(figsize=(2 + 1.4 * len(pivot.columns), 4.5))
    im = ax.imshow(pivot.to_numpy(float), aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{m}\\nB{b}" for m, b in pivot.columns],
                       fontsize=8)
    ax.set_yticks(range(len(cols))); ax.set_yticklabels(cols, fontsize=8)
    for i in range(len(cols)):
        for j in range(len(pivot.columns)):
            v = pivot.to_numpy(float)[i, j]
            ax.text(j, i, f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}",
                    ha="center", va="center", fontsize=7,
                    color="white" if v < np.nanmax(
                        pivot.to_numpy(float)) / 2 else "black")
    ax.set_title("Métricas del contrato — valores crudos (oficiales)")
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 5. Asignación territorial: ¿cuántas estaciones por AGEB?

    La respuesta del proyecto a «¿una o tres estaciones por AGEB?» es
    **condicional al presupuesto y al método**: la tabla muestra cuántas
    AGEBs reciben 1, 2 o 3+ sitios por motor y presupuesto. Los techos
    por análogos fueron retirados de los motores 1 y 2: el número de
    estaciones por AGEB es ahora únicamente el resultado de la
    cobertura con rendimientos decrecientes.
    """)
    code("""
    display(result["asignacion"])
    asig = result["asignacion"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [f"{m}\\nB{b}" for m, b in zip(asig.motor, asig.budget)]
    bottom = np.zeros(len(asig))
    for col, color, lab in [("agebs_1", GREEN, "1 sitio"),
                            ("agebs_2", BLUE, "2 sitios"),
                            ("agebs_3plus", RED, "3+ sitios")]:
        ax.bar(labels, asig[col], bottom=bottom, color=color,
               label=lab, alpha=0.85)
        bottom += asig[col].to_numpy(float)
    ax.set(ylabel="número de AGEBs",
           title="Estaciones por AGEB — portafolios oficiales")
    ax.legend(fontsize=8); plt.tight_layout(); plt.show()
    """)
    md("""
    ## 6. Traslape y consenso

    Jaccard por parejas de motores sobre los **conjuntos de sitios** y
    sobre los **conjuntos de AGEBs** cubiertos, y sitios de consenso —
    elegidos por 2 o por los 3 motores—: evidencia de que los métodos
    convergen o divergen territorialmente.
    """)
    code("""
    ov = result["overlap"]
    display(ov)
    b_grid = sorted(ov.budget.unique())
    fig, axes = plt.subplots(len(b_grid), 2,
                             figsize=(9, 3.2 * len(b_grid)))
    for r, b in enumerate(b_grid):
        for c, kind in enumerate(["jaccard_sites", "jaccard_agebs"]):
            ax = axes[r, c] if len(b_grid) > 1 else axes[c]
            M = np.eye(3)
            motors = ["m1", "m2", "m3"]
            sub = ov.loc[ov.budget.eq(b)]
            for _, row in sub.iterrows():
                i, j = motors.index(row.motor_a), motors.index(row.motor_b)
                M[i, j] = M[j, i] = row[kind]
            im = ax.imshow(M, vmin=0, vmax=1, cmap="YlGnBu")
            for i in range(3):
                for j in range(3):
                    ax.text(j, i, f"{M[i, j]:.2f}", ha="center",
                            va="center", fontsize=8)
            ax.set_xticks(range(3)); ax.set_yticks(range(3))
            ax.set_xticklabels(motors); ax.set_yticklabels(motors)
            ax.set_title(f"{kind} — B={b}")
    plt.tight_layout(); plt.show()
    display(Markdown("**Sitios de consenso por presupuesto**"))
    display(pd.DataFrame(report["consensus_counts"]).T)
    """)
    code("""
    universe = result["universe04"]
    universe = features_plot = result["features"].to_crs(
        CONFIG["metric_crs"])
    sites = result["sites"]
    stations = result["stations"]
    b_main = CONFIG["primary_budget"]
    catalog = {f"{e['motor']}|{e['variant']}|{e['budget']}": e["sel"]
               for e in result["catalog"]}
    station_xy = {str(s): (g.x, g.y) for s, g in
                  zip(stations.station_id, stations.geometry)}
    site_xy = {s: (g.x, g.y) for s, g in zip(sites.site_id,
                                           sites.geometry)}
    def _attach_xy(a):
        if str(a).startswith("est:"):
            return station_xy.get(str(a)[4:])
        return site_xy.get(a)
    fig, axes = plt.subplots(1, 4, figsize=(22, 7))
    for ax, m in zip(axes[:3], ["m1", "m2", "m3"]):
        universe.plot(ax=ax, color="#F5F5F5", edgecolor="#DDDDDD",
                      linewidth=0.15)
        sites.plot(ax=ax, color="#DDDDDD", markersize=1.5, alpha=0.5)
        sel = catalog[[k for k in catalog
                       if k.startswith(f"{m}|") and
                       k.endswith(f"|{b_main}")][0]]
        segs = []
        for _, row in sel.iterrows():
            dst = _attach_xy(row.attach)
            if dst is not None:
                segs.append([(row.geometry.x, row.geometry.y), dst])
        if segs:
            ax.add_collection(LineCollection(
                segs, colors="#BBBBBB", linewidths=0.6, zorder=2))
        stations.plot(ax=ax, color=GRAY, markersize=3, alpha=0.6)
        sel.plot(ax=ax, color=MOTOR_COLOR[m], markersize=35,
                 edgecolor="black", linewidth=0.4)
        ax.set_axis_off()
        ax.set_title(f"{MOTOR_LABEL[m]} — B={b_main}")
    ax = axes[3]
    universe.plot(ax=ax, color="#F5F5F5", edgecolor="#DDDDDD",
                  linewidth=0.15)
    cons = result["consensus"]
    cons_b = cons.loc[cons.budget.eq(b_main)] if len(cons) else cons
    stations.plot(ax=ax, color=GRAY, markersize=3, alpha=0.5)
    if len(cons_b):
        cons_b.plot(ax=ax, column="n_motors", cmap="autumn",
                    markersize=40, edgecolor="black", linewidth=0.4,
                    legend=True, vmin=2, vmax=3,
                    legend_kwds={"label": "motores que lo eligen",
                                 "shrink": 0.5})
    ax.set_axis_off(); ax.set_title(f"Consenso (≥2 motores) — B={b_main}")
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 7. La tensión equidad–similitud

    El hallazgo central de la comparación es una tensión de objetivos:
    el Motor 1 selecciona sitios en AGEBs **semejantes** a la referencia
    de alta actividad —perfiles afluentes—; la cobertura poblacional
    empuja hacia la periferia densa y menos afluente. Las barras
    comparan la media de escolaridad y de hogares con auto de las AGEBs
    seleccionadas contra la media de **todos** los sitios candidatos:
    valores por encima de la línea indican sesgo hacia entornos
    afluentes; por debajo, sesgo hacia los menos afluentes.
    """)
    code("""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, col, lab in [
            (axes[0], "mean_grado_escolar_prom", "grado escolar prom."),
            (axes[1], "mean_pct_viviendas_auto", "% viviendas con auto")]:
        sel_c, all_c = f"{col}_selected", f"{col}_all_sites"
        x = np.arange(len(of))
        ax.bar(x, of[sel_c], color=[MOTOR_COLOR[m] for m in of.motor],
               alpha=0.85)
        ax.axhline(of[all_c].iloc[0], color=GRAY, linestyle="--",
                   label="media de todos los sitios")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{m}\\nB{b}" for m, b in
                            zip(of.motor, of.budget)], fontsize=8)
        ax.set_title(f"AGEBs anfitrionas: {lab}")
        ax.legend(fontsize=8)
    plt.tight_layout(); plt.show()
    display(Markdown("**Ejes equidad y similitud del radar**"))
    display(radar.loc[radar.axis.isin(["equidad", "similitud_golden"])]
            .pivot_table(index=["motor", "budget"], columns="axis",
                         values="value"))
    """)
    md("""
    ## 8. Contexto de backtest: qué puede afirmar cada motor

    Estas cifras se **leen** de los reportes publicados —no se
    recalculan— y contextualizan qué tipo de evidencia respalda cada
    puntaje: los motores 1 y 2 tienen backtests de ranking sobre AGEBs
    con servicio; el Motor 3 no —su puntaje es **afinidad estructural**,
    no un modelo de actividad, así que no admite ese protocolo—.
    """)
    code("""
    display(result["backtest"])
    """)
    md("""
    ## 9. Conclusiones condicionales y límites

    Las conclusiones de este cuaderno son **condicionales**: dependen del
    presupuesto, del objetivo que se priorice y de los supuestos del
    contrato —no existe un ganador global—.

    - Si el criterio es **cobertura nueva**, los portafolios se ordenan
      por `new_pop` a cada presupuesto, con la cota `P_norm` como
      referencia común.
    - Si el criterio es **semejanza al núcleo con servicio**, domina la
      similitud; si es **equidad territorial**, dominan los portafolios
      que bajan la escolaridad media de las AGEBs anfitrionas.
    - El consenso entre motores identifica sitios robustos al método
      elegido; el traslape bajo identifica decisiones sensibles al
      método.

    Límites compartidos: la interpolación areal de población y la
    captura de 500 m son **supuestos**, no demanda observada; no hay red
    vial, costos, factibilidad de terreno ni validación de campo; los
    tres métodos son heurísticos sin garantía de optimalidad; la
    comparación es descriptiva y el área del radar no es un puntaje.
    """)
    code("""
    display(pd.DataFrame({"pending_validation":
                          report["pending_validation"]}))
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Comparación verificada de los "
                     "portafolios publicados por los tres motores."))
    display(JSON({"c8_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
