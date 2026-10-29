"""Documented notebook recipes; results read the committed ETL audit."""
from textwrap import dedent

NOTEBOOKS = {"00_Manifest_y_Fuentes.ipynb": [], "01_ETL_Reproducible.ipynb": []}


def md(book, text):
    book.append(("markdown", dedent(text).strip()))


def code(book, text):
    book.append(("code", dedent(text).strip()))


BOOT = """
import json
import sys
from pathlib import Path
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq
from IPython.display import display, Markdown

BASE = Path.cwd().resolve()
PROJECT = next(folder for folder in [BASE, *BASE.parents]
               if (folder / "V3/data/raw").is_dir())
V3 = PROJECT / "V3"
sys.path.insert(0, str(PROJECT))
from V3.src.etl_contract import build_manifest, verify_manifest, provenance, get_processed_root, get_quarantine_root
from V3.src.enterprise_etl import run_etl, verify_outputs
print("Directorio del proyecto:", V3)
"""

book = NOTEBOOKS["00_Manifest_y_Fuentes.ipynb"]
md(book, """
# 00. Registro de fuentes y contrato de reproducibilidad

Registramos los insumos disponibles antes de transformarlos y delimitamos la
versión del ETL que los procesa. El contrato incluye las huellas SHA-256 de
las fuentes, las políticas de limpieza, las versiones del entorno y el código
productor. Esta identificación permite distinguir cambios de datos de cambios
de procedimiento y conservar la evidencia de cada generación.
""")
code(book, BOOT)
md(book, """
## Inventario del contenido de RAW

Calculamos las huellas a partir del contenido de los archivos y mantenemos
RAW en modo de lectura. Excluimos únicamente `.DS_Store`, que contiene
metadatos de Finder y no observaciones. Las copias extraídas de DENUE y GTFS
se registran en el inventario y se verifican contra el miembro correspondiente
de su ZIP; la lectura analítica se realiza una sola vez desde el archivo
comprimido. Una diferencia entre copia y archivo original detiene el ETL.
""")
code(book, """
manifest = build_manifest(V3)
sources = pd.DataFrame(manifest["files"])
sources["bytes"] = sources.bytes.astype("Int64")
sources = provenance(sources, sources.path.astype("string"), manifest)
display(sources)
display(Markdown(f"**Resultados.** Registramos {len(sources):,} archivos de datos y documentación. "
                 f"El contrato activo es `{manifest['contract_id']}`."))
""")
md(book, """
## Políticas y alcance de la versión

La versión actual normaliza estaciones, AGEBs, viajes, los tabulados del Censo,
DENUE, GTFS, ciclovías y registros viales C5, de accidentes y de víctimas SSC.
Los diccionarios, metadatos y publicaciones se conservan como documentación
estructurada, no como observaciones. No completamos nulos por defecto:
distinguimos faltantes legítimos, valores suprimidos, atributos opcionales y
ausencia de campos necesarios para una tarea.

El año 2025 delimita las observaciones de viajes e incidentes. Los catálogos
y las fuentes estructurales conservan su época de origen: Censo 2020, marco
geográfico diciembre de 2025, catálogo GBFS septiembre de 2026 y DENUE 2026.
El calendario GTFS contiene servicios de diferentes años. Estas diferencias
se mantienen como limitaciones temporales y no se reinterpretan como mediciones
simultáneas de 2025.
""")
code(book, """
display(pd.Series(manifest["policy"], name="politica").to_frame())
display(pd.Series(manifest["versions"], name="version").to_frame())
display(pd.Series(manifest["code_hashes"], name="sha256_productor").to_frame())
display(sources.groupby("role").size().rename("archivos").to_frame())
""")
md(book, """
## Verificación del contrato

Repetimos la comprobación de RAW para asegurar que el contrato permanece
vigente. Las generaciones anteriores no se eliminan ni se reinterpretan:
mantienen sus auditorías y artefactos. Una modificación requiere una
actualización explícita de versión. El timestamp UTC de las tablas pertenece
a la época lógica del contrato; las horas reales de ejecución se registran
separadamente, de modo que no alteran los archivos de datos en cada corrida.
""")
code(book, """
assert verify_manifest(V3) == manifest
display(Markdown("**Resultados.** El contrato conserva las mismas fuentes, políticas "
                 "y versiones. La verificación de contenido no detectó cambios en RAW."))
""")

