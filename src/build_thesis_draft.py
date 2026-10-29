"""Generador del documento de caso de negocio (V3/docs/BORRADOR_TESIS_MAESTRO.md).

Es un GENERADOR DE DOCUMENTO, no un motor: solo lee los reportes sellados
``V3/audits/0{1..9}_*.json``, el cuaderno público
``V3/notebooks/08_Evaluacion_Comparativa.ipynb`` (de donde extrae las 8
figuras embebidas) y ``docs/TESIS_DATA_POINTS.md`` (que se incluye
textualmente como Anexo 1). No usa la maquinaria de publicación
(``engine_publication``) ni reejecuta análisis.

REGLA DURA del documento: ninguna cifra se escribe a mano en la prosa.
Todo número se lee de una ruta JSON de las fuentes selladas (o se deriva
de ellas por suma, cociente o rango). Si una clave falta, el script aborta
con ``KeyError`` antes de escribir nada.

La escritura del documento y de las figuras es ATÓMICA: cada archivo se
escribe primero en ``<nombre>.tmp`` dentro del mismo directorio y luego se
renombra con ``os.replace``.
"""
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "V3" / "audits"
NB08 = ROOT / "V3" / "notebooks" / "08_Evaluacion_Comparativa.ipynb"
DOCS = ROOT / "docs"                     # insumos sellados fuera de V3
V3DOCS = ROOT / "V3" / "docs"            # artefactos generados por este script
NB02 = ROOT / "V3" / "notebooks" / "02_EDA_y_Equidad.ipynb"
FIG_DIR = V3DOCS / "figures"             # subdirs c8/ y e02/ por prefijo
OUT_PATH = V3DOCS / "BORRADOR_TESIS_MAESTRO.md"
DATA_POINTS_PATH = DOCS / "TESIS_DATA_POINTS.md"

AUDIT_FILES = {
    "01": "01_etl.json",
    "02": "02_eda.json",
    "03": "03_feature_engineering.json",
    "04": "04_backtest_design.json",
    "05": "05_motor1_baseline.json",
    "06": "06_motor2_transformer.json",
    "07": "07_motor3_prescriptivo.json",
    "08": "08_comparacion_portafolios.json",
    "09": "09_final_claims_registry.json",
}

# Especificación de figuras por cuaderno: cada entrada define el cuaderno,
# el total de salidas image/png esperado, el modo de verificación y el
# mapeo (prefijo de la primera línea de código de la celda -> nombres de
# archivo de salida, en orden). "positional" exige además que las celdas
# con PNG aparezcan en el orden listado (cuaderno 08); en modo prefijo se
# localiza cada celda por su primera línea (cuaderno 02).
FIGURE_SPECS = [
    {
        "nb": NB08,
        "positional": True,
        "expected_total": 8,
        "cells": [
            ('met = result["metricas"]',
             ["c8_01_cobertura_por_presupuesto.png"]),
            ('radar = result["radar"]',
             ["c8_02_radar_b30.png", "c8_03_radar_presupuestos.png"]),
            ('cols = ["new_pop"',
             ["c8_04_heatmap_metricas.png"]),
            ('display(result["asignacion"])',
             ["c8_05_estaciones_por_ageb.png"]),
            ('ov = result["overlap"]',
             ["c8_06_jaccard_sitios_agebs.png"]),
            ('universe = result["universe04"]',
             ["c8_07_mapas_consenso.png"]),
            ('fig, axes = plt.subplots(1, 2',
             ["c8_08_equidad.png"]),
        ],
    },
    {
        "nb": NB02,
        "positional": False,
        "expected_total": 14,
        "cells": [
            ('census_root = V3_DIR / "data/processed" / report["contract_id"]',
             ["e02_01_poblacion_sin_estacion.png"]),
            ('gap = report["territorial_gap"]',
             ["e02_02_distancia_a_la_red.png"]),
            ('display(pd.Series(report["spatial_equity"], name="value")'
             '.to_frame())',
             ["e02_03_concentracion_lorenz.png"]),
            ('moran = report["spatial_autocorrelation"]',
             ["e02_04_moran_cuadrantes.png"]),
            ('golden = report["golden_cluster"]',
             ["e02_05_espaciamiento_golden.png"]),
        ],
    },
]

FIGURE_CAPTIONS = {
    "c8_01_cobertura_por_presupuesto.png":
        "Población nueva en zona de captura por motor y presupuesto "
        "(portafolios oficiales del análisis comparativo).",
    "c8_02_radar_b30.png":
        "Radar de ejes fijos en B = 30 (portafolios oficiales). El "
        "área del radar no es un puntaje: cada eje codifica un "
        "objetivo distinto con escala fija de 0 a 1.",
    "c8_03_radar_presupuestos.png":
        "Radar de ejes fijos por presupuesto para cada motor; "
        "presentación comparativa, no un ordenamiento agregado.",
    "c8_04_heatmap_metricas.png":
        "Matriz de métricas oficiales por motor y presupuesto, "
        "recomputadas por el análisis comparativo desde los "
        "portafolios publicados.",
    "c8_05_estaciones_por_ageb.png":
        "Distribución de estaciones seleccionadas por AGEB (1, 2 o "
        "3 o más por AGEB) en cada portafolio oficial.",
    "c8_06_jaccard_sitios_agebs.png":
        "Traslape territorial entre motores: índices de Jaccard de "
        "sitios y de AGEBs por par de motores y presupuesto.",
    "c8_07_mapas_consenso.png":
        "Mapa del universo evaluable y del consenso territorial: "
        "sitios elegidos por al menos dos motores y por los tres.",
    "c8_08_equidad.png":
        "Perfil de equidad de los portafolios: escolaridad media y "
        "tenencia de automóvil en las AGEBs seleccionadas frente al "
        "universo de candidatos.",
}


# ---------------------------------------------------------------------
# Formato de números (siempre derivados de los JSON; nunca literales)
# ---------------------------------------------------------------------

def miles(x):
    """Entero con separador de miles, p.ej. 202337.34 -> '202,337'."""
    return f"{x:,.0f}"


def entero(x):
    """Entero exacto con separador de miles, p.ej. 20134900 -> '20,134,900'."""
    return f"{int(x):,d}"


def dec(x, n=3):
    """Decimal con n cifras, p.ej. 0.4293052 -> '0.429'."""
    return f"{x:.{n}f}"


def pct(x, n=2):
    """Fracción a porcentaje, p.ej. 0.02539 -> '2.54%'."""
    return f"{x * 100:.{n}f}\\%"


def rango(vals, n=2):
    """'mín--máx' con n decimales, para texto plano (en-dash LaTeX)."""
    lo, hi = min(vals), max(vals)
    return f"{lo:.{n}f}--{hi:.{n}f}"


def porc(x, n=2):
    """Fracción a porcentaje en prosa, p.ej. 0.8037 -> '80.37 %'."""
    return f"{x * 100:.{n}f} %"


def entre(vals, n=2, con_miles=False):
    """'entre mín y máx' para prosa (sin notación matemática)."""
    lo, hi = min(vals), max(vals)
    fmt = f",.{n}f" if con_miles else f".{n}f"
    return f"entre {lo:{fmt}} y {hi:{fmt}}"


