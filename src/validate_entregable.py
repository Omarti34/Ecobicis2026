"""Agente Validador del entregable (paper LaTeX + presentación HTML).

Criterio de aceptación independiente del generador: deriva las cifras
esperadas directamente de los reportes sellados (V3/audits/*.json) y
rechaza el entregable si hay cifras obsoletas, primera persona, figuras
sin referenciar, HTML no autocontenido o el TeX no compila.

Uso: conda run -n CM python V3/src/validate_entregable.py
Código de salida 0 = aprobado; 1 = rechazado (imprime todas las fallas).
"""
import html.parser
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
AUD = V3 / "audits"
ENT = V3 / "entregable"
ZIP = ENT / "tesis_overleaf.zip"
HTML = ENT / "presentacion_ejecutiva.html"

FAILS = []


def fail(msg):
    FAILS.append(msg)


def load(name):
    return json.loads((AUD / name).read_text(encoding="utf-8"))


def miles(x):
    return f"{x:,.0f}"


# ---------------------------------------------------------------- hechos
def expected():
    a01 = load("01_etl.json")
    a02 = load("02_eda.json")
    a04 = load("04_backtest_design.json")
    a06 = load("06_motor2_transformer.json")
    a07 = load("07_motor3_prescriptivo.json")
    a08 = load("08_comparacion_portafolios.json")
    a09 = load("09_final_claims_registry.json")
    hum = a02["human_dimension"]
    eq = a02["spatial_equity"]
    mor = a02["spatial_autocorrelation"]
    mor = mor.get("moran", mor) if isinstance(mor, dict) else mor
    ofi = [m for m in a08["metricas"] if m["tier"] == "oficial"]
    w = a07["primary"]["weight"]
    runs = a07["runs"]
    ex = {}  # nombre -> cadena que debe aparecer en AMBOS documentos
    ex["pob_sin_estacion"] = miles(hum["population_without_internal_station_known"])
    ex["agebs_sin_estacion"] = miles(hum["agebs_without_internal_station"])
    ex["gini_estaciones"] = f"{eq['gini_stations']:.4f}"
    ex["gini_actividad"] = f"{eq['gini_activity']:.4f}"
    ex["viajes_aceptados"] = miles(a01["trip_rows"]["accepted_rows"]) \
        if "trip_rows" in a01 else None
    for m in ofi:
        if m["budget"] in (15, 30, 50) and m["motor"] in ("m1", "m2", "m3"):
            ex[f"{m['motor']}_B{m['budget']}"] = miles(m["new_pop"])
    derived = set()
    for b in (15, 30, 50):
        g = [r for r in runs if r["method"] == "greedy"
             and r["budget"] == b and r["weight"] == w][0]
        gas = [r for r in runs if r["method"] == "ga"
               and r["budget"] == b and r["weight"] == w]
        best = max(gas, key=lambda r: r["f"])
        ex[f"greedy_B{b}"] = miles(g["new_pop"])
        ex[f"ga_B{b}"] = miles(best["new_pop"])
        derived.add(miles(g["new_pop"] - best["new_pop"]))
    gp = a07["primary"]
    gv = [r for r in a07["ga_vs_greedy"]
          if r["weight"] == w and r["budget"] == gp["budget"]][0]
    ex["t_greedy_run"] = f"{gv['greedy_wall_s']:.3f}"
    ex["t_ga_run"] = f"{gv['ga_mean_wall_s_per_seed']:.1f}"
    ex["t_ga_total"] = miles(a07["timing"]["ga_total_wall_s"])
    ex["speedup"] = miles(gv["ga_mean_wall_s_per_seed"] / gv["greedy_wall_s"])
    ex["ridge_rmse"] = f"{a06['dictamen']['mean_rmse']['ridge']:.4f}"
    ex["ft_rmse"] = f"{a06['dictamen']['mean_rmse']['ft_transformer']:.4f}"
    ex["blocks"] = str(a04["spatial_cv"]["n_blocks"])
    ex["moran_i"] = f"{mor['i']:.4f}"
    ex["diferencia_B30"] = miles(
        [r for r in runs if r["method"] == "greedy" and r["budget"] == 30
         and r["weight"] == w][0]["new_pop"]
        - max([r for r in runs if r["method"] == "ga" and r["budget"] == 30
               and r["weight"] == w], key=lambda r: r["f"])["new_pop"])
    ex = {k: v for k, v in ex.items() if v}
    # universo de cifras con separador de miles permitidas
    universe = set(derived)
    for p in sorted(AUD.glob("0[0-9]_*.json")):
        if "archive" in str(p):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, (int, float)) and not isinstance(x, bool):
                if abs(x) >= 1000:
                    universe.update({miles(x), miles(int(x)), miles(abs(x))})
                    universe.add(miles(round(x)))
                    universe.add(miles(int(abs(x)) + 1))
    # rangos de aceleración y otros derivados legítimos
    sp = [r["ga_mean_wall_s_per_seed"] / r["greedy_wall_s"]
          for r in a07["ga_vs_greedy"]]
    universe.update({miles(min(sp)), miles(max(sp)), miles(sum(sp) / len(sp))})
    pob_ga = [r["new_pop"] for r in runs if r["method"] == "ga"]
    universe.update({miles(v) for v in pob_ga})
    universe.add(miles(sum(r["new_pop"] for r in runs if r["method"] == "ga"
                           and r["budget"] == 30 and r["weight"] == w)
                       / len([r for r in runs if r["method"] == "ga"
                              and r["budget"] == 30 and r["weight"] == w])))
    return ex, universe


