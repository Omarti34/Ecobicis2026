"""Receta del cuaderno 06: Motor 2, estudio honesto de capacidad.

Narrativa formal en español; ningún número se incrusta: todo se lee de
result/report. El cuaderno mide si un Transformer tabular aprende algo
fuera de muestra contra controles simples, sobre el arnés publicado del
04. El antiguo Motor 2 de series de stock-out quedó descartado: aquí no
hay nada temporal.
"""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 06. Motor 2 — estudio honesto de capacidad del Transformer

    El Motor 2 responde una pregunta acotada: **¿un modelo flexible —un
    Transformer tabular— aprende relaciones útiles fuera de muestra entre
    el entorno de la AGEB y la actividad observada media por estación, o
    solo memoriza una muestra pequeña?** El universo son las AGEBs
    etiquetadas del cuaderno 04, concentradas en la zona servida y con
    dependencia espacial entre vecinas.

    El antiguo Motor 2 de pronóstico de stock-out quedó **descartado del
    diseño vigente**: este cuaderno no contiene nada temporal.

    **Lo que este motor puede decir.** Si el Transformer supera de forma
    consistente a controles simples bajo validación espacial, existe
    capacidad predictiva adicional en los atributos de entorno; si no, la
    tesis debe declararlo.

    **Lo que no puede decir.** No promete superioridad a priori, no
    estima demanda latente en territorio sin servicio y sus importancias
    son asociación predictiva, no causalidad.

    **La tarea común.** El cuaderno 04 alimenta a los motores 1, 2 y 3
    **en paralelo**: los tres resuelven la misma tarea de despliegue
    —un portafolio de $B$ sitios bajo reglas de red idénticas— y
    ninguno lee las salidas de los otros. El cierre de este cuaderno
    aporta la respuesta del Motor 2 con su propia compuerta de dominio
    y los puntajes de su modelo tabular de despliegue, **sin usar
    insumos del Motor 1**.

    **Insumos.** Publicaciones verificadas byte a byte: atributos del
    cuaderno 03, universo/particiones/arnés y el contrato de despliegue
    —sitios, celdas, reglas y métricas— del 04, y el entorno de
    estaciones del 02.
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
    from V3.src.m2_analysis import (
        CONFIG, MODELS, CONTROLS, load_inputs, analyze)
    from V3.src.m2_publication import stage_results

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
        "validation_analysis_id": report["upstream"]["validation_analysis_id"],
        "eda_analysis_id": report["upstream"]["eda_analysis_id"],
        "no_motor1_motor3_inputs":
            report["upstream"]["motor1_motor3_not_inputs"],
    }]))
    """)
    md("""
    ## 1. Datos, objetivo y preprocesado local por pliegue

    Los predictores son los atributos brutos del contrato del cuaderno 03
    sobre las AGEBs evaluables del 04; el objetivo es
    `log1p(actividad_media_estacion)`. A diferencia del Motor 1 —que
    ajustaba su representación con todas las proyectables no excluidas—
    aquí el ajuste es **supervisado y más estricto**: el preprocesador
    (contrato de atributos, imputación por mediana, escalado; **sin
    PCA**, los atributos entran completos a todos los modelos) se ajusta
    únicamente con las filas de `train_ids`, y el objetivo solo proviene
    de `train_target`. Las filas de prueba y su buffer nunca participan.
    """)
    code("""
    mets = result["cv_metrics"]
    sizes = (result["ranking_detail"]
             .loc[lambda d: d.model.eq("constante")]
             [["fold_scheme", "fold", "n_train_used",
               "n_buffer_excluded", "n_relevant"]])
    display(sizes.drop_duplicates())
    display(Markdown(
        f"AGEBs evaluables: **{report['scope']['n_evaluable']}**; "
        f"modelos: {', '.join(MODELS)}."))
    """)
    md("""
    ## 2. Controles: constante, Ridge y bosque

    La pregunta de capacidad solo tiene sentido contra controles
    transparentes:

    - **`constante`** predice la media de entrenamiento: la cota de
      plomería que todo modelo debe superar.
    - **`ridge`** es un lineal regularizado cuyo alpha se elige por
      validación cruzada **interna** sobre el entrenamiento retenido —
      nunca sobre los pliegues externos.
    - **`random_forest`** aporta no linealidad barata y robusta con
      hiperparámetros fijos.

    Si el Transformer no supera a estos controles, su flexibilidad no se
    traduce en capacidad fuera de muestra.
    """)
    md(r"""
    ## 3. Arquitectura y entrenamiento controlado

    El FT-Transformer tokeniza cada atributo con su propio peso y sesgo
    —`token_j = x_j·W_j + b_j`—, antepone un token CLS aprendible y pasa
    la secuencia por dos capas de encoder (`d_token` fijo, norm-first,
    GELU); la cabeza lee solo el CLS. El objetivo se estandariza con
    media y desviación del entrenamiento retenido y se invierte al
    predecir.

    Todos los hiperparámetros están **fijados a priori** —no hay ajuste
    sobre los pliegues externos—: parada temprana con paciencia fija
    sobre una partición interna **agrupada** del entrenamiento (bloques
    espaciales en el esquema primario, `cvegeo` en el esquema AGEB), y
    cinco semillas fijas cuyas predicciones se promedian. La variabilidad
    entre semillas se reporta, no se oculta.
    """)
    code("""
    tc = result["training_curves"]
    prim = CONFIG["primary_scheme"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sub = tc.loc[tc.fold_scheme.eq(prim) & tc.fold.isin([0, 1])]
    for (fold, seed), g in sub.groupby(["fold", "seed"]):
        ax.plot(g.epoch, g.train_loss, color=GRAY, lw=0.6, alpha=0.6)
        ax.plot(g.epoch, g.val_loss, color=BLUE, lw=0.8, alpha=0.8)
    ax.set_yscale("log")
    ax.set(xlabel="época", ylabel="MSE (log)",
           title="Curvas de entrenamiento — dos pliegues, todas las semillas")
    ax.legend(handles=[Patch(facecolor=GRAY, label="entrenamiento"),
                       Patch(facecolor=BLUE, label="validación interna")])
    plt.tight_layout(); plt.show()
    epochs = (tc.groupby(["fold_scheme", "fold", "seed"]).epoch.max()
              .rename("epocas").reset_index())
    display(epochs.groupby("fold_scheme").epocas.describe()[["mean", "max"]])
    """)
    md("""
    ## 4. Evaluación fuera de muestra

    Las métricas de regresión se computan **después** del backtest, desde
    las predicciones almacenadas contra el objetivo del universo —nunca
    dentro del motor—. Las métricas de ranking provienen del arnés del
    04, el mismo que evalúa a los tres motores. La brecha
    entrenamiento–prueba y el std entre semillas del Transformer son el
    termómetro de memorización.
    """)
    code("""
    display(Markdown("**Medias por modelo y esquema**"))
    display(result["mean_by"].assign(
        gap=lambda d: d.train_rmse - d.rmse))
    display(Markdown("**Ranking: medias del arnés (esquema primario)**"))
    rm = report["ranking_means_by_model_scheme"]
    prim = CONFIG["primary_scheme"]
    rows = [{"model": k.split("|")[0], **v}
            for k, v in rm.items() if k.endswith(prim)]
    display(pd.DataFrame(rows).set_index("model")[
        [c for c in ["precision@10", "recall@10", "ndcg@10"]
         if c in pd.DataFrame(rows).columns]])
    sd = result["cv_metrics"].loc[
        result["cv_metrics"].model.eq("ft_transformer")
        & result["cv_metrics"].fold_scheme.eq(prim)]
    display(sd[["fold", "rmse", "seed_rmse_std", "train_rmse"]])
    fig, ax = plt.subplots(figsize=(9, 4))
    for model, color in zip(MODELS, [GRAY, BLUE, GOLD, GREEN]):
        sub = result["cv_metrics"].loc[
            result["cv_metrics"].model.eq(model)
            & result["cv_metrics"].fold_scheme.eq(prim)]
        ax.plot(sub.fold, sub.rmse, "-o", ms=4, label=model, color=color)
    ax.set(xlabel="pliegue", ylabel="RMSE (log)",
           title="RMSE de prueba por pliegue — esquema primario")
    ax.legend(fontsize=8); plt.tight_layout(); plt.show()
    """)
    md("""
    ## 5. Curva de aprendizaje — ¿más datos ayudarían?

    Sobre el esquema primario se reentrenan los controles y el
    Transformer (tres semillas) con fracciones crecientes del
    entrenamiento retenido de cada pliegue —**la misma submuestra para
    todos los modelos**—. Una pendiente descendente que aún no se aplana
    sugiere que el límite es de datos, no de capacidad; una curva plana
    indica que más filas del mismo tipo no ayudarían.
    """)
    code("""
    curve = result["learning_curve"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for model, color in zip(CONTROLS + ["ft_transformer"],
                            [BLUE, GOLD, GREEN]):
        sub = curve.loc[curve.model.eq(model)]
        g = sub.groupby("fraction").rmse.agg(["mean", "std"])
        ax.errorbar(g.index, g["mean"], yerr=g["std"], marker="o",
                    label=model, color=color, capsize=3)
    ax.set(xlabel="fracción del entrenamiento retenido",
           ylabel="RMSE de prueba (log)",
           title="Curva de aprendizaje — esquema primario")
    ax.legend(); plt.tight_layout(); plt.show()
    display(curve.groupby(["model", "fraction"])
            .rmse.mean().unstack("fraction"))
    """)
    md("""
    ## 6. Interpretación: importancia por permutación

    En cada pliegue del esquema primario se permuta cada atributo en la
    prueba y se mide el deterioro del RMSE, promediado sobre repeticiones
    y pliegues. Es **asociación predictiva dentro del modelo ajustado**:
    dice qué atributos usa cada modelo, no qué atributos *causan*
    actividad.
    """)
    code("""
    imp = result["importance_summary"]
    heat = imp.pivot(index="feature", columns="model",
                     values="delta_rmse_mean")
    fig, ax = plt.subplots(figsize=(7, 5.5))
    im = ax.imshow(heat.to_numpy(), aspect="auto", cmap="YlGn")
    ax.set_xticks(range(len(heat.columns)), heat.columns, rotation=20)
    ax.set_yticks(range(len(heat.index)), heat.index)
    fig.colorbar(im, ax=ax, label="ΔRMSE medio")
    ax.set_title("Importancia por permutación (no causal)")
    plt.tight_layout(); plt.show()
    display(heat.sort_values(heat.columns[-1], ascending=False).round(4))
    """)
    md("""
    ## 7. Dictamen, despliegue exploratorio y publicación

    El dictamen se computa mecánicamente con la regla declarada a priori:
    el Transformer aporta solo si (a) su RMSE medio en el esquema
    primario es menor que el del mejor control, (b) le gana en al menos
    cuatro de cinco pliegues y (c) la mejora media supera la variabilidad
    entre semillas. Si no se cumplen las tres, el cuaderno declara que
    **no hay evidencia de capacidad adicional** —ese resultado también es
    el resultado—.

    La compuerta de dominio también es **propia**: Mahalanobis sobre el
    soporte completo de su entrenamiento —todas las AGEBs servidas
    etiquetadas— en el espacio estandarizado del Motor 2, y fuera de
    dominio el puntaje es cero. A diferencia de la compuerta del Motor 1
    —referida a la similitud con la referencia de alta actividad—, esta
    mide pertenencia al soporte de los datos de entrenamiento.
    """)
    code("""
    d = report["dictamen"]
    display(pd.Series({
        "transformer_aporta": d["transformer_aporta"],
        "mejor_control": d["best_control"],
        "rmse_medio_transformer": d["mean_rmse"]["ft_transformer"],
        "victorias_vs_control": f"{d['condition_b_fold_wins_vs_best_control']}/5",
        "mejora_media": d["condition_c_improvement"],
        "std_semillas_medio": d["condition_c_seed_std_mean"],
        "condicion_a": d["condition_a_rmse_below_controls"],
        "condicion_c": d["condition_c_holds"],
    }, name="dictamen").to_frame())
    display(pd.DataFrame([{"model": m, **v}
                          for m, v in report["beats_constante"].items()]))
    dep = report["deployment"]
    display(Markdown(
        f"**Despliegue.** Puntaje del portafolio: "
        f"`{dep['selected_model']}` (método propio); candidatas: "
        f"{dep['candidates']} — en dominio m2: "
        f"{dep['candidates_in_domain_m2']}, fuera: "
        f"{dep['candidates_out_domain_m2']}. Aviso: "
        f"*{dep['extrapolation_flag']}*."))
    cand = result["candidate_predictions"]
    display(cand.nlargest(10, "pred_selected")[
        ["cvegeo", "nom_mun", "pred_selected", "domain_status_04",
         "domain_status_m2"]])
    """)
    md(r"""
    ## 8. Navaja de Ockham: dictamen del Motor 2

    La comparación anterior responde una segunda pregunta: **¿la
    complejidad del FT-Transformer se justifica?** La regla mecánica ya
    dio su veredicto: la ventaja del Transformer sobre el mejor control
    es mucho menor que su propia variación entre semillas —la mejora
    media no supera el desvío estándar de semillas reportado arriba—. El
    FT-Transformer se retira del flujo de despliegue y se conserva
    únicamente como **caso de estudio de inestabilidad estocástica**: el
    mismo modelo, mismos datos, distinta semilla, respuestas distintas.

    El **Random Forest** pasa a ser el modelo tabular de despliegue por
    **parsimonia y estabilidad, NO por dominancia demostrada**: la
    diferencia frente a Ridge es pequeña —se reporta abajo el delta de
    RMSE medio y los pliegues ganados— y **ningún modelo es
    predictivamente fuerte** en este protocolo: el R² espacial medio de
    todos los modelos es bajo. La predicción de despliegue se mantiene
    como lo que es: **exploratoria**, con bandera de extrapolación y su
    compuerta de dominio propia.
    """)
    code("""
    ok = report["ockham"]
    display(pd.Series({
        "transformer_fuera_del_despliegue":
            ok["transformer_removed_from_deployment"],
        "dictamen_no_added_capacity": ok["dictamen_no_added_capacity"],
        "delta_rmse_rf_menos_ridge":
            ok["rf_vs_ridge"]["delta_rmse_mean"],
        "pliegues_ganados_por_rf":
            f"{ok['rf_vs_ridge']['rf_fold_wins']}"
            f"/{ok['rf_vs_ridge']['n_folds']}",
    }, name="navaja de Ockham").to_frame())
    display(Markdown("**R² espacial medio por modelo** — ninguno es "
                     "predictivamente fuerte"))
    display(pd.Series(ok["r2_spatial_mean"], name="r2_medio").to_frame())
    """)
    md(r"""
    ## 9. Portafolio del Motor 2 (sin techos)

    El `greedy_coverage` del contrato 04 construye los portafolios con
    el puntaje del **bosque aleatorio** —expm1 de la predicción de la
    AGEB anfitriona, 0 fuera del dominio m2— **sin techo por AGEB**: el
    número de estaciones que recibe cada AGEB es únicamente el resultado
    de la cobertura con rendimientos decrecientes.
    """)
    md(r"""
    ### Remoción del techo por análogos

    En la versión anterior el portafolio acotaba cada AGEB por la
    mediana de densidad histórica de sus 5 análogos euclídeos por su
    área. Ese techo **reproducía la densidad histórica de planeación,
    no la demanda**, y su backtest —que se conserva abajo solo como
    evidencia— perdía contra un comparador de densidad constante igual
    a la mediana de las retenidas. El techo se retira del flujo: las
    salidas de este cuaderno ya no contienen columnas ni campos de
    techo (`ceiling`, `hits_ceiling`, `allocated_B*`, artefacto por
    AGEB), y el portafolio cambia respecto al publicado con techos —
    abajo se compara el $B=30$ anterior contra el actual, leyendo los
    valores del reporte—.
    """)
    code("""
    display(pd.Series(report["ceiling_backtest"], name="valor")
            .to_frame())
    tr = report["portafolio"]["techo_removido"]
    display(pd.DataFrame([{
        "esquema_previo": tr["previous_schema"],
        "new_pop_previa_B30": tr["previous_B30"]["new_pop"],
        "agebs_previo_B30": tr["previous_B30"]["n_agebs"],
        "new_pop_actual_B30": tr["current_B30"]["new_pop"],
        "agebs_actual_B30": tr["current_B30"]["n_agebs"],
        "delta_new_pop": tr["delta_B30_new_pop"],
        "delta_n_agebs": tr["delta_B30_n_agebs"],
    }]))
    display(Markdown("**Métricas de portafolio por presupuesto** "
                     "(contrato común)"))
    display(pd.DataFrame(
        report["portafolio"]["por_presupuesto"]).T)
    port = result["portafolios"]
    prim_b = report["portafolio"]["budget_grid"][1]
    sel = port.loc[port.method.eq("random_forest")
                   & port.budget.eq(prim_b)]
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
    sel.plot(ax=ax, column="order", cmap="viridis", markersize=40,
             edgecolor="black", linewidth=0.4, legend=True,
             legend_kwds={"label": "orden de inserción", "shrink": 0.6})
    ax.set_axis_off()
    ax.set_title("Portafolio del Motor 2 — presupuesto primario")
    plt.tight_layout(); plt.show()
    display(Markdown("**Estaciones por AGEB** (presupuesto primario)"))
    display(sel.cvegeo.value_counts().value_counts().sort_index()
            .rename("n_agebs").to_frame())
    display(pd.DataFrame({"pending_validation":
                          report["pending_validation"]}))
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Estudio de capacidad y portafolio "
                     "del Motor 2 publicados con verificación de "
                     "integridad; sin insumos de otros motores."))
    display(JSON({"m2_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
