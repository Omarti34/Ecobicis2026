"""Receta del cuaderno 09: registro sellado de afirmaciones.

Narrativa formal en español; ningún número se incrusta: todo se lee de
result/report. El 09 solo LEE las publicaciones verificadas 02–08 —no
entrena ni recalcula modelos ni portafolios— y construye el registro de
afirmaciones con su ruta JSON de origen. La única computación propia es
la verificación independiente del arnés espacial del 04.
"""
from textwrap import dedent


def get_notebook_cells():
    cells = []

    def md(text):
        cells.append(("markdown", dedent(text).strip()))

    def code(text):
        cells.append(("code", dedent(text).strip()))

    md(r"""
    # 09. Registro de afirmaciones (claims registry)

    Este cuaderno sella el **registro auditable de afirmaciones** del
    proyecto: cada cifra que la tesis puede citar, con la ruta JSON
    exacta de la publicación de donde sale. No entrena ni recalcula
    modelos ni portafolios: lee los punteros verificados byte a byte de
    los cuadernos 02–08 bajo la misma maquinaria de publicación que el
    08, y aborta ante cualquier discrepancia.

    La única computación propia es una **verificación independiente**:
    el conteo de pares colindantes prueba–entrenamiento tras el buffer
    del arnés espacial del 04 se reconstruye desde los artefactos
    publicados (asignaciones de fold, exclusiones de buffer y geometría
    del universo) y debe coincidir con el reporte —si no, el build
    aborta—. El documento ejecutivo `TESIS_DATA_POINTS.md` se genera
    mecánicamente desde el registro: ningún número está escrito a mano.
    """)
    code("""
    import sys
    import json
    from pathlib import Path
    import pandas as pd
    from IPython.display import display, Markdown, JSON

    BASE = Path.cwd().resolve()
    PROJECT = next(p for p in [BASE, *BASE.parents] if (p / "V3/data/raw").is_dir())
    V3_DIR = PROJECT / "V3"
    if str(PROJECT) not in sys.path:
        sys.path.insert(0, str(PROJECT))
    from V3.src.c9_analysis import CONFIG, load_inputs, analyze
    from V3.src.c9_publication import stage_results

    data = load_inputs(V3_DIR)
    result = analyze(data, verbose=True)
    report = result["report"]
    display(pd.DataFrame([{
        "contract_id": report["contract_id"],
        "analysis_version": report["schema_version"],
        "shared_validation_analysis_id":
            report["upstream"]["shared_validation_analysis_id"],
        "reads_verified_only":
            report["scope"]["reads_verified_publications_only"],
        "trains_no_models": report["scope"]["trains_no_models"],
    }]))
    """)
    md("""
    ## 1. Linaje de publicaciones

    Los cuadernos 01–08 que alimentan el registro, con su esquema,
    `analysis_id` y el sha256 del puntero leído. La auditoría ETL (01)
    no es un reporte de motor: no lleva `analysis_id` y se registra por
    su hash de archivo.
    """)
    code("""
    display(result["lineage_df"])
    """)
    md("""
    ## 2. Afirmaciones registradas

    Cada afirmación declara su estatus —`hecho_verificado`,
    `comparacion_descriptiva`, `resultado_negativo` o
    `advertencia_de_alcance`—, sus fuentes (reporte, `analysis_id` y
    ruta JSON) y sus salvedades, que nunca están vacías.
    """)
    code("""
    display(result["claims_df"][["id", "tema", "estatus", "enunciado"]])
    for _, row in result["claims_df"].iterrows():
        display(Markdown(f"**{row['id']} · {row['tema']}** — "
                         f"salvedades:"))
        for s in json.loads(row["salvedades_json"]):
            display(Markdown(f"- {s}"))
    """)
    md("""
    ## 3. Certificación del arnés espacial

    El esquema primario `fold_spatial_block` elimina la colindancia
    prueba–entrenamiento con un buffer de 500 m sobre la distancia
    poligonal. La columna `recomputado_after` viene de la verificación
    independiente de este cuaderno (adyacencia poligonal ≤ 1 m
    recalculada desde los artefactos publicados): debe ser 0 en todos
    los folds e igual a lo publicado. La garantía cubre colindancia
    poligonal y buffer de 500 m; no descarta autocorrelación espacial a
    mayores distancias.
    """)
    code("""
    cert = report["certificacion_arnes_espacial"]
    display(pd.Series({
        "certificado": cert["certificado"],
        "suma_pares_after_buffer": cert["suma_pares_after_buffer"],
        "min_train_test_distance_m": cert["min_train_test_distance_m"],
        "buffer_m": cert["buffer_m"],
        "n_blocks": cert["n_blocks"],
        "blocks_contiguous_share": cert["blocks_contiguous_share"],
        "n_adjacency_components": cert["n_adjacency_components"],
        "recomputo_coincide": cert["recomputo"]["coincide_con_publicado"],
    }, name="valor").to_frame())
    display(pd.DataFrame(cert["folds"]))
    display(Markdown("**Referencia optimista** "
                     "(`fold_groupkfold_ageb`, sin buffer): pares "
                     f"colindantes {cert['referencia_optimista_groupkfold']['pares_por_fold']}, "
                     f"suma {cert['referencia_optimista_groupkfold']['suma_pares']}."))
    """)
    md("""
    ## 4. Encuadres corregidos

    Dos encuadres frecuentes que el registro corrige con la evidencia
    publicada: «Ridge domina numéricamente al FT-Transformer» y el
    cociente de tiempos totales no emparejados del GA frente al greedy.
    """)
    code("""
    for e in report["encuadres_corregidos"]:
        display(Markdown(
            f"**{e['id']}** — afirmación original: *{e['afirmacion_original']}* "
            f"({e['estatus_afirmacion_original']}).<br/>"
            f"Encuadre correcto: {e['encuadre_correcto']}"))
        display(pd.DataFrame(
            pd.Series(e["evidencia"], dtype=object), columns=["valor"]))
    """)
    md("""
    ## 5. Ledger de límites

    Unión de las listas `pending_validation` de los reportes 04–08 con
    su origen: toda cifra del registro hereda estas limitaciones.
    """)
    code("""
    display(pd.DataFrame(report["limitations_ledger"]))
    """)
    md("""
    ## 6. Documento ejecutivo y cierre

    `TESIS_DATA_POINTS.md` se genera desde el registro con un léxico
    controlado (sin «domina», «ganador», «demuestra», «óptimo» sin
    negación, ni similitud/cobertura presentadas como demanda) y se
    publica como output sellado más una copia atómica en
    `docs/TESIS_DATA_POINTS.md` tras la activación del puntero.
    """)
    code("""
    doc = report["document"]
    display(pd.Series({
        "documento": doc["output"],
        "sha256": doc["sha256"],
        "copia_docs": doc["docs_copy_path"],
        "lexico_verificado": doc["forbidden_lexicon_checked"],
        "n_claims": len(report["claims"]),
    }, name="valor").to_frame())
    display(Markdown(result["documento"]))
    report_path = stage_results(V3_DIR, data, result)
    display(Markdown("**Cierre.** Registro de afirmaciones sellado: "
                     "toda cifra citable queda ligada a su publicación "
                     "de origen."))
    display(JSON({"c9_report_path": report_path.relative_to(V3_DIR).as_posix()}))
    """)
    return cells