# ------------------------------------------------------------------ texto
class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def html_text(src):
    p = _Text()
    p.feed(src)
    return " ".join(p.out)


def tex_text(src):
    s = re.sub(r"(?<!\\)%.*", "", src)
    s = re.sub(r"\\(label|ref|cite|includegraphics|bibliography|"
               r"bibliographystyle|usepackage|documentclass)(\[[^\]]*\])?"
               r"\{[^}]*\}", " ", s)
    s = re.sub(r"\$[^$]*\$", " ", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    return re.sub(r"[{}\\~]", " ", s)


FIRST_PERSON = re.compile(
    r"\b(nosotros|nuestr[oa]s?|hemos|\w+(?:amos|emos)|"
    r"hicimos|decidimos|elegimos|definimos|medimos|obtuvimos|vimos|"
    r"fijamos|jubilamos|creímos|usamos|utilizamos|dejamos|quitamos|"
    r"recomendamos|sumamos)\b", re.I)
ALLOW_1P = {"ramos", "gramos", "diagramos", "programas", "estemos"}
COLLOQUIAL = ["Ojo", "jubil", "bastante", "¿Y qué", "chida", "cambia de deporte",
              "puntear", "a consciencia", "no lo creímos", "al grano",
              "de frente", "nada espectacular"]
STALE = ["7,739", "7739", "304,459", "509,267", "K-Means", "KMeans",
         "kmeans", "K-means", "50 minutos", "0.8 s", "0.8s", "~0.8",
         "V3", "ipynb", "uaderno", "build_", "notebook", "isócron"]


def check_style(name, text, strict_first_person=True):
    for s in STALE:
        if s.lower() in text.lower():
            fail(f"{name}: contiene término/cifra prohibido {s!r}")
    for c in COLLOQUIAL:
        if c in text:
            fail(f"{name}: lenguaje coloquial {c!r}")
    if strict_first_person:
        bad = {m.group(0) for m in FIRST_PERSON.finditer(text)
               if m.group(0).lower() not in ALLOW_1P}
        if bad:
            fail(f"{name}: posible primera persona: {sorted(bad)[:15]}")
    if text.count("¿") > 3:
        fail(f"{name}: demasiadas preguntas retóricas ({text.count('¿')})")
    if re.search(r"(?<![\d.])\b0[4-9]\s*:|\b(del|El|el|al)\s+0[4-9]\b",
                 text):
        fail(f"{name}: numeración interna de análisis sin sanear")


def check_numbers(name, text, ex, universe):
    for k, v in ex.items():
        if v not in text:
            fail(f"{name}: falta la cifra sellada {k}={v}")
    for m in set(re.findall(r"(?<![\d,.])\d{1,3}(?:,\d{3})+(?![\d,])", text)):
        if m not in universe:
            fail(f"{name}: cifra {m} no corresponde a ningún reporte sellado")


# ----------------------------------------------------------------- checks
def main():
    if not ZIP.exists() or not HTML.exists():
        print("Falta entregable/presentacion_ejecutiva.html o tesis_overleaf.zip")
        return 1
    ex, universe = expected()
    tmp = Path(tempfile.mkdtemp(prefix="entregable_chk_"))
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(tmp)
        names = z.namelist()
    tex_path = tmp / "main.tex"
    if not tex_path.exists():
        fail("zip: no hay main.tex en la raíz")
        print("\n".join(FAILS))
        return 1
    tex = tex_path.read_text(encoding="utf-8")
    if not list(tmp.glob("*.bib")):
        fail("zip: no hay archivo .bib")
    if r"\bibliography{" not in tex:
        fail("tex: no usa \\bibliography{}")

    # estructura obligatoria, en orden
    order = ["Introducción", "Planteamiento del problema", "Hipótesis",
             "Datos y tratamiento", "Los tres motores", "Motor 1", "Motor 2",
             "Motor 3", "Resultados y discusión", "Conclusiones",
             "Bibliografía"]
    pos = -1
    for t in order:
        m = re.search(r"\\(sub)?section\*?\{[^}]*" + re.escape(t), tex)
        if not m:
            fail(f"tex: falta la sección '{t}'")
            continue
        if m.start() < pos:
            fail(f"tex: la sección '{t}' está fuera de orden")
        pos = m.start()

    # figuras y tablas: existen, están referenciadas y explicadas ANTES
    figs = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)
    for f in figs:
        if not (tmp / f).exists() and not any((tmp / (f + e)).exists()
                                              for e in (".png", ".pdf")):
            fail(f"tex: figura inexistente en el zip: {f}")
    zipped_imgs = {n for n in names if n.lower().endswith((".png", ".pdf", ".jpg"))}
    unused = [n for n in zipped_imgs if not any(n.endswith(f) or f.endswith(n)
                                                for f in figs)]
    if unused:
        fail(f"zip: figuras sin usar: {unused[:5]}")
    for env in ("figure", "figure*", "table", "table*"):
        for m in re.finditer(r"\\begin\{" + re.escape(env) + r"\}(.*?)"
                             r"\\end\{" + re.escape(env) + r"\}", tex, re.S):
            lab = re.search(r"\\label\{([^}]+)\}", m.group(1))
            if not lab:
                fail(f"tex: {env} sin \\label (cerca de {m.group(1)[:50]!r})")
                continue
            if "\\caption" not in m.group(1):
                fail(f"tex: {env} {lab.group(1)} sin caption")
            refs = [r.start() for r in re.finditer(
                r"\\(?:ref|autoref|cref)\{" + re.escape(lab.group(1)) + r"\}", tex)]
            if not refs:
                fail(f"tex: {lab.group(1)} nunca se referencia en el texto")
            elif min(refs) > m.start():
                fail(f"tex: {lab.group(1)} se explica DESPUÉS de aparecer")
    if tex.count("\\footnote{") < 10:
        fail("tex: menos de 10 notas al pie explicando términos")
    if not re.search(r"unión|union|traslape", tex, re.I):
        fail("tex: falta la nota sobre la unión espacial / traslape de zonas")
    if "Ward" not in tex:
        fail("tex: no menciona el método Ward para los bloques espaciales")
    if not re.search(r"B\s*=\s*50.{0,400}(Greedy|voraz)", tex, re.S):
        fail("tex: no discute explícitamente B=50 con Greedy")
    check_style("tex", tex_text(tex))
    check_numbers("tex", tex, ex, universe)

    # HTML autocontenido
    page = HTML.read_text(encoding="utf-8")
    if re.search(r"(src|href)\s*=\s*[\"']https?://", page, re.I) \
            or re.search(r"url\(\s*[\"']?https?://", page, re.I) \
            or re.search(r"<script[^>]+src=", page, re.I) \
            or re.search(r"<link[^>]+href=", page, re.I):
        fail("html: depende de recursos externos (no es autocontenido)")
    n_img = len(re.findall(r"<img[^>]+src=[\"']data:image/", page, re.I))
    if n_img < len(figs):
        fail(f"html: {n_img} imágenes embebidas < {len(figs)} figuras del paper")
    if re.findall(r"<img(?![^>]*\balt=)[^>]*>", page, re.I):
        fail("html: hay <img> sin atributo alt")
    if page.count("<figcaption") < n_img:
        fail("html: hay imágenes sin figcaption")
    htxt = html_text(page)
    for t in ("Introducción", "Planteamiento del problema", "Hipótesis",
              "Datos y tratamiento", "Motor 1", "Motor 2", "Motor 3",
              "Resultados", "Conclusiones", "Bibliografía"):
        if t not in htxt:
            fail(f"html: falta la sección '{t}'")
    if "Ward" not in htxt:
        fail("html: no menciona Ward")
    check_style("html", htxt)
    check_numbers("html", htxt, ex, universe)
    # coherencia cruzada: toda cifra grande del HTML debe estar en el paper
    ttxt = tex
    for m in set(re.findall(r"(?<![\d,.])\d{1,3}(?:,\d{3})+(?![\d,])", htxt)):
        if m not in ttxt:
            fail(f"html/tex: la cifra {m} del HTML no aparece en el paper")

    # compilación completa: pdflatex, bibtex, pdflatex x2
    def run(cmd):
        return subprocess.run(cmd, cwd=tmp, capture_output=True,
                              text=True, errors="replace")
    r = run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    if r.returncode:
        fail("pdflatex (1) falló")
    b = run(["bibtex", "main"])
    if b.returncode:
        fail("bibtex falló: " + b.stdout[-300:])
    run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    r = run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    if r.returncode:
        fail("pdflatex (final) falló")
    log = (tmp / "main.log").read_text(errors="ignore") \
        if (tmp / "main.log").exists() else ""
    if re.search(r"undefined (references|citations)|Citation .* undefined|"
                 r"Reference .* undefined", log):
        fail("tex: referencias o citas sin resolver tras compilar")
    if re.search(r"Overfull \\hbox \(([2-9]\d|\d{3,})", log):
        fail("tex: overfull hbox > 20pt")
    m = re.search(r"Output written on main\.pdf \((\d+) pages", log)
    if not m:
        fail("no se generó main.pdf")
    elif int(m.group(1)) < 8:
        fail(f"el PDF tiene solo {m.group(1)} páginas")
    else:
        print(f"PDF: {m.group(1)} páginas")
    shutil.rmtree(tmp, ignore_errors=True)

    if FAILS:
        print(f"RECHAZADO: {len(FAILS)} falla(s)")
        for f in FAILS:
            print(" -", f)
        return 1
    print("APROBADO: cifras, estilo, figuras, HTML autocontenido y compilación OK")
    return 0


