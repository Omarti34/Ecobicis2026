"""Spanish academic narrative and executable recipe for the corrected EDA."""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 02. Actividad observada, concentración territorial y límites de inferencia

    Este análisis describe la actividad registrada por EcoBici durante 2025 y su
    asociación con el entorno territorial. La actividad realizada no mide demanda
    latente: también depende de la oferta, disponibilidad y ubicación de estaciones.
    El cuaderno no estima efectos causales, no entrena modelos y no identifica una
    separación óptima entre estaciones. Los resultados permiten formular hipótesis
    y requisitos de validación para los cuadernos posteriores.

    Las fuentes se leen exclusivamente de la generación ETL comprometida y verificada.
    Se distinguen tres temporalidades: actividad de 2025, población censal de 2020 y
    directorios posteriores utilizados como contexto retrospectivo. El catálogo
    de estaciones capturado en 2026 no prueba por sí solo ubicaciones, capacidades
    ni períodos completos de operación en 2025. Estas limitaciones acompañan los
    resultados y no desaparecen al comprobar la integridad de los archivos.

    ## 1. Fuentes verificadas y reglas reproducibles

    La implementación separa cálculo, presentación y publicación. Los parámetros,
    versiones y hashes del código analítico se registran junto con los hashes de
    los insumos. La asignación estación–AGEB exige una relación única; cualquier
    pérdida o duplicación detiene el análisis antes de producir resultados.
    """)
    code("""
    import sys
    from pathlib import Path
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display, Markdown, JSON

    BASE = Path.cwd().resolve()
    PROJECT = next(p for p in [BASE, *BASE.parents] if (p / "V3/data/raw").is_dir())
    V3_DIR = PROJECT / "V3"
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from V3.src.eda02_analysis import CONFIG, load_inputs, analyze
    from V3.src.eda02_publication import stage_results

    GREEN, GRAY, BLUE = "#004731", "#546E7A", "#0D47A1"
    plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 11})
    data = load_inputs(V3_DIR)
    result = analyze(data)
    report = result["report"]
    display(pd.DataFrame([{"contract_id": report["contract_id"],
                           "analysis_version": report["schema_version"],
                           "n_stations": len(result["stations"]),
                           "n_agebs": len(result["agebs"])}]))
    """)
    md(r"""
    ## 2. Retención de registros y definición de actividad

    La retención expresa cumplimiento de reglas del ETL, no una certificación de
    veracidad, representatividad o «pureza» estadística. La cuarentena incluye
    identificadores no utilizables y registros fuera del período, algunos legítimos
    bajo otro universo temporal. No se atribuye una función de mantenimiento a
    códigos ausentes del catálogo sin evidencia documental.

    La actividad de una estación se define como
    \[
    a_i=(R_i+A_i)/(2\cdot365),
    \]
    donde \(R_i\) y \(A_i\) son extremos válidos conocidos de 2025. Esta cohorte de
    eventos no coincide necesariamente con la de viajes completos aceptados:
    un extremo válido puede conservarse aunque el viaje entero quede en cuarentena.
    El denominador fijo permite comparar tasas anuales, pero no controla días de
    operación, disponibilidad de bicicletas o cambios de ubicación.
    """)
    code("""
    accounting = report["sample_accounting"]
    display(pd.Series(accounting, name="value").to_frame())
    display(Markdown(
        f"**Resultado.** Se aceptaron {accounting['accepted_rows']:,} de "
        f"{accounting['input_rows']:,} filas ({accounting['retention_percent']:.6f}%). "
        f"La cuarentena conserva {accounting['quarantine_rows']:,} filas. "
        f"La suma de actividad corresponde a "
        f"{accounting['endpoint_activity_trip_equivalents']:,.0f} equivalentes "
        "de viaje por extremos; no se identifica con el número de viajes completos."
    ))
    """)
    md("""
    ## 3. Distribución de actividad y observaciones extremas

    El IQR identifica estaciones de actividad elevada sin excluirlas. El percentil
    85 define una cohorte descriptiva denominada Golden Cluster; no identifica
    productividad causal ni rentabilidad. El histograma conserva la distribución
    observada y las estaciones extremas. Un resultado atípico no equivale a un error.
    """)
    code("""
    target = report["target_metrics"]
    y = result["stations"]["viajes_diarios_prom"].to_numpy(dtype=float)
    display(pd.Series(target, name="value").to_frame())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.histplot(y, bins=40, ax=axes[0], color=GREEN)
    axes[0].axvline(target["p85"], color=BLUE, ls="--", label="P85")
    axes[0].axvline(target["upper_fence"], color=GRAY, ls=":", label="IQR: valla superior")
    axes[0].set(xlabel="Actividad diaria: extremos / (2 × 365)", ylabel="Estaciones")
    axes[0].legend()
    sns.boxplot(x=y, ax=axes[1], color=GREEN)
    axes[1].set(xlabel="Actividad diaria", title="Extremos conservados, no eliminados")
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 4. Concentración de infraestructura entre polígonos

    El Gini utiliza conteos brutos de estaciones por AGEB, incluyendo ceros, y
    pondera cada polígono por igual. No es un indicador per cápita ni una medida
    completa de equidad de acceso. La línea de Lorenz representa reparto uniforme
    entre AGEBs, no un criterio normativo de distribución óptima. Las proporciones
    acumuladas utilizan los puntos 0, 1/n, …, n/n.

    «Sin estación interna» describe pertenencia geométrica: una estación situada
    en un polígono vecino puede ser accesible. Ni la proporción de AGEBs ni el Gini
    deben interpretarse como proporción de habitantes excluidos. Las AGEBs rurales
    conservan población desconocida; no se sustituyen esos faltantes por cero.
    """)
    code("""
    display(pd.Series(report["spatial_equity"], name="value").to_frame())
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    agebs = result["agebs"]
    agebs.plot(ax=axes[0], color="#EEEEEE", edgecolor="#CCCCCC", linewidth=0.2)
    agebs[agebs.n_estaciones.gt(0)].plot(ax=axes[0], color="#A5D6A7")
    result["stations"].plot(ax=axes[0], color=GREEN, markersize=5)
    axes[0].set_title("AGEBs con estación interna: no equivale a acceso poblacional")
    axes[0].set_axis_off()
    axes[1].plot(result["lorenz_x"], result["lorenz_y"], color=GREEN, label="Estaciones")
    axes[1].plot([0, 1], [0, 1], "--", color=GRAY, label="Reparto uniforme por AGEB")
    axes[1].set(xlabel="Proporción acumulada de AGEBs",
                ylabel="Proporción acumulada de estaciones", xlim=(0, 1), ylim=(0, 1))
    axes[1].legend(); plt.tight_layout(); plt.show()
    """)
    md("""
    ## 5. Distancia de centroide a red

    Se calcula distancia euclidiana en EPSG:32614 desde el centroide de cada AGEB
    sin estación interna hasta el catálogo actual. Es un diagnóstico no ponderado
    por población, no distancia caminable ni distancia desde un sitio factible.
    Los centroides de polígonos cóncavos o multipartes pueden quedar fuera de ellos.
    El radio de 400 m solo ilustra que ausencia interna y proximidad son distintos;
    no constituye un umbral calibrado de servicio o de separación eficiente.

    Una mediana distante motiva investigar corredores y conectividad. No prueba
    imposibilidad matemática de expansión continua ni necesidad de Node2Vec.
    """)
    code("""
    gap = report["territorial_gap"]
    display(pd.Series(gap, name="value").to_frame())
    unserved = agebs[agebs.n_estaciones.eq(0)]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.ecdfplot(unserved.dist_centroide_red_km, ax=axes[0], color=GREEN)
    axes[0].axvline(gap["median_km"], color=BLUE, ls="--", label="Mediana")
    axes[0].set(xlabel="Distancia euclidiana centroide–red (km)", ylabel="Fracción de AGEBs")
    axes[0].legend()
    unserved.plot(column="dist_centroide_red_km", ax=axes[1], legend=True, cmap="YlGnBu")
    axes[1].set_title("Distancia por polígono, no exposición poblacional")
    axes[1].set_axis_off(); plt.tight_layout(); plt.show()
    display(Markdown(
        f"**Resultado.** Mediana: {gap['median_km']:.2f} km. "
        f"{gap['centroids_outside_own_polygon']} centroides quedan fuera de su polígono; "
        f"{gap['no_internal_station_but_centroid_within_400m']} AGEBs sin estación interna "
        "tienen su centroide a 400 m o menos de una estación."
    ))
    """)
    md("""
    ## 6. Moran global y cuadrantes descriptivos

    La matriz W utiliza ocho vecinos más cercanos de cada estación, pesos 1/8 por
    fila y diagonal cero. Es dirigida y no necesariamente simétrica. No se usa
    contigüidad Queen: la unidad son puntos de estaciones, no polígonos.
    El contraste unilateral de autocorrelación positiva emplea 999 permutaciones y
    semilla 42. Su pseudo-p es (excedencias + 1)/(999 + 1); el mínimo posible es 0.001.

    El mapa muestra **Cuadrantes de Moran sin significancia local**. Clasifica signos
    de actividad centrada y retardo espacial; no es una prueba LISA local y no
    confirma hotspots. El Moran global describe actividad dentro de la red observada,
    no exclusión de AGEBs sin estaciones. Se evalúa sensibilidad a k y a log1p.
    """)
    code("""
    moran = report["spatial_autocorrelation"]
    display(Markdown(f"**Resultado global.** I = {moran['i']:.6f}; "
                     f"pseudo-p = {moran['p_value']:.3f}, unilateral."))
    display(result["moran_sensitivity"])
    stations = result["stations"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sns.regplot(data=stations, x="moran_centered_activity", y="moran_spatial_lag",
                ci=None, ax=axes[0], color=GREEN, scatter_kws={"s": 12, "alpha": 0.5})
    axes[0].axhline(0, color=GRAY, ls=":"); axes[0].axvline(0, color=GRAY, ls=":")
    axes[0].set(xlabel="Actividad centrada: a − media(a)", ylabel="Retardo espacial W(a − media(a))",
                title=f"Moran global: I={moran['i']:.3f}; p={moran['p_value']:.3f}")
    palette = {"High-High": GREEN, "Low-Low": BLUE, "High-Low": "#E65100", "Low-High": GRAY}
    for label, color in palette.items():
        stations[stations.moran_quadrant.eq(label)].plot(
            ax=axes[1], color=color, markersize=12, label=label)
    axes[1].set_title("Cuadrantes de Moran sin significancia local")
    axes[1].set_axis_off(); axes[1].legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 7. Actividad terciaria: proxy retrospectivo DENUE 2026

    El directorio de 2026 no reconstruye el stock de establecimientos de 2025.
    Excluir altas posteriores evita incorporar esas altas conocidas, pero no
    recupera cierres ni cambios previos de ubicación, actividad o tamaño. La fecha
    de alta en DENUE tampoco demuestra fecha de apertura. Las fechas desconocidas
    se excluyen de esta cohorte y se contabilizan, sin imputar antigüedad.

    Se incluyen explícitamente los sectores SCIAN 43, 46, 48, 49, 51–56, 61, 62,
    71, 72, 81 y 93: comercio, transporte, servicios y gobierno. Se excluyen sectores
    primarios, manufactura, construcción y electricidad. La medida sigue siendo
    un proxy de personal ocupado registrado, no empleo formal observado ni empleo
    residente de la AGEB.

    Los estratos cerrados se convierten a sus puntos medios. Para «251 y más» no
    existe punto medio identificable: 300 es únicamente el escenario de referencia,
    contrastado con 251, 500 y 1,000. No se asignan tres personas a estratos desconocidos.
    Un cero agregado significa ausencia de establecimientos elegibles y emparejados
    en este directorio, no ausencia demostrada de empleos durante 2025.
    """)
    code("""
    display(pd.Series({k: v for k, v in report["denue_retrospective_proxy"].items()
                       if k != "open_band_sensitivity"}, name="value").to_frame())
    display(pd.DataFrame({"included_scian_sector": CONFIG["tertiary_scian_sectors"]}))
    display(result["employment_sensitivity"])
    """)
    md("""
    ## 8. Proximidad a paradas GTFS

    La variable principal mide distancia euclidiana a cualquier parada aceptada
    del feed. No se denomina «efecto Metro». Las referencias stop_times → trips →
    routes permiten identificar agencias y tipos de ruta; el vínculo al calendario
    muestra cobertura temporal declarada, no prueba histórica de posición o servicio.
    La distancia principal mantiene todas las paradas para conservar su definición,
    pero identifica paradas sin viajes aceptados y sin calendario vinculado a 2025.

    Las rutas incluyen RTP y transporte concesionado, además de modos masivos.
    La distribución empírica de agencias más cercanas permite comprobar qué mide
    la variable. Las métricas específicas de Metro o por modo deberán construirse
    con universos explícitos antes de utilizarlas como atributos de modelado.
    """)
    code("""
    gtfs = report["gtfs_proximity"]
    display(pd.Series({k: v for k, v in gtfs.items()
                       if k not in ("nearest_agency_counts", "route_type_counts")},
                      name="value").to_frame())
    display(pd.Series(gtfs["nearest_agency_counts"], name="nearest_to_ecobici").to_frame())
    display(pd.Series(gtfs["route_type_counts"], name="accepted_routes").to_frame())
    counts = pd.Series(gtfs["nearest_agency_counts"]).rename(
        index={"unlinked_in_accepted_trips": "Sin viaje aceptado vinculado"}).sort_values()
    counts.plot.barh(color=GREEN, figsize=(9, 4))
    plt.xlabel("Estaciones EcoBici"); plt.ylabel("Agencias de la parada más cercana")
    plt.title("Proximidad GTFS: composición modal, no un efecto Metro")
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 9. Asociaciones observadas: Pearson y Spearman

    Pearson describe asociación lineal; Spearman describe asociación monotónica
    entre rangos. Para Pearson del proxy de empleo se utiliza log1p; la transformación
    no cambia sus rangos para Spearman. No se interpretan estas correlaciones como
    elasticidades, efectos causales ni prueba de ausencia universal de relación.

    Los p-valores bajo independencia se muestran únicamente como referencia.
    Las estaciones comparten AGEB y tienen dependencia espacial. Los intervalos
    exploratorios emplean 1,000 remuestreos de AGEBs con reemplazo, conservando juntas
    sus estaciones. Este procedimiento no elimina dependencia entre AGEBs vecinas.
    Se reportan muestra, transformación, número de AGEBs y ambas correlaciones,
    sin escoger únicamente la medida más favorable a una narrativa.
    """)
    code("""
    display(result["correlations"])
    env = result["environment"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    features = [("densidad_pob_km2", "Densidad poblacional 2020"),
                ("dist_gtfs_m", "Distancia a cualquier parada GTFS (m)"),
                ("empleo_terciario_proxy", "log1p(proxy terciario retrospectivo)")]
    for ax, (column, label) in zip(axes, features):
        x = env[column].astype(float)
        if column == "empleo_terciario_proxy":
            x = np.log1p(x)
        sns.regplot(x=x, y=env.viajes_diarios_prom.astype(float), ax=ax, ci=None,
                    color=GREEN, scatter_kws={"s": 12, "alpha": 0.4})
        ax.set(xlabel=label, ylabel="Actividad diaria observada")
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 10. Golden Cluster y densidad de infraestructura

    Las estaciones con actividad mayor o igual a P85 se asignan a sus AGEBs
    anfitrionas únicas. Se publican ambos universos, sin suponer que 102 estaciones
    representan 102 entornos independientes. La lista de AGEBs se deriva de las
    llaves vigentes y no de un conteo histórico fijado manualmente.

    La mediana de vecino cercano dentro del Golden Cluster describe **alta densidad
    de infraestructura**. No demuestra canibalización: cercanía puede reflejar
    complementariedad, capacidad o accesibilidad. El vecino Golden–Golden se busca
    en un subconjunto distinto al vecino de toda la red, por lo que la comparación
    no identifica un efecto de competencia.

    No se deriva una separación óptima de 400 m. Cualquier restricción futura
    requiere justificación de planificación y sensibilidad. Para el PCA debe
    decidirse si cada AGEB pesa igual o si pesa según sus estaciones; son estimandos
    distintos. En backtest el umbral y el perfil de referencia se estimarán solo
    con la partición de entrenamiento cuando utilicen actividad observada.
    """)
    code("""
    golden = report["golden_cluster"]
    display(pd.Series({k: v for k, v in golden.items() if k != "ageb_ids"},
                      name="value").to_frame())
    display(result["golden_agebs"][["cvegeo", "n_golden_stations",
                                    "golden_mean_daily_activity"]])
    fig, ax = plt.subplots(figsize=(9, 4))
    sns.ecdfplot(result["golden_nn_m"], ax=ax, color=GREEN, label="Vecino Golden–Golden")
    sns.ecdfplot(result["network_nn_m"], ax=ax, color=GRAY, label="Vecino dentro de toda la red")
    ax.set(xlabel="Distancia al vecino más cercano (m)", ylabel="Fracción de estaciones",
           title="Densidad de infraestructura: no identifica canibalización")
    ax.legend(); plt.tight_layout(); plt.show()
    display(Markdown(
        f"**Resultado.** {golden['n_stations']} estaciones en "
        f"{golden['n_unique_agebs']} AGEBs únicas. Mediana Golden–Golden: "
        f"{golden['golden_neighbor_median_m']:.2f} m; mediana de toda la red: "
        f"{golden['network_neighbor_median_m']:.2f} m."
    ))
    """)
    md("""
    ## 11. Fuga de datos por construcción de variables

    turnover_ratio = 2 × actividad / capacidad es una transformación de la variable
    objetivo. Se calcula su Spearman real sobre capacidades positivas conocidas;
    su exclusión no depende de que la correlación sea casi uno. La capacidad varía
    entre estaciones y corresponde al catálogo posterior, no a una constante global.
    Las capacidades cero o desconocidas hacen indefinido el cociente: se excluyen
    únicamente de esta correlación, sin retirar la estación del diagnóstico.
    El coeficiente anterior cercano a 0.890 incluía una división por cero; no se
    reutiliza como resultado válido. La muestra y los identificadores afectados
    se registran explícitamente junto con el coeficiente corregido.

    No se calcula PageRank en este EDA y no se presenta ningún sustituto artificial
    como centralidad observada. Las centralidades construidas con flujos del período
    objetivo no son atributos ex ante para una estación hipotética sin viajes.
    La capacidad es una decisión de diseño que deberá tratarse según el objetivo y
    la temporalidad del modelo; su endogeneidad no se demuestra con una correlación.
    El cuaderno no entrena modelos ni reporta un rango de R² como estándar de rigor.
    """)
    code("""
    display(pd.Series(report["leakage_audit"], name="value").to_frame())
    display(Markdown(
        "**Resultado observado.** Spearman entre actividad y turnover_ratio: "
        f"{report['leakage_audit']['turnover_ratio_spearman']:.6f}. "
        "La identidad con el target impide utilizarlo como predictor de esa misma actividad."
    ))
    """)
    md("""
    ## 12. Alcance para atributos, validación y conectividad

    Se conserva la información faltante y se compara su disponibilidad entre AGEBs
    con y sin estación interna. El presente cuaderno no resuelve el MAUP ni produce
    todavía una matriz PCA completa. Los atributos adicionales requieren contrato
    de fuente, fecha, denominador, supresión y elegibilidad temporal.

    GroupKFold por AGEB evita dividir un mismo polígono entre entrenamiento y
    prueba, pero no evita proximidad entre polígonos contiguos. El diseño de
    validación deberá explicitar bloques, buffers y distancias entre folds.
    Imputación, escalamiento, PCA y perfiles supervisados se ajustarán dentro de
    entrenamiento bajo un objetivo inductivo; cualquier diseño transductivo deberá
    declararse y respetar qué información existe al momento de decisión.

    Los enlaces OD observados, de cercanía hipotética y de intermodalidad no son
    intercambiables. Un enlace de Metro no garantiza posibilidad de retirar y
    devolver una bicicleta. La expansión debe evaluar conexión física con la red,
    estaciones puente y componentes aislados. Grafos, embeddings y optimización
    genética son alternativas a contrastar con baselines, no necesidades demostradas.
    Quedan pendientes diagnóstico horario/mensual y estabilidad del Golden Cluster,
    accesibilidad ponderada por población y evaluación fuera del dominio observado.
    """)
    code("""
    display(result["feature_coverage"])
    display(pd.DataFrame({"pending_validation": report["pending_validation"]}))
    """)
    md("""
    ## 13. Publicación trazable de resultados

    Los derivados EDA se publican fuera de la generación ETL inmutable, en una
    carpeta identificada por el contrato y el hash de este análisis. Incluyen las
    AGEBs Golden, entorno por estación, diagnóstico territorial, correlaciones y
    sensibilidad, con linaje de contrato y versión analítica. La auditoría conserva
    parámetros, versiones, hashes de insumos/código y verificaciones de salida.
    Una ejecución fallida no reemplaza el cuaderno canónico; la auditoría activa se
    actualiza después de guardar el cuaderno ejecutado. La versión previa queda archivada.
    """)
    code("""
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Diagnósticos calculados con observaciones verificadas. "
                     "Las limitaciones y requisitos pendientes permanecen explícitos."))
    display(JSON({"eda_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
