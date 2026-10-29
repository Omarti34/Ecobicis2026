#!/usr/bin/env bash
# Orden exacto de ejecución del pipeline auditado (cuadernos 00-09 y
# entregables). Ejecutar desde la raíz del repositorio.
#
# Requisitos previos:
#   1. Entorno con requirements-notebooks.txt instalado (torch + jupyter).
#   2. Datos crudos de entrada en 4_proyecto/V3/data/raw/ (ver README).
#
# La raíz de ejecución que el código espera es 4_proyecto/V3/.
# El cuaderno 07 tarda ~26 min (greedy principal + GA de comparación).

set -euo pipefail
cd "$(dirname "$0")"
PROYECTO="4_proyecto/V3"

echo "== Fase 1: manifiesto de fuentes y ETL (cuadernos 00 y 01) =="
python "$PROYECTO/src/crear_fase1_notebooks.py"
python "$PROYECTO/src/ejecutar_fase1_notebooks.py"

echo "== Cuaderno 02: EDA y equidad =="
python "$PROYECTO/src/build_notebook_02.py"

echo "== Cuaderno 03: ingeniería de características y PCA =="
python "$PROYECTO/src/build_notebook_03.py"

echo "== Cuaderno 04: diseño de validación espacial (bloques + anillo 500 m) =="
python "$PROYECTO/src/build_notebook_04.py"

echo "== Cuadernos 05/06/07: los tres motores (en paralelo) =="
python "$PROYECTO/src/build_notebook_05.py" &
python "$PROYECTO/src/build_notebook_06.py" &
python "$PROYECTO/src/build_notebook_07.py" &
wait

echo "== Cuaderno 08: evaluación comparativa de portafolios =="
python "$PROYECTO/src/build_notebook_08.py"

echo "== Cuaderno 09: sello del registro de afirmaciones =="
python "$PROYECTO/src/build_notebook_09.py"

echo "== Documento académico y paquete Overleaf =="
python "$PROYECTO/src/build_thesis_draft.py"
python "$PROYECTO/src/build_overleaf_bundle.py"

echo "== Entregable: presentación ejecutiva =="
python "$PROYECTO/src/build_entregable.py"

echo "== Puerta de aceptación: validador del entregable =="
python "$PROYECTO/src/validate_entregable.py"

echo "Pipeline completo. Resultados en 4_proyecto/V3/audits/ y V3/entregable/."