# ------------------------------------------------------------ variante 2
V2_PRESENTES = [
    "p ≤ 0.001",
    "coeficiente w = 0.5 y normalización de variables",
    "la diferencia de error es menor a la variación entre semillas",
    "Pregunta e hipótesis",
    "Despliegue del piloto",
    "Supuestos del modelo frente a la realidad",
    "8,100,000",
    "450,000",
    "18 sitios",
    "Pob*",
    "Referencias simples a B = 30",
    "Solo población (Motor 3 con w = 1)",
    "Repositorio en GitHub con código fuente",
    "github.com/Omarti34/Ecobicis2026",
    "Nota sobre el uso de IA generativa",
    'id="qr-slot"',
    'role="math"',
]
V2_AUSENTES = [
    "es posible", "mitad y mitad", "empate estadístico",
    "empate práctico", "los 18 de consenso doble", "mitigando",
    "p = 0.001", "incorpora la conectividad", "QR PROVISIONAL",
]


def validate_v2(path):
    """Valida una presentación HTML de la variante 2 (archivo único)."""
    path = Path(path)
    if not path.exists():
        print(f"no existe: {path}")
        return 1
    page = path.read_text(encoding="utf-8")
    htxt = html_text(page)

    # autocontención (el namespace xmlns www.w3.org/2000/svg no es un
    # recurso cargado; las mismas pautas del validador original)
    for pat, msg in [
            (r"(src|href)\s*=\s*[\"']https?://",
             "src/href http(s)://"),
            (r"url\(\s*[\"']?https?://", "url() http(s)://"),
            (r"fetch\(", "fetch()"),
            (r"XMLHttpRequest", "XMLHttpRequest"),
            (r"WebSocket", "WebSocket"),
            (r"<script[^>]+src=", "script externo"),
            (r"<link[^>]+href=", "link externo")]:
        if re.search(pat, page, re.I):
            fail(f"v2 html: dependencia externa ({msg})")
    externas = [u for u in re.findall(r"https?://[^\s\"'<>)]+", page)
                if "w3.org/2000/svg" not in u
                and "github.com/Omarti34/Ecobicis2026" not in u]
    if externas:
        fail(f"v2 html: URLs externas no permitidas {externas[:3]}")

    # estilo (mismas listas que el entregable)
    check_style("v2 html", htxt)

    for s in V2_PRESENTES:
        if s not in htxt and s not in page:
            fail(f"v2 html: falta cadena obligatoria {s!r}")
    for s in V2_AUSENTES:
        if s.lower() in htxt.lower():
            fail(f"v2 html: contiene cadena prohibida {s!r}")

    # scatter congelado: las cifras se derivan del JSON, no se escriben
    sc = json.loads((V3 / "data" / "presentacion_v2"
                     / "scatter_azar_b30.json").read_text(encoding="utf-8"))
    n_cloud = len(re.findall(r'class="cloud"', page))
    if n_cloud != len(sc["points"]):
        fail(f"v2 html: {n_cloud} puntos de nube != {len(sc['points'])} "
             "del JSON")
    for s, origen in [
            (f"{sc['universe_esc']:.2f}", "universo_esc"),
            (f"{sc['cloud']['esc_mean']:.2f}", "media de la nube"),
            (miles(sc["cloud"]["pop_max"]), "pop_max de la nube"),
            (f"{sc['median_viajes_diarios_red']:.1f}", "mediana red"),
            (str(sc["n_estaciones"]), "n_estaciones"),
            (miles(sc["official"]["m1"]["new_pop"]), "pop m1"),
            (miles(sc["official"]["m2"]["new_pop"]), "pop m2"),
            (miles(sc["official"]["m3"]["new_pop"]), "pop m3"),
            (f"{sc['official']['m1']['esc']:.2f}", "esc m1"),
            (f"{sc['official']['m3']['esc']:.2f}", "esc m3")]:
        if s not in page:
            fail(f"v2 html: falta la cifra del scatter {origen}={s}")
    pct_m1 = round(sc["rank"]["m1"]["share_random_esc_le"] * 100)
    pct_m3 = round(sc["rank"]["m3"]["share_random_esc_le"] * 100)
    if f"percentil {pct_m1}" not in htxt:
        fail(f"v2 html: falta 'percentil {pct_m1}' (m1)")
    if f"percentil {pct_m3}" not in htxt:
        fail(f"v2 html: falta 'percentil {pct_m3}' (m3)")

    # w_sweep / p_norm: tabla de referencias y barrido de pesos
    ws = sc["w_sweep"]
    base_pop = sc["cloud"]["pop_mean"]

    def rx(pop):
        return f"{pop / base_pop:.2f}×"

    for s, origen in [
            (miles(sc["p_norm"]), "p_norm"),
            (miles(ws["1.0"]["new_pop"]), "w=1 new_pop"),
            (miles(ws["0.0"]["new_pop"]), "w=0 new_pop"),
            (f"{ws['0.0']['esc']:.2f}", "w=0 esc"),
            (rx(base_pop), "ratio azar"),
            (rx(sc["official"]["m1"]["new_pop"]), "ratio m1"),
            (rx(sc["official"]["m2"]["new_pop"]), "ratio m2"),
            (rx(sc["official"]["m3"]["new_pop"]), "ratio m3"),
            (f"Jaccard {ws['1.0']['jaccard_vs_w05']:.1f}",
             "jaccard w=1 vs w=0.5"),
            (miles(sc["cloud"]["pop_sd"]), "sd nube")]:
        if s not in page and s not in htxt:
            fail(f"v2 html: falta la cifra derivada {origen}={s}")

    # el JSON w_sweep debe reproducir las filas greedy de m3_runs.csv
    import csv
    import glob
    runs_p = glob.glob(str(
        V3 / "data" / "engines" / "07_motor3" / "*"
        / "3aa53121*" / "m3_runs.csv"))
    if not runs_p:
        fail("v2: no se encontró m3_runs.csv del Motor 3")
    else:
        run_pops = {}
        for r in csv.DictReader(open(runs_p[0])):
            if r["method"] == "greedy" and r["budget"] == "30":
                run_pops[r["weight"]] = float(r["new_pop"])
        for k, v in ws.items():
            ref = run_pops.get(str(float(k)))
            if ref is None or abs(ref - v["new_pop"]) > 1e-6:
                fail(f"v2: w_sweep w={k} no reproduce m3_runs.csv "
                     f"({v['new_pop']} vs {ref})")

    # Motor 2: NDCG@10 (backtest 08) y Spearman/R² (regression_means 06)
    a06 = load("06_motor2_transformer.json")
    a08 = load("08_comparacion_portafolios.json")
    bt = {r["subject"]: r for r in a08["backtest_context"]
          if r["scheme"] == "fold_spatial_block"}
    reg_sp = {r["model"]: r for r in a06["regression_means"]
              if r["fold_scheme"] == "fold_spatial_block"}
    reg_gp = {r["model"]: r for r in a06["regression_means"]
              if r["fold_scheme"] == "fold_groupkfold_ageb"}
    for s, origen in [
            (f"{reg_sp['random_forest']['spearman']:.3f}",
             "spearman RF espacial"),
            (f"{bt['random_forest']['ndcg_at_10']:.3f}", "NDCG@10 RF"),
            (f"{bt['control_aleatorio']['ndcg_at_10']:.3f}",
             "NDCG@10 control"),
            (f"{reg_sp['random_forest']['r2']:.3f}", "R² RF"),
            (f"{reg_gp['random_forest']['spearman']:.3f}",
             "spearman RF grupos")]:
        if s not in htxt:
            fail(f"v2 html: falta la cifra sellada {origen}={s}")

    # figuras 1–19 siguen presentes
    for n in range(1, 20):
        if f"Figura {n}." not in htxt:
            fail(f"v2 html: falta 'Figura {n}.'")
    n_img = len(re.findall(r"<img[^>]+src=[\"']data:image/", page, re.I))
    if n_img < 19:
        fail(f"v2 html: {n_img} imágenes embebidas < 19")

    if FAILS:
        print(f"RECHAZADO: {len(FAILS)} falla(s)")
        for f in FAILS:
            print(" -", f)
        return 1
    print(f"APROBADO v2: {path}")
    return 0