book = NOTEBOOKS["01_ETL_Reproducible.ipynb"]
md(book, """
# 01. Normalización reproducible de las fuentes

Transformamos las fuentes certificadas en tablas tipadas y documentadas para
el análisis posterior. Cada registro conserva su origen y las tablas
normalizadas se publican junto con una cuarentena inspeccionable. Los faltantes
no se eliminan ni se sustituyen globalmente por cero. La aceptación depende
del uso previsto: una coordenada ausente impide una operación espacial, mientras
que un teléfono ausente no invalida una unidad económica.
""")
code(book, BOOT + """
assert (V3 / "audits/00_manifest.json").is_file(), "Ejecutar primero el cuaderno00."
manifest = verify_manifest(V3)
""")
md(book, """
## Ejecución y publicación de una generación

Aplicamos reglas específicas por fuente, normalizamos texto a UTF-8/NFC y
preservamos identificadores como cadenas cuando sus ceros iniciales tienen
significado. Los conteos utilizan enteros nulables y los pesos de eventos
utilizan valores fraccionarios. La deduplicación utiliza fechas de actualización
cuando están disponibles; sin ellas, el desempate es determinista por hash
y fila, sin afirmar que la fecha de registro represente una actualización.

La publicación utiliza staging, bloqueo exclusivo y comprobaciones de
conservación. La auditoría final actúa como marcador de compromiso: los
consumidores rechazan generaciones incompletas. Las tablas de esta versión
son insumos preparados; no constituyen todavía una matriz PCA ni una
validación causal, temporal o predictiva.
""")
code(book, """
audit = run_etl(V3)
processed = get_processed_root(V3)
quarantine = get_quarantine_root(V3)
display(pd.Series(audit["stations"], name="estaciones").to_frame())
display(pd.Series(audit["agebs"], name="agebs").to_frame())
display(pd.Series(audit["trip_rows"], name="viajes").to_frame())
auxiliary_quality = pd.DataFrame(audit["auxiliary"]["tables"]).T
display(auxiliary_quality)
display(Markdown(f"**Resultados.** La generación conserva {audit['stations']['accepted_rows']:,} "
                 f"estaciones y {audit['agebs']['accepted_rows']:,} AGEBs. En viajes, "
                 f"{audit['trip_rows']['accepted_rows']:,} filas cumplen el contrato y "
                 f"{audit['trip_rows']['quarantine_rows']:,} se conservan en cuarentena."))
""")
md(book, """
## Identidad de estaciones, actividad y uso extremo

Resolvemos los códigos dobles del catálogo mediante una tabla de alias. Los
componentes de `158-159`, por ejemplo, apuntan a una sola estación física.
Esto evita perder eventos por códigos secundarios o crear estaciones nuevas
sin respaldo en el catálogo.

La actividad diaria es `(retiros + arribos) / (2 × 365)`. Marcamos las
estaciones por encima de `Q3 + 1.5 × IQR`, sin excluirlas. El criterio IQR
no define el Golden Cluster: esa definición por P85 corresponde al EDA.
El snapshot GBFS de 2026 no acredita por sí solo operación de cada estación
durante todo 2025.
""")
code(book, """
stations = pd.read_parquet(processed / "estaciones.parquet")
aliases = pd.read_parquet(processed / "station_aliases.parquet")
activity = pd.read_parquet(processed / "actividad_estaciones.parquet")
display(stations[["ce_id", "name", "_updated_at", "catalog_snapshot_outside_2025"]].head())
display(aliases.head())
display(activity[["ce_id", "viajes_diarios_prom", "is_outlier_high"]].head())
assert activity.dias_calendario.eq(365).all()
assert len(activity) == len(stations)
display(Markdown(f"**Resultados.** {len(aliases):,} códigos se resuelven en {len(stations):,} "
                 f"estaciones físicas. Conservamos las {int(activity.is_outlier_high.sum()):,} "
                 "estaciones señaladas por IQR."))
""")
md(book, """
## Geometrías AGEB y tabulados del Censo

Conservamos las AGEBs rurales sin población disponible y mantenemos su
densidad como faltante. Respetamos el CRS declarado de las geometrías y
calculamos las áreas en EPSG:32614. La cuarentena conserva las geometrías que
no cumplen las comprobaciones de forma, finitud y tipo.

En el Censo distinguimos totales de entidad, municipio, localidad, AGEB y
manzana. Conservamos todas las filas y publicamos una vista de totales AGEB
para evitar sumar repetidamente niveles de agregación. Los asteriscos de
supresión estadística se representan como nulos con indicadores explícitos.
La ausencia de un dato suprimido no se interpreta como cero.
""")
code(book, """
agebs = gpd.read_parquet(processed / "agebs.parquet")
census_ageb = pd.read_parquet(processed / "censo_ageb_2020.parquet")
rural = agebs.loc[agebs.is_rural_nan.fillna(False)]
display(rural[["cvegeo", "pob_total", "densidad_pob_km2", "is_rural_nan"]])
display(census_ageb[["cvegeo", "POBTOT", "has_suppressed_values"]].head())
assert len(rural) == 22 and rural.pob_total.isna().all() and rural.densidad_pob_km2.isna().all()
assert census_ageb.cvegeo.is_unique
display(Markdown(f"**Resultados.** Preservamos {len(rural)} AGEBs rurales sin población "
                 f"y publicamos {len(census_ageb):,} totales AGEB del Censo. "
                 "La conservación de nulos evita fabricar densidades o conteos."))
""")
md(book, """
### Hallazgos de correspondencia territorial

En la ejecución registrada en `audits/01_findings_v3.json` conservamos las
68,941 filas censales y obtuvimos 2,433 totales AGEB, sin mezclar esos totales
con sus manzanas. Las 2,430 geometrías urbanas tienen correspondencia censal;
tres claves censales no aparecen en la capa geométrica disponible. Conservamos
esas claves sin fabricar polígonos. Las diferencias de marco territorial
requieren revisión explícita antes de construir atributos espaciales.

Estos resultados corresponden a la generación de fuentes completas registrada
en esa auditoría. La aceptación estructural no implica ausencia de supresión
estadística ni sustituye una comprobación sustantiva de cada variable.
""")
md(book, """
## Unidades económicas DENUE

Validamos identificadores, clasificación SCIAN y coordenadas, conservando
atributos opcionales como teléfono, correo y razón social cuando son nulos.
Señalamos claves AGEB sin correspondencia con el marco geográfico sin
atribuirles automáticamente una localización administrativa nueva. Las
categorías de personal ocupado permanecen como intervalos; una estimación
puntual de empleo requerirá una decisión explícita en feature engineering.

Los metadatos identifican esta edición como DENUE 2026. La conservamos con
esa advertencia y no afirmamos que represente establecimientos existentes en
2025. La fecha de alta tampoco se utiliza como fecha de actualización.
""")
code(book, """
denue_quality = audit["auxiliary"]["tables"]["denue"]
display(pd.Series(denue_quality, name="calidad_denue").to_frame())
batch = next(pq.ParquetFile(processed / "denue.parquet").iter_batches(batch_size=5), None)
display(batch.to_pandas() if batch is not None else pd.DataFrame())
display(Markdown(f"**Resultados.** DENUE: {denue_quality['accepted_rows']:,} registros aceptados "
                 f"y {denue_quality['quarantine_rows']:,} conservados en cuarentena. "
                 "El informe distingue nulos por atributo y problemas de identidad o coordenadas."))
""")
md(book, """
### Hallazgos de DENUE

La ejecución registrada conserva 462,732 establecimientos sin rechazos por
identidad, clasificación SCIAN o coordenadas. Sin embargo, 1,498 registros
tienen claves AGEB sin correspondencia con la capa geográfica disponible.
El indicador `ageb_key_unmatched` permite identificarlos sin excluirlos ni
asignarlos automáticamente a una AGEB.

La edición es 2026 y 9,627 registros tienen fecha de alta posterior a 2025.
No interpretamos la fecha de alta de los restantes establecimientos como
prueba de que seguían operando en 2025. La utilización del directorio como
contexto urbano requiere conservar esta diferencia temporal.
""")
md(book, """
## GTFS y consistencia de relaciones

Normalizamos agencias, rutas, servicios, paradas, viajes, secuencias y
frecuencias, comprobando las referencias entre tablas. Los horarios GTFS
pueden superar las 24 horas, por lo que se convierten a segundos sin tratarlos
como errores de reloj. Los campos opcionales permanecen nulos y los valores
predeterminados se aplican únicamente cuando están definidos por el formato.
El calendario conserva su vigencia real; los servicios de 2026 no se
presentan como evidencia de servicio en 2025.
""")
code(book, """
gtfs_quality = {name: report for name, report in audit["auxiliary"]["tables"].items()
                if name.startswith("gtfs_")}
display(pd.DataFrame(gtfs_quality).T)
display(pd.read_parquet(processed / "gtfs_calendar.parquet").head())
display(pd.read_parquet(processed / "gtfs_stops.parquet").head())
display(Markdown("**Resultados.** Las particiones publicadas identifican los rechazos por "
                 "clave, coordenada, horario o referencia. La vigencia temporal permanece explícita."))
""")
md(book, """
### Hallazgos de integridad referencial GTFS

Identificamos una ruta, un viaje y una frecuencia que no cumplen las
referencias entre tablas. La ruta `TR13` declara la agencia `SEMOVI`, que
no está presente en `agency.txt`; su viaje y frecuencia quedan también
fuera de la partición válida. Conservamos los tres registros con sus
motivos, sin inventar una equivalencia de agencias. El calendario incluye
doce servicios con intervalos que intersectan 2025 y un servicio de 2026.
""")
md(book, """
## Infraestructura ciclista y fuentes de incidentes

Validamos las geometrías y conservamos por separado cada capa de ciclovías.
La capa total no se concatena con sus componentes, porque hacerlo duplicaría
longitudes. El GeoJSON alternativo y el shapefile mantienen sus identidades
de fuente; tampoco se suman como infraestructura independiente.

En C5 y accidentes delimitamos una cohorte analítica de 2025. Los registros
históricos quedan en cuarentena como fuera del universo, no necesariamente
como datos corruptos. En SSC conservamos registros de víctimas y señalamos
posibles repeticiones, sin convertir coincidencias de fecha y posición en
eventos únicos demostrados. Las fuentes viales no se concatenan como si sus
observaciones fueran independientes.
""")
code(book, """
display(pd.read_parquet(processed / "ciclovias_capas.parquet"))
incident_quality = {name: report for name, report in audit["auxiliary"]["tables"].items()
                    if name.startswith(("incidentes_", "accidentes_", "ssc_"))}
display(pd.DataFrame(incident_quality).T)
display(pd.read_parquet(processed / "ssc_victimas_2025.parquet").head())
display(Markdown("**Resultados.** Publicamos capas y tablas con su partición de aceptación "
                 "y cuarentena. Los indicadores de uso, vigencia y repetición se conservan "
                 "para seleccionar fuentes y unidades de análisis en las etapas siguientes."))
""")
md(book, """
### Hallazgos temporales de C5 y límites del universo analítico

La fuente C5 contiene 2,115,080 registros con fechas entre el 31 de diciembre
de 2013 y el 29 de febrero de 2024. No contiene observaciones de 2025.
En consecuencia, la tabla `incidentes_c5_2025` queda vacía y conservamos las
filas fuera del período en cuarentena; doce también se identificaron como
duplicados desplazados. La ausencia de registros para 2025 no representa
ausencia de incidentes ni justifica asignar riesgo cero.

Esta fuente puede apoyar una revisión histórica con un universo temporal
distinto, pero no se incorpora como medición vial contemporánea de 2025.
Los registros fechados en 2025 de accidentes y víctimas SSC se mantienen
como fuentes separadas y no se suman entre sí sin comprobar solapamientos
y unidad de observación.
""")
md(book, """
## Motivos de cuarentena de viajes

Una fila de viaje puede incumplir el contrato completo y conservar un extremo
válido. Por ello diferenciamos la cohorte de viajes de la actividad por eventos:
la llegada de enero de un viaje iniciado en diciembre de 2024 sigue contando
en 2025. Verificamos que cada fila pertenece a una sola partición y que el
peso de eventos válidos equivale a la suma de los pesos catalogados y no
catalogados.

El código `1000` no aparece en el catálogo disponible. Esa ausencia justifica
su tratamiento como identidad no resuelta; no permite afirmar que corresponda
a un taller, una estación de prueba o un servicio público. La cuarentena
conserva el motivo, el registro original y su origen para una revisión posterior.
""")
code(book, """
dlq = pd.concat([pd.read_parquet(path, columns=["_quarantine_reason"])
                 for path in sorted(quarantine.glob("viajes_2025-*.parquet"))], ignore_index=True)
breakdown = dlq._quarantine_reason.str.split("|").explode().value_counts().rename("ocurrencias")
display(breakdown.to_frame())
quality = pd.read_parquet(processed / "auditoria_viajes.parquet")
assert quality.accepted_rows.add(quality.quarantine_rows).eq(quality.input_rows).all()
for role in ["retiros", "arribos"]:
    residual = quality["valid_" + role] - quality["known_" + role + "_weight"] - quality["unknown_" + role + "_weight"]
    assert residual.abs().lt(1e-5).all()
display(Markdown(f"**Resultados.** Conservamos {len(dlq):,} viajes en cuarentena. "
                 "Una fila puede tener varios motivos; la suma de ocurrencias no es el "
                 "número de filas rechazadas. La conservación de filas y pesos se verifica por archivo."))
""")
md(book, """
## Cierre, documentación y lectura de la generación activa

Verificamos los hashes de los artefactos y las fuentes al cerrar el proceso.
Los cuadernos posteriores resuelven `get_processed_root(V3)` en lugar de
escribir un hash fijo. El lector comprueba el manifiesto, el compromiso de
la generación, las rutas y la integridad de sus archivos sin modificar datos.

La preparación de fuentes no equivale a ausencia de faltantes ni a validación
de todas sus afirmaciones sustantivas. Los indicadores conservados delimitan
qué operaciones son posibles y qué supuestos adicionales requieren el EDA
y la construcción de atributos. Una nueva ejecución reutiliza únicamente
artefactos verificados bajo el mismo contrato.
""")
code(book, """
display(pd.read_parquet(processed / "source_disposition.parquet"))
display(pd.read_parquet(processed / "raw_mirrors.parquet"))
display(pd.read_parquet(processed / "documentacion_fuentes.parquet")[["resource_type", "_source_file"]])
verify_outputs(V3, audit)
assert verify_manifest(V3) == manifest
assert run_etl(V3) == audit
display(Markdown("**Resultados finales.** La generación activa está verificada. "
                 "Todas las fuentes registradas tienen un destino de normalización, "
                 "documentación o comprobación de copia, sin eliminar RAW ni generaciones anteriores."))
""")
