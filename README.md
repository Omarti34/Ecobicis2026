# Caso de negocio EcoBici: expansión territorial con tres motores analíticos auditados

Proyecto de ciencia de datos aplicada para la expansión de la red de EcoBici
en la Ciudad de México. El objetivo es diseñar una expansión **justa y
conectada** que no replique el sesgo histórico de cobertura: en lugar de
imitar las zonas donde el sistema ya es exitoso, se modela la ciudad como un
grafo y se maximiza la población nueva cubierta a 500 m bajo restricciones
de contigüidad territorial, con un arnés de validación espacial auditable
de punta a punta.

El estudio compara tres motores independientes:

| Motor | Enfoque | Resultado a B = 30 |
|---|---|---|
| **Motor 1** | Similitud no supervisada al "Cluster Dorado" (PCA + coseno + compuerta Mahalanobis) | 202,337 residentes nuevos |
| **Motor 2** | Predictivo supervisado (Random Forest, validación espacial) | 282,102 residentes nuevos |
| **Motor 3** | Prescriptivo sobre grafo: cobertura poblacional normalizada + afinidad al Cluster Dorado | **310,288 residentes nuevos** |

Cada cifra publicada está sellada en un registro de auditoría
(`data/audits/`), verificable byte a byte.

## Estructura del proyecto

```
OMMS2070/
├── README.md                       Este documento
├── Dockerfile                      Demo reproducible de la Tabla 5
├── requirements.txt                Núcleo del pipeline (versiones exactas)
├── requirements-notebooks.txt      Entorno completo (torch + jupyter)
├── run_pipeline.sh                 Orden de ejecución de los cuadernos 00-09
│
├── src/                            Código fuente completo del pipeline
│   ├── crear_fase1_notebooks.py        Cuadernos 00-01: manifiesto y ETL
│   ├── ejecutar_fase1_notebooks.py
│   ├── build_notebook_02.py … _09.py   EDA, features, validación, motores,
│   │                                   comparación y sello de afirmaciones
│   ├── enterprise_etl.py, auxiliary_etl.py, etl_contract.py
│   ├── eda02_*, fe03_*, fe04_*         Análisis y contenido de fases 2-4
│   ├── m1_*, m2_*, m3_*                Los tres motores
│   ├── c8_*, c9_*                      Comparación y registro de afirmaciones
│   ├── build_entregable.py, validate_entregable.py   Entregable y puerta QA
│   ├── build_dashboard_html.py, build_slides_html.py Presentaciones
│   ├── make_scatter_data.py            Datos del scatter equidad-cobertura
│   └── generar_tabla5_resultados.py    Demo de reproducibilidad (Tabla 5)
│
├── data/                           Solo datos ligeros y sellados
│   ├── audits/                     Manifiestos y reportes JSON por cuaderno
│   ├── resultados/                 Artefactos publicados (c8_*.csv, scatter)
│   └── diccionarios/               Diccionario de variables del modelo
│
├── entregables/                    Productos finales
│   ├── presentacion_ejecutiva.html     Original interactiva (autocontenida)
│   ├── presentacion_ejecutiva_2.html   Versión revisada para lectura
│   ├── presentacion_ejecutiva_slides.html  Versión diapositivas 16:9
│   └── app2.0/                       Planeador offline + CSV de prueba
│
├── 1_presentacion/                 Copia canónica de las presentaciones
├── 2_documento/                    tesis.pdf, fuentes Overleaf, figuras
├── 3_notebooks/                    Cuadernos 00-09 con salidas calculadas
├── 4_proyecto/V3/                  Proyecto reproducible (raíz de ejecución)
│   ├── src/                        Código canónico (espejo de src/)
│   ├── audits/                     Registro de auditoría sellado
│   └── data/                       Artefactos publicados del pipeline
│
├── entorno/environment.yml         Entorno conda original (Python 3.10.19)
└── GUIA_ESTUDIO_DEFENSA_ECOBICI.*  Guía de estudio de la defensa
```

> **Nota sobre los datos:** los viajes crudos (20.1 M de registros, 2025) y
> los insumos territoriales pesados no se incluyen por los límites de GitHub;
> `.gitignore` excluye `4_proyecto/V3/data/{raw,quarantine,processed}/`.
> Todas son fuentes públicas: portal de datos abiertos de EcoBici-CDMX,
> Censo 2020 (INEGI), DENUE, GTFS de movilidad, ciclovías e incidentes C5/SSC.
> Con los insumos colocados en `4_proyecto/V3/data/raw/`, `run_pipeline.sh`
> regenera el árbol completo; las cifras del estudio se reproducen sin ellos
> desde los artefactos sellados en `data/resultados/` (ver demo abajo).

## Instrucciones de ejecución

### 1. Entorno local (venv + pip)

```bash
cd OMMS2070
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

La demo de la Tabla 5 no requiere dependencias (solo la biblioteca estándar):

```bash
python src/generar_tabla5_resultados.py
```

Verifica primero la firma sha256 del artefacto sellado contra el registro de
auditoría 08 y después imprime la tabla de cobertura por presupuesto
(B = 15, 30, 50) con las 9 filas canónicas.

Para re-ejecutar los cuadernos 00-09 completos (incluye el caso de estudio
FT-Transformer y la ejecución vía Jupyter):

```bash
pip install -r requirements-notebooks.txt
./run_pipeline.sh    # o revise el orden dentro del script en Windows
```

El pipeline auditado se desarrolló en Python 3.10.19 (ver
`entorno/environment.yml` para reproducir el ambiente conda exacto).

### 2. Docker (reproducir la Tabla 5)

```bash
cd OMMS2070
docker build -t ecobici-tabla5 .
docker run --rm ecobici-tabla5
```

El contenedor instala `requirements.txt` sobre Python 3.11 y ejecuta
`src/generar_tabla5_resultados.py`, que imprime en consola la tabla de
resultados tras verificar la integridad del artefacto. La imagen es ligera
porque la demo trabaja sobre los artefactos sellados del pipeline; la
regeneración desde datos crudos se hace con `run_pipeline.sh` en el entorno
completo.

## Aplicativo interactivo

`entregables/app2.0/planeador_expansion_ecobici.html` es una herramienta
**offline** (un solo archivo, sin servidor ni recursos externos) para
evaluar escenarios de expansión. Abra el HTML en un navegador y cargue las
bases de prueba de `entregables/app2.0/bases_prueba/`:

| CSV | Escenario |
|---|---|
| `01_red_base_2025_canonica.csv` | Red actual validada |
| `02_red_expandida_oriente_conectada.csv` | Expansión oriente conectada |
| `03_red_semilla_sur_coyoacan.csv` | Red semilla sur |
| `04_red_estres_validador_errores.csv` | Casos de error del validador |

Las tres presentaciones ejecutivas (`entregables/*.html`) también son
archivos únicos autocontenidos; la versión `_slides` se navega con ← / →,
`G` abre el índice y `F` entra a pantalla completa.

## Declaración de transparencia

Declaración de uso de herramientas de IA: Se emplearon Modelos de Lenguaje
Grande (LLMs) como asistentes para la refactorización de código del
simulador interactivo, la generación de entornos reproducibles (Docker) y
la corrección de estilo del documento final. Toda la lógica deductiva,
diseño de motores, validación espacial y toma de decisiones fue diseñada y
verificada por el autor humano.