SLIDES_PRESENTES = [
    "Pob*",
    "Referencias simples a B = 30",
    "github.com/Omarti34/Ecobicis2026",
    'id="qr-slot"',
    'role="math"',
    "Nota sobre el uso de IA generativa",
    "8,100,000",
    "450,000",
    "p ≤ 0.001",
]
SLIDES_AUSENTES = [
    "es posible", "mitad y mitad", "empate estadístico",
    "empate práctico", "los 18 de consenso doble", "mitigando",
    "p = 0.001", "incorpora la conectividad", "QR PROVISIONAL",
]


def validate_slides(path):
    """Puerta de aceptación de la presentación de diapositivas."""
    path = Path(path)
    if not path.exists():
        print(f"no existe: {path}")
        return 1
    page = path.read_text(encoding="utf-8")
    htxt = html_text(page)

    for pat, msg in [
            (r"(src|href)\s*=\s*[\"']https?://",
             "src/href http(s)://"),
            (r"url\(\s*[\"']?https?://", "url() http(s)://"),
            (r"fetch\(", "fetch()"),
            (r"XMLHttpRequest", "XMLHttpRequest"),
            (r"WebSocket", "WebSocket"),
            (r"<script[^>]+src=", "script externo"),
            (r"<link[^>]+href=", "link externo")]:
        if re.search(pat, page, re.I):
            fail(f"slides: dependencia externa ({msg})")
    externas = [u for u in re.findall(r"https?://[^\s\"'<>)]+", page)
                if "w3.org/2000/svg" not in u
                and "github.com/Omarti34/Ecobicis2026" not in u]
    if externas:
        fail(f"slides: URLs externas no permitidas {externas[:3]}")

    check_style("slides", htxt)

    for s in SLIDES_PRESENTES:
        if s not in htxt and s not in page:
            fail(f"slides: falta cadena obligatoria {s!r}")
    for s in SLIDES_AUSENTES:
        if s.lower() in htxt.lower():
            fail(f"slides: contiene cadena prohibida {s!r}")

    # cada figura 1-20: una diapositiva con pie y texto que la nombre
    slides = re.findall(
        r'<section class="slide"[^>]*>(.*?)</section>', page, re.S)
    if not slides:
        fail("slides: no se encontraron <section class='slide'>")
    for n in range(1, 21):
        ok = False
        for sec in slides:
            if f"Figura {n}." in sec:
                if len(re.findall(rf"Figura {n}(?![0-9])", sec)) >= 2:
                    ok = True
                    break
        if not ok:
            fail(f"slides: Figura {n} sin diapositiva que la nombre")

    # cifras clave del guion, derivadas de los JSON sellados
    ex, _u = expected()
    for k in ("pob_sin_estacion", "agebs_sin_estacion", "gini_estaciones",
              "gini_actividad", "viajes_aceptados", "m3_B30", "m1_B30",
              "m2_B30", "greedy_B15", "greedy_B30", "greedy_B50",
              "ga_B15", "ga_B30", "ga_B50", "moran_i", "blocks",
              "ridge_rmse", "ft_rmse", "t_greedy_run", "t_ga_run"):
        v = ex.get(k)
        if v is None:
            fail(f"slides: expected() no derivó {k}")
        elif v not in htxt and v not in page:
            fail(f"slides: falta la cifra sellada {k}={v}")

    # scatter congelado
    sc = json.loads((V3 / "data" / "presentacion_v2"
                     / "scatter_azar_b30.json").read_text(encoding="utf-8"))
    n_cloud = len(re.findall(r'class="cloud"', page))
    if n_cloud != len(sc["points"]):
        fail(f"slides: {n_cloud} puntos de nube != {len(sc['points'])}")
    ws = sc["w_sweep"]
    base_pop = sc["cloud"]["pop_mean"]
    for s, origen in [
            (f"{sc['universe_esc']:.2f}", "universo_esc"),
            (f"{sc['cloud']['esc_mean']:.2f}", "media nube"),
            (miles(sc["cloud"]["pop_mean"]), "pop_mean nube"),
            (miles(sc["cloud"]["pop_max"]), "pop_max nube"),
            (miles(sc["cloud"]["pop_sd"]), "sd nube"),
            (f"{sc['median_viajes_diarios_red']:.1f}", "mediana red"),
            (str(sc["n_estaciones"]), "n_estaciones"),
            (miles(sc["p_norm"]), "p_norm"),
            (miles(sc["official"]["m1"]["new_pop"]), "pop m1"),
            (miles(sc["official"]["m2"]["new_pop"]), "pop m2"),
            (miles(sc["official"]["m3"]["new_pop"]), "pop m3"),
            (f"{sc['official']['m1']['esc']:.2f}", "esc m1"),
            (f"{sc['official']['m2']['esc']:.2f}", "esc m2"),
            (f"{sc['official']['m3']['esc']:.2f}", "esc m3"),
            (miles(ws["1.0"]["new_pop"]), "w=1 new_pop"),
            (miles(ws["0.0"]["new_pop"]), "w=0 new_pop"),
            (f"{ws['0.0']['esc']:.2f}", "w=0 esc"),
            (f"{base_pop / base_pop:.2f}×", "ratio azar"),
            (f"{sc['official']['m1']['new_pop'] / base_pop:.2f}×",
             "ratio m1"),
            (f"{sc['official']['m2']['new_pop'] / base_pop:.2f}×",
             "ratio m2"),
            (f"{sc['official']['m3']['new_pop'] / base_pop:.2f}×",
             "ratio m3"),
            (f"{ws['0.0']['new_pop'] / base_pop:.2f}×", "ratio w=0"),
            (f"Jaccard {ws['1.0']['jaccard_vs_w05']:.1f}", "jaccard w=1")]:
        if s not in page and s not in htxt:
            fail(f"slides: falta la cifra del scatter {origen}={s}")
    pct_m1 = round(sc["rank"]["m1"]["share_random_esc_le"] * 100)
    pct_m3 = round(sc["rank"]["m3"]["share_random_esc_le"] * 100)
    if f"{pct_m1} %" not in htxt and f"percentil {pct_m1}" not in htxt:
        fail(f"slides: falta percentil {pct_m1} (m1)")
    if f"percentil {pct_m3}" not in htxt:
        fail(f"slides: falta 'percentil {pct_m3}' (m3)")

    # w_sweep contra m3_runs.csv
    import csv
    import glob
    runs_p = glob.glob(str(
        V3 / "data" / "engines" / "07_motor3" / "*"
        / "3aa53121*" / "m3_runs.csv"))
    if not runs_p:
        fail("slides: no se encontró m3_runs.csv del Motor 3")
    else:
        run_pops = {}
        for r in csv.DictReader(open(runs_p[0])):
            if r["method"] == "greedy" and r["budget"] == "30":
                run_pops[r["weight"]] = float(r["new_pop"])
        for k, v in ws.items():
            ref = run_pops.get(str(float(k)))
            if ref is None or abs(ref - v["new_pop"]) > 1e-6:
                fail(f"slides: w_sweep w={k} no reproduce m3_runs.csv "
                     f"({v['new_pop']} vs {ref})")

    # Motor 2 sellado
    a06 = load("06_motor2_transformer.json")
    a08 = load("08_comparacion_portafolios.json")
    bt = {r["subject"]: r for r in a08["backtest_context"]
          if r["scheme"] == "fold_spatial_block"}
    reg_sp = {r["model"]: r for r in a06["regression_means"]
              if r["fold_scheme"] == "fold_spatial_block"}
    reg_gp = {r["model"]: r for r in a06["regression_means"]
              if r["fold_scheme"] == "fold_groupkfold_ageb"}
    for s, origen in [
            (f"{reg_sp['random_forest']['spearman']:.3f}",
             "spearman RF espacial"),
            (f"{reg_sp['random_forest']['r2']:.3f}", "R² RF"),
            (f"{reg_sp['ridge']['rmse']:.4f}", "RMSE ridge"),
            (f"{reg_sp['ft_transformer']['rmse']:.4f}", "RMSE FT"),
            (f"{bt['random_forest']['ndcg_at_10']:.3f}", "NDCG@10 RF"),
            (f"{bt['control_aleatorio']['ndcg_at_10']:.3f}",
             "NDCG@10 control"),
            (f"{reg_gp['random_forest']['spearman']:.3f}",
             "spearman RF grupos")]:
        if s not in htxt and s not in page:
            fail(f"slides: falta la cifra sellada {origen}={s}")

    if FAILS:
        print(f"RECHAZADO: {len(FAILS)} falla(s)")
        for f in FAILS:
            print(" -", f)
        return 1
    print(f"APROBADO slides: {path} ({len(slides)} diapositivas)")
    return 0


if __name__ == "__main__":
    if "--html" in sys.argv:
        i = sys.argv.index("--html")
        sys.exit(validate_v2(sys.argv[i + 1]))
    if "--slides" in sys.argv:
        i = sys.argv.index("--slides")
        sys.exit(validate_slides(sys.argv[i + 1]))
    sys.exit(main())
