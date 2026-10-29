"""Receta del cuaderno 03: cobertura, contrato de atributos y espacio PCA.

La narrativa es presentación en español formal del proyecto; todos los
números, conteos, componentes y coeficientes se leen de result/report, sin
constantes incrustadas.
"""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 03. Cobertura territorial, contrato de atributos y espacio PCA compartido

    Este cuaderno construye la matriz de atributos **no derivados de la
    actividad de viajes** por AGEB y un espacio de componentes principales
    compartido entre la referencia Golden y las AGEBs candidatas. El PCA es
    **descriptivo y transductivo**: se ajusta una sola vez sobre el universo
    proyectable y no constituye una evaluación inductiva ni una prueba de
    ranking. No se entrenan modelos predictivos ni se afirma métrica
    predictiva alguna.

    Todas las fuentes provienen de la generación ETL comprometida y verificada,
    y del reporte EDA activo cuya identidad queda ligada a la de este análisis.
    Los derivados se publican bajo `data/features/<contrato>/<análisis>/`,
    separados de la generación ETL inmutable.
    """)
    code("""
    import sys
    from pathlib import Path
    import numpy as np
    import pandas as pd
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import seaborn as sns
    from IPython.display import display, Markdown, JSON

    BASE = Path.cwd().resolve()
    PROJECT = next(p for p in [BASE, *BASE.parents] if (p / "V3/data/raw").is_dir())
    V3_DIR = PROJECT / "V3"
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from V3.src.fe03_analysis import CONFIG, FEATURE_NAMES, load_inputs, analyze
    from V3.src.fe03_publication import stage_results

    GREEN, GRAY, BLUE = "#004731", "#546E7A", "#0D47A1"
    plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 11})
    data = load_inputs(V3_DIR)
    result = analyze(data)
    report = result["report"]
    features, scores = result["features"], result["scores"]
    loadings, centroid = result["loadings"], result["centroid"]
    assert isinstance(features, gpd.GeoDataFrame)
    display(pd.DataFrame([{
        "contract_id": report["contract_id"],
        "analysis_version": report["schema_version"],
        "n_agebs": len(features),
        "projectable_agebs": report["feature_matrix"]["projectable_agebs"],
        "n_features": report["feature_matrix"]["n_features_raw"],
    }]))
    """)
    md("""
    ## 1. Cobertura territorial y escenario de candidatas

    Los buffers son **euclidianos proyectados de 500 m** en EPSG:32614. No son
    áreas de servicio caminables ni geodésicas, y **no resuelven el MAUP**.
    La regla «fracción cubierta < 15%» es un **escenario de planificación**;
    una cobertura igual o mayor al 15% no constituye saturación ni evidencia
    de suficiencia de servicio.

    El diagnóstico distingue tres magnitudes que no deben mezclarse: el
    **conteo territorial** de AGEBs candidatas, el **conteo proyectable**
    (las candidatas que además cumplen el contrato de atributos) y las
    **participaciones de área** respecto al polígono total. La sensibilidad
    reporta radios y umbrales alternativos con el mismo criterio.
    """)
    code("""
    maup = report["maup_mitigation"]
    display(pd.Series(maup, name="value").to_frame())
    display(result["maup_sensitivity"])
    fig, ax = plt.subplots(figsize=(9, 8))
    features.plot(ax=ax, color="#EEEEEE", edgecolor="#CCCCCC", linewidth=0.2)
    features[features.is_candidata_territorial].plot(
        ax=ax, color="#90CAF9", edgecolor="#64B5F6", linewidth=0.2)
    features[features.is_golden_cluster].plot(
        ax=ax, color=GREEN, edgecolor="white", linewidth=0.2)
    ax.set_title(f"Cobertura euclidiana {CONFIG['buffer_radius_m']} m: "
                 "candidatas territoriales vs referencia Golden")
    ax.legend(handles=[
        Patch(facecolor=GREEN, label="Golden Cluster"),
        Patch(facecolor="#90CAF9", label="Candidata territorial"),
        Patch(facecolor="#EEEEEE", label="Resto de AGEBs"),
    ], loc="upper left", bbox_to_anchor=(1.02, 1))
    ax.set_axis_off(); plt.show()
    display(Markdown(
        f"**Resultado.** {maup['territorial_candidates_count']:,} AGEBs "
        f"candidatas territoriales, de las cuales "
        f"{maup['projectable_candidates_count']:,} son proyectables; "
        f"participación en conteo {maup['candidate_ageb_share']:.2%} y en "
        f"área {maup['candidate_area_share']:.2%}."
    ))
    """)
    md("""
    ## 2. Filtros de fuente y contrato exacto de atributos

    - **DENUE**: se conservan únicamente altas de sectores terciarios SCIAN
      explícitos con **fecha de alta conocida hasta 2025**, leídas del
      directorio edición 2026. Es un **proxy retrospectivo**, no la
      reconstrucción del stock histórico: no recupera cierres, cambios de
      actividad ni reubicaciones previas.
    - **GTFS**: la distancia a Metro/Metrobús se filtra mediante vínculos
      aceptados stop_times → trips → routes y el **calendario de servicio
      con cobertura declarada en 2025**; no se mide servicio observado ni
      acceso caminable.
    - **Infraestructura ciclista**: solo tramos en estado «En operación»;
      las tipologías incluidas son **heterogéneas y no exclusivamente
      segregadas**.
    - **Censo 2020**: las tasas residenciales conservan sus denominadores
      documentados; valores censales crudos preservados.

    La tabla siguiente es el contrato completo de los atributos usados por
    el espacio compartido: fuente, unidad, numerador, denominador,
    transformación y política de faltantes.
    """)
    code("""
    sources = report["source_filters"]
    for name in ["denue", "gtfs", "cycling"]:
        display(Markdown(f"**{name}**"))
        display(pd.Series(sources[name], name="value").to_frame())
    contract = pd.DataFrame(report["feature_matrix"]["feature_contract"])
    assert len(contract) == len(FEATURE_NAMES)
    display(contract)
    """)
    md("""
    ## 3. Faltantes, elegibilidad y política de imputación

    Las AGEBs rurales y las filas con tasas residenciales estructuralmente
    indefinidas (denominador poblacional, de vivienda o laboral ausente) se
    **excluyen del ajuste**, no se convierten en perfiles de «residente
    promedio» fabricados. Las exclusiones por causas no residenciales
    **tampoco significan demanda potencial cero**.

    Cuando falta un numerador pero su denominador es aplicable y positivo,
    la mediana imputa la **tasa derivada** —nunca sustituye el numerador en
    sí—; los **valores crudos se preservan** junto con los indicadores de
    faltante e imputación para auditoría posterior.
    """)
    code("""
    fm = report["feature_matrix"]
    summary_keys = ["projectable_agebs", "unprojectable_agebs",
                    "rural_nans_preserved_count", "imputed_rows",
                    "imputed_candidate_rows", "imputed_golden_rows",
                    "imputed_cells"]
    display(pd.Series({k: fm[k] for k in summary_keys}, name="value").to_frame())
    display(pd.Series(sources["exclusion_reason_counts_nonexclusive"],
                      name="n_agebs").to_frame())
    display(pd.Series(fm["imputed_cells_by_feature"],
                      name="missing_cells").to_frame())
    """)
    md("""
    ## 4. Espacio PCA compartido y lectura de PC1

    El PCA se ajusta una vez con las filas proyectables y aplica la **misma
    canalización** (contrato → mediana → estandarización → componentes) a
    Golden y candidatas, garantizando comparabilidad en una base ortonormal.
    La retención se define por el objetivo de varianza acumulada declarado
    en la configuración.

    **PC1 — Eje de Equipamiento y Composición Socioeconómica Residencial.**
    Los coeficientes mostrados son cargas del vector propio con su signo;
    **no son efectos causales, ni medidas de centralidad ni de atracción**.
    Advertencia de sesgo: la similitud en este eje puede replicar contextos
    afluentes —el ingreso no se observa directamente— sin optimizar el
    servicio de transporte.
    """)
    code("""
    pca = report["pca_reduction"]
    individual = np.asarray(pca["individual_variance_explained"], dtype=float)
    order = np.arange(1, len(individual) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].bar(order, individual, color=GREEN, alpha=0.85)
    axes[0].plot(order, np.cumsum(individual), marker="o", color=BLUE)
    axes[0].axhline(CONFIG["variance_target"], color=GRAY, ls="--",
                    label=f"Objetivo {CONFIG['variance_target']:.0%}")
    axes[0].set(xlabel="Componente", ylabel="Varianza explicada",
                title=f"Scree: k={pca['k_components_80_pct']} componentes")
    axes[0].legend()
    sns.heatmap(loadings, cmap="RdBu_r", center=0, ax=axes[1],
                cbar_kws={"label": "coeficiente del vector propio"})
    axes[1].set_title("Coeficientes PCA: cargas, no efectos")
    plt.tight_layout(); plt.show()
    display(pd.Series(pca["top_pc1_signed_coefficients"],
                      name="coeficiente_PC1").to_frame())
    display(Markdown(
        f"**Resultado.** {pca['k_components_80_pct']} componentes explican "
        f"el {pca['cumulative_variance_explained']:.2%} de la varianza; "
        "los coeficientes principales de PC1 se muestran con signo."
    ))
    """)
    md("""
    ## 5. Referencia Golden y distancias en el espacio compartido

    El centroide Golden usa **un peso igual por AGEB proyectable**, no por
    estación. La similitud por **dirección (coseno)** difiere de la
    similitud por **magnitud (euclidiana)**; ambas se derivan de la misma
    base, por lo que compartir el espacio **no prueba por sí solo un
    ranking válido**. La covarianza de referencia y el umbral de dominio
    para distancias de Mahalanobis quedan pendientes de calibración
    explícita.
    """)
    code("""
    pc_names = [c for c in scores.columns if str(c).startswith("PC")]
    x_name = pc_names[0]
    y_name = pc_names[1] if len(pc_names) > 1 else pc_names[0]
    rest = scores.is_projectable & ~scores.is_golden_cluster \
        & ~scores.is_candidata_proyectable
    cand = scores.is_projectable & scores.is_candidata_proyectable \
        & ~scores.is_golden_cluster
    gold = scores.is_projectable & scores.is_golden_cluster
    fig, ax = plt.subplots(figsize=(8.5, 6))
    ax.scatter(scores.loc[rest, x_name], scores.loc[rest, y_name],
               s=10, color="#BBBBBB", alpha=0.5, label="Resto proyectable")
    ax.scatter(scores.loc[cand, x_name], scores.loc[cand, y_name],
               s=14, color=BLUE, alpha=0.7, label="Candidatas proyectables")
    ax.scatter(scores.loc[gold, x_name], scores.loc[gold, y_name],
               s=20, color=GREEN, label="Golden Cluster")
    ax.scatter(centroid[x_name].iloc[0], centroid[y_name].iloc[0],
               marker="*", s=220, color="black",
               label=f"Centroide Golden (n={int(centroid['n_golden_agebs'].iloc[0])})")
    ax.set(xlabel=x_name, ylabel=y_name,
           title="Espacio PCA compartido: base común, no prueba de ranking")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    plt.tight_layout(); plt.show()
    """)
    md("""
    ## 6. Alcance, validación pendiente y publicación

    Este ajuste es **global, descriptivo y transductivo**. Para la evaluación
    inductiva del cuaderno 04 el preprocesamiento (imputación, escalamiento,
    PCA), la selección Golden por P85 y el centroide deberán reajustarse
    **dentro de cada pliegue de entrenamiento**, junto con bloques espaciales
    o buffers entre particiones: GroupKFold por AGEB por sí solo no aísla
    polígonos vecinos. La sensibilidad del ranking al umbral P85 queda
    **pendiente**; no se afirma haberla ejecutado.

    **Reutilización del espacio.** La canalización publicada puede cargarse
    una vez activado el reporte, sin reajuste, sobre atributos nuevos que
    cumplan el mismo contrato de 20 columnas de entrada (las 18
    características brutas más `TVIVHAB` y `PEA` como denominadores de
    elegibilidad; no son coordenadas ni identificadores):

    ```python
    from V3.src.fe03_analysis import INPUT_COLUMNS
    from V3.src.fe03_publication import load_feature_pipeline
    pipeline = load_feature_pipeline(V3_DIR)          # solo tras activación
    scores_nuevos = pipeline.transform(nuevos_atributos[INPUT_COLUMNS])
    ```

    Los derivados se publican fuera de la generación ETL, con identidad
    ligada al código, las fuentes y el reporte EDA activo; la auditoría
    activa se actualiza solo después de guardar el cuaderno ejecutado.
    """)
    code("""
    display(pd.DataFrame({"pending_validation": report["pending_validation"]}))
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Atributos, espacio compartido y canalización "
                     "publicados con verificación de integridad."))
    display(JSON({"fe03_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
