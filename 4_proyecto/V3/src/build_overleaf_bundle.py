#!/usr/bin/env python3
"""Empaqueta V3/docs/BORRADOR_TESIS_MAESTRO.md como documento LaTeX para Overleaf.

Fuente única de verdad: el markdown ya generado por V3/src/build_thesis_draft.py.
Este script NO re-lee los JSONs de V3/audits ni recomputa cifras: traduce el
markdown sellado a IEEEtran (conference), copia las figuras referenciadas y
comprime el directorio resultante en un zip subible a Overleaf.

Stdlib pura. Determinista (bytes idénticos entre ejecuciones). Escritura
atómica: todo archivo se escribe a un temporal y se renombra con os.replace.

Salida:
  V3/docs/overleaf_caso_negocio/main.tex
  V3/docs/overleaf_caso_negocio/figures/...   (subdirs c8/ y e02/)
  V3/caso_negocio_overleaf.zip                (main.tex en la raíz del zip)
"""

import hashlib
import os
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "V3" / "docs"
MD = DOCS / "BORRADOR_TESIS_MAESTRO.md"
BUNDLE = DOCS / "overleaf_caso_negocio"
ZIP_PATH = ROOT / "V3" / "caso_negocio_overleaf.zip"


def fail(msg):
    print(f"ERROR build_overleaf_bundle: {msg}", file=sys.stderr)
    sys.exit(1)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    mode = "wb" if isinstance(data, bytes) else "w"
    kw = {} if isinstance(data, bytes) else {"encoding": "utf-8", "newline": "\n"}
    with open(tmp, mode, **kw) as f:
        f.write(data)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Texto en línea: matemáticas, código, escapes y énfasis
# --------------------------------------------------------------------------

UNICODE_MAP = {
    "≤": r"$\le$",
    "≥": r"$\ge$",
    "−": r"$-$",
    "×": r"$\times$",
    "²": r"\textsuperscript{2}",
    "·": r"\textperiodcentered{}",
    "…": r"\dots{}",
}

_SENT = "\x00"


