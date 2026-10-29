"""Receta del cuaderno 05: Motor 1, baseline estadístico de similitud.

Narrativa formal en español; ningún número se incrusta: todo se lee de
result/report. El cuaderno corre el Motor 1 contra el arnés publicado
del 04 y publica el ranking territorial de candidatas como insumo
declarado del Motor 3.
"""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 05. Motor 1 — baseline estadístico de similitud del coseno

    El Motor 1 responde una pregunta deliberadamente acotada: **entre
    AGEBs que ya tienen estaciones, ¿la similitud del entorno permite
    redescubrir las de mayor actividad observada media por estación?**
    Es un baseline transparente: cada AGEB se representa en el espacio de
    atributos del cuaderno 03 y se ordena por su similitud de coseno a un
    centroide de referencia de alta actividad.

    **Lo que este motor puede decir.** Si el baseline recupera las AGEBs
    relevantes de cada pliegue, la estructura de similitud del entorno
    contiene señal útil para priorizar territorio; si no, la tesis no
    puede apoyarse en similitud ingenua.

    **Lo que no puede decir.** La similitud no es demanda: el ranking
    territorial del cierre es una **heurística de priorización**, no una
    estimación de viajes ni de demanda latente. No usa coordenadas,
    conteos de estaciones ni banderas Golden como insumo —estas últimas
    están prohibidas porque su umbral P85 se calculó con todas las
    estaciones, incluidas las de validación.

    **La tarea común.** El cuaderno 04 alimenta a los motores 1, 2 y 3
    **en paralelo**: los tres resuelven la misma tarea de despliegue
    —un portafolio de $B$ sitios bajo reglas de red idénticas— con
    métodos distintos, y ninguno lee las salidas de los otros. El
    cierre de este cuaderno aporta la respuesta del Motor 1: un
    portafolio de sitios por presupuesto, **sin cuotas por AGEB** —el
    techo por análogos se retiró tras mostrarse peor que una densidad
    constante (sección 7)—.

    **Insumos.** Todo proviene de publicaciones verificadas byte a byte:
    el contrato de atributos y el pipeline del cuaderno 03, el universo,
    las particiones, el arnés y el contrato de despliegue —sitios,
    celdas, reglas y métricas— del cuaderno 04, y el entorno de
    estaciones del cuaderno 02.
    """)
    code("""
    import sys
    from pathlib import Path
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from IPython.display import display, Markdown, JSON

    BASE = Path.cwd().resolve()
    PROJECT = next(p for p in [BASE, *BASE.parents] if (p / "V3/data/raw").is_dir())
    V3_DIR = PROJECT / "V3"
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from V3.src.m1_analysis import (
        CONFIG, VARIANTS, PRIMARY_VARIANT, load_inputs, analyze)
    from V3.src.m1_publication import stage_results

    GREEN, GRAY, BLUE, RED, GOLD = "#004731", "#546E7A", "#0D47A1", "#B03A2E", "#B8860B"
    plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 11})
    data = load_inputs(V3_DIR)
    result = analyze(data)
    report = result["report"]
    display(pd.DataFrame([{
        "contract_id": report["contract_id"],
        "analysis_version": report["schema_version"],
        "feature_analysis_id": report["upstream"]["feature_analysis_id"],
        "eda_analysis_id": report["upstream"]["eda_analysis_id"],
        "validation_analysis_id": report["upstream"]["validation_analysis_id"],
        "primary_variant": report["primary_variant"],
    }]))
    """)
    md("""
    ## 1. Construcción local por pliegue

    En cada pliegue, el motor ajusta un **pipeline fe03 nuevo**
    (contrato de atributos, imputación por mediana, escalado y PCA al
    objetivo de varianza declarado) usando **todas las AGEBs
    proyectables fuera de `fit_exclusion_ids`** —incluidas candidatas
    territoriales y cubiertas sin estación, que son filas de ajuste
    legítimas porque no tienen etiqueta—. La prueba y su buffer nunca
    entran al ajuste.

    La **referencia de alta actividad** se construye solo con
    `train_target`: las AGEBs de entrenamiento retenido con actividad
    media por estación en el cuantil superior declarado, y su centroide
    $\\mu$ en el espacio PCA **del pliegue**. El número de componentes
    `k_fold` puede variar entre pliegues porque el PCA se reajusta en
    cada uno.
    """)
    code("""
    diag = result["fold_diagnostics"]
    prim = diag.loc[diag.variant.eq(PRIMARY_VARIANT)]
    display(prim[["fold_scheme", "fold", "k_fold", "n_reference",
                 "n_over_p", "reference_threshold", "domain_threshold",
                 "n_in_domain_test", "n_test", "covariance_estimator",
                 "shrinkage", "condition_number",
                 "condition_number_empirical", "empirical_status"]])
    """)
    md(r"""
    ## 2. Coseno y compuerta de dominio

    La similitud de coseno mide **dirección, no magnitud**: dos AGEBs con
    perfil proporcional $(1,1)$ y $(10,10)$ tienen coseno 1 aunque sus
    niveles difieran por un factor de diez —la variante euclidiana, que
    sí distingue magnitudes, queda como comparador—. Una norma cero hace
    indefinido el coseno y produce abstención, no un puntaje inventado.

    La **compuerta de dominio** ajusta `fit_mahalanobis` sobre las
    coordenadas PCA de la referencia del pliegue, con umbral
    $\sqrt{\chi^2_{k_{fold}}(q)}$ y `df = k_fold`. Con referencias
    pequeñas —el cuantil de referencia retiene apenas ~15% del
    entrenamiento, y la razón $n/p \approx 3$— la covarianza muestral es
    **inestable**: autovalores pequeños cercanos a cero inflan la
    distancia en direcciones mal estimadas. Por eso la compuerta usa el
    estimador **Ledoit-Wolf**, que encoge la covarianza muestral hacia
    la diagonal escalada con un encogimiento estimado por los datos; la
    tabla reporta por pliegue el encogimiento y el número de condición
    junto al de la covarianza empírica (o el motivo de su rechazo).

    **Umbral nominal.** Con encogimiento, las distancias de la referencia
    ya no siguen exactamente una $\chi^2_{k}$: el cuantil es un corte
    nominal coherente con el arnés, no una cobertura probabilística
    exacta. Fuera de dominio significa extrapolación fuera del soporte,
    no «mala ubicación». La variante `m1_coseno_compuerta_empirica`
    conserva la compuerta empírica anterior como contraste explícito en
    el backtest.
    """)
    code("""
    g = prim.loc[prim.fold_scheme.eq(CONFIG["primary_scheme"])].copy()
    g["share_in_domain"] = g.n_in_domain_test / g.n_test
    display(g[["fold", "k_fold", "n_reference", "n_over_p",
               "domain_threshold", "shrinkage", "condition_number",
               "condition_number_empirical", "empirical_status",
               "n_in_domain_test", "n_test", "share_in_domain"]])
    display(Markdown(
        f"**Participación dentro de dominio (esquema primario):** "
        f"media {g.share_in_domain.mean():.2%}, "
        f"mínima {g.share_in_domain.min():.2%}."))
    gate = report["deployment"]["gate"]
    display(Markdown("**Compuerta de despliegue (referencia global)**"))
    display(pd.Series(gate, name="valor").to_frame())
    """)
    md("""
    ## 3. Backtest espacial contra el arnés del 04

    Todas las variantes corren sobre **ambos esquemas** del arnés. El
    esquema por AGEB es la **referencia optimista** (no aísla vecinos);
    el veredicto se lee en `fold_spatial_block` con buffer de 500 m. Los
    comparadores son deliberados: `m1_coseno_compuerta_empirica` (la
    compuerta anterior con covarianza muestral —mide si Ledoit-Wolf
    cambia `decision_coverage` y las métricas, sin afirmar mejora si no
    la hay—), `m1_coseno` sin compuerta (¿la abstención cuesta o
    protege?), `m1_euclidiana` (¿importa la magnitud?), `heur_metro`
    (heurística transparente de distancia al METRO/MB, sin ajuste) y
    `control_aleatorio` (plomería: debe rondar la tasa base).

    Las victorias pliegue a pliegue contra cada comparador se cuentan de
    forma **descriptiva** —cinco pliegues no sustentan inferencia
    estadística—. Si el primario no supera a `heur_metro` o al control
    aleatorio, el cuaderno lo dice explícitamente.
    """)
    code("""
    summ = result["backtest_summary"]
    key_metrics = ["precision@10", "recall@10", "ndcg@10",
                   "ndcg_cond@10", "precision_cond@10",
                   "decision_coverage",
                   "relevant_abstained", "n_relevant"]
    piv = (summ.loc[summ.metric.isin(key_metrics)]
           .pivot_table(index=["variant", "fold_scheme"],
                        columns="metric", values="mean"))
    display(piv[[c for c in key_metrics if c in piv.columns]])
    detail = result["backtest_detail"]
    nan_recall = detail.loc[detail["recall@10"].isna(),
                            ["variant", "fold_scheme", "fold", "n_relevant"]]
    if len(nan_recall):
        display(Markdown("**Pliegues sin relevantes** — recall `NaN` "
                         "reportado explícitamente:"))
        display(nan_recall)
    prim_scheme = CONFIG["primary_scheme"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    palette = {"m1_coseno_compuerta": GREEN,
               "m1_coseno_compuerta_empirica": "#80C080",
               "m1_coseno": BLUE, "m1_euclidiana": GOLD,
               "heur_metro": GRAY, "control_aleatorio": "#BBBBBB"}
    for ax, metric in zip(axes, ["ndcg@10", "precision@10"]):
        sub = detail.loc[detail.fold_scheme.eq(prim_scheme)]
        order = VARIANTS
        data_plot = [sub.loc[sub.variant.eq(v), metric].to_numpy()
                     for v in order]
        ax.boxplot(data_plot, labels=[v.replace("m1_", "") for v in order],
                   showfliers=False, medianprops={"color": "black"})
        rng_plot = np.random.default_rng(7)
        for i, vals in enumerate(data_plot):
            ax.scatter(rng_plot.uniform(i + 0.85, i + 1.15, len(vals)),
                       vals, s=18, alpha=0.75,
                       color=palette[order[i]], zorder=3)
        ax.set_title(f"{metric} por variante — {prim_scheme}")
        ax.tick_params(axis="x", rotation=20)
    plt.tight_layout(); plt.show()
    display(Markdown("**Victorias del primario por pliegue** "
                     "(esquema primario, descriptivo)"))
    display(result["win_counts"])
    """)
    md("""
    ## 4. Sensibilidad de la configuración

    Un factor a la vez sobre la variante y el esquema primarios:
    objetivo de varianza del PCA, cuantil de referencia y cuantil de
    dominio. La tabla reporta la media por pliegue de las métricas del
    arnés bajo cada valor alternativo.
    """)
    code("""
    sens = result["sensitivity"]
    display(sens)
    fig, ax = plt.subplots(figsize=(9, 4))
    for param, sub in sens.groupby("parameter"):
        ax.scatter([f"{param}={v}" for v in sub.value],
                   sub["mean_ndcg@10"], s=45, label=param)
    base = detail.loc[detail.variant.eq(PRIMARY_VARIANT)
                    & detail.fold_scheme.eq(prim_scheme), "ndcg@10"].mean()
    ax.axhline(base, color=RED, ls="--", label="base declarada")
    ax.set(ylabel="media NDCG@10", title="Sensibilidad un-factor del primario")
    ax.tick_params(axis="x", rotation=30)
    ax.legend(fontsize=8)
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 5. Ranking territorial de despliegue

    Para el despliegue el espacio es **exactamente el publicado por el
    cuaderno 03**: el pipeline se ajusta sobre todas las AGEBs
    proyectables y el cuaderno verifica que su transformación reproduce
    los scores publicados y coincide con el pipeline cargado por el
    cargador verificado —si difiriera, el cuaderno fallaría—.

    La referencia global son las AGEBs evaluables con actividad media en
    el cuantil superior declarado; la tabla cruzada contra el Golden-03
    muestra cuánta coincidencia hay entre ambas nociones de «alta
    actividad». La compuerta m1 usa la covarianza de **esa** referencia,
    no la Golden. `attractiveness = max(cos, 0)` dentro de dominio y 0
    fuera: es el insumo declarado del Motor 3, no una probabilidad.
    """)
    code("""
    dep = report["deployment"]
    display(pd.Series({k: v for k, v in dep.items()
                       if not isinstance(v, (dict, list))},
                      name="valor").to_frame())
    display(Markdown("**Referencia m1 vs Golden-03** "
                     "(filas: pertenencia a la referencia m1)"))
    display(pd.DataFrame(dep["reference_vs_golden03"]))
    display(Markdown("**Compuerta m1 vs estatus publicado del 04**"))
    display(pd.DataFrame(dep["m1_vs_04_status"]))
    ranking = result["ranking"]
    universe = data["frames"]["universe"]
    stations = data["frames"]["station_env"]
    top50 = result["top50"]
    fig, ax = plt.subplots(figsize=(9, 7))
    universe.plot(ax=ax, color="#F2F2F2", edgecolor="#DDDDDD",
                  linewidth=0.15)
    ranking.loc[ranking.domain_status_m1.eq("out_of_domain")].plot(
        ax=ax, color="#D8D8D8", edgecolor="none")
    in_dom = ranking.loc[ranking.domain_status_m1.eq("in_domain")]
    in_dom.loc[~in_dom.index.isin(top50.index)].plot(
        ax=ax, color=BLUE, alpha=0.45, edgecolor="none")
    top50.plot(ax=ax, color=GREEN, edgecolor="none")
    stations.plot(ax=ax, color=RED, markersize=1.5, alpha=0.5)
    ax.legend(handles=[
        Patch(facecolor=GREEN, label="top-50 m1"),
        Patch(facecolor=BLUE, alpha=0.45, label="dentro de dominio m1"),
        Patch(facecolor="#D8D8D8", label="fuera de dominio m1"),
        Patch(facecolor=RED, label="estaciones existentes")],
        loc="upper left", bbox_to_anchor=(1.02, 1))
    ax.set_axis_off(); ax.set_title("Ranking territorial del Motor 1")
    plt.tight_layout(); plt.show()
    cols = ["cvegeo", "nom_mun", "cos_score", "mahalanobis_m1",
            "domain_status_m1", "domain_status_04", "rank_m1",
            "rank_sin_compuerta", "attractiveness", "dist_red_m",
            "frontera"]
    display(top50.head(20)[cols])
    """)
    md("""
    ## 6. Sesgo y conectividad

    La similitud del entorno puede estar **replicando contextos
    afluentes**: las correlaciones de rango entre el puntaje de coseno y
    los atributos socioeconómicos se reportan abajo, junto a la media de
    esos atributos en el top-50 dentro de dominio frente a todas las
    candidatas. La renta no se observa directamente.

    La conectividad es **descriptor, no componente del puntaje**:
    `dist_red_m` mide la distancia del polígono al punto de estación más
    cercano y `frontera` marca candidatas dentro del umbral declarado.
    Una parte del top-50 puede quedar lejos de la red existente —es el
    motivo por el que el Motor 3 optimiza colocación y conectividad de
    forma explícita en lugar de heredar el orden del baseline—.
    """)
    code("""
    display(result["bias"])
    conn = report["connectivity"]
    display(pd.Series(conn, name="valor").to_frame())
    frontier = int(top50.frontera.sum())
    display(Markdown(
        f"**Frontera de red.** {frontier} de las "
        f"{len(top50)} candidatas del top-50 dentro de dominio están a "
        f"{int(conn['frontier_m'])} m o menos de una estación existente; "
        f"mediana de distancia a la red: top-50 "
        f"{conn['median_dist_red_top50']:.0f} m vs. todas las candidatas "
        f"{conn['median_dist_red_all']:.0f} m."))
    """)
    md(r"""
    ## 7. Portafolio del Motor 1 y remoción del techo por análogos

    El portafolio usa el `greedy_coverage` del contrato 04 con puntaje
    de sitio = atractividad de su AGEB anfitriona, bajo las reglas de
    red idénticas para los tres motores, **sin techo por AGEB**: la
    cantidad de estaciones que recibe cada AGEB es ahora únicamente el
    resultado de la cobertura con rendimientos decrecientes.

    ### Remoción del techo por análogos

    En la publicación anterior (`v3-motor1-2`) cada AGEB recibía un
    *techo teórico*: la mediana de densidad histórica (estaciones/km²)
    de sus 5 análogas de referencia por coseno, multiplicada por su
    área. El backtest del techo mostró que **reproducía la densidad
    histórica de planeación, no demanda**, y que **perdía contra una
    densidad constante** —la mediana de densidad del pliegue— tanto en
    MAE como en Spearman. Por eso se retiró del despliegue: imponerlo
    heredaba a la cartera un patrón histórico de inversión que no es
    evidencia sobre el objetivo.

    El backtest se **conserva** a continuación solo como evidencia de
    esa decisión: compara, dentro del mismo protocolo de pliegues, la
    densidad por análogos contra la densidad constante mediana. Los
    campos de techo (`ceiling`, `hits_ceiling_*`, `allocated_B*`) ya no
    existen en las salidas publicadas. La tabla de contraste compara el
    portafolio $B=30$ de esta publicación con el publicado anteriormente.
    """)
    code("""
    cb = report["ceiling_backtest"]
    display(pd.Series({k: v for k, v in cb.items() if k != "previous_publication"},
                      name="valor").to_frame())
    display(Markdown("**Corrida previa (v3-motor1-2, referencia)**"))
    display(pd.Series(cb["previous_publication"], name="valor").to_frame())
    rem = report["portafolio"]["techo_removido"]
    display(Markdown("**Cambio del portafolio por la remoción del techo** "
                     "(presupuesto primario B=30)"))
    display(pd.DataFrame({"previo (con techos)": rem["previous_B30"],
                          "actual (sin techos)": rem["current_B30"]}))
    display(pd.Series({"delta_new_pop": rem["delta_B30_new_pop"],
                       "delta_n_agebs": rem["delta_B30_n_agebs"]},
                      name="delta").to_frame())
    display(Markdown("**Métricas de portafolio por presupuesto** "
                     "(contrato común)"))
    metrics_long = pd.DataFrame(
        report["portafolio"]["por_presupuesto"]).T
    display(metrics_long)
    port = result["portafolios"]
    prim = port.loc[port.budget.eq(
        report["portafolio"]["budget_grid"][1])]
    sites = result["sites"]
    stations = data["frames"]["station_env"].to_crs(
        CONFIG["metric_crs"])
    universe_g = data["frames"]["universe"].to_crs(
        CONFIG["metric_crs"])
    fig, ax = plt.subplots(figsize=(9, 7))
    universe_g.plot(ax=ax, color="#F5F5F5", edgecolor="#DDDDDD",
                    linewidth=0.15)
    sites.plot(ax=ax, color="#DDDDDD", markersize=1.5, alpha=0.5)
    stations.plot(ax=ax, color=BLUE, markersize=4, alpha=0.6)
    prim.plot(ax=ax, column="order", cmap="viridis", markersize=40,
              edgecolor="black", linewidth=0.4, legend=True,
              legend_kwds={"label": "orden de inserción",
                           "shrink": 0.6})
    ax.set_axis_off()
    ax.set_title("Portafolio del Motor 1 — presupuesto primario")
    plt.tight_layout(); plt.show()
    display(Markdown("**Estaciones por AGEB** (presupuesto primario)"))
    display(prim.cvegeo.value_counts().value_counts().sort_index()
            .rename("n_agebs").to_frame())
    """)
    md("""
    ## 8. Límites y publicación

    El Motor 1 es un **baseline de similitud**, no un modelo de demanda:
    sus métricas miden redescubrimiento de actividad observada entre
    AGEBs servidas, su ranking territorial ordena candidatas por
    parecido a un centroide de referencia, y ni la compuerta Ledoit-Wolf
    —cuyo umbral χ² es nominal bajo encogimiento— ni la abstención
    convierten a `attractiveness` en probabilidad de éxito. El techo por
    análogos quedó fuera del despliegue por evidencia (perdía contra una
    densidad constante); su backtest se conserva solo como diagnóstico
    histórico. El portafolio usa las reglas comunes del contrato 04 sin
    cuotas por AGEB y su factibilidad queda verificada por `is_feasible`;
    la atractividad que puntúa sitios hereda el posible sesgo de
    afluencia del baseline —el coseno sigue correlacionado con
    escolaridad, internet y auto, y la similitud no es causalidad ni
    demanda.

    Se publican: el detalle y resumen del backtest por variante y
    esquema, la tabla de decisiones, los diagnósticos por pliegue
    (incluidos encogimiento y números de condición de la compuerta), la
    sensibilidad, el ranking georreferenciado de candidatas, la tabla de
    referencia, los portafolios por presupuesto, el backtest del techo
    (evidencia de su remoción) y el paquete serializado del pipeline de
    despliegue con su compuerta.
    """)
    code("""
    display(pd.DataFrame({"pending_validation":
                          report["pending_validation"]}))
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Baseline del Motor 1 publicado con "
                     "verificación de integridad: ranking territorial "
                     "y portafolio de sitios bajo el contrato común."))
    display(JSON({"m1_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
