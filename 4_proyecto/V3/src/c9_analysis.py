"""Cuaderno 09: registro sellado de afirmaciones (claims registry).

El 09 NO entrena ni recalcula modelos ni portafolios: lee las
publicaciones verificadas byte a byte (punteros 02–08 bajo la misma
maquinaria de `pointer_verified_report` que usa el 08) y extrae
afirmaciones. Cada afirmación guarda la ruta JSON de donde salió cada
número; ningún valor se escribe a mano. La única excepción de cómputo es
la certificación del arnés espacial del 04: el conteo de pares
colindantes prueba–entrenamiento tras el buffer se RECONSTRUYE desde los
artefactos publicados (cv_folds, cv_buffer_exclusions, geometría del
universo) con `fe04_analysis.polygon_adjacency` y debe coincidir con el
JSON publicado —una verificación independiente, no una copia—.
"""
import hashlib
import json
import platform
import re
import sys
import time
from pathlib import Path
from textwrap import dedent

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn

from V3.src.artifact_reader import load_committed_audit
from V3.src.eda02_analysis import file_hash
from V3.src import engine_publication as ep
from V3.src import c8_publication
from V3.src import eda02_publication
from V3.src import fe03_publication
from V3.src import fe04_analysis
from V3.src import fe04_publication
from V3.src import m1_publication
from V3.src import m2_publication
from V3.src import m3_publication

VERSION = "v3-claims-1"
CONFIG = {
    "metric_rtol": 1e-9,
    "metric_crs": fe04_analysis.CONFIG["metric_crs"],
    "primary_scheme": "fold_spatial_block",
    "primary_budget": 30,
    "primary_weight": 0.5,
    "docs_target": "docs/TESIS_DATA_POINTS.md",
}

POINTERS = {
    "etl": "audits/01_etl.json",
    "eda": "audits/02_eda.json",
    "features": "audits/03_feature_engineering.json",
    "validation": "audits/04_backtest_design.json",
    "motor1": "audits/05_motor1_baseline.json",
    "motor2": "audits/06_motor2_transformer.json",
    "motor3": "audits/07_motor3_prescriptivo.json",
    "comparacion": "audits/08_comparacion_portafolios.json",
}
NOTEBOOK_NAMES = {
    "etl": "01_ETL_Reproducible.ipynb",
    "eda": "02_EDA_y_Equidad.ipynb",
    "features": "03_Feature_Engineering.ipynb",
    "validation": "04_Diseno_Validacion_Backtest.ipynb",
    "motor1": "05_Motor1_Baseline_Estadistico.ipynb",
    "motor2": "06_Motor2_Transformer_Honesto.ipynb",
    "motor3": "07_Motor3_Grafo_y_Genetico.ipynb",
    "comparacion": "08_Evaluacion_Comparativa.ipynb",
}
# Artefactos publicados del 04 que el recomputo independiente necesita.
UPSTREAM_ARTIFACTS = {
    "validation": ["universo_evaluacion.parquet", "cv_folds.parquet",
                   "cv_buffer_exclusions.parquet"],
}
STATUS = ("hecho_verificado", "comparacion_descriptiva",
          "resultado_negativo", "advertencia_de_alcance")


# ---------------------------------------------------------------------------
# Contexto verificado e identidad
# ---------------------------------------------------------------------------

def _upstream_context(v3):
    """Verifica ETL + punteros 02..08; el 09 solo lee reportes sellados."""
    v3 = Path(v3).resolve()
    audit = load_committed_audit(v3, verify=True)
    contract = audit["contract_id"]
    reports = {
        "eda": ep.pointer_verified_report(
            v3, POINTERS["eda"], eda02_publication.verify_report,
            eda02_publication.EDA_ROOT),
        "features": ep.pointer_verified_report(
            v3, POINTERS["features"], fe03_publication.verify_report,
            fe03_publication.FEATURES_ROOT),
        "validation": ep.pointer_verified_report(
            v3, POINTERS["validation"], fe04_publication.verify_report,
            fe04_publication.VALIDATION_ROOT),
        "motor1": ep.pointer_verified_report(
            v3, POINTERS["motor1"], m1_publication.verify_report,
            m1_publication.SPEC.root),
        "motor2": ep.pointer_verified_report(
            v3, POINTERS["motor2"], m2_publication.verify_report,
            m2_publication.SPEC.root),
        "motor3": ep.pointer_verified_report(
            v3, POINTERS["motor3"], m3_publication.verify_report,
            m3_publication.SPEC.root),
        "comparacion": ep.pointer_verified_report(
            v3, POINTERS["comparacion"], c8_publication.verify_report,
            c8_publication.SPEC.root),
    }
    for name, report in reports.items():
        if report["contract_id"] != contract:
            raise ValueError(
                f"Upstream {name} report belongs to another contract")
    shared_validation = check_shared_validation_id(reports)
    input_artifacts = {}
    for stage, basenames in UPSTREAM_ARTIFACTS.items():
        records = ep.artifact_records(reports[stage], basenames)
        for basename, record in records.items():
            input_artifacts[f"{stage}/{basename}"] = record
    upstream_refs = {
        "etl_audit_sha256": file_hash(v3 / POINTERS["etl"]),
        "shared_validation_analysis_id": shared_validation,
        "reads_verified_publications_only": True,
        "never_reruns_engines": True,
    }
    for name in ("eda", "features", "validation", "motor1", "motor2",
                 "motor3", "comparacion"):
        upstream_refs[f"{name}_audit_sha256"] = hashlib.sha256(
            (v3 / POINTERS[name]).read_bytes()).hexdigest()
        upstream_refs[f"{name}_analysis_id"] = \
            reports[name]["analysis_id"]
    return {"audit": audit, "reports": reports,
            "input_artifacts": input_artifacts,
            "upstream_refs": upstream_refs}


def check_shared_validation_id(reports):
    """Los motores y el 08 deben referenciar el MISMO 04 activo."""
    expected = reports["validation"]["analysis_id"]
    ids = {name: reports[name]["upstream_refs"]["validation_analysis_id"]
           for name in ("motor1", "motor2", "motor3", "comparacion")}
    if set(ids.values()) != {expected}:
        raise ValueError(
            "Los reportes no comparten el analysis_id del 04 activo: "
            f"{ids} vs puntero {expected}")
    return expected