def _escape_text(s):
    """Escapa especiales LaTeX en texto plano (sin tocar \\x ya escapados)."""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            out.append(s[i:i + 2])          # secuencia ya escapada (\%, \{, ...)
            i += 2
            continue
        if ch in "&%#":
            out.append("\\" + ch)
        elif ch == "_":
            out.append(r"\_")
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch in "{}":
            out.append("\\" + ch)
        elif ch in UNICODE_MAP:
            out.append(UNICODE_MAP[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _escape_code(s):
    out = []
    for ch in s:
        if ch in "&%#_{}":
            out.append("\\" + ch)
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        elif ch == "\\":
            out.append(r"\textbackslash{}")
        elif ch in UNICODE_MAP:
            out.append(UNICODE_MAP[ch])
        else:
            out.append(ch)
    return "".join(out)


def _render_code(raw):
    """`código` -> \\texttt; tokens largos/rutas/hashes -> \\path (rompe líneas).

    \\path lee su argumento en modo verbatim: no admite espacios ni marcas
    internas; para cualquier código con espacios se usa \\texttt escapado.
    """
    if (" " not in raw
            and (len(raw) >= 24 or "/" in raw
                 or re.fullmatch(r"[0-9a-fA-F]{20,}", raw))):
        return r"\path{" + raw + "}"
    return r"\texttt{" + _escape_code(raw) + "}"


# Definiciones de notas al pie markdown ([^n]: texto) recolectadas por
# build_tex; las referencias [^n] en línea se convierten a \footnote{...}.
FOOTNOTES = {}


def tex(s):
    """Convierte un fragmento markdown en línea a LaTeX."""
    maths, codes, fns = [], [], []

    def stash_fn(m):
        fns.append(m.group(1))
        return f"{_SENT}F{len(fns) - 1}{_SENT}"

    def stash_math(m):
        maths.append(m.group(0))
        return f"{_SENT}M{len(maths) - 1}{_SENT}"

    def stash_code(m):
        codes.append(m.group(1))
        return f"{_SENT}C{len(codes) - 1}{_SENT}"

    s = re.sub(r"\[\^([^\]]+)\]", stash_fn, s)
    s = re.sub(r"\$[^$]+\$", stash_math, s)
    s = re.sub(r"`([^`]+)`", stash_code, s)
    s = _escape_text(s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"\*([^*]+)\*", r"\\emph{\1}", s)

    def unstash(m):
        tag, idx = m.group(1), int(m.group(2))
        if tag == "M":
            return maths[idx]
        if tag == "C":
            return _render_code(codes[idx])
        key = fns[idx]
        if key not in FOOTNOTES:
            fail(f"nota al pie [^{key}] sin definición")
        return r"\footnote{" + tex(FOOTNOTES[key]) + "}"

    return re.sub(_SENT + r"([MCF])(\d+)" + _SENT, unstash, s)


def plain(s):
    """Longitud de texto plano (sin marcas md) para estimar anchos de tabla."""
    s = re.sub(r"\[\^[^\]]+\]", "", s)
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = s.replace("**", "").replace("*", "")
    return s


# --------------------------------------------------------------------------
# Tablas
# --------------------------------------------------------------------------

def split_row(line):
    inner = line.strip().strip("|")
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", inner)]


def is_separator(cells):
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def render_table(lines, in_quote=False):
    rows = [split_row(l) for l in lines]
    header, body = rows[0], [r for r in rows[1:] if not is_separator(r)]
    ncols = len(header)
    if any(len(r) != ncols for r in body):
        fail(f"fila de tabla con número de columnas distinto: {lines[0][:60]}")
    maxlen = [0] * ncols
    for r in [header] + body:
        for j, c in enumerate(r):
            maxlen[j] = max(maxlen[j], len(plain(c)))
    est = sum(maxlen) + 4 * ncols
    W_CH = 0.011          # fracción de \linewidth estimada por carácter
    seps = 0.015 * ncols  # \tabcolsep y renglón

    if in_quote:
        # dentro de quote (una columna): todo envuelve en p{frac\linewidth}
        avail_p = 0.90 - seps
        spec = "".join(
            r">{\raggedright\arraybackslash}p{%.2f\linewidth}"
            % max(0.08, avail_p * maxlen[j] / max(1, sum(maxlen)))
            for j in range(ncols))
        prose = set()
        avail = 10**9      # jamás resizebox dentro de quote
    else:
        prose = {j for j, L in enumerate(maxlen) if L >= 45}
        avail = 92 if (ncols > 6 or est > 90 or prose) else 44
        if prose:
            fixed = seps + sum(W_CH * maxlen[j]
                               for j in range(ncols) if j not in prose)
            avail_p = 0.94 - fixed
            total = sum(maxlen[j] for j in prose) or 1
            spec = "".join(
                (r">{\raggedright\arraybackslash}p{%.2f\linewidth}"
                 % max(0.10, avail_p * maxlen[j] / total))
                if j in prose else "l"
                for j in range(ncols))
        else:
            spec = "l" * ncols

    def row_tex(r):
        return " & ".join(tex(c) for c in r) + r" \\"

    body_tex = [row_tex(header), r"\midrule"] + [row_tex(r) for r in body]
    tabular = [r"\begin{tabular}{%s}" % spec, r"\toprule"] + body_tex + [
        r"\bottomrule", r"\end{tabular}"]

    if not in_quote and not prose and est > avail:
        tabular = [r"\resizebox{\linewidth}{!}{%"] + tabular + ["}%"]

    if in_quote:
        return tabular
    env = "table*" if (ncols > 6 or est > 90 or prose) else "table"
    return [rf"\begin{{{env}}}[!tbp]", r"\centering"] + tabular + [rf"\end{{{env}}}"]


# --------------------------------------------------------------------------
# Figuras
# --------------------------------------------------------------------------

def png_ratio(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        fail(f"no es un PNG válido: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return w / h


# --------------------------------------------------------------------------
# Bloques markdown -> LaTeX
# --------------------------------------------------------------------------

NORMAL_HEAD = {1: "section", 2: "section", 3: "subsection"}
ANNEX_HEAD = {1: "subsection", 2: "subsubsection", 3: "paragraph"}


def strip_manual_number(text):
    text = re.sub(r"^\d+\.\s+", "", text)
    text = re.sub(r"^Apéndice\s+[A-Z]\.\s+", "", text)
    return text.strip()


def render_lines(lines, in_quote=False, annex=False):
    """Traduce una lista de líneas md. Devuelve (líneas tex, figuras usadas)."""
    out, figs = [], []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()

        if not s:
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl, txt = len(m.group(1)), m.group(2)
            hmap = ANNEX_HEAD if annex else NORMAL_HEAD
            cmd = hmap.get(min(lvl, 3))
            if cmd is None:
                fail(f"encabezado de nivel {lvl} no soportado: {s[:60]}")
            out.append(rf"\{cmd}{{{tex(strip_manual_number(txt))}}}")
            i += 1
            continue

        if s.startswith("!["):
            m = re.fullmatch(r"!\[(.*)\]\((.+)\)", s)
            if not m:
                fail(f"imagen mal formada: {s[:80]}")
            cap, rel = m.group(1), m.group(2)
            src = DOCS / rel
            if not src.exists():
                fail(f"figura referenciada no existe: {rel}")
            figs.append(rel)
            env = "figure*" if png_ratio(src) > 1.9 else "figure"
            out += [rf"\begin{{{env}}}[!tbp]", r"\centering",
                    rf"\includegraphics[width=\linewidth]{{{rel}}}",
                    rf"\caption{{{tex(cap)}}}",
                    rf"\label{{fig:{len(figs)}}}",
                    rf"\end{{{env}}}"]
            i += 1
            continue

        if s.startswith("|"):
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            if j - i < 2 or not is_separator(split_row(lines[i + 1])):
                fail(f"tabla mal formada cerca de: {s[:60]}")
            out += render_table([l.strip() for l in lines[i:j]], in_quote)
            i = j
            continue

        if s.startswith(">"):
            j = i
            inner = []
            while j < n and lines[j].lstrip().startswith(">"):
                inner.append(re.sub(r"^\s*>\s?", "", lines[j]))
                j += 1
            sub, subfigs = render_lines(inner, in_quote=True, annex=annex)
            figs += subfigs
            out += [r"\begin{quote}", r"\itshape"] + sub + [r"\end{quote}"]
            i = j
            continue

        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            j = i
            out.append(r"\begin{itemize}")
            while j < n:
                mm = re.match(r"^[-*]\s+(.*)$", lines[j].strip())
                if not mm:
                    break
                out.append(r"\item " + tex(mm.group(1)))
                j += 1
            out.append(r"\end{itemize}")
            i = j
            continue

        if re.match(r"^\d+\.\s+", s):
            j = i
            out.append(r"\begin{enumerate}")
            while j < n:
                mm = re.match(r"^\d+\.\s+(.*)$", lines[j].strip())
                if not mm:
                    break
                out.append(r"\item " + tex(mm.group(1)))
                j += 1
            out.append(r"\end{enumerate}")
            i = j
            continue

        # párrafo: acumula líneas consecutivas que no abran otro bloque
        j = i
        segs = []
        while j < n:
            raw = lines[j]
            t = raw.strip()
            if (not t or t.startswith(("#", "!", "|", ">", "- "))
                    or re.match(r"^\d+\.\s", t)):
                break
            seg = tex(t)
            if raw.rstrip().endswith("  ") or raw.endswith("  "):
                seg += r" \newline"            # quiebre duro markdown (dos espacios)
            segs.append(seg)
            j += 1
        out.append(" ".join(segs))
        i = j
    return out, figs


# --------------------------------------------------------------------------
# Documento completo
# --------------------------------------------------------------------------

PREAMBLE = r"""\documentclass[conference]{IEEEtran}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[spanish]{babel}
\usepackage{amsmath}
\usepackage{graphicx,booktabs,url,hyperref,float,array}
\hypersetup{colorlinks=true,linkcolor=black,citecolor=black,urlcolor=blue}
% Permite que \path/\url quiebren tokens largos (hashes de analysis_id) en
% cualquier carácter; de otro modo un hash de 64 caracteres no cabe en columna.
\def\UrlBreaks{\do\a\do\b\do\c\do\d\do\e\do\f\do\g\do\h\do\i\do\j\do\k\do\l
\do\m\do\n\do\o\do\p\do\q\do\r\do\s\do\t\do\u\do\v\do\w\do\x\do\y\do\z
\do\A\do\B\do\C\do\D\do\E\do\F\do\G\do\H\do\I\do\J\do\K\do\L\do\M\do\N
\do\O\do\P\do\Q\do\R\do\S\do\T\do\U\do\V\do\W\do\X\do\Y\do\Z
\do0\do1\do2\do3\do4\do5\do6\do7\do8\do9\do-\do_\do.\do/}
"""

KEYWORDS = ("EcoBici, expansión de red, optimización espacial, micromovilidad, "
            "caso de negocio")


def build_tex(md_text):
    lines = md_text.split("\n")

    # Notas al pie: recolecta definiciones [^n]: ... (una línea cada una)
    # y las retira del flujo; las referencias se expanden a \footnote{}.
    FOOTNOTES.clear()
    kept = []
    for l in lines:
        t = l.strip()
        m = re.match(r"^\[\^([^\]]+)\]:\s*(.+)$", t)
        if m:
            FOOTNOTES[m.group(1)] = m.group(2).strip()
        elif t.startswith("[^"):
            fail(f"definición de nota al pie mal formada: {t[:70]}")
        else:
            kept.append(l)
    lines = kept

    # Título: primer H1 del documento
    m = re.match(r"^#\s+(.*)$", lines[0])
    if not m:
        fail("el markdown no empieza con un título H1")
    title = tex(m.group(1).strip())

    # Abstract: primeros dos párrafos de la Introducción
    abstract = ""
    for k, l in enumerate(lines):
        if l.strip() == "## Introducción":
            paras = []
            for t in lines[k + 1:]:
                t = t.strip()
                if not t:
                    continue
                if t.startswith("#"):
                    break
                paras.append(re.sub(r"^\*\*[^*]+\*\*\s*", "", t))
                if len(paras) == 2:
                    break
            if len(paras) < 2:
                fail("Introducción sin al menos dos párrafos")
            abstract = tex(paras[0]) + " " + tex(paras[1])
            break
    if not abstract:
        fail("no se encontró la sección '## Introducción'")

    # Cuerpo: localiza Apéndice A / Anexo 1 y separa modo anexo
    body, figs = [], []
    annex_mode = False
    appendix_done = False
    i = 1
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        h2 = re.match(r"^##\s+(.*)$", s)
        if h2 and not annex_mode:
            label = h2.group(1)
            if label.startswith("Apéndice") and not appendix_done:
                body.append(r"\appendix")
                body.append(rf"\section{{{tex(strip_manual_number(label))}}}")
                appendix_done = True
                i += 1
                continue
            if label.startswith("Anexo"):
                body.append(rf"\section{{{tex(label)}}}")
                annex_mode = True
                i += 1
                continue
        if annex_mode:
            sub, sf = render_lines(lines[i:], annex=True)
            body += sub
            figs += sf
            break
        # bloque regular: hasta el próximo encabezado ## Apéndice/Anexo
        j = i
        while j < n and not re.match(r"^##\s+(Apéndice|Anexo)", lines[j].strip()):
            j += 1
        sub, sf = render_lines(lines[i:j])
        body += sub
        figs += sf
        i = j

    body_tex = "\n\n".join(b for b in body if b != "") + "\n"

    tex_doc = (
        PREAMBLE
        + rf"\title{{{title}}}" + "\n"
        + "% TODO: completar autores\n"
        + r"\author{Autor por completar}" + "\n"
        + r"\date{}" + "\n\n"
        + r"\begin{document}" + "\n"
        + r"\maketitle" + "\n\n"
        + r"\begin{abstract}" + "\n" + abstract + "\n" + r"\end{abstract}" + "\n\n"
        + r"\begin{IEEEkeywords}" + "\n" + tex(KEYWORDS) + "\n" + r"\end{IEEEkeywords}" + "\n\n"
        + body_tex
        + r"\end{document}" + "\n"
    )
    return tex_doc, figs


def verify_tex(tex_doc):
    bad = []
    for ln, l in enumerate(tex_doc.split("\n"), 1):
        if "**" in l or "](" in l or l.startswith("#") or l.lstrip().startswith("|"):
            bad.append((ln, l[:80]))
    if bad:
        for ln, l in bad[:10]:
            print(f"  residuo markdown en línea {ln}: {l}", file=sys.stderr)
        fail("traducción incompleta: quedan constructos markdown sin procesar")


def main():
    if not MD.exists():
        fail(f"no existe el markdown fuente: {MD}")
    md_text = MD.read_text(encoding="utf-8")
    tex_doc, figs = build_tex(md_text)
    verify_tex(tex_doc)

    # limpia el directorio destino (es generado íntegramente por este script)
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)

    # copia figuras referenciadas preservando subdirectorios
    copied = []
    for rel in sorted(set(figs)):
        src = DOCS / rel
        dst = BUNDLE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append(rel)

    atomic_write(BUNDLE / "main.tex", tex_doc)

    # zip determinista: main.tex en la raíz, entradas ordenadas, fecha fija
    names = ["main.tex"] + copied
    tmp = ZIP_PATH.parent / (ZIP_PATH.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, (BUNDLE / name).read_bytes())
    os.replace(tmp, ZIP_PATH)

    h_tex = hashlib.sha256((BUNDLE / "main.tex").read_bytes()).hexdigest()
    h_zip = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    n_tstar = tex_doc.count(r"\begin{table*}")
    n_tbl = tex_doc.count(r"\begin{table}[")
    n_fstar = tex_doc.count(r"\begin{figure*}")
    n_fig = tex_doc.count(r"\begin{figure}[")
    print(f"main.tex:  {BUNDLE / 'main.tex'}")
    print(f"sha256:    {h_tex}")
    print(f"zip:       {ZIP_PATH}")
    print(f"sha256:    {h_zip}")
    print(f"figuras:   {len(copied)} copiadas ({n_fig} figure, {n_fstar} figure*)")
    print(f"tablas:    {n_tbl} table, {n_tstar} table*")


if __name__ == "__main__":
    main()