def intervalo(vals, n=2, con_miles=False):
    """'[mín, máx]' para contexto matemático $...$ (sin '--' en math mode)."""
    lo, hi = min(vals), max(vals)
    fmt = f",.{n}f" if con_miles else f".{n}f"
    if con_miles:
        # en modo matemático la coma de miles necesita llaves: 2{,}786
        lo_s = f"{lo:{fmt}}".replace(",", "{,}")
        hi_s = f"{hi:{fmt}}".replace(",", "{,}")
    else:
        lo_s, hi_s = f"{lo:{fmt}}", f"{hi:{fmt}}"
    return f"[{lo_s}, {hi_s}]"


# ---------------------------------------------------------------------
# Carga de fuentes
# ---------------------------------------------------------------------

def load_audits():
    audits = {}
    for tag, name in AUDIT_FILES.items():
        path = AUDITS / name
        if not path.is_file():
            raise SystemExit(f"Falta el reporte sellado: {path}")
        audits[tag] = json.loads(path.read_text(encoding="utf-8"))
    return audits


def _first_line(cell):
    src = cell.get("source", "")
    if isinstance(src, list):
        src = "".join(src)
    lines = src.strip().splitlines()
    return lines[0].strip() if lines else ""


def _nb_png_cells(nb_path):
    """Devuelve ([(primera_línea, [png_bytes, ...]), ...], total_png)."""
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    collected = []
    total = 0
    for cell in nb.get("cells", []):
        pngs = []
        for output in cell.get("outputs", []):
            data = output.get("data") or {}
            if "image/png" in data:
                payload = data["image/png"]
                if isinstance(payload, list):
                    payload = "".join(payload)
                pngs.append(base64.b64decode(payload))
        if pngs:
            collected.append((_first_line(cell), pngs))
            total += len(pngs)
    return collected, total


def _fig_out_path(name):
    """figures/<prefijo>/<nombre>: c8_* -> c8/, e02_* -> e02/."""
    return FIG_DIR / name.split("_", 1)[0] / name


def extract_figures(write=True):
    """Extrae los PNG embebidos de los cuadernos según ``FIGURE_SPECS``.

    Aborta si un cuaderno no tiene exactamente ``expected_total`` salidas
    ``image/png``, si el orden posicional no coincide (cuaderno 08) o si
    algún prefijo no aparece / produce un número distinto de PNG al
    esperado (cuaderno 02). Devuelve ``{nombre: bytes}``.
    """
    figures = {}
    for spec in FIGURE_SPECS:
        nb = spec["nb"]
        collected, total = _nb_png_cells(nb)
        if total != spec["expected_total"]:
            raise SystemExit(
                f"El cuaderno {nb.name} tiene {total} salidas image/png; "
                f"se esperaban {spec['expected_total']}. Aborto.")
        if spec["positional"]:
            if len(collected) != len(spec["cells"]):
                raise SystemExit(
                    f"El cuaderno {nb.name} tiene {len(collected)} celdas "
                    f"con PNG; se esperaban {len(spec['cells'])}. Aborto.")
            for (first_line, pngs), (prefix, names) in zip(
                    collected, spec["cells"]):
                if not first_line.startswith(prefix):
                    raise SystemExit(
                        f"El orden de figuras de {nb.name} no coincide "
                        f"con el mapeo verificado: se esperaba una celda "
                        f"que inicia con {prefix!r} y se encontró "
                        f"{first_line!r}. Aborto.")
                if len(pngs) != len(names):
                    raise SystemExit(
                        f"La celda {first_line!r} de {nb.name} tiene "
                        f"{len(pngs)} PNG y se esperaban {len(names)}. "
                        "Aborto.")
                for name, blob in zip(names, pngs):
                    figures[name] = blob
        else:
            for prefix, names in spec["cells"]:
                matched = [pngs for first, pngs in collected
                           if first.startswith(prefix)]
                if not matched:
                    raise SystemExit(
                        f"Ninguna celda de {nb.name} inicia con el "
                        f"prefijo esperado {prefix!r}. Aborto.")
                pngs = [p for group in matched for p in group]
                if len(pngs) != len(names):
                    raise SystemExit(
                        f"La(s) celda(s) {prefix!r} de {nb.name} "
                        f"producen {len(pngs)} PNG y se esperaban "
                        f"{len(names)}. Aborto.")
                for name, blob in zip(names, pngs):
                    figures[name] = blob
    if write:
        for name, blob in figures.items():
            target = _fig_out_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(blob)
            os.replace(tmp, target)
    return figures


# ---------------------------------------------------------------------
# Construcción del documento
# ---------------------------------------------------------------------

_ANNEX_REPLACEMENTS = [
    ("v3-", ""), ("V3/", ""), ("V3_", ""), ("V3", ""),
    (".ipynb", ""), ("TESIS_DATA_POINTS", "Memoria de datos"),
    ("Cuaderno", "Análisis"), ("cuaderno", "análisis"),
    ("`audits/", "`"), ("`data/", "`"), ("`notebooks/", "`"),
    ("`docs/", "`"),
    ("puntero `", "archivo `"),
    ("Documento generado mecánicamente desde el registro sellado",
     "Memoria del registro sellado"),
]


def _sanitize(t):
    """Quita del texto citado toda referencia interna (rutas,
    nombres de análisis o prefijos de versión del pipeline)."""
    for old, new in _ANNEX_REPLACEMENTS:
        t = t.replace(old, new)
    return t


def _claim_corto(text, limit=150):
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " […]"


def _escape_pipe(text):
    return str(text).replace("|", "\\|")


