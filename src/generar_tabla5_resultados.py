#!/usr/bin/env python3
"""Reconstruye la Tabla 5 del caso EcoBici: cobertura por presupuesto.

Lee el artefacto sellado ``c8_metricas.csv`` publicado por el cuaderno 08
(Evaluación Comparativa), verifica su firma sha256 contra el registro de
auditoría ``audits/08_comparacion_portafolios.json`` y formatea en consola
la tabla de portafolios oficiales (3 motores x B en {15, 30, 50}).

Usa únicamente la biblioteca estándar: no requiere pandas ni numpy.

Uso:
    python src/generar_tabla5_resultados.py
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICAS = ROOT / "data" / "resultados" / "c8_metricas.csv"
AUDIT = ROOT / "data" / "audits" / "08_comparacion_portafolios.json"

# Cifras canónicas del registro de afirmaciones (auditoría 09) para contraste.
CANONICAS = {
    ("m1", 15): 113528.21, ("m2", 15): 136490.42, ("m3", 15): 166731.06,
    ("m1", 30): 202337.35, ("m2", 30): 282101.84, ("m3", 30): 310287.81,
    ("m1", 50): 300803.12, ("m2", 50): 428400.77, ("m3", 50): 481553.56,
}

NOMBRES = {
    "m1": "Motor 1 (similitud PCA)",
    "m2": "Motor 2 (Random Forest)",
    "m3": "Motor 3 (grafo, w=0.5)",
}


def sha256_de(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def verificar_integridad():
    """Compara el sha256 del CSV con el firmado en la auditoría 08."""
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    esperados = {
        Path(o["path"]).name: o["sha256"] for o in audit.get("outputs", [])
    }
    esperado = esperados.get(METRICAS.name)
    real = sha256_de(METRICAS)
    if esperado is None:
        print("AVISO: el audit no registra firma para", METRICAS.name)
        return
    estado = "COINCIDE" if real == esperado else "NO COINCIDE"
    print(f"Integridad del artefacto ({METRICAS.name}):")
    print(f"  sha256 registrado en auditoría 08: {esperado}")
    print(f"  sha256 del archivo en el repo:     {real}")
    print(f"  Resultado: {estado}\n")
    if real != esperado:
        sys.exit("ERROR: el artefacto no coincide con la firma sellada.")


def main():
    verificar_integridad()
    with open(METRICAS, newline="", encoding="utf-8") as f:
        filas = [r for r in csv.DictReader(f) if r["tier"] == "oficial"]
    filas.sort(key=lambda r: (r["motor"], int(r["budget"])))

    print("Tabla 5. Cobertura por presupuesto — portafolios oficiales")
    print("(población nueva a 500 m, retícula de 200 m; artefacto sellado "
          "por el pipeline, no recalculada desde datos crudos)\n")
    encabezado = f"{'Motor':<26}{'B':>4}{'Sitios':>8}{'Pob. nueva':>13}" \
                 f"{'% brecha':>10}{'Escolaridad':>13}{'AGEBs':>7}"
    print(encabezado)
    print("-" * len(encabezado))
    errores = []
    for r in filas:
        motor, b = r["motor"], int(r["budget"])
        pob = float(r["new_pop"])
        print(f"{NOMBRES[motor]:<26}{b:>4}{r['n_selected']:>8}"
              f"{pob:>13,.0f}{float(r['new_pop_share']) * 100:>9.1f}%"
              f"{float(r['mean_grado_escolar_prom_selected']):>13.2f}"
              f"{r['n_agebs']:>7}")
        canon = CANONICAS[(motor, b)]
        if abs(pob - canon) > 0.5:
            errores.append((motor, b, pob, canon))
    print("-" * len(encabezado))
    print("Referencia de sensibilidad: Motor 3 con GA, B=30 -> 305,090 "
          "(fila 'sensibilidad' del mismo artefacto)\n")

    if errores:
        for motor, b, pob, canon in errores:
            print(f"DISCREPANCIA {motor} B={b}: {pob:,.0f} != {canon:,.0f}")
        sys.exit("ERROR: la tabla no reproduce las cifras canónicas.")
    print("VERIFICADO: las 9 filas reproducen las cifras canónicas de la "
          "auditoría (tolerancia < 1 persona).")


if __name__ == "__main__":
    main()