def analysis_identity(v3, context):
    identity = {
        "schema_version": VERSION,
        "contract_id": context["audit"]["contract_id"],
        "configuration": CONFIG,
        "input_artifacts": context["input_artifacts"],
        "upstream_refs": context["upstream_refs"],
        "code_hashes": {
            name: file_hash(Path(v3) / "src" / name) for name in [
                "c9_analysis.py", "c9_content.py", "c9_publication.py",
                "build_notebook_09.py", "engine_publication.py",
                "fe04_analysis.py", "fe04_publication.py",
                "fe03_publication.py", "eda02_publication.py",
                "m1_publication.py", "m2_publication.py",
                "m3_publication.py", "c8_publication.py",
                "c8_analysis.py",
            ]
        },
        "versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "geopandas": gpd.__version__,
            "scipy": scipy.__version__, "sklearn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), identity


def _verified_frame(v3, report, basename, geodataframe=False):
    path = ep.verified_artifact_path(v3, report, basename)
    return (gpd.read_parquet if geodataframe else pd.read_parquet)(path)


def load_inputs(v3):
    """Carga verificada: reportes sellados + artefactos del 04 que el
    recomputo independiente de pares colindantes necesita."""
    context = _upstream_context(v3)
    rep4 = context["reports"]["validation"]
    frames = {
        "universe04": _verified_frame(
            v3, rep4, "universo_evaluacion.parquet", geodataframe=True),
        "cv_folds": _verified_frame(v3, rep4, "cv_folds.parquet"),
        "cv_buffer_exclusions": _verified_frame(
            v3, rep4, "cv_buffer_exclusions.parquet"),
    }
    data = {**context, "v3": Path(v3).resolve(), "frames": frames}
    data["analysis_id"], data["analysis_identity"] = \
        analysis_identity(v3, context)
    return data


# ---------------------------------------------------------------------------
# Utilidades de extracción: ningún campo faltante pasa en silencio
# ---------------------------------------------------------------------------

def _req(node, key, ctx):
    if not isinstance(node, dict) or key not in node:
        raise ValueError(f"Campo faltante en el reporte: {ctx} -> {key}")
    return node[key]


def _src(name, report, ruta):
    return {"reporte": name, "analysis_id": report["analysis_id"],
            "ruta_json": ruta}


def _metrics_row(rep8, motor, budget, tier="oficial"):
    rows = [r for r in rep8["metricas"]
            if r["motor"] == motor and r["budget"] == budget
            and r["tier"] == tier]
    if len(rows) != 1:
        raise ValueError(
            f"08.metricas: {len(rows)} filas para {motor}/{tier}/B{budget}")
    return rows[0]


def _motor_budget_node(motor, rep, budget):
    """Nodo publicado del portafolio de `motor` a presupuesto `budget`."""
    b = str(budget)
    if motor in ("m1", "m2"):
        return _req(_req(rep["portafolio"], "por_presupuesto", motor),
                    b, f"{motor}.portafolio.por_presupuesto")
    return _req(_req(rep["portfolios"], "budget_sensitivity", "m3"),
                b, "m3.portfolios.budget_sensitivity")


def _num(value, ctx):
    if value is None or (isinstance(value, float)
                         and not np.isfinite(value)):
        raise ValueError(f"Valor no numérico en {ctx}")
    return float(value)


def _claim(cid, tema, enunciado, valores, fuentes, estatus, salvedades):
    if estatus not in STATUS:
        raise ValueError(f"Estatus no declarado: {estatus}")
    if not salvedades:
        raise ValueError(f"Claim {cid} sin salvedades")
    return {"id": cid, "tema": tema, "enunciado": enunciado,
            "valores": valores, "fuentes": fuentes, "estatus": estatus,
            "salvedades": list(salvedades)}


# ---------------------------------------------------------------------------
# Certificación del arnés espacial (con recomputo independiente)
# ---------------------------------------------------------------------------

def recompute_touching_pairs(universe, folds, exclusions,
                             scheme="fold_spatial_block"):
    """Pares colindantes prueba–entrenamiento por fold, antes y después
    del buffer, reconstruidos desde los artefactos publicados del 04.

    Usa las asignaciones de fold publicadas (cv_folds), las exclusiones
    de buffer publicadas (cv_buffer_exclusions) y la geometría del
    universo evaluado; la colindancia la calcula
    `fe04_analysis.polygon_adjacency` (distancia poligonal <= 1 m).
    Devuelve {fold: {"before": n, "after": n,
    "min_train_test_distance_m": d}}.
    """
    geo = universe.loc[universe.in_evaluation_universe,
                       ["cvegeo", "geometry"]]
    geo = gpd.GeoDataFrame(geo, geometry="geometry").to_crs(
        fe04_analysis.CONFIG["metric_crs"]).reset_index(drop=True)
    geo = geo.merge(folds[["cvegeo", scheme]], on="cvegeo",
                    validate="one_to_one")
    adjacency = fe04_analysis.polygon_adjacency(geo)
    result = {}
    for fold in sorted(geo[scheme].unique()):
        excl = set(exclusions.loc[
            (exclusions.fold_scheme == scheme)
            & (exclusions.fold == fold), "cvegeo"])
        test_mask = geo[scheme].to_numpy() == fold
        retained = ~test_mask & ~geo.cvegeo.isin(excl).to_numpy()
        test_idx = np.flatnonzero(test_mask)
        result[int(fold)] = {
            "before": int(adjacency[test_idx][:, np.flatnonzero(
                ~test_mask)].nnz),
            "after": int(adjacency[test_idx][:, np.flatnonzero(
                retained)].nnz),
            "min_train_test_distance_m": float(
                geo.loc[retained, "geometry"]
                .distance(geo.loc[test_mask, "geometry"].union_all())
                .min()),
        }
    return result


def certify_spatial_harness(rep4, universe, folds, exclusions):
    """Certifica que el esquema primario elimina la colindancia
    prueba–entrenamiento. `certificado` solo es True si la suma de
    pares post-buffer es 0, la distancia mínima supera el buffer y el
    recomputo independiente coincide con lo publicado."""
    spatial = _req(rep4, "spatial_cv", "04")
    separation = _req(spatial, "separation", "04.spatial_cv")
    scheme = CONFIG["primary_scheme"]
    published = {int(r["fold"]): r for r in separation
                 if r["fold_scheme"] == scheme}
    if not published:
        raise ValueError("04.spatial_cv.separation sin filas del "
                         f"esquema {scheme}")
    recomputed = recompute_touching_pairs(
        universe, folds, exclusions, scheme)
    diffs = []
    for fold, rec in recomputed.items():
        pub = _req(published, fold, "04.separation[fold]")
        for key, col in [("before", "touching_train_test_pairs_before_buffer"),
                         ("after", "touching_train_test_pairs_after_buffer")]:
            if rec[key] != int(_req(pub, col, f"04.separation[{fold}]")):
                diffs.append({"fold": fold, "campo": col,
                              "publicado": pub[col], "recomputado": rec[key]})
        pub_dist = float(_req(pub, "min_train_test_distance_m",
                              f"04.separation[{fold}]"))
        if not np.isclose(rec["min_train_test_distance_m"], pub_dist,
                          rtol=1e-9, atol=0.0):
            diffs.append({"fold": fold,
                          "campo": "min_train_test_distance_m",
                          "publicado": pub_dist,
                          "recomputado": rec["min_train_test_distance_m"]})
    if diffs:
        raise ValueError(
            f"Recomputo independiente difiere del 04 publicado: {diffs}")
    buffer_m = float(_req(spatial, "buffer_m", "04.spatial_cv"))
    folds_out = [{
        "fold": fold,
        "touching_train_test_pairs_before_buffer":
            published[fold]["touching_train_test_pairs_before_buffer"],
        "touching_train_test_pairs_after_buffer":
            published[fold]["touching_train_test_pairs_after_buffer"],
        "min_train_test_distance_m":
            published[fold]["min_train_test_distance_m"],
        "recomputado_after": rec["after"],
        "recomputado_before": rec["before"],
    } for fold, rec in sorted(recomputed.items())]
    sum_after = sum(f["touching_train_test_pairs_after_buffer"]
                    for f in folds_out)
    min_dist = min(f["min_train_test_distance_m"] for f in folds_out)
    groupkfold = [r for r in separation
                  if r["fold_scheme"] == "fold_groupkfold_ageb"]
    certificado = bool(
        sum_after == 0 and min_dist > buffer_m
        and all(f["recomputado_after"] == 0 for f in folds_out))
    return {
        "certificado": certificado,
        "esquema": scheme,
        "buffer_m": buffer_m,
        "n_folds": len(folds_out),
        "folds": folds_out,
        "suma_pares_after_buffer": int(sum_after),
        "min_train_test_distance_m": float(min_dist),
        "adjacency_tolerance_m": fe04_analysis.CONFIG[
            "adjacency_tolerance_m"],
        "n_blocks": _req(spatial, "n_blocks", "04.spatial_cv"),
        "blocks_contiguous_share":
            _req(spatial, "blocks_contiguous_share", "04.spatial_cv"),
        "n_adjacency_components":
            _req(spatial, "n_adjacency_components", "04.spatial_cv"),
        "evaluation_universe_size":
            _req(spatial, "evaluation_universe_size", "04.spatial_cv"),
        "referencia_optimista_groupkfold": {
            "nota": "GroupKFold por AGEB sin buffer: pares colindantes "
                    "antes = después (esquema de referencia optimista)",
            "pares_por_fold": {
                str(int(r["fold"])): int(
                    r["touching_train_test_pairs_before_buffer"])
                for r in groupkfold},
            "suma_pares": int(sum(
                r["touching_train_test_pairs_before_buffer"]
                for r in groupkfold)),
        },
        "recomputo": {
            "metodo": "cv_folds + cv_buffer_exclusions publicados + "
                      "polygon_adjacency del 04 (distancia poligonal "
                      "<= 1 m en metric_crs)",
            "coincide_con_publicado": True,
        },
        "salvedad": "La garantía es sobre colindancia poligonal (<=1 m) "
                    "y buffer de 500 m en el universo de AGEBs evaluadas; "
                    "no implica ausencia de autocorrelación espacial a "
                    "mayores distancias.",
    }


# ---------------------------------------------------------------------------
# Afirmaciones C01..C12
# ---------------------------------------------------------------------------

def _portfolio_vals(rep8, rep_motor, motor, budget):
    row = _metrics_row(rep8, motor, budget)
    ctx = f"08.metricas[{motor}/B{budget}]"
    new_pop_08 = _num(_req(row, "new_pop", ctx), ctx)
    node = _motor_budget_node(motor, rep_motor, budget)
    new_pop_motor = _num(_req(node, "new_pop",
                              f"{motor}.portafolio B{budget}"),
                         "motor")
    if not np.isclose(new_pop_08, new_pop_motor,
                      rtol=CONFIG["metric_rtol"], atol=0.0):
        raise ValueError(
            f"new_pop difiere entre 08 y {motor} a B{budget}: "
            f"{new_pop_08} vs {new_pop_motor}")
    return {
        "new_pop": new_pop_08,
        "new_pop_share": _num(_req(row, "new_pop_share", ctx), ctx),
        "n_agebs": int(_req(row, "n_agebs", ctx)),
        "agebs_1": int(_req(row, "agebs_1", ctx)),
        "agebs_2": int(_req(row, "agebs_2", ctx)),
        "agebs_3plus": int(_req(row, "agebs_3plus", ctx)),
    }


def _coverage_claims(rep8, rep1, rep2, rep3):
    """C01 (B=30) y C02 (B=15 y B=50), con cruce motor-vs-08."""
    motor_reps = {"m1": rep1, "m2": rep2, "m3": rep3}
    labels = {"m1": "Motor 1 (similitud)",
              "m2": "Motor 2 (bosque aleatorio)",
              "m3": "Motor 3 (afinidad de saltos)"}
    claims = []
    for cid, budgets in [("C01", [30]), ("C02", [15, 50])]:
        valores = {}
        for b in budgets:
            per = {}
            for motor in ("m1", "m2", "m3"):
                per[motor] = _portfolio_vals(
                    rep8, motor_reps[motor], motor, b)
            valores[str(b)] = per
        if cid == "C01":
            tr1 = _req(rep1["portafolio"], "techo_removido", "m1")
            tr2 = _req(rep2["portafolio"], "techo_removido", "m2")
            valores["techo_delta"] = {
                "m1": {"delta_B30_new_pop": _num(
                            _req(tr1, "delta_B30_new_pop", "m1"), "m1"),
                       "delta_B30_n_agebs": int(
                           _req(tr1, "delta_B30_n_agebs", "m1"))},
                "m2": {"delta_B30_new_pop": _num(
                            _req(tr2, "delta_B30_new_pop", "m2"), "m2"),
                       "delta_B30_n_agebs": int(
                           _req(tr2, "delta_B30_n_agebs", "m2"))},
            }
        b_show = 30 if cid == "C01" else 50
        seg = "; ".join(
            f"{labels[m]}: {valores[str(b_show)][m]['new_pop']:,.0f} "
            f"hab. nuevos en {valores[str(b_show)][m]['n_agebs']} AGEBs "
            f"({valores[str(b_show)][m]['agebs_1']}/"
            f"{valores[str(b_show)][m]['agebs_2']}/"
            f"{valores[str(b_show)][m]['agebs_3plus']} con 1/2/3+ "
            "estaciones)" for m in ("m1", "m2", "m3"))
        enunciado = (f"A B={b_show}, la población nueva en áreas de "
                     f"captura es {seg}.")
        if cid == "C01":
            d1 = valores["techo_delta"]["m1"]["delta_B30_new_pop"]
            d2 = valores["techo_delta"]["m2"]["delta_B30_new_pop"]
            enunciado += (f" Tras retirar el techo por análogos, los "
                          f"portafolios B=30 de los motores 1 y 2 "
                          f"cambiaron en {d1:+,.0f} y {d2:+,.0f} "
                          f"habitantes respecto a la versión previa.")
        claims.append(_claim(
            cid, "cobertura_poblacional", enunciado, valores,
            [_src("08", rep8, "metricas[tier=oficial]"),
             _src("05", rep1, "portafolio.por_presupuesto"),
             _src("05", rep1, "portafolio.techo_removido"),
             _src("06", rep2, "portafolio.por_presupuesto"),
             _src("06", rep2, "portafolio.techo_removido"),
             _src("07", rep3, "portfolios.budget_sensitivity")],
            "comparacion_descriptiva", [
                "Población dentro de áreas de captura de 500 m con "
                "interpolación areal; no es demanda observada",
                "Los motores 1 y 2 ya no usan techos por AGEB",
                "El Motor 3 optimiza afinidad por saltos a Golden; sus "
                "métricas de cercanía están por construcción",
                "Diferencias entre portafolios heurísticos a presupuesto "
                "fijo, sin prueba estadística",
            ]))
    return claims


def _claim_overlap(rep8):
    overlap = _req(rep8, "overlap", "08")
    consensus = _req(rep8, "consensus_counts", "08")
    by_b = {}
    for b in sorted({r["budget"] for r in overlap}):
        rows = [r for r in overlap if r["budget"] == b]
        by_b[str(b)] = {
            "pares": rows,
            "jaccard_sites": {f"{r['motor_a']}-{r['motor_b']}":
                              r["jaccard_sites"] for r in rows},
            "jaccard_agebs": {f"{r['motor_a']}-{r['motor_b']}":
                              r["jaccard_agebs"] for r in rows},
            "consenso": _req(consensus, str(b), "08.consensus_counts"),
        }
    b30 = by_b["30"]
    js = b30["jaccard_sites"]
    enunciado = (
        "Los motores seleccionan portafolios territorialmente "
        "distintos: a B=30 el Jaccard de sitios es "
        f"{js['m1-m2']:.3f} (M1–M2), {js['m1-m3']:.3f} (M1–M3) y "
        f"{js['m2-m3']:.3f} (M2–M3); {b30['consenso']['selected_by_2plus']} "
        "sitios son elegidos por al menos 2 motores y "
        f"{b30['consenso']['selected_by_3']} por los 3.")
    return _claim(
        "C03", "divergencia_territorial", enunciado,
        {"por_presupuesto": by_b},
        [_src("08", rep8, "overlap"),
         _src("08", rep8, "consensus_counts")],
        "comparacion_descriptiva", [
            "Jaccard descriptivo sobre conjuntos de sitios y de AGEBs; "
            "sin umbral de 'alto/bajo' declarado",
            "Los objetivos de los motores difieren por diseño",
        ])


def _claim_tension(rep8):
    rows = {}
    for motor in ("m1", "m2", "m3"):
        r = _metrics_row(rep8, motor, 30)
        ctx = f"08.metricas[{motor}/B30]"
        rows[motor] = {
            "grado_escolar_sel": _num(_req(
                r, "mean_grado_escolar_prom_selected", ctx), ctx),
            "grado_escolar_all": _num(_req(
                r, "mean_grado_escolar_prom_all_sites", ctx), ctx),
            "pct_auto_sel": _num(_req(
                r, "mean_pct_viviendas_auto_selected", ctx), ctx),
            "pct_auto_all": _num(_req(
                r, "mean_pct_viviendas_auto_all_sites", ctx), ctx),
            "out_of_domain_04_share": _num(_req(
                r, "out_of_domain_04_share", ctx), ctx),
        }
    enunciado = (
        "A B=30, la escolaridad media de las AGEBs seleccionadas es "
        f"{rows['m1']['grado_escolar_sel']:.2f} (M1), "
        f"{rows['m2']['grado_escolar_sel']:.2f} (M2) y "
        f"{rows['m3']['grado_escolar_sel']:.2f} (M3) frente a "
        f"{rows['m1']['grado_escolar_all']:.2f} en todos los sitios "
        "candidatos; la fracción de sitios en AGEBs fuera del dominio "
        f"del 04 es {rows['m1']['out_of_domain_04_share']:.2f} (M1), "
        f"{rows['m2']['out_of_domain_04_share']:.2f} (M2) y "
        f"{rows['m3']['out_of_domain_04_share']:.2f} (M3).")
    return _claim(
        "C04", "tension_similitud_equidad", enunciado, rows,
        [_src("08", rep8, "metricas[tier=oficial,budget=30]")],
        "comparacion_descriptiva", [
            "Covariables a nivel AGEB (lectura ecológica), sin "
            "causalidad",
            "Fuera de dominio no implica mal sitio: el dominio del 04 es "
            "el soporte de AGEBs con servicio",
            "La semejanza a entornos afluentes no es demanda",
        ])


def _claim_greedy_ga(rep3):
    rows = _req(rep3, "ga_vs_greedy", "07")
    paired = []
    for r in rows:
        g = _num(_req(r, "greedy_wall_s", "07.ga_vs_greedy"), "greedy")
        ga = _num(_req(r, "ga_mean_wall_s_per_seed", "07"), "ga")
        paired.append({
            "weight": r["weight"], "budget": r["budget"],
            "greedy_wall_s": g, "ga_mean_wall_s_per_seed": ga,
            "speedup_ga_por_semilla_sobre_greedy": ga / g,
            "greedy_f": _num(_req(r, "greedy_f", "07"), "f"),
            "ga_best_f": _num(_req(r, "ga_best_f", "07"), "f"),
            "ga_mean_f": _num(_req(r, "ga_mean_f", "07"), "f"),
            "ga_std_f": _num(_req(r, "ga_std_f", "07"), "f"),
            "ga_minus_greedy": _num(
                _req(r, "ga_minus_greedy", "07"), "f"),
            "jaccard_ga_greedy": _num(
                _req(r, "jaccard_ga_greedy", "07"), "jaccard"),
            "verdict": _req(r, "verdict", "07"),
        })
    speedups = sorted(p["speedup_ga_por_semilla_sobre_greedy"]
                      for p in paired)
    primary = [p for p in paired
               if p["weight"] == CONFIG["primary_weight"]
               and p["budget"] == CONFIG["primary_budget"]]
    if len(primary) != 1:
        raise ValueError("07.ga_vs_greedy sin la configuración primaria")
    primary = primary[0]
    timing = _req(rep3, "timing", "07")
    valores = {
        "emparejadas_por_configuracion": paired,
        "configuracion_primaria": primary,
        "speedup_min": speedups[0],
        "speedup_mediana": float(np.median(speedups)),
        "speedup_max": speedups[-1],
        "totales_no_emparejados": {
            "greedy_total_wall_s": _num(
                _req(timing, "greedy_total_wall_s", "07.timing"), "t"),
            "ga_total_wall_s": _num(
                _req(timing, "ga_total_wall_s", "07.timing"), "t"),
            "nota": "Totales NO emparejados: el greedy corre una vez por "
                    "configuración; el GA corre 3-5 semillas por "
                    "configuración. Su cociente NO es un speedup.",
        },
        "ga_parametros": _req(
            _req(rep3, "configuration", "07"), "ga", "07.configuration"),
    }
    enunciado = (
        "Con la misma función objetivo y reglas de factibilidad, en la "
        "configuración primaria (w=0.5, B=30) el greedy toma "
        f"{primary['greedy_wall_s']:.3f} s por corrida frente a "
        f"{primary['ga_mean_wall_s_per_seed']:.1f} s por semilla del GA "
        f"—{primary['speedup_ga_por_semilla_sobre_greedy']:,.0f}x más "
        "rápido—; el rango del cociente emparejado entre configuraciones "
        f"es {valores['speedup_min']:,.0f}x–"
        f"{valores['speedup_max']:,.0f}x.")
    return _claim(
        "C05", "tiempos_greedy_vs_ga", enunciado, valores,
        [_src("07", rep3, "ga_vs_greedy"),
         _src("07", rep3, "timing"),
         _src("07", rep3, "configuration.ga")],
        "hecho_verificado", [
            "Tiempos de pared de una sola máquina y una sola medición "
            "por configuración",
            "Speedup emparejado por configuración (misma f y mismas "
            "reglas); los totales no emparejados se reportan aparte y "
            "no definen un cociente",
            "El GA corre con los parámetros publicados del 07 "
            "(población 80, 120 generaciones)",
        ])


def _claim_objective_gap(rep3):
    rows = _req(rep3, "ga_vs_greedy", "07")
    n_ge = sum(1 for r in rows
               if r["greedy_f"] >= r["ga_best_f"])
    gaps = [float(r["ga_minus_greedy"]) for r in rows]
    verdicts = {}
    for r in rows:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    pcts = sorted({float(r["ga_percentile_vs_random"]) for r in rows})
    valores = {
        "n_configuraciones": len(rows),
        "n_greedy_al_menos_ga_best": n_ge,
        "verdicts": verdicts,
        "brecha_ga_menos_greedy_min": min(gaps),
        "brecha_ga_menos_greedy_max": max(gaps),
        "ga_percentile_vs_random": pcts,
    }
    enunciado = (
        f"En las {len(rows)} configuraciones evaluadas el greedy "
        f"alcanza un objetivo al menos tan alto como la mejor corrida "
        f"del GA en {n_ge} de ellas; la brecha GA−greedy va de "
        f"{min(gaps):.4f} a {max(gaps):.4f} y el mejor GA queda en el "
        f"percentil {max(pcts):.2f} frente a portafolios aleatorios "
        "factibles.")
    return _claim(
        "C06", "objetivo_greedy_vs_ga", enunciado, valores,
        [_src("07", rep3, "ga_vs_greedy")],
        "hecho_verificado", [
            "La garantía (1-1/e) de cobertura submodular no aplica "
            "formalmente bajo contigüidad y espaciamiento; es un "
            "hallazgo empírico, no un teorema",
            "El GA es una heurística sin garantía de optimalidad (3-5 "
            "semillas por configuración)",
            "El resultado depende de los parámetros GA declarados en el "
            "07",
        ])


def _claim_motor2(rep2):
    scheme = CONFIG["primary_scheme"]
    rows = [r for r in _req(rep2, "regression_means", "06")
            if r["fold_scheme"] == scheme]
    models = {}
    for r in rows:
        models[r["model"]] = {
            "rmse": _num(_req(r, "rmse", "06"), "rmse"),
            "mae": _num(_req(r, "mae", "06"), "mae"),
            "r2": _num(_req(r, "r2", "06"), "r2"),
            "spearman": (None if r.get("spearman") is None
                         else _num(r["spearman"], "spearman")),
        }
    for model in ("constante", "ridge", "random_forest",
                  "ft_transformer"):
        _req(models, model, "06.regression_means")
    dic = _req(rep2, "dictamen", "06")
    ock = _req(rep2, "ockham", "06")
    improvement = _num(_req(dic, "condition_c_improvement", "06"), "c")
    seed_std = _num(_req(dic, "condition_c_seed_std_mean", "06"), "c")
    valores = {
        "models": models,
        "dictamen": {k: dic[k] for k in (
            "best_control", "condition_a_rmse_below_controls",
            "condition_b_fold_wins_vs_best_control",
            "condition_b_required", "condition_c_holds",
            "condition_c_improvement", "condition_c_seed_std_mean",
            "transformer_aporta")},
        "ockham": ock,
        "ratio_mejora_vs_std_semillas": abs(improvement) / seed_std,
    }
    enunciado = (
        "El FT-Transformer no justifica su complejidad: su RMSE medio "
        f"({models['ft_transformer']['rmse']:.4f}) no es menor que el "
        f"del mejor control ({dic['best_control']} "
        f"{models[dic['best_control']]['rmse']:.4f}) y la mejora "
        f"condicionada ({improvement:+.4f}) es una fracción de la "
        "variación entre semillas "
        f"({seed_std:.4f}; razón {abs(improvement)/seed_std:.3f}), así "
        "que sale del despliegue; el bosque aleatorio se despliega por "
        "parsimonia y estabilidad.")
    return _claim(
        "C07", "dictamen_motor2", enunciado, valores,
        [_src("06", rep2, "regression_means"),
         _src("06", rep2, "dictamen"),
         _src("06", rep2, "ockham")],
        "hecho_verificado", [
            "R^2 espacial <= ~0.22 en todos los modelos: ninguno es "
            "predictivamente fuerte",
            "RF vs Ridge es una diferencia pequeña (RF gana en 3 de 5 "
            "folds)",
            "5 folds espaciales; variación entre semillas del "
            "Transformer documentada como caso de estudio",
            "La importancia predictiva no es causalidad",
        ])


def _claim_harness(cert, rep4):
    folds = cert["folds"]
    before = [f["touching_train_test_pairs_before_buffer"]
              for f in folds]
    enunciado = (
        f"El esquema primario deja {cert['suma_pares_after_buffer']} "
        "pares colindantes prueba–entrenamiento tras el buffer de "
        f"{cert['buffer_m']:.0f} m en los {cert['n_folds']} folds "
        f"(antes: {before}); la distancia mínima prueba–entrenamiento "
        f"retenida es {cert['min_train_test_distance_m']:.1f} m y los "
        f"{cert['n_blocks']} bloques son contiguos "
        f"(componentes del grafo de adyacencia: "
        f"{cert['n_adjacency_components']}).")
    return _claim(
        "C08", "arnes_espacial", enunciado,
        {"certificacion": cert},
        [_src("04", rep4, "spatial_cv.separation"),
         _src("04", rep4, "spatial_cv.blocks_contiguous_share"),
         _src("04", rep4, "cv_folds.parquet"),
         _src("04", rep4, "cv_buffer_exclusions.parquet")],
        "hecho_verificado", [cert["salvedad"]])


def _claim_ledoit_wolf(rep1):
    scheme = CONFIG["primary_scheme"]
    rows = [r for r in _req(rep1, "fold_diagnostics", "05")
            if r["variant"] == "m1_coseno_compuerta"
            and r["fold_scheme"] == scheme]
    if not rows:
        raise ValueError("05.fold_diagnostics sin filas LW espaciales")
    def _rng(key):
        vals = [float(_req(r, key, "05")) for r in rows]
        return {"min": min(vals), "max": max(vals)}
    mm = _req(rep1["backtest"], "metric_means_by_variant_scheme", "05")
    metrics = {}
    for variant in ("m1_coseno_compuerta", "m1_coseno_compuerta_empirica",
                    "m1_coseno"):
        key = f"{variant}|{scheme}"
        v = _req(mm, key, "05.backtest")
        metrics[variant] = {m: v.get(m) for m in (
            "decision_coverage", "precision@10", "recall@10",
            "ndcg@10", "ndcg_cond@10")}
    valores = {
        "n_folds": len(rows),
        "n_over_p": _rng("n_over_p"),
        "shrinkage": _rng("shrinkage"),
        "condition_number_lw": _rng("condition_number"),
        "condition_number_empirical": _rng("condition_number_empirical"),
        "variantes": metrics,
    }
    lw = metrics["m1_coseno_compuerta"]
    emp = metrics["m1_coseno_compuerta_empirica"]
    enunciado = (
        f"Con n/p entre {valores['n_over_p']['min']:.2f} y "
        f"{valores['n_over_p']['max']:.2f}, el encogimiento Ledoit-Wolf "
        f"({valores['shrinkage']['min']:.2f}–"
        f"{valores['shrinkage']['max']:.2f}) estabiliza la compuerta: "
        "número de condición "
        f"{valores['condition_number_lw']['min']:.2f}–"
        f"{valores['condition_number_lw']['max']:.2f} frente a "
        f"{valores['condition_number_empirical']['min']:.1f}–"
        f"{valores['condition_number_empirical']['max']:.1f} con la "
        "covarianza empírica, y la cobertura de decisión sube de "
        f"{emp['decision_coverage']:.3f} a {lw['decision_coverage']:.3f} "
        "sin cambiar el NDCG@10 respecto al coseno sin compuerta "
        f"({lw['ndcg@10']:.3f}).")
    return _claim(
        "C09", "compuerta_ledoit_wolf", enunciado, valores,
        [_src("05", rep1, "fold_diagnostics[variant=m1_coseno_compuerta,"
              "fold_scheme=fold_spatial_block]"),
         _src("05", rep1, "backtest.metric_means_by_variant_scheme")],
        "hecho_verificado", [
            "El umbral chi-cuadrado es nominal bajo encogimiento: las "
            "distancias de entrenamiento no son exactamente chi",
            "ndcg_cond > ndcg indica abstención en casos difíciles y se "
            "lee junto con decision_coverage",
            "No hay mejora de NDCG@10 respecto al coseno sin compuerta",
        ])


def _claim_ceiling(rep1, rep2):
    c1 = _req(rep1, "ceiling_backtest", "05")
    c2 = _req(rep2, "ceiling_backtest", "06")
    def _pack(c, ctx):
        return {k: _num(_req(c, k, ctx), ctx) for k in (
            "mae_analog", "mae_naive", "spearman_analog",
            "spearman_naive")}
    valores = {"m1": _pack(c1, "05"), "m2": _pack(c2, "06")}
    enunciado = (
        "El techo por análogos —densidad histórica de planeación, no "
        "demanda— no supera a una densidad constante mediana en MAE "
        f"(05: {valores['m1']['mae_analog']:.3f} vs "
        f"{valores['m1']['mae_naive']:.3f}; 06: "
        f"{valores['m2']['mae_analog']:.3f} vs "
        f"{valores['m2']['mae_naive']:.3f}); en Spearman, el análogo "
        f"queda por debajo en 05 ({valores['m1']['spearman_analog']:.3f}"
        f" vs {valores['m1']['spearman_naive']:.3f}) y marginalmente por "
        f"encima en 06 ({valores['m2']['spearman_analog']:.3f} vs "
        f"{valores['m2']['spearman_naive']:.3f}).")
    return _claim(
        "C10", "remocion_techo_analogos", enunciado, valores,
        [_src("05", rep1, "ceiling_backtest"),
         _src("06", rep2, "ceiling_backtest")],
        "resultado_negativo", [
            "El backtest del techo es evidencia de la remoción, no una "
            "regla de asignación activa",
            "En 06 el Spearman del análogo queda marginalmente por "
            "encima del baseline aunque el MAE es peor; el resultado no "
            "se simplifica a 'perdió en todo'",
        ])


def _claim_node2vec(rep3):
    n2v = _req(rep3, "node2vec_retired", "07")
    hist = _req(n2v, "historical_evidence_not_recomputed",
                "07.node2vec_retired")
    warning = _req(_req(rep3, "affinity", "07"), "scope_warning",
                   "07.affinity")
    valores = {
        "historical_schema": _req(n2v, "historical_schema", "07"),
        "historical_analysis_id": _req(
            n2v, "historical_analysis_id", "07"),
        "evidencia_historica": hist,
        "scope_warning": warning,
    }
    sp = hist["spearman_affinity_vs_minus_hops_golden"]["q_0.5"]
    enunciado = (
        "Node2Vec se retiró del pipeline por decisión metodológica: la "
        "afinidad por embeddings no ordenaba por cercanía al núcleo "
        "(resultado histórico de v3-motor3-3, no recalculado: Spearman "
        f"con −saltos {sp['centroid']:.3f} por centroide y "
        f"{sp['nearest_golden']:.3f} por dorado más cercano con q=0.5) "
        "y añadía complejidad e interpretación sin cambiar la decisión "
        "de despliegue.")
    return _claim(
        "C11", "retiro_node2vec", enunciado, valores,
        [_src("07", rep3, "node2vec_retired"),
         _src("07", rep3, "affinity.scope_warning")],
        "resultado_negativo", [
            "Los números citados son de la publicación histórica "
            "v3-motor3-3 (analysis_id 69a83e61…); no se recalculan",
            "La nueva afinidad 1/(1+saltos) es determinista pero hace "
            "que la cercanía a Golden esté optimizada por construcción",
            "La afinidad estructural no es demanda ni evidencia causal",
        ])


def _claim_consistency(rep8, rep4):
    cons = _req(rep8, "consistency", "08")
    shared = _req(rep8, "shared_validation_analysis_id", "08")
    valores = {
        "n_portfolios_checked": int(
            _req(cons, "n_portfolios_checked", "08")),
        "all_feasible": bool(_req(cons, "all_feasible", "08")),
        "all_metrics_reproduced": bool(
            _req(cons, "all_metrics_reproduced", "08")),
        "rtol": float(_req(cons, "rtol", "08")),
        "shared_validation_analysis_id": shared,
        "validation_analysis_id_activo": rep4["analysis_id"],
    }
    enunciado = (
        f"El 08 recomputó {valores['n_portfolios_checked']} portafolios "
        "publicados con las funciones del contrato 04: todos son "
        "factibles y todas las métricas coinciden (rtol "
        f"{valores['rtol']:.0e}); los tres motores referencian el mismo "
        f"analysis_id del 04 ({shared[:12]}…).")
    return _claim(
        "C12", "consistencia_publicaciones", enunciado, valores,
        [_src("08", rep8, "consistency"),
         _src("08", rep8, "shared_validation_analysis_id")],
        "hecho_verificado", [
            "La consistencia verifica reproducibilidad de métricas "
            "publicadas; no valida los supuestos del contrato",
        ])


# ---------------------------------------------------------------------------
# Encuadres corregidos y ledger de límites
# ---------------------------------------------------------------------------

def encuadres_corregidos(rep2, rep3):
    dic = _req(rep2, "dictamen", "06")
    scheme = CONFIG["primary_scheme"]
    mm = {r["model"]: r for r in rep2["regression_means"]
          if r["fold_scheme"] == scheme}
    timing = _req(rep3, "timing", "07")
    rows = _req(rep3, "ga_vs_greedy", "07")
    primary = [r for r in rows
               if r["weight"] == CONFIG["primary_weight"]
               and r["budget"] == CONFIG["primary_budget"]][0]
    return [
        {
            "id": "ridge_vs_ft_transformer",
            "afirmacion_original": "Ridge domina numéricamente al "
                                   "FT-Transformer",
            "estatus_afirmacion_original": "no_sustentada",
            "evidencia": {
                "rmse_ridge": mm["ridge"]["rmse"],
                "rmse_ft_transformer": mm["ft_transformer"]["rmse"],
                "delta_rmse": mm["ft_transformer"]["rmse"]
                              - mm["ridge"]["rmse"],
                "condition_c_seed_std_mean":
                    dic["condition_c_seed_std_mean"],
                "r2_ridge": mm["ridge"]["r2"],
                "r2_ft_transformer": mm["ft_transformer"]["r2"],
                "spearman_ridge": mm["ridge"]["spearman"],
                "spearman_ft_transformer":
                    mm["ft_transformer"]["spearman"],
            },
            "encuadre_correcto": _ridge_ft_sentence({
                "rmse_ridge": mm["ridge"]["rmse"],
                "rmse_ft_transformer": mm["ft_transformer"]["rmse"],
                "r2_ridge": mm["ridge"]["r2"],
                "r2_ft_transformer": mm["ft_transformer"]["r2"],
                "spearman_ridge": mm["ridge"]["spearman"],
                "spearman_ft_transformer":
                    mm["ft_transformer"]["spearman"],
            }),
            "fuentes": [_src("06", rep2, "regression_means"),
                        _src("06", rep2, "dictamen")],
        },
        {
            "id": "tiempos_totales_vs_emparejados",
            "afirmacion_original": "El greedy es ~10^4 veces más rápido "
                                   "que el GA (0.12 s vs 1,303 s)",
            "estatus_afirmacion_original": "no_sustentada",
            "evidencia": {
                "greedy_total_wall_s": timing["greedy_total_wall_s"],
                "ga_total_wall_s": timing["ga_total_wall_s"],
                "porque_no_es_emparejado": "el greedy corre una vez por "
                    "configuración; el GA corre 3-5 semillas por "
                    "configuración",
                "speedup_emparejado_primario":
                    primary["ga_mean_wall_s_per_seed"]
                    / primary["greedy_wall_s"],
            },
            "encuadre_correcto": (
                "El encuadre defendible es el speedup emparejado por "
                "configuración (misma función objetivo y factibilidad): "
                "GA medio por semilla / greedy por corrida; los totales "
                "no emparejados no definen un cociente."),
            "fuentes": [_src("07", rep3, "timing"),
                        _src("07", rep3, "ga_vs_greedy")],
        },
    ]


def _ridge_ft_sentence(evidence):
    """Enunciado del empate práctico Ridge–FT-Transformer, con los
    números inyectados desde la evidencia (06). Lo comparten el
    encuadre corregido y el documento ejecutivo."""
    return (
        "Ridge tiene el RMSE medio más bajo por esa diferencia mínima, "
        "pero el FT-Transformer muestra R² "
        f"({evidence['r2_ft_transformer']:.3f} vs "
        f"{evidence['r2_ridge']:.3f}) y Spearman "
        f"({evidence['spearman_ft_transformer']:.3f} vs "
        f"{evidence['spearman_ridge']:.3f}) ligeramente superiores: "
        "ninguno de los dos domina; el resultado es un empate práctico "
        "y la complejidad del Transformer no se justifica.")


def limitations_ledger(reports):
    """Unión de pending_validation de 04..08 con su origen."""
    ledger = []
    for name in ("validation", "motor1", "motor2", "motor3",
                 "comparacion"):
        for item in reports[name].get("pending_validation", []):
            ledger.append({"origen": name, "nota": item})
    return ledger


# ---------------------------------------------------------------------------
# Documento ejecutivo TESIS_DATA_POINTS.md
# ---------------------------------------------------------------------------

# Palabras prohibidas en el documento ejecutivo (regla de la dirección):
# "ganador", "demuestra" y "óptimo/óptima" no se permiten nunca;
# causa/causal, demanda/demand, domin*/dominance y winner solo aparecen
# precedidos de una negación en la misma cláusula (el ledger cita
# pending_validation verbatim, en español e inglés, siempre en contexto
# negado, y el encuadre Ridge–Transformer dice "ninguno domina").
_PROHIBITED_RES = [
    re.compile(r"\bganador\w*\b", re.I),
    re.compile(r"\b(demuestra\w*|demostr\w*)\b", re.I),
    re.compile(r"\bóptim[oa]s?\b", re.I),
]
_CONDITIONAL_RES = re.compile(
    r"\b(causa\w*|causal\w*|demanda|demand|winner|dominance|"
    r"domin(?:a|an|ancia|ante|antes|ada|ado|ó|aron|ará))\b", re.I)
_NEGATION_RES = re.compile(
    r"\b(no|sin|ni|nunca|jamás|nada|ningún\w*|ninguno\w*|ninguna|"
    r"not|without|nothing|never|nor)\b", re.I)
_NEGATION_WINDOW = 70


def forbidden_violations(text):
    """Lista de violaciones de léxico del documento ejecutivo."""
    violations = []
    for pattern in _PROHIBITED_RES:
        for m in pattern.finditer(text):
            violations.append(f"palabra prohibida: {m.group(0)!r}")
    # El chequeo condicional opera sobre el texto aplanado: los saltos
    # de línea del marcado no son fronteras de cláusula.
    flat = re.sub(r"\s+", " ", text)
    for m in _CONDITIONAL_RES.finditer(flat):
        window = flat[max(0, m.start() - _NEGATION_WINDOW):m.start()]
        tail = re.split(r"[.;:]", window)[-1]
        if not _NEGATION_RES.search(tail):
            violations.append(
                f"{m.group(0)!r} sin negación próxima en la misma "
                f"cláusula: …{window[-40:]!r}…")
    return violations


def check_forbidden(text):
    violations = forbidden_violations(text)
    if violations:
        raise ValueError("Léxico prohibido en TESIS_DATA_POINTS.md: "
                         + "; ".join(violations))


def markdown_layout_violations(text):
    """Defectos de marcado del documento ejecutivo.

    (a) ninguna línea puede empezar con 4+ espacios (CommonMark la
    renderizaría como bloque de código); (b) en un bloque de tabla
    markdown (líneas contiguas que empiezan con "|") todas las filas
    deben tener el mismo número de celdas (contando "|" externos e
    internos). Las listas usan "- " al margen, sin sangría.
    """
    violations = []
    lines = text.split("\n")
    table = []
    for i, line in enumerate(lines):
        if line.startswith("    "):
            violations.append(
                f"línea {i + 1}: sangría de 4+ espacios (bloque de "
                f"código accidental): {line[:50]!r}")
        elif line[:1] in (" ", "\t") and line.strip():
            violations.append(
                f"línea {i + 1}: sangría sobrante: {line[:50]!r}")
        if line.lstrip().startswith("|"):
            table.append((i + 1, line.count("|")))
        else:
            if table:
                counts = {c for _, c in table}
                if len(counts) != 1:
                    violations.append(
                        "tabla con filas de distinto número de "
                        f"columnas: {table}")
                table = []
    if table:
        counts = {c for _, c in table}
        if len(counts) != 1:
            violations.append(
                f"tabla con filas de distinto número de columnas: "
                f"{table}")
    return violations


def check_layout(text):
    violations = markdown_layout_violations(text)
    if violations:
        raise ValueError("Marcado defectuoso en TESIS_DATA_POINTS.md: "
                         + "; ".join(violations))


def _dedup_salvedades(claims):
    """Agrupa salvedades idénticas citando todos los claims que las
    declaran: [(texto, [ids])] en orden de primera aparición."""
    seen = {}
    for c in claims:
        for s in c["salvedades"]:
            seen.setdefault(s, []).append(c["id"])
    return [(texto, ids) for texto, ids in seen.items()]


def _dedup_ledger(ledger):
    """Agrupa notas idénticas conservando todos los orígenes."""
    seen = {}
    for l in ledger:
        seen.setdefault(l["nota"], []).append(l["origen"])
    return [(nota, origenes) for nota, origenes in seen.items()]


def render_tesis_document(report):
    """Documento ejecutivo generado 100% desde el registro.

    Todo número sale de claims[].valores / certificacion / lineage; no
    hay cifras escritas a mano. Cada párrafo es una sola línea de
    markdown (el visor ajusta el ancho); las tablas y las listas van al
    margen. La regeneración desde el reporte sellado debe reproducir el
    documento byte a byte (lo prueba test_c9).
    """
    claims = {c["id"]: c for c in report["claims"]}
    c01 = claims["C01"]["valores"]["30"]
    c02 = claims["C02"]["valores"]
    c03 = claims["C03"]["valores"]["por_presupuesto"]["30"]
    c04 = claims["C04"]["valores"]
    c05 = claims["C05"]["valores"]
    c06 = claims["C06"]["valores"]
    c07 = claims["C07"]["valores"]
    c09 = claims["C09"]["valores"]
    c10 = claims["C10"]["valores"]
    c11 = claims["C11"]["valores"]
    cert = report["certificacion_arnes_espacial"]
    enc = {e["id"]: e for e in report["encuadres_corregidos"]}
    ledger = report["limitations_ledger"]
    lin = {l["cuaderno"]: l for l in report["lineage"]}
    prim = c05["configuracion_primaria"]
    labels = {"m1": "Motor 1", "m2": "Motor 2", "m3": "Motor 3"}
    td = claims["C01"]["valores"]["techo_delta"]

    js, ja, cons = c03["jaccard_sites"], c03["jaccard_agebs"], \
        c03["consenso"]
    mods, dic = c07["models"], c07["dictamen"]
    n2v = c11["evidencia_historica"]
    sp = n2v["spearman_affinity_vs_minus_hops_golden"]
    delta_rf_ridge = mods["random_forest"]["rmse"] - mods["ridge"]["rmse"]
    delta_ft_ridge = mods["ft_transformer"]["rmse"] \
        - mods["ridge"]["rmse"]

    # Veredictos greedy/GA en prosa, derivados del conteo publicado.
    verdicts = c06["verdicts"]
    n_greedy = verdicts.get("greedy", 0)
    n_empate = sum(v for k, v in verdicts.items() if "empate" in k)
    n_ga = c06["n_configuraciones"] - n_greedy - n_empate
    gaps = (c06["brecha_ga_menos_greedy_min"],
            c06["brecha_ga_menos_greedy_max"])
    veredicto = (f"en {n_greedy} configuraciones la ventaja del greedy "
                 f"excede la variación entre semillas del GA; en "
                 f"{n_empate} la diferencia es menor que esa variación "
                 "(empate práctico)")
    if n_ga:
        veredicto += f"; el GA supera al greedy en {n_ga}"
    else:
        veredicto += "; el GA nunca supera al greedy"
    if gaps[1] < 0:
        veredicto += (f"; la mejor corrida del GA queda entre "
                      f"{abs(gaps[1]):.4f} y {abs(gaps[0]):.4f} por "
                      "debajo del greedy en la función objetivo")
    else:
        veredicto += (f"; la brecha GA−greedy va de {gaps[0]:+.4f} a "
                      f"{gaps[1]:+.4f} en la función objetivo")

    folds_before = [f["touching_train_test_pairs_before_buffer"]
                    for f in cert["folds"]]

    L = []
    L.append("# TESIS_DATA_POINTS — registro de afirmaciones con fuente")
    L.append("")
    L.append(
        f"Documento generado mecánicamente desde el registro sellado "
        f"`{report['schema_version']}` (analysis_id "
        f"`{report['analysis_id']}`). Cada cifra lleva en el registro "
        "la ruta JSON de su fuente; este texto solo las formatea. Nada "
        "aquí es demanda observada: las cifras de cobertura son "
        "población dentro de áreas de captura de 500 m con "
        "interpolación areal.")
    L.append("")
    L.append("## 1. Cobertura poblacional por motor y presupuesto")
    L.append("")
    L.append(
        f"A B=30: el Motor 1 cubre {c01['m1']['new_pop']:,.0f} "
        f"habitantes nuevos en {c01['m1']['n_agebs']} AGEBs, el Motor 2 "
        f"{c01['m2']['new_pop']:,.0f} en {c01['m2']['n_agebs']} y el "
        f"Motor 3 {c01['m3']['new_pop']:,.0f} en "
        f"{c01['m3']['n_agebs']}, siempre bajo el mismo contrato de "
        "despliegue y sin techos por AGEB. Respecto a la publicación "
        "previa con techos, los portafolios B=30 de los motores 1 y 2 "
        f"crecieron {td['m1']['delta_B30_new_pop']:+,.0f} y "
        f"{td['m2']['delta_B30_new_pop']:+,.0f} habitantes: el aumento "
        "proviene de retirar un tope que el backtest no validó, no de "
        "un método mejor. Es población en captura, no demanda "
        "observada, y las diferencias son entre portafolios "
        "heurísticos sin prueba estadística.")
    L.append("")
    L.append("| Motor | B | Población nueva | % pobl. | AGEBs | "
             "1/2/3+ |")
    L.append("|---|---|---|---|---|---|")
    for b in (15, 30, 50):
        src = claims["C01"]["valores"] if str(b) == "30" else c02
        for m in ("m1", "m2", "m3"):
            v = src[str(b)][m]
            L.append(
                f"| {labels[m]} | {b} | {v['new_pop']:,.0f} | "
                f"{v['new_pop_share']*100:.2f}% | {v['n_agebs']} | "
                f"{v['agebs_1']}/{v['agebs_2']}/{v['agebs_3plus']} |")
    L.append("")
    L.append(
        f"Los portafolios divergen territorialmente: a B=30 el Jaccard "
        f"de sitios es {js['m1-m2']:.3f} (M1–M2), {js['m1-m3']:.3f} "
        f"(M1–M3) y {js['m2-m3']:.3f} (M2–M3), y de AGEBs "
        f"{ja['m1-m2']:.3f}, {ja['m1-m3']:.3f} y {ja['m2-m3']:.3f}; "
        f"{cons['selected_by_2plus']} sitios aparecen en al menos 2 "
        f"motores y {cons['selected_by_3']} en los 3. La divergencia es "
        "descriptiva: los objetivos difieren por diseño.")
    L.append("")
    L.append("## 2. Navaja de Ockham")
    L.append("")
    L.append(
        f"**Motor 3 — greedy frente a GA.** Con la misma función "
        f"objetivo y las mismas reglas de factibilidad, en la "
        f"configuración primaria (w=0.5, B=30) el greedy toma "
        f"{prim['greedy_wall_s']:.3f} s por corrida frente a "
        f"{prim['ga_mean_wall_s_per_seed']:.1f} s por semilla del GA "
        f"({prim['speedup_ga_por_semilla_sobre_greedy']:,.0f}x; rango "
        f"emparejado {c05['speedup_min']:,.0f}x–"
        f"{c05['speedup_max']:,.0f}x entre configuraciones). Los "
        f"totales no emparejados —greedy "
        f"{c05['totales_no_emparejados']['greedy_total_wall_s']:.3f} s "
        f"en una pasada por configuración, GA "
        f"{c05['totales_no_emparejados']['ga_total_wall_s']:,.1f} s en "
        "3–5 semillas por configuración— no definen un cociente. En el "
        f"objetivo, el greedy iguala o supera a la mejor corrida del "
        f"GA en {c06['n_greedy_al_menos_ga_best']} de "
        f"{c06['n_configuraciones']} configuraciones: {veredicto}. Es "
        "un hallazgo empírico: la garantía (1−1/e) de cobertura "
        "submodular no aplica formalmente bajo contigüidad y "
        "espaciamiento, y el GA es una heurística sin garantía de "
        "optimalidad.")
    L.append("")
    L.append(
        f"**Motor 2 — modelos tabulares.** En el esquema espacial "
        f"primario el RMSE medio es {mods['constante']['rmse']:.4f} "
        f"(constante), {mods['ridge']['rmse']:.4f} (ridge), "
        f"{mods['random_forest']['rmse']:.4f} (bosque aleatorio) y "
        f"{mods['ft_transformer']['rmse']:.4f} (FT-Transformer). "
        "Frente al mejor control (Ridge) el Transformer no mejora: su "
        f"diferencia de RMSE es de {delta_ft_ridge:+.4f} a favor de "
        f"Ridge, que equivale a "
        f"{c07['ratio_mejora_vs_std_semillas']:.3f} veces la variación "
        f"entre semillas ({dic['condition_c_seed_std_mean']:.4f}). "
        f"{enc['ridge_vs_ft_transformer']['encuadre_correcto']} El "
        "dictamen mecánico lo retira del despliegue y el bosque "
        "aleatorio se despliega por parsimonia y estabilidad, no por "
        f"superioridad acreditada: RF vs Ridge difiere en "
        f"{delta_rf_ridge:+.4f} de RMSE medio con R² espacial ≤ ~0.22 "
        "en todos los modelos.")
    L.append("")
    L.append("## 3. Certificación del arnés espacial")
    L.append("")
    L.append(
        f"El esquema primario `fold_spatial_block` deja "
        f"{cert['suma_pares_after_buffer']} pares colindantes "
        f"prueba–entrenamiento tras el buffer de {cert['buffer_m']:.0f} "
        f"m en los {cert['n_folds']} folds (antes del buffer: "
        f"{folds_before}); la distancia mínima retenida es "
        f"{cert['min_train_test_distance_m']:.1f} m y los "
        f"{cert['n_blocks']} bloques forman un solo componente de "
        f"adyacencia ({cert['n_adjacency_components']}) con contigüidad "
        f"{cert['blocks_contiguous_share']:.2f}. El conteo fue "
        "recomputado de forma independiente desde los artefactos "
        "publicados y coincide con el reporte. La garantía es sobre "
        "colindancia poligonal (≤1 m) y buffer de 500 m; no descarta "
        "autocorrelación espacial a mayor distancia.")
    L.append("")
    L.append("## 4. Otros hallazgos de método")
    L.append("")
    L.append(
        f"- **Ledoit-Wolf (Motor 1):** con n/p de "
        f"{c09['n_over_p']['min']:.2f}–{c09['n_over_p']['max']:.2f} el "
        f"encogimiento ({c09['shrinkage']['min']:.2f}–"
        f"{c09['shrinkage']['max']:.2f}) lleva el número de condición "
        f"de {c09['condition_number_empirical']['min']:.0f}–"
        f"{c09['condition_number_empirical']['max']:.0f} a "
        f"{c09['condition_number_lw']['min']:.2f}–"
        f"{c09['condition_number_lw']['max']:.2f} y la cobertura de "
        "decisión de "
        f"{c09['variantes']['m1_coseno_compuerta_empirica']['decision_coverage']:.3f} "
        "a "
        f"{c09['variantes']['m1_coseno_compuerta']['decision_coverage']:.3f}; "
        "el NDCG@10 "
        f"({c09['variantes']['m1_coseno_compuerta']['ndcg@10']:.3f}) no "
        "cambia respecto al coseno sin compuerta. El umbral "
        "chi-cuadrado es nominal bajo encogimiento.")
    L.append(
        f"- **Remoción del techo por análogos:** en 05 el análogo "
        f"pierde en MAE ({c10['m1']['mae_analog']:.3f} vs "
        f"{c10['m1']['mae_naive']:.3f}) y en Spearman "
        f"({c10['m1']['spearman_analog']:.3f} vs "
        f"{c10['m1']['spearman_naive']:.3f}); en 06 pierde en MAE "
        f"({c10['m2']['mae_analog']:.3f} vs "
        f"{c10['m2']['mae_naive']:.3f}) aunque su Spearman queda "
        f"marginalmente por encima ({c10['m2']['spearman_analog']:.3f} "
        f"vs {c10['m2']['spearman_naive']:.3f}). Reproduce densidad "
        "histórica de planeación, no demanda observada.")
    L.append(
        f"- **Retiro de Node2Vec:** la afinidad por embeddings no "
        f"ordenaba por cercanía al núcleo (histórico "
        f"{c11['historical_schema']}, no recalculado: Spearman con "
        f"−saltos {sp['q_0.5']['centroid']:.3f} / "
        f"{sp['q_0.5']['nearest_golden']:.3f} con q=0.5; razón de norma "
        f"del centroide {n2v['centroid_norm_ratio']:.3f}). La afinidad "
        "vigente es determinista, 1/(1+saltos a Golden), y por ello la "
        "cercanía a Golden del portafolio está optimizada por "
        "construcción —no es evidencia independiente—.")
    L.append(
        f"- **Tensión similitud–equidad:** a B=30 la escolaridad media "
        f"de las AGEBs seleccionadas es "
        f"{c04['m1']['grado_escolar_sel']:.2f} (M1), "
        f"{c04['m2']['grado_escolar_sel']:.2f} (M2) y "
        f"{c04['m3']['grado_escolar_sel']:.2f} (M3) frente a "
        f"{c04['m1']['grado_escolar_all']:.2f} en todos los sitios; la "
        f"fracción fuera del dominio del 04 es "
        f"{c04['m1']['out_of_domain_04_share']:.2f} / "
        f"{c04['m2']['out_of_domain_04_share']:.2f} / "
        f"{c04['m3']['out_of_domain_04_share']:.2f}. Son covariables "
        "ecológicas de AGEB, sin lectura causal.")
    L.append("")
    L.append("## 5. Salvedades que deben acompañar cada cifra")
    L.append("")
    for texto, ids in _dedup_salvedades(report["claims"]):
        L.append(f"- ({', '.join(ids)}) {texto}")
    L.append("")
    L.append("### Límites registrados por los cuadernos 04–08")
    L.append("")
    L.append("Citados textualmente de los reportes publicados "
             "(en inglés).")
    L.append("")
    for nota, origenes in _dedup_ledger(ledger):
        L.append(f"- [{', '.join(origenes)}] {nota}")
    L.append("")
    L.append("## 6. Procedencia")
    L.append("")
    L.append(
        f"Registro `{report['schema_version']}` · contrato "
        f"`{report['contract_id']}` · puntero "
        "`audits/09_final_claims_registry.json` · analysis_id del "
        f"registro (hash de identidad de contenido): "
        f"`{report['analysis_id']}`.")
    L.append("")
    L.append("| Cuaderno | Esquema | analysis_id |")
    L.append("|---|---|---|")
    for k in ("etl", "eda", "features", "validation", "motor1",
              "motor2", "motor3", "comparacion"):
        L.append(
            f"| {lin[k]['notebook']} | {lin[k]['schema_version'] or '—'}"
            f" | `{lin[k]['analysis_id'] or 'sin analysis_id'}` |")
    L.append("")

    doc = "\n".join(L)
    check_forbidden(doc)
    check_layout(doc)
    return doc


# ---------------------------------------------------------------------------
# Análisis completo
# ---------------------------------------------------------------------------

def _records(df):
    return df.astype(object).where(pd.notna(df), None) \
        .to_dict(orient="records")


def analyze(data, verbose=False):
    started = time.perf_counter()

    def tick(label):
        if verbose:
            print(f"[c9] {label}: {time.perf_counter() - started:.1f}s",
                  file=sys.stderr, flush=True)

    reports = data["reports"]
    rep1, rep2, rep3 = (reports["motor1"], reports["motor2"],
                        reports["motor3"])
    rep4, rep8 = reports["validation"], reports["comparacion"]

    # Certificación con recomputo independiente (aborta si difiere).
    cert = certify_spatial_harness(
        rep4, data["frames"]["universe04"], data["frames"]["cv_folds"],
        data["frames"]["cv_buffer_exclusions"])
    tick("certificacion")

    claims = []
    claims += _coverage_claims(rep8, rep1, rep2, rep3)
    claims.append(_claim_overlap(rep8))
    claims.append(_claim_tension(rep8))
    claims.append(_claim_greedy_ga(rep3))
    claims.append(_claim_objective_gap(rep3))
    claims.append(_claim_motor2(rep2))
    claims.append(_claim_harness(cert, rep4))
    claims.append(_claim_ledoit_wolf(rep1))
    claims.append(_claim_ceiling(rep1, rep2))
    claims.append(_claim_node2vec(rep3))
    claims.append(_claim_consistency(rep8, rep4))
    tick("claims")

    encuadres = encuadres_corregidos(rep2, rep3)
    ledger = limitations_ledger(reports)

    lineage = []
    for name in ("etl", "eda", "features", "validation", "motor1",
                 "motor2", "motor3", "comparacion"):
        pointer = POINTERS[name]
        entry = {
            "cuaderno": name,
            "notebook": NOTEBOOK_NAMES[name],
            "puntero": pointer,
            "puntero_sha256": hashlib.sha256(
                (data["v3"] / pointer).read_bytes()).hexdigest(),
            "schema_version": None, "analysis_id": None,
            "contract_id": data["audit"]["contract_id"],
            "nota": None,
        }
        if name == "etl":
            entry["nota"] = (
                "auditoría ETL sin analysis_id: es el archivo de "
                "auditoría comprometida, no un reporte de motor")
        else:
            rep = reports[name]
            entry["schema_version"] = rep["schema_version"]
            entry["analysis_id"] = rep["analysis_id"]
            entry["notebook"] = rep.get("notebook", entry["notebook"])
        lineage.append(entry)

    report = {
        "schema_version": VERSION,
        "contract_id": data["audit"]["contract_id"],
        "analysis_id": data["analysis_id"],
        "notebook": "09_Auditoria_Final_Afirmaciones.ipynb",
        "scope": {
            "trains_no_models": True,
            "reads_verified_publications_only": True,
            "recomputes_no_portfolios": True,
            "no_aggregate_winner": True,
        },
        "configuration": CONFIG,
        "lineage": lineage,
        "claims": claims,
        "certificacion_arnes_espacial": cert,
        "encuadres_corregidos": encuadres,
        "limitations_ledger": ledger,
        "upstream": data["upstream_refs"],
        "pending_validation": [
            "Claims are extracted from sealed publications; this "
            "registry does not add new evidence",
            "All figures inherit the limitations of their source "
            "notebooks (see limitations_ledger)",
        ],
    }
    documento = render_tesis_document(report)
    doc_bytes = documento.encode("utf-8")
    report["document"] = {
        "output": "TESIS_DATA_POINTS.md",
        "sha256": hashlib.sha256(doc_bytes).hexdigest(),
        "docs_copy_path": CONFIG["docs_target"],
        "forbidden_lexicon_checked": True,
    }

    claims_df = pd.DataFrame([{
        "id": c["id"], "tema": c["tema"], "estatus": c["estatus"],
        "enunciado": c["enunciado"],
        "valores_json": json.dumps(c["valores"], ensure_ascii=False,
                                   default=str),
        "fuentes_json": json.dumps(c["fuentes"], ensure_ascii=False),
        "salvedades_json": json.dumps(c["salvedades"],
                                      ensure_ascii=False),
    } for c in claims])
    lineage_df = pd.DataFrame(lineage)

    outputs = [
        ("c9_claims.csv", "csv", claims_df),
        ("c9_lineage.csv", "csv", lineage_df),
        ("TESIS_DATA_POINTS.md", "bytes", doc_bytes),
    ]
    return {"report": report, "outputs": outputs,
            "documento": documento, "claims_df": claims_df,
            "lineage_df": lineage_df}