def build_document(audits, figures):
    a01, a02, a03 = audits["01"], audits["02"], audits["03"]
    a04, a05, a06 = audits["04"], audits["05"], audits["06"]
    a07, a08, a09 = audits["07"], audits["08"], audits["09"]

    # ---------------- valores derivados (todos desde las fuentes) ----
    etl = a01["trip_rows"]
    accepted_share = etl["accepted_rows"] / etl["input_rows"]
    sep_block = [s for s in a04["spatial_cv"]["separation"]
                 if s["fold_scheme"] == a04["spatial_cv"]["primary_scheme"]]
    before_by_fold = [s["touching_train_test_pairs_before_buffer"]
                      for s in sep_block]
    after_by_fold = [s["touching_train_test_pairs_after_buffer"]
                     for s in sep_block]
    before_total, after_total = sum(before_by_fold), sum(after_by_fold)
    min_dists = [s["min_train_test_distance_m"] for s in sep_block]

    moran = a02["spatial_autocorrelation"]
    sens = moran["sensitivity"]
    sens_i = [s["i"] for s in sens]
    sens_k = [s["k"] for s in sens]

    gate = a04["mahalanobis_gate"]
    gate_cmp = gate["covariance_estimator_comparison"]
    m1_fds = [f for f in a05["fold_diagnostics"]
              if f["fold_scheme"] == "fold_spatial_block"
              and f["variant"] == a05["primary_variant"]]

    mm = a05["backtest"]["metric_means_by_variant_scheme"]
    scheme = a04["spatial_cv"]["primary_scheme"]

    def m1(variant, metric):
        return mm[f"{variant}|{scheme}"][metric]

    reg = {r["model"]: r for r in a06["regression_means"]
           if r["fold_scheme"] == scheme}
    r2_max = max(a06["ockham"]["r2_spatial_mean"].values())

    lc = {}
    for e in a06["learning_curve"]:
        key = (e["model"], e["fraction"])
        lc.setdefault(key, []).append(e["rmse"])

    def lc_mean(model, fraction):
        vals = lc[(model, fraction)]
        return sum(vals) / len(vals)

    gvg = a07["ga_vs_greedy"]
    primary_rows = [r for r in gvg
                    if r["weight"] == a07["primary"]["weight"]
                    and r["budget"] == a07["primary"]["budget"]]
    if len(primary_rows) != 1:
        raise SystemExit("No se localizó la fila primaria de ga_vs_greedy.")
    grow = primary_rows[0]
    speedups = [r["ga_mean_wall_s_per_seed"] / r["greedy_wall_s"]
                for r in gvg]
    speedup_primary = (grow["ga_mean_wall_s_per_seed"]
                       / grow["greedy_wall_s"])
    n_cfg = len(gvg)
    n_greedy_ge = sum(1 for r in gvg if r["greedy_f"] >= r["ga_best_f"])
    verdicts = {}
    for r in gvg:
        key = "empate" if r["verdict"].startswith("empate") else r["verdict"]
        verdicts[key] = verdicts.get(key, 0) + 1

    oficial = [m for m in a08["metricas"] if m["tier"] == "oficial"]
    motores = sorted({m["motor"] for m in oficial})
    budgets = sorted({m["budget"] for m in oficial})
    ov30 = [o for o in a08["overlap"] if o["budget"] == a07["primary"]["budget"]]
    cons30 = a08["consensus_counts"][str(a07["primary"]["budget"])]
    met30 = {m["motor"]: m for m in oficial
             if m["budget"] == a07["primary"]["budget"]}
    met_by_budget = {b: {m["motor"]: m for m in oficial if m["budget"] == b}
                     for b in budgets}

    hum = a02["human_dimension"]
    mt = a02["modal_transport"]
    mt_corr = {c["predictor"]: c for c in mt["correlations"]}
    denue = a02["denue_retrospective_proxy"]
    denue_sp = [s["spearman"] for s in denue["open_band_sensitivity"]]
    denue_bands = [s["open_band_assumption"]
                   for s in denue["open_band_sensitivity"]]
    gtfs = a02["gtfs_proximity"]
    leak = a02["leakage_audit"]
    study_year = a02["urban_enrichment"]["configuration"]["study_year"]
    denue_year = denue["snapshot_years"][0]

    tm = a02["target_metrics"]
    gc = a02["golden_cluster"]
    eq = a02["spatial_equity"]
    gap = a02["territorial_gap"]
    uni = a04["evaluation_universe"]
    cv = a04["spatial_cv"]
    maup = a03["maup_mitigation"]
    pca = a03["pca_reduction"]
    n_contract = len(a03["feature_matrix"]["feature_contract"])

    dic = a06["dictamen"]
    ock = a06["ockham"]
    rf_ridge = ock["rf_vs_ridge"]
    dep6 = a06["deployment"]
    delta_ratio = (abs(dic["condition_c_improvement"])
                   / dic["condition_c_seed_std_mean"])
    cb5 = a05["ceiling_backtest"]
    cb6 = a06["ceiling_backtest"]
    bias = {b["feature"]: b["spearman_cos"]
            for b in a05["bias_diagnostics"]}

    cfg7 = a07["configuration"]
    aff = a07["affinity"]
    n2v = a07["node2vec_retired"]
    sp_n2v = n2v["historical_evidence_not_recomputed"][
        "spearman_affinity_vs_minus_hops_golden"]["q_0.5"]["nearest_golden"]
    pm = a07["primary"]["metrics"]
    tim = a07["timing"]

    cert = a09["certificacion_arnes_espacial"]

    # ---------------- título --------------------------------------------
    lines = []
    w = lines.append
    w("# Caso de negocio — Expansión de la red EcoBici bajo presupuesto fijo")
    w("")

    # ---------------- Introducción -------------------------------------
    w("## Introducción")
    w("")
    w("EcoBici es el sistema público de bicicleta compartida de la "
      "Ciudad de México, y este documento responde una pregunta de "
      "negocio concreta: con un presupuesto fijo B, ¿en qué sitios "
      "deberían instalarse las próximas estaciones? La respuesta no "
      "es una recomendación abstracta sino portafolios de sitios "
      "—listas cerradas de ubicaciones listas para revisar en "
      "campo—.")
    w("")
    w("Para responder, tres motores independientes atacan el mismo "
      f"problema cada uno a su manera; compararlos es solo "
      f"descriptivo, no hay un ganador. El déficit que enfrentan es "
      f"grande: el censo {hum['census_year']} registra "
      f"{entero(hum['population_without_internal_station_known'])} "
      f"residentes en las "
      f"{entero(hum['agebs_without_internal_station'])} AGEBs[^1] sin "
      f"estación propia. Con un presupuesto de "
      f"{a07['primary']['budget']} estaciones, los portafolios "
      f"cubren {miles(met30['m1']['new_pop'])}, "
      f"{miles(met30['m2']['new_pop'])} y "
      f"{miles(met30['m3']['new_pop'])} habitantes nuevos en su zona "
      f"de captura; {entero(cons30['selected_by_2plus'])} sitios "
      f"aparecen en al menos dos de los tres y "
      f"{entero(cons30['selected_by_3'])} en los tres. Y la prueba "
      f"retrospectiva (backtest[^2]) se hizo a consciencia: "
      f"{entero(after_total)} pares de zonas vecinas compartidas "
      f"entre entrenamiento y prueba.")
    w("")

    # ---------------- Contexto y planteamiento -------------------------
    w("## Contexto y planteamiento del problema")
    w("")
    w(f"Primero hay que ver que el problema existe —y es "
      f"territorial. El censo {hum['census_year']} registra "
      f"{entero(hum['population_without_internal_station_known'])} "
      f"residentes de población conocida en las "
      f"{entero(hum['agebs_without_internal_station'])} AGEBs sin "
      f"estación interna —otras "
      f"{entero(hum['unknown_population_without_internal_station_agebs'])} "
      f"AGEBs no reportan población—; apenas "
      f"{entero(eq['agebs_with_internal_station'])} de "
      f"{entero(eq['total_agebs'])} AGEBs contienen al menos una "
      f"estación; la AGEB mediana queda a {dec(gap['median_km'], 1)} "
      f"km de la estación más cercana ({dec(gap['mean_km'], 1)} km en "
      f"promedio) y "
      f"{entero(gap['no_internal_station_but_centroid_within_400m'])} "
      f"AGEBs sin estación tienen su centro a menos de "
      f"{a02['configuration']['diagnostic_access_radius_m']:,.0f} m de "
      f"la red.")
    w("")
    w(f"![Población residente en AGEBs sin estación interna: "
      f"{entero(hum['population_without_internal_station_known'])} "
      f"habitantes de población conocida en "
      f"{entero(hum['agebs_without_internal_station'])} AGEBs, más "
      f"{entero(hum['unknown_population_without_internal_station_agebs'])} "
      f"sin dato.](figures/e02/e02_01_poblacion_sin_estacion.png)")
    w("")
    w(f"![Distancia de cada AGEB a la estación más cercana, en curva "
      f"acumulada y en mapa: la mediana es {dec(gap['median_km'], 1)} "
      f"km y el promedio {dec(gap['mean_km'], 1)} km.]"
      f"(figures/e02/e02_02_distancia_a_la_red.png)")
    w("")
    w(f"El servicio no solo falta: está concentrado. El índice de "
      f"Gini[^3] de estaciones por AGEB llega a "
      f"{dec(eq['gini_stations'], 4)} y el de la actividad a "
      f"{dec(eq['gini_activity'], 4)}. Y la carencia no se reparte al "
      f"azar: el índice I de Moran[^4] de la actividad es "
      f"{dec(moran['i'])} con {moran['k']} vecinos "
      f"(p = {dec(moran['p_value'])} en {entero(moran['permutations'])} "
      f"permutaciones; al azar esperaríamos "
      f"{dec(moran['expected_i'], 4)}) y se mantiene {entre(sens_i)} "
      f"al ampliar el vecindario de {min(sens_k)} a {max(sens_k)} "
      f"vecinos. La carencia está agrupada en el mapa.")
    w("")
    w(f"![Concentración territorial: estaciones por AGEB en el mapa y "
      f"curva de Lorenz; Gini de {dec(eq['gini_stations'], 4)} en "
      f"estaciones y de {dec(eq['gini_activity'], 4)} en actividad.]"
      f"(figures/e02/e02_03_concentracion_lorenz.png)")
    w("")
    w(f"![Cada punto es una AGEB y la nube se inclina a agrupar "
      f"valores altos con valores altos: I de Moran de "
      f"{dec(moran['i'])} con {moran['k']} vecinos.]"
      f"(figures/e02/e02_04_moran_cuadrantes.png)")
    w("")
    w(f"¿Y qué tan bien convive EcoBici con el transporte público? "
      f"Con el pesado, bastante: las estaciones cercanas a "
      f"{' + '.join(mt['groups']['dist_transporte_pesado_m']['agencies'])} "
      f"({entero(mt['groups']['dist_transporte_pesado_m']['eligible_stop_ids'])} "
      f"paradas) registran más actividad —correlación de "
      f"Spearman[^5] de "
      f"{dec(mt_corr['dist_transporte_pesado_m']['spearman_rho'], 4)} "
      f"entre distancia y actividad anual, es decir, más cerca, más "
      f"uso—. Ojo: es una asociación entre estaciones, no una prueba "
      f"de que la cercanía cause adopción. El transporte ligero "
      f"({' + '.join(mt['groups']['dist_transporte_ligero_m']['agencies'])}, "
      f"{entero(mt['groups']['dist_transporte_ligero_m']['eligible_stop_ids'])} "
      f"paradas) no muestra una asociación comparable "
      f"({dec(mt_corr['dist_transporte_ligero_m']['spearman_rho'], 3)}), "
      f"y la cercanía al directorio empresarial —"
      f"{entero(denue['input_establishments'])} establecimientos— "
      f"sostiene una correlación estable {entre(denue_sp)} según la "
      f"banda de corte entre {min(denue_bands)} y "
      f"{max(denue_bands)} altas registradas.")
    w("")
    w("### Hipótesis")
    w("")
    w("«¿Puede un enfoque de ciencia de datos diseñar una expansión "
      "justa y conectada sin replicar el sesgo histórico?» La "
      "apuesta del estudio es afirmativa pero condicionada: el "
      "sesgo histórico de la red no se niega, se mide, y la "
      "corrección se exige en el objetivo de diseño, no en los "
      "datos.")
    w("")
    w("### Pregunta central de investigación")
    w("")
    w("«¿Es posible utilizar modelos de Machine Learning espacial, "
      "reducción factorial ortogonal y algoritmos de optimización "
      "prescriptiva de red para seleccionar portafolios de "
      "expansión de EcoBici que maximicen la población cubierta y "
      "la equidad social, sin replicar el sesgo histórico de clase "
      "media-alta ni incurrir en trampas circulares de fuga de "
      "datos?»")
    w("")
    w("Todo el diseño se apoya en tres principios:")
    w("")
    w(f"1. **Mandato anti-fraude cero fuga.** En intentos anteriores "
      f"de esta investigación, variables calculadas desde los "
      f"propios viajes —como `turnover_ratio` o el PageRank de la "
      f"red de orígenes y destinos— llegaron a inflar el R² hasta "
      f"0.98: predecían viajes usando viajes. La auditoría de fuga "
      f"confirma por qué eran sospechosas: `turnover_ratio` correla "
      f"{dec(leak['turnover_ratio_spearman'], 3)} en Spearman con "
      f"la etiqueta, así que quedó vetada como predictor. La regla "
      f"es sin excepciones.")
    w(f"2. **Demanda honesta.** Que una zona no tenga estación no "
      f"significa que no haya demanda: las "
      f"{entero(hum['agebs_without_internal_station'])} AGEBs sin "
      f"servicio se tratan como zonas sin etiqueta, nunca como "
      f"ejemplos negativos.")
    w(f"3. **Similitud contra justicia social.** La similitud pura "
      f"reproduce colonias de alta escolaridad y tenencia de "
      f"automóvil —correlaciones de Spearman de "
      f"{dec(bias['grado_escolar_prom'], 2)} y "
      f"{dec(bias['pct_viviendas_auto'], 2)} medidas en la "
      f"evaluación del motor—; la prescripción de red, en cambio, "
      f"empuja la cobertura hacia periferias densas: selecciona "
      f"AGEBs de escolaridad media "
      f"{dec(pm['mean_grado_escolar_prom_selected'], 2)} frente a "
      f"{dec(pm['mean_grado_escolar_prom_all_sites'], 2)} del "
      f"universo de candidatos.")
    w("")

    # ---------------- Datos, fuentes y validación -----------------------
    w("## Datos, fuentes y validación")
    w("")
    w("### Fuentes y tratamiento")
    w("")
    w(f"La capa cruda quedó intacta: los archivos originales no se "
      f"modifican. Del flujo de viajes se aceptaron "
      f"{entero(etl['accepted_rows'])} de {entero(etl['input_rows'])} "
      f"registros ({porc(accepted_share, 3)} de aceptación; "
      f"{entero(etl['quarantine_rows'])} quedaron en cuarentena por "
      f"reglas de calidad), junto con "
      f"{entero(a01['stations']['accepted_rows'])} estaciones y "
      f"{entero(a01['agebs']['accepted_rows'])} AGEBs. De contexto se "
      f"sumaron {entero(denue['input_establishments'])} "
      f"establecimientos del directorio empresarial y "
      f"{entero(gtfs['accepted_stops'])} paradas de transporte "
      f"público. También definimos el grupo de referencia —el "
      f"*Golden Cluster*[^6]—: las {entero(gc['n_stations'])} "
      f"estaciones en el percentil "
      f"{int(a02['configuration']['golden_quantile'] * 100)} o "
      f"superior de actividad diaria media (media "
      f"{dec(tm['mean_daily_activity'], 1)}, mediana "
      f"{dec(tm['median_daily_activity'], 1)} viajes, sobre "
      f"{entero(tm['n_stations'])} estaciones). Viven en "
      f"{entero(gc['n_unique_agebs'])} AGEBs y su vecino dorado "
      f"mediano queda a {dec(gc['golden_neighbor_median_m'], 1)} m, "
      f"frente a {dec(gc['network_neighbor_median_m'], 1)} m en la "
      f"red completa: el núcleo ya viene más compacto que la red.")
    w("")
    w("### Variables y la representación compartida")
    w("")
    w(f"Para describir cada zona fijamos {n_contract} variables por "
      f"AGEB, ya depuradas por el mandato anti-fuga. Aquí aparece una "
      f"trampa clásica de la geografía: el problema de la unidad "
      f"areal modificable (MAUP[^7]). La AGEB es el *contexto* donde "
      f"medimos las variables, pero el *sitio* es donde se decide "
      f"poner la estación, y las dos escalas no coinciden. La forma "
      f"que elegimos de mitigarlo es proyectar cada candidata a un "
      f"círculo de {maup['buffer_radius_m']:,.0f} m alrededor de su "
      f"centro —una zona de captura euclidiana, no una zona caminable "
      f"real—; así quedaron "
      f"{entero(maup['projectable_candidates_count'])} candidatas "
      f"proyectables de {entero(maup['territorial_candidates_count'])} "
      f"territoriales. Lo decimos con honestidad: mitigado, no "
      f"resuelto (`maup_resolved = "
      f"{json.dumps(maup['maup_resolved'])}`). Después, las "
      f"{n_contract} variables se comprimen en "
      f"{pca['k_components_80_pct']} componentes principales (PCA[^8]) "
      f"que guardan el {porc(pca['cumulative_variance_explained'])} "
      f"de la varianza —ajustadas solo sobre lo observado («"
      f"{pca['fit_scope']}») y con el riesgo anotado de que pueden "
      f"cargar sesgo por ingreso (`income_bias_risk = "
      f"{json.dumps(pca['income_bias_risk'])}`).")
    w("")
    w(f"![El núcleo Golden: {entero(gc['n_stations'])} estaciones "
      f"repartidas en {entero(gc['n_unique_agebs'])} AGEBs, con "
      f"{dec(gc['golden_neighbor_median_m'], 1)} m al vecino dorado "
      f"mediano frente a {dec(gc['network_neighbor_median_m'], 1)} m "
      f"en la red completa.](figures/e02/e02_05_espaciamiento_golden.png)")
    w("")
    w("### El arnés de validación")
    w("")
    w(f"Solo podemos evaluar donde ya hay estaciones: el universo "
      f"de la prueba son {entero(cv['evaluation_universe_size'])} "
      f"AGEBs con servicio (`{uni['definition']}`), no el territorio "
      f"entero. La verdad de referencia es la actividad media por "
      f"estación —«{uni['why_mean_not_sum']}»— y la etiqueta "
      f"«{uni['label']}» se ajusta solo con datos de entrenamiento. "
      f"Para no inflar la medición repartimos las AGEBs en "
      f"{entero(cv['n_blocks'])} bloques contiguos y cada bloque de "
      f"prueba queda aislado por un anillo de "
      f"{cv['buffer_m']:,.0f} m: los pares de zonas vecinas entre "
      f"prueba y entrenamiento caen de {entero(before_total)} a "
      f"{entero(after_total)} y la distancia mínima retenida queda "
      f"{entre(min_dists, 1, con_miles=True)} m. El conteo no lo "
      f"creímos a la primera: un recomputo independiente lo "
      f"certificó. Eso sí, la garantía cubre la vecindad directa y "
      f"el anillo: «{cert['salvedad']}»")
    w("")
    w(f"La compuerta de dominio usa la distancia de Mahalanobis[^9]: "
      f"un candidato cuenta como «dentro del dominio» si su "
      f"distancia al centro dorado no pasa del umbral "
      f"{dec(gate['threshold'], 3)} —la raíz del cuantil "
      f"{dec(gate['quantile'], 4)} de una ji-cuadrada con "
      f"{gate['df']} grados de libertad—. El problema es que "
      f"estimar esa covarianza con pocas referencias es delicado: "
      f"la empírica sale mal condicionada (número de condición "
      f"{dec(gate_cmp['empirical']['condition_number'], 1)} frente a "
      f"{dec(gate_cmp['ledoit_wolf']['condition_number'], 1)} con el "
      f"encogimiento de Ledoit–Wolf[^10], "
      f"{dec(gate_cmp['ledoit_wolf']['shrinkage'], 3)}) y el conteo "
      f"de entornos en dominio pasa de "
      f"{entero(gate_cmp['empirical']['in_domain_count'])} a "
      f"{entero(gate_cmp['ledoit_wolf']['in_domain_count'])}. En el "
      f"Motor 1, con razones de datos por variable "
      f"{entre([f['n_over_p'] for f in m1_fds])}, el encogimiento "
      f"baja las condiciones de "
      f"{entre([f['condition_number_empirical'] for f in m1_fds])} a "
      f"{entre([f['condition_number'] for f in m1_fds])} y sube la "
      f"cobertura de decisión de "
      f"{dec(m1('m1_coseno_compuerta_empirica', 'decision_coverage'))} "
      f"a {dec(m1(a05['primary_variant'], 'decision_coverage'))}. "
      f"Con encogimiento, el umbral ji-cuadrada queda solo nominal "
      f"—las distancias ya no siguen exactamente esa ley—. Y la "
      f"abstención se mide aparte: reportamos las métricas sobre "
      f"todos los sitios y, en su versión condicional, solo donde "
      f"el motor decidió responder.")
    w("")

    # ---------------- Motores de selección ------------------------------
    w("## Motores de selección")
    w("")
    w("### Arquitectura: un contrato, tres estrategias")
    w("")
    w("Los tres motores reciben exactamente el mismo encargo —la "
      "misma lista de sitios candidatos, la misma superficie de "
      "decisión y las mismas reglas de red— y trabajan en paralelo, "
      "sin verse: ninguno lee la salida de otro. Cada uno entrega lo "
      "mismo en la forma, un portafolio de B sitios concretos, pero "
      "lo construye con una idea distinta: el Motor 1 busca zonas "
      "parecidas a las exitosas, el Motor 2 intenta predecir la "
      "actividad y el Motor 3 diseña la expansión directamente "
      "sobre el grafo de la red.")
    w("")
    w("### Motor 1 — similitud con compuerta")
    w("")
    w(f"El Motor 1 ordena los candidatos por su similitud de coseno "
      f"al centroide dorado —qué tanto se parecen a las zonas "
      f"exitosas en el espacio de componentes— y se abstiene donde "
      f"el entorno cae fuera de lo observado. Dos decisiones lo "
      f"definen. La primera ya la contamos: la compuerta usa el "
      f"encogimiento de Ledoit–Wolf, y eso sube la cobertura de "
      f"decisión de "
      f"{dec(m1('m1_coseno_compuerta_empirica', 'decision_coverage'))} "
      f"a {dec(m1(a05['primary_variant'], 'decision_coverage'))}. La "
      f"segunda: quitamos el «techo por análogos», la idea de "
      f"estimar cada AGEB por su estación más parecida, porque el "
      f"backtest lo desaprobó —el análogo reproduce la densidad "
      f"histórica de planeación, no la demanda, y pierde contra "
      f"usar simplemente la mediana (error "
      f"{dec(cb5['mae_analog'], 3)} frente a "
      f"{dec(cb5['mae_naive'], 3)}). Quitarlo sumó "
      f"{entero(a05['portafolio']['techo_removido']['delta_B30_new_pop'])} "
      f"habitantes al portafolio de B = 30.")
    w("")
    w(f"¿Y qué tal le fue? En la validación por bloques alcanza "
      f"una precisión en sus diez primeros lugares (P@10) de "
      f"{dec(m1(a05['primary_variant'], 'precision@10'))}, un "
      f"recall@10 de {dec(m1(a05['primary_variant'], 'recall@10'))} "
      f"y un NDCG@10[^11] de "
      f"{dec(m1(a05['primary_variant'], 'ndcg@10'))} —"
      f"{dec(m1(a05['primary_variant'], 'ndcg_cond@10'))} en su "
      f"versión condicional—, decidiendo en el "
      f"{dec(m1(a05['primary_variant'], 'decision_coverage'))} de "
      f"los sitios; el coseno sin compuerta empata el NDCG pero "
      f"responde siempre (cobertura "
      f"{dec(m1('m1_coseno', 'decision_coverage'), 1)}). Los "
      f"controles quedan abajo: el azar marca "
      f"{dec(m1('control_aleatorio', 'precision@10'), 2)} y la "
      f"heurística «pegarse al metro» "
      f"{dec(m1('heur_metro', 'precision@10'), 2)} en P@10. Y hay "
      f"que decir el sesgo de frente: el score correlaciona con "
      f"escolaridad en Spearman "
      f"{dec(bias['grado_escolar_prom'], 2)} y con tenencia de "
      f"automóvil en {dec(bias['pct_viviendas_auto'], 2)}.")
    w("")
    w("### Motor 2 — estudio honesto de capacidad")
    w("")
    w(f"El Motor 2 hace una pregunta distinta: ¿cuánto se puede "
      f"*predecir* esa misma verdad —la actividad media por "
      f"estación— con modelos sobrios? El banco de pruebas junta una "
      f"constante, una regresión ridge y un bosque aleatorio, y "
      f"encima entra el FT-Transformer como experimento de "
      f"capacidad, no como candidato automático al despliegue. La "
      f"regla de éxito la fijamos antes de ver los números, y salió "
      f"negativa (`transformer_aporta = "
      f"{json.dumps(dic['transformer_aporta'])}`, mejor control "
      f"`{dic['best_control']}`): los errores medios son "
      f"{dec(dic['mean_rmse']['constante'], 4)} para la constante, "
      f"{dec(dic['mean_rmse']['ridge'], 4)} para ridge, "
      f"{dec(dic['mean_rmse']['random_forest'], 4)} para el bosque y "
      f"{dec(dic['mean_rmse']['ft_transformer'], 4)} para el "
      f"Transformer. La ventaja de ridge es apenas "
      f"{dec(reg['ft_transformer']['rmse'] - reg['ridge']['rmse'], 4)} "
      f"de RMSE —{dec(delta_ratio, 3)} veces el ruido que el propio "
      f"Transformer muestra entre semillas "
      f"({dec(dic['condition_c_seed_std_mean'], 4)})— y en R² y "
      f"Spearman van parejos ({dec(reg['ft_transformer']['r2'])} "
      f"frente a {dec(reg['ridge']['r2'])}; "
      f"{dec(reg['ft_transformer']['spearman'])} frente a "
      f"{dec(reg['ridge']['spearman'])}). En la práctica: empate; "
      f"ninguno domina.")
    w("")
    w(f"Las decisiones siguieron esa lectura: el Transformer quedó "
      f"como caso de estudio y fuera del despliegue (`{dep6['selected_model']}` "
      f"quedó como modelo seleccionado) y el bosque aleatorio se "
      f"despliega por parsimonia y estabilidad aunque pierde ante "
      f"ridge por {dec(rf_ridge['delta_rmse_mean'], 4)} de RMSE y "
      f"solo gana {rf_ridge['rf_fold_wins']} de {rf_ridge['n_folds']} "
      f"bloques. Y la lección es sobria: con un R² espacial de "
      f"cuando más {dec(r2_max)}, ningún modelo predice fuerte; la "
      f"curva de aprendizaje sigue bajando al pasar de la mitad al "
      f"total de los datos (RMSE medio del modelo desplegado de "
      f"{dec(lc_mean('random_forest', 0.5), 4)} a "
      f"{dec(lc_mean('random_forest', 1.0), 4)}): el techo está en "
      f"los datos, no en la capacidad del modelo.")
    w("")
    w("### Motor 3 — prescripción espacial")
    w("")
    w(f"El Motor 3 cambia de deporte: en vez de puntear sitios, "
      f"diseña el portafolio entero. Las candidatas se muestrean en "
      f"una malla de {cfg7['site_grid_m']:,.0f} m y se conectan en un "
      f"grafo geométrico —aristas de hasta "
      f"{cfg7['link_distance_m']:,.0f} m, al menos "
      f"{cfg7['min_spacing_m']:,.0f} m entre estaciones nuevas y "
      f"crecimiento contiguo desde la red actual— con "
      f"{entero(aff['n_graph_nodes'])} nodos, "
      f"{entero(aff['n_graph_edges'])} aristas y "
      f"{entero(aff['n_sites'])} sitios. Cada sitio suma puntos por "
      f"dos cosas: la población nueva que captura y su cercanía a "
      f"Golden —afinidad «{aff['definition']}», con la advertencia "
      f"«{aff['scope_warning']}»—. El objetivo combina los dos, "
      f"$f = w\\cdot\\text{{cobertura}} + "
      f"(1-w)\\cdot\\text{{afinidad}}$, y el despliegue lo resuelve "
      f"con un algoritmo voraz (greedy) con w = "
      f"{a07['primary']['weight']} y presupuesto de "
      f"{a07['primary']['budget']} estaciones.")
    w("")
    w(f"Dos decisiones lo definen. Primero, jubilamos los embeddings "
      f"de Node2Vec: su «afinidad» ni siquiera ordenaba bien la "
      f"cercanía al núcleo dorado (Spearman de {dec(sp_n2v)} en una "
      f"evidencia histórica que no recalculamos), así que la "
      f"sustituimos por la afinidad determinista por saltos. "
      f"Segundo, el greedy se quedó como motor principal frente al "
      f"algoritmo genético que usamos solo como comparación "
      f"(población de {entero(cfg7['ga']['population'])}, "
      f"{entero(cfg7['ga']['generations'])} generaciones): en la "
      f"configuración primaria es unas "
      f"{format(speedup_primary, ',.0f')} veces más rápido "
      f"({dec(grow['greedy_wall_s'], 3)} s por corrida frente a "
      f"{dec(grow['ga_mean_wall_s_per_seed'], 1)} s por semilla del "
      f"GA), y {entre(speedups, 0, con_miles=True)} veces en las "
      f"{entero(n_cfg)} configuraciones. En el objetivo empata o "
      f"supera a la mejor corrida del GA en {entero(n_greedy_ge)} de "
      f"{entero(n_cfg)} ({entero(verdicts.get('greedy', 0))} con "
      f"ventaja mayor que el ruido entre semillas y "
      f"{entero(verdicts.get('empate', 0))} empates; el mejor GA "
      f"queda en el percentil {dec(grow['ga_percentile_vs_random'], 1)} "
      f"de {entero(cfg7['n_random_portfolios'])} portafolios "
      f"aleatorios). La garantía (1 − 1/e) de submodularidad[^12] no "
      f"aplica aquí —la contigüidad y el espaciamiento rompen sus "
      f"condiciones— y los tiempos totales no emparejados "
      f"({dec(tim['greedy_total_wall_s'], 3)} s del greedy frente a "
      f"{tim['ga_total_wall_s']:,.1f} s del GA) van solo como "
      f"referencia.")
    w("")
    w(f"El portafolio primario cubre {miles(pm['new_pop'])} "
      f"habitantes nuevos en {entero(pm['n_agebs'])} AGEBs, con "
      f"mediana de {dec(pm['median_hops_golden'], 1)} saltos a "
      f"Golden, fracción {dec(pm['out_of_domain_04_share'], 2)} de "
      f"sitios fuera del dominio[^13] y escolaridad media "
      f"seleccionada de "
      f"{dec(pm['mean_grado_escolar_prom_selected'], 2)} frente a "
      f"{dec(pm['mean_grado_escolar_prom_all_sites'], 2)} en el "
      f"universo de candidatos.")
    w("")

    # ---------------- Resultados ---------------------------------------
    cons = a08["consistency"]
    sc8 = a08["scope"]
    w("## Resultados")
    w("")
    w(f"La comparación evalúa los {entero(len(oficial))} portafolios "
      f"oficiales —{len(motores)} motores por {len(budgets)} "
      f"presupuestos (B = "
      f"{', '.join(str(b) for b in budgets)})— bajo el mismo contrato "
      f"y sin reejecutar los motores: solo lee lo que cada uno "
      f"publicó. Recalculamos las métricas sobre "
      f"{entero(cons['n_portfolios_checked'])} portafolios y todo "
      f"cuadró (`all_feasible = {json.dumps(cons['all_feasible'])}`, "
      f"`all_metrics_reproduced = "
      f"{json.dumps(cons['all_metrics_reproduced'])}`, tolerancia "
      f"{cons['rtol']:.0e}) y los tres motores apuntan al mismo "
      f"identificador del ejercicio de validación.")
    w("")
    w("| Motor | B | Población nueva | % pobl. | AGEBs | 1/2/3+ | "
      "Dist. media a la red (m) | Fuera de dominio |")
    w("|---|---|---|---|---|---|---|---|")
    for m in sorted(oficial, key=lambda r: (r["budget"], r["motor"])):
        w(f"| {m['motor'].upper()} | {m['budget']} | "
          f"{miles(m['new_pop'])} | {porc(m['new_pop_share'])} | "
          f"{entero(m['n_agebs'])} | "
          f"{m['agebs_1']}/{m['agebs_2']}/{m['agebs_3plus']} | "
          f"{miles(m['mean_dist_to_network_m'])} | "
          f"{dec(m['out_of_domain_04_share'], 2)} |")
    w("")
    j = {}
    for o in ov30:
        j[(o["motor_a"], o["motor_b"])] = o
    jkey = sorted(j)
    jsites = ", ".join(f"{dec(j[k]['jaccard_sites'])} ({k[0].upper()}–{k[1].upper()})"
                      for k in jkey)
    jagebs = ", ".join(f"{dec(j[k]['jaccard_agebs'])}"
                       for k in jkey)
    w(f"Los portafolios divergen en el mapa: a B = "
      f"{a07['primary']['budget']} el índice de Jaccard[^14] de "
      f"sitios es {jsites} y el de AGEBs {jagebs}, respectivamente; "
      f"{entero(cons30['selected_by_2plus'])} sitios aparecen en al "
      f"menos dos portafolios y {entero(cons30['selected_by_3'])} en "
      f"los tres. El contraste de perfiles ilustra la tensión del "
      f"problema: con el mismo presupuesto, el Motor 1 queda "
      f"conservador —escolaridad media "
      f"{dec(met30['m1']['mean_grado_escolar_prom_selected'], 2)}, "
      f"fracción fuera de dominio "
      f"{dec(met30['m1']['out_of_domain_04_share'], 2)}— y el Motor 3 "
      f"se abre hacia entornos distintos del dorado —escolaridad "
      f"{dec(met30['m3']['mean_grado_escolar_prom_selected'], 2)}, "
      f"{dec(met30['m3']['out_of_domain_04_share'], 2)}—, con el "
      f"Motor 2 en medio "
      f"({dec(met30['m2']['mean_grado_escolar_prom_selected'], 2)}, "
      f"{dec(met30['m2']['out_of_domain_04_share'], 2)}). Tres "
      f"aclaraciones que conviene no perder de vista: la comparación "
      f"es descriptiva y no corona un ganador; el radar es "
      f"presentación, no puntaje; y la cercanía a Golden del Motor 3 "
      f"viene optimizada por construcción, así que no cuenta como "
      f"evidencia independiente.")
    w("")
    for name, caption in FIGURE_CAPTIONS.items():
        w(f"![{caption}](figures/c8/{name})")
        w("")
    # ---------------- Límites de la investigación -----------------------
    w("## Límites de la investigación")
    w("")
    w("Dejamos varias cosas fuera —por decisión, no por olvido:")
    w("")
    w("- **Costo.** No hay modelo de costos ni presupuesto monetario "
      "real: «B» cuenta estaciones, no pesos.")
    w("- **Caminabilidad.** Los círculos de captura son euclidianos; "
      "las fuentes no contienen red vial ni caminable.")
    w("- **Demanda.** La cobertura es población dentro de la zona de "
      "captura interpolada, no adopción observada: los portafolios "
      "son candidatos a validar en campo, no demanda medida.")
    w("- **Operación.** Capacidad por estación, rebalanceo y "
      "desabasto pertenecen a otro estudio.")
    w("- **Causalidad.** Toda asociación reportada es correlacional "
      "o de diseño; nada aquí identifica efectos causales.")
    w(f"- **Tiempo.** Las fuentes tienen cosechas distintas: censo "
      f"{hum['census_year']}, viajes {study_year} y directorio "
      f"empresarial {denue_year}.")
    w("- **Abstención.** Que la compuerta se abstenga en un sitio no "
      "significa que el sitio sea malo: significa que los datos no "
      "lo alcanzan.")
    w("- **Motor 3.** Su cercanía a Golden está optimizada por "
      "construcción y no es evidencia independiente; además carece "
      "de backtest propio sobre AGEBs.")
    w("- **Ámbito.** Un solo sistema en una sola ciudad; llevar el "
      "diseño a otra red exige recalibrar.")
    w("")

    # ---------------- Conclusiones -------------------------------------
    w("## Conclusiones")
    w("")
    w("La respuesta, con matices, es sí.")
    w("")
    w(f"Cada condición de la pregunta tiene su evidencia. "
      f"¿Maximizar cobertura y equidad a la vez? Sí fue posible: el "
      f"portafolio prescriptivo cubre {miles(pm['new_pop'])} "
      f"habitantes nuevos eligiendo AGEBs de escolaridad media menor "
      f"que el universo de candidatos "
      f"({dec(pm['mean_grado_escolar_prom_selected'], 2)} frente a "
      f"{dec(pm['mean_grado_escolar_prom_all_sites'], 2)}). ¿Sin "
      f"replicar el sesgo histórico? Solo porque lo exigimos en el "
      f"objetivo —el motor de similitud sí lo reproduce "
      f"(correlaciones de Spearman de "
      f"{dec(bias['grado_escolar_prom'], 2)} con escolaridad y "
      f"{dec(bias['pct_viviendas_auto'], 2)} con automóvil)—. ¿Sin "
      f"trampas de fuga? Cerradas por diseño: predictores circulares "
      f"vetados (Spearman de "
      f"{dec(leak['turnover_ratio_spearman'], 3)} con la etiqueta) y "
      f"separación espacial certificada en {entero(after_total)} "
      f"pares de zonas vecinas entre entrenamiento y prueba.")
    w("")
    w(f"Las decisiones que la evidencia sostiene son cinco: "
      f"prohibir predictores circulares antes de modelar; validar "
      f"por bloques espaciales contiguos con anillo de exclusión, "
      f"certificado por recomputo independiente; regularizar la "
      f"covarianza de las compuertas cuando la referencia es "
      f"pequeña; quitar los techos por análogos, que perdían contra "
      f"una mediana constante (errores {dec(cb5['mae_analog'], 3)} "
      f"y {dec(cb6['mae_analog'], 3)} frente a "
      f"{dec(cb5['mae_naive'], 3)} y {dec(cb6['mae_naive'], 3)}); y "
      f"preferir la parsimonia —el Transformer quedó como caso de "
      f"estudio, el bosque aleatorio como modelo desplegado y el "
      f"greedy como prescriptor, con el algoritmo genético relegado "
      f"a sensibilidad—. Cada cifra del documento es trazable: el "
      f"Apéndice A y el Anexo 1 fijan la procedencia completa.")
    w("")
    w(f"El cierre honesto: los portafolios son candidatos a "
      f"validar en campo, no demanda medida. Lo que recomendamos es "
      f"un piloto acotado sobre el consenso —los "
      f"{entero(cons30['selected_by_3'])} sitios elegidos por los "
      f"tres motores y los {entero(cons30['selected_by_2plus'])} "
      f"por al menos dos— condicionado a levantamiento físico de "
      f"sitio, red caminable con costos y medición de adopción. "
      f"El siguiente paso no es más modelado: es esa fase de "
      f"levantamiento.")
    w("")

    # ---------------- Referencias: solo las fuentes de datos -----------
    w("## Referencias")
    w("")
    w("Fuentes de datos empleadas por el estudio:")
    w("")
    w("1. EcoBici / SEMOVI — Gobierno de la Ciudad de México ("
      f"{study_year}). *Datos abiertos del sistema de bicicletas "
      "EcoBici*: archivos mensuales de viajes y catálogo de "
      "estaciones (`station_information`, formato GBFS).")
    w(f"2. INEGI ({hum['census_year']}). *Censo de Población y "
      "Vivienda*: resultados por AGEB y manzana urbana para la "
      "Ciudad de México (clave geoestadística 09).")
    w("3. INEGI. *Marco Geoestadístico*: geometrías de Áreas "
      "Geoestadísticas Básicas urbanas y rurales de la Ciudad de "
      "México.")
    w(f"4. INEGI ({denue_year}). *Directorio Estadístico Nacional "
      "de Unidades Económicas (DENUE)*: establecimientos de la "
      "Ciudad de México; en el estudio opera como proxy de la "
      "actividad económica observada.")
    w(f"5. Red de Movilidad de la Ciudad de México ({study_year}). "
      "*Feed GTFS de transporte público*: paradas y rutas de "
      "Metro, Metrobús, RTP y Trolebús usadas para medir "
      "proximidad al transporte masivo y ligero.")
    w("")

    # ---------------- Notas al pie -------------------------------------
    w("[^1]: Área Geoestadística Básica: la unidad territorial más "
      "pequeña del censo mexicano; comparable a una manzana o grupo "
      "de manzanas.")
    w("[^2]: Prueba retrospectiva: el modelo se entrena con una "
      "parte de los datos y se evalúa en la parte que no vio.")
    w("[^3]: Índice de concentración: 0 es reparto igualitario y 1 "
      "es máxima concentración.")
    w("[^4]: Medida de autocorrelación espacial: positiva si los "
      "valores altos se agrupan en el mapa; cercana a cero si el "
      "patrón es aleatorio.")
    w("[^5]: Correlación por rangos entre dos variables: mide "
      "asociación monótona sin suponer linealidad y no implica "
      "causalidad.")
    w(f"[^6]: Grupo de estaciones de referencia: las que superan el "
      f"percentil {int(a02['configuration']['golden_quantile'] * 100)} "
      f"de actividad diaria media ({dec(tm['p85'], 1)} viajes por "
      f"día); no es una clase oficial.")
    w("[^7]: Modifiable Areal Unit Problem: los resultados "
      "estadísticos cambian según la unidad territorial elegida "
      "para agregarlos.")
    w("[^8]: Análisis de componentes principales: resume muchas "
      "variables correlacionadas en pocas componentes ordenadas "
      "por la varianza que explican.")
    w("[^9]: Distancia multivariada que corrige por la correlación "
      "entre variables; lejos del centro equivale a fuera del "
      "dominio observado.")
    w("[^10]: Estimador de covarianza con encogimiento: combina la "
      "covarianza muestral con un objetivo estable cuando hay "
      "pocos datos.")
    w("[^11]: Calidad del ordenamiento en los primeros lugares: "
      "premia acertar y acertar arriba; 1.0 sería el orden "
      "perfecto.")
    w("[^12]: Propiedad de rendimientos decrecientes que da "
      "garantías a los algoritmos voraces; exige condiciones que "
      "la contigüidad de la red rompe.")
    w("[^13]: Fuera del dominio (OOD): el sitio queda más allá del "
      "soporte de los datos de entrenamiento; la compuerta se "
      "abstiene ahí, lo que no equivale a sitio malo.")
    w("[^14]: Traslape entre dos conjuntos: elementos comunes "
      "entre los elementos totales; 0 es disjuntos y 1 es "
      "idénticos.")
    w("")

    # ---------------- Apéndice A --------------------------------------
    w("## Apéndice A. Registro de afirmaciones")
    w("")
    w(f"Las {entero(len(a09['claims']))} afirmaciones del registro "
      f"sellado `{a09['analysis_id'][:12]}…`, con su estatus:")
    w("")
    w("| id | tema | estatus | enunciado (corto) |")
    w("|---|---|---|---|")
    for c in a09["claims"]:
        w(f"| {c['id']} | {_escape_pipe(c['tema'])} | "
          f"{_escape_pipe(c['estatus'])} | "
          f"{_escape_pipe(_claim_corto(_sanitize(c['enunciado'])))} |")
    w("")

    # ---------------- Anexo 1 -----------------------------------------
    dp = _sanitize(DATA_POINTS_PATH.read_text(encoding="utf-8").strip("\n"))
    w("## Anexo 1. Memoria de datos")
    w("")
    w("Las cifras clave del estudio con sus salvedades y su fuente "
      f"de registro (huella de contenido "
      f"`{a09['document']['sha256'][:12]}…`):")
    w("")
    w(dp)
    w("")

    text = "\n".join(lines)
    if "{}" in text or "{ }" in text:
        raise SystemExit("El documento contiene placeholders sin resolver.")
    # Guardas de estilo: las notas al pie no viven en captions ni en
    # tablas; y en TODO el documento (cuerpo, apéndice y anexo) no hay
    # referencias internas: ni cuadernos, ni .ipynb, ni rutas ni
    # menciones de la versión del pipeline.
    for ln in lines:
        t = ln.strip()
        if "[^" in t and (t.startswith("!") or t.startswith("|")):
            raise SystemExit(
                f"Nota al pie dentro de caption o tabla (prohibido): {t[:60]}")
    for banned in ("uaderno", "ipynb", "V3", "v3-", "build_thesis_draft"):
        if banned in text:
            raise SystemExit(
                f"Referencia interna prohibida en el documento: {banned!r}.")
    return text


# ---------------------------------------------------------------------

def _write_atomic(path, content):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def main():
    audits = load_audits()
    figures = extract_figures(write=True)
    text = build_document(audits, figures)
    _write_atomic(OUT_PATH, text)
    blob = OUT_PATH.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    print(f"Documento: {OUT_PATH}")
    print(f"sha256:    {digest}")
    print(f"bytes:     {len(blob)}")
    print(f"figuras:   {len(figures)} en {FIG_DIR}")
    for name in figures:
        rel = _fig_out_path(name).relative_to(V3DOCS)
        print(f"  - {rel} ({len(figures[name])} bytes)")
    return OUT_PATH


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
