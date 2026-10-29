# Guía de estudio para la defensa

## Expansión de la red EcoBici en la Ciudad de México: tres motores de ciencia de datos

Documento de preparación para la defensa de tesis. Cada concepto se explica
primero en lenguaje llano, luego con una analogía cotidiana, después con el
detalle técnico suficiente para sostenerlo ante un sínodo exigente, y al final
con la respuesta corta que conviene dar si preguntan por ello. Todas las
cifras citadas son las verificadas del estudio; si en la defensa no recuerdas
un número, responde cualitativamente en vez de aproximar.

---

## Índice

- [0. Cómo usar esta guía y mapa mental del proyecto](#0-cómo-usar-esta-guía-y-mapa-mental-del-proyecto)
- [Cifras que debes memorizar](#cifras-que-debes-memorizar)
- [1. Datos y ETL](#1-datos-y-etl)
  - 1.1 Qué es un ETL y un contrato de datos
  - 1.2 Cuarentena de filas y reproducibilidad por hash
  - 1.3 Las fuentes del estudio
  - 1.4 Conceptos clave: AGEB, DENUE, GTFS y sistema de coordenadas proyectado
- [2. Base conceptual de estadística y aprendizaje](#2-base-conceptual-de-estadística-y-aprendizaje)
  - 2.1 Población, muestra, variable, observación y unidad de análisis
  - 2.2 Media, mediana, cuantil y percentil
  - 2.3 Varianza y desviación estándar
  - 2.4 Correlación: Pearson frente a Spearman
  - 2.5 Distribución sesgada y transformación logarítmica
  - 2.6 Estandarización (z-score)
  - 2.7 Valores faltantes e imputación
  - 2.8 Sobreajuste, subajuste y el trade-off sesgo-varianza
  - 2.9 Entrenamiento, validación, prueba y validación cruzada
  - 2.10 Semillas aleatorias, determinismo y reproducibilidad
  - 2.11 Métricas de regresión: RMSE, MAE y R²
  - 2.12 Métricas de ranking: precisión@K, recall@K, NDCG@K y línea base
  - 2.13 Target, predictor y fuga de datos
- [3. Fundamentos del problema geoestadístico](#3-fundamentos-del-problema-geoestadístico)
  - 3.1 Índice de Gini
  - 3.2 Autocorrelación espacial e Índice I de Moran
  - 3.3 Fuga de datos y causalidad inversa
  - 3.4 Diagnóstico de cobertura territorial
- [4. Ingeniería de variables y diseño de validación](#4-ingeniería-de-variables-y-diseño-de-validación)
  - 4.1 Ingeniería de variables: el contrato de 18
  - 4.2 El universo de evaluación y la etiqueta
  - 4.3 MAUP: el problema de la unidad areal modificable
  - 4.4 Validación espacial: bloques de Ward, buffer y referencias
- [5. Motor 1: similitud y compuerta de dominio](#5-motor-1-similitud-y-compuerta-de-dominio)
  - 5.1 Análisis de componentes principales (PCA)
  - 5.2 Similitud del coseno
  - 5.3 Distancia de Mahalanobis frente a euclidiana
  - 5.4 Encogimiento de Ledoit-Wolf
  - 5.5 Las variantes comparadas y sus resultados
  - 5.6 Cobertura de decisión y abstención
  - 5.7 Hiperparámetros y sensibilidad
- [6. Motor 2: predicción supervisada](#6-motor-2-predicción-supervisada)
  - 6.1 Árboles de decisión y Random Forest
  - 6.2 Ridge y el modelo constante: los controles
  - 6.3 Redes neuronales y FT-Transformer
  - 6.4 Curva de aprendizaje, importancia por permutación y semillas múltiples
  - 6.5 Principio de parsimonia (navaja de Ockham)
- [7. Motor 3: optimización de grafos y prescripción](#7-motor-3-optimización-de-grafos-y-prescripción)
  - 7.1 Teoría de grafos aplicada a la red
  - 7.2 Embeddings y Node2Vec (y por qué se retiró)
  - 7.3 Algoritmos genéticos
  - 7.4 Greedy, submodularidad y rendimientos decrecientes
  - 7.5 Factibilidad, razones de paro, aleatorios y sensibilidad
- [8. Resultados e integración](#8-resultados-e-integración)
  - 8.1 Índice de Jaccard y consenso
  - 8.2 El trade-off final
  - 8.3 Integración: cómo se comparan los motores
  - 8.4 Pregunta de investigación e hipótesis
  - 8.5 Registro de afirmaciones y trazabilidad
- [9. Límites y amenazas a la validez](#9-límites-y-amenazas-a-la-validez)
- [10. Trabajo futuro](#10-trabajo-futuro)
- [Glosario](#glosario)
- [Preguntas trampa](#preguntas-trampa)
- [Guion de presentación](#guion-de-presentación)

---

## 0. Cómo usar esta guía y mapa mental del proyecto

### 0.1 El proyecto en una página

- **Problema.** La red EcoBici de la Ciudad de México está muy concentrada:
  de 2,452 AGEBs urbanas, solo 243 tienen al menos una estación (Gini de
  estaciones 0.9296). Crecer "pareciéndose a las zonas exitosas" replica el
  sesgo histórico; crecer sin conectividad produce islas inútiles.
- **Pregunta de investigación.** ¿Puede un enfoque de ciencia de datos
  diseñar una expansión justa y conectada sin replicar el sesgo histórico?
- **Hipótesis (afirmativa, refutable).** A igual presupuesto, un diseño de
  expansión que incorpora la conectividad con la red existente en su
  objetivo cubre más población nueva y selecciona zonas de menor nivel
  socioeconómico que un diseño basado solo en la similitud con las zonas
  históricamente exitosas.
- **Método.** Tres motores independientes que proponen portafolios de B
  estaciones nuevas bajo el mismo contrato de factibilidad: el Motor 1
  prioriza por similitud estadística con el núcleo de alto uso; el Motor 2
  prioriza por demanda predicha con un modelo supervisado validado
  espacialmente; el Motor 3 optimiza un objetivo que mezcla cobertura de
  población nueva y cercanía a la red.
- **Resultado.** A B = 30: Motor 1 cubre 202,337 habitantes nuevos con
  escolaridad media 13.02 (replica el sesgo); Motor 2 cubre 282,102 con
  11.83; Motor 3 cubre 310,288 con 11.64, frente a 12.23 del universo.
  La hipótesis queda apoyada, con un costo documentado: el Motor 3 sale
  más del dominio calibrado.

### 0.2 El mapa del pipeline

El proyecto es un pipeline auditado: cada etapa produce artefactos con
procedencia declarada y cada cifra del documento apunta a una fuente
verificable. El flujo completo:

- **Fuentes (cinco)**: viajes y catálogo de estaciones EcoBici/SEMOVI 2025;
  Censo de Población y Vivienda 2020 (INEGI); Marco Geoestadístico
  (geometrías de AGEB, INEGI); DENUE (actividad económica); GTFS (red de
  movilidad). Capas auxiliares: accidentes viales y ciclovías.
- **ETL (análisis 01)**: cada fuente pasa por un contrato de datos; las
  filas que no cumplen van a cuarentena, no se "arreglan" en silencio.
- **EDA y equidad (análisis 02)**: Gini, I de Moran, superficie de
  población cubierta y no cubierta.
- **Ingeniería de variables (análisis 03)**: el contrato de 18 variables
  por AGEB, el target y el universo de evaluación.
- **Diseño de validación (análisis 04)**: compuerta de dominio de
  Mahalanobis, pliegues espaciales de Ward con buffer, etiqueta por
  percentil 85 ajustada solo con entrenamiento, y el contrato de
  despliegue (sitios, reglas, presupuestos) que comparten los motores.
- **Tres motores en paralelo (análisis 05, 06 y 07)**: dependen
  únicamente de las salidas de 03 y 04; **ningún motor consume la salida
  de otro**. No es una cascada: son tres respuestas independientes a la
  misma pregunta bajo el mismo contrato de factibilidad.
- **Comparación e integración (análisis 08)**: identidad de sitio,
  Jaccard, consenso y radar de métricas.
- **Registro de afirmaciones (análisis 09)**: cada afirmación del estudio
  con su cifra y su fuente.

### 0.3 Cómo estudiar con este documento

- Lee primero la sección 0 entera y memoriza la tabla de cifras.
- Las secciones 1–2 son el vocabulario: léelas una vez y vuelve a ellas
  cuando un término aparezca después.
- Las secciones 3–7 son el corazón técnico; cada una termina con su
  bloque de **Argumentos clave para la defensa**: esas frases son las que
  conviene decir casi literalmente.
- Las secciones 8–10 son el cierre argumentativo; el glosario y las
  preguntas trampa son para ensayar en voz alta.

> **Argumentos clave para la defensa**
> - "El proyecto responde una pregunta con una hipótesis refutable y tres
>   motores independientes bajo un mismo contrato de factibilidad; no es
>   una cascada ni un único modelo."
> - "El resultado no es un ganador sino un trade-off medido: cobertura y
>   equidad del Motor 3 frente a permanencia en dominio del Motor 1, con
>   el Motor 2 en medio."
> - "Toda cifra que diga aquí existe en el registro de afirmaciones con su
>   fuente; las que no existen ahí se declaran no citables."

---

## Cifras que debes memorizar

### Contexto y datos

| Concepto | Cifra |
|---|---|
| Estaciones de la red base | 677 |
| Filas de viaje de entrada / aceptadas / cuarentena | 20,134,900 / 20,133,540 / 1,360 |
| AGEBs urbanas del territorio | 2,452 (243 con estación, 2,209 sin) |
| Gini de estaciones / de actividad | 0.9296 / 0.9448 |
| I de Moran de la actividad | 0.4293 (p = 0.001, k = 8; robusto a 4 y 12) |
| Golden Cluster | 102 estaciones en 61 AGEBs (≥ 127.62 viajes/día, P85) |
| Celdas de población de 200 m | 67,872 |
| Población cubierta / no cubierta | 1,170,299 / 7,968,089 |
| Sitios candidatos | 1,656 en 446 AGEBs con sitios |

### Validación

| Concepto | Cifra |
|---|---|
| Universo de evaluación | 242 AGEBs con servicio |
| Pliegues espaciales | 5 pliegues, 15 bloques de Ward, buffer 500 m |
| Pares colindantes train–test | [95, 57, 59, 50, 59] → [0, 0, 0, 0, 0] |
| Etiqueta | target ≥ P85 del entrenamiento (122.38) |
| MAUP | mitigado, no resuelto |

### Motor 1

| Concepto | Cifra |
|---|---|
| PCA | 18 variables → 8 componentes, 80.37 % de varianza |
| Variante primaria (coseno + compuerta LW) | precisión@10 0.38, NDCG@10 0.673, cobertura 0.901 |
| Coseno sin compuerta / euclidiana | 0.38 / 0.673 / 1.00 · 0.18 / 0.574 / 1.00 |
| Spearman puntaje–escolaridad | 0.7213 |

### Motor 2

| Concepto | Cifra |
|---|---|
| RMSE espacial: constante / ridge / RF / FT | 0.5444 / 0.4195 / 0.4288 / 0.4206 |
| R² espacial: constante / ridge / RF / FT | −0.3028 / 0.1938 / 0.1720 / 0.2148 |
| Dictamen FT | 3/5 pliegues (exigía 4); mejora −0.0010 vs ruido 0.0313 |
| Modelo desplegado | Random Forest (parsimonia y estabilidad) |

### Motor 3 y resultados

| Concepto | Cifra |
|---|---|
| Objetivo | w = 0.5 (mitad cobertura, mitad afinidad) |
| Población nueva a B=30: M1 / M2 / M3 | 202,337 / 282,102 / 310,288 |
| Escolaridad media: M1 / M2 / M3 / universo | 13.02 / 11.83 / 11.64 / 12.23 |
| Fuera de dominio: M1 / M2 / M3 | 0.30 / 0.23 / 0.57 |
| Jaccard: M1–M2 / M1–M3 / M2–M3 | 0.176 / 0.091 / 0.250 |
| Consenso a B=30 | 18 con ≥2 motores, 4 con los 3 (incluidos) |
| Greedy vs GA a B=30 | 310,288 vs 305,090; 0.016 s vs 51.4 s (3,193×) |

---

## 1. Datos y ETL

### 1.1 Qué es un ETL y un contrato de datos

**Qué es.** ETL son las siglas de *extract, transform, load*: extraer los
datos de sus fuentes, transformarlos al formato que el análisis necesita y
cargarlos en un repositorio ordenado. Un **contrato de datos** es la
especificación formal de cómo debe lucir cada tabla de entrada: qué
columnas, qué tipos, qué valores válidos, qué llaves únicas. Si una fila
no cumple el contrato, no entra — o entra marcada.

**Analogía.** La aduana de un aeropuerto: cada pasajero (fila) presenta
documentos (columnas); quien cumple los requisitos pasa, quien no, queda
retenido y registrado — nadie "arregla" un pasaporte falso en la fila.

**Por qué importa en la defensa.** Un pipeline sin contrato deja pasar
errores que se vuelven conclusiones. Con contrato, cada exclusión es una
decisión declarada y auditable, no un accidente silencioso.

### 1.2 Cuarentena de filas y reproducibilidad por hash

**Qué es la cuarentena.** En vez de corregir o descartar silenciosamente
las filas que violan el contrato (coordenadas vacías, valores fuera de
rango, duplicados), se apartan a una tabla de cuarentena con su causa.
Así el conjunto aceptado es limpio y el conjunto rechazado es auditable.

**Qué es la reproducibilidad por hash.** Un hash es una huella digital:
una función que convierte cualquier archivo en una cadena corta única
(SHA-256 produce 64 caracteres). Si el archivo cambia aunque sea un byte,
el hash cambia. Registrar el hash de cada insumo prueba que el análisis se
corrió sobre exactamente esos datos, y permite a cualquiera verificar que
reproduce con los mismos.

**Si te preguntan X, responde Y.**
- *"¿Cómo sé que no limpiaste datos a mano?"* Porque toda exclusión tiene
  causa registrada en cuarentena y todo insumo tiene hash: la limpieza es
  código y reglas, no edición manual.

### 1.3 Las fuentes del estudio

| Fuente | Qué aporta | Conteos verificados |
|---|---|---|
| Viajes EcoBici/SEMOVI 2025 | El uso observado de la red | 20,134,900 filas de entrada; 20,133,540 aceptadas; 1,360 en cuarentena; 20,134,368 retiros y 20,134,527 arribos válidos |
| Catálogo de estaciones | Dónde está cada estación | 677 entrada, 677 aceptadas, 0 en cuarentena, 12 estaciones físicas compuestas |
| Censo 2020 (INEGI) | Población y rasgos sociodemográficos | 68,941 filas aceptadas; vista por AGEB con 2,433 filas; 22 filas de AGEB sin población (NaN rural: faltante no equivale a cero) |
| Marco Geoestadístico (INEGI) | Los polígonos de las 2,452 AGEBs urbanas | 2,452 de entrada y aceptadas |
| DENUE | Directorio de unidades económicas: proxy de actividad | 462,732 registros |
| GTFS | Red de transporte público (Metro, Metrobús, etc.) | 11,362 paradas; 300 rutas (1 en cuarentena por agencia desconocida); 1,204 viajes (1 en cuarentena); 127,135 puntos de trazado; 13 registros de calendario; 10 agencias |
| Capas auxiliares | Accidentes viales 2025: 472; ciclovías en varias capas | 98, 42, 100, 61, 231, 34, 651, 85 y 80 registros |

**Dos declaraciones que hay que saber decir.**
- El catálogo de estaciones es un **snapshot**: describe dónde están las
  estaciones, pero no es evidencia de cuáles estaban activas en 2025; el
  reporte lo declara explícitamente.
- El año de estudio es **2025**, con denominador fijo de **365 días** para
  la actividad diaria.

### 1.4 Conceptos clave: AGEB, DENUE, GTFS y sistema de coordenadas proyectado

- **AGEB** (Área Geoestadística Básica): la unidad territorial más pequeña
  del censo mexicano, un polígono urbano que agrupa manzanas. Es la
  unidad de análisis del estudio: cada zona de la ciudad se describe con
  los atributos de su AGEB.
- **DENUE** (Directorio Estadístico Nacional de Unidades Económicas): el
  censo de negocios del INEGI. Se usa como *proxy* (aproximación) de
  actividad económica por zona: cuántos comercios y oficinas hay cerca.
- **GTFS** (General Transit Feed Specification): el formato estándar
  mundial con que las agencias publican su transporte público: paradas,
  rutas, viajes y trazados.
- **CRS proyectado y EPSG:32614.** Las coordenadas geográficas
  (latitud/longitud) miden grados sobre una esfera; un grado de longitud
  no mide lo mismo en el ecuador que en el polo. Para medir distancias en
  **metros** se proyecta la superficie a un plano: la proyección UTM zona
  14 Norte, que cubre la Ciudad de México, es la EPSG:32614. Todas las
  distancias del estudio (500 m de enlace, 300 m de separación, buffers)
  se calculan en ese CRS; hacerlo en grados daría metros equivocados.

**Si te preguntan X, responde Y.**
- *"¿Por qué AGEB y no colonia o alcaldía?"* Porque es la unidad censal
  oficial de mayor resolución con geometría y atributos consistentes; se
  fijó como soporte declarado (y su costo es el MAUP, sección 4.3).
- *"¿Los viajes son individuales?"* Son registros de viaje agregados por
  estación y día para la actividad; el conteo anual supera los 20
  millones.

> **Argumentos clave para la defensa**
> - "Cada fuente pasó un contrato de datos con cuarentena: las 1,360 filas
>   de viaje rechazadas tienen causa registrada; nada se corrigió a mano."
> - "Todas las distancias se miden en EPSG:32614 (UTM 14N): metros reales,
>   no grados; por eso la regla de 500 m es operativa."
> - "El catálogo es un snapshot y así se declara: no se afirma que las 677
>   estaciones estuvieran activas todo 2025."
> - "El Censo es de 2020 y el uso de 2025: es el soporte disponible y se
>   declara como límite temporal, no se oculta."

---

## 2. Base conceptual de estadística y aprendizaje

Esta sección es el vocabulario mínimo. Cada concepto aparece después en
los motores.

### 2.1 Población, muestra, variable, observación y unidad de análisis

- **Población**: el conjunto completo sobre el que se quiere concluir
  (todas las AGEBs urbanas de la CDMX). **Muestra**: la parte que se
  observa. Si la muestra no representa a la población, las conclusiones
  se sesgan.
- **Variable**: una característica medida de cada unidad (escolaridad
  promedio). **Observación**: un registro concreto (una AGEB concreta).
- **Unidad de análisis**: aquello de lo que hablan las filas y sobre lo
  que se concluye. Aquí es la **AGEB** —no el viaje ni la estación— y esa
  elección se declara porque de ella dependen los resultados (MAUP,
  sección 4.3).

**Analogía.** En una encuesta electoral, la población son los votantes,
la muestra los entrevistados, la variable la preferencia y la unidad de
análisis la persona — si encuestas solo a estudiantes, "la ciudad opina X"
es una afirmación sobre estudiantes disfrazada.

### 2.2 Media, mediana, cuantil y percentil

- **Media**: el promedio aritmético; sensible a valores extremos.
- **Mediana**: el valor central ordenando los datos; robusta a extremos.
- **Cuantil q**: el valor que deja la fracción q de los datos por debajo.
  La mediana es el cuantil 0.5. Los **percentiles** son cuantiles en
  escala de cien: el percentil 85 (P85) deja 85 % abajo y 15 % arriba.

**Por qué importa aquí.** El Golden Cluster se define con el **percentil
85** de actividad diaria (umbral 127.62 viajes/día en el catálogo de
estaciones) y la etiqueta de evaluación con el P85 del target (122.38);
la tabla de distancias de enlace usa cuantiles P05–P99. Cuantiles, no
medias, porque las distribuciones son sesgadas.

### 2.3 Varianza y desviación estándar

**Qué es.** Cuánto se dispersan los datos alrededor de su media. La
**varianza** es el promedio de las desviaciones al cuadrado; la
**desviación estándar** es su raíz, en las mismas unidades que el dato.
Una desviación estándar grande significa heterogeneidad.

**Dónde aparece.** Es la base de todo lo demás: el PCA busca direcciones
de máxima varianza; el "ruido entre semillas" del Motor 2 es la desviación
estándar de sus métricas entre semillas (0.0313); el trade-off
sesgo-varianza gobierna la elección de modelos.

### 2.4 Correlación: Pearson frente a Spearman

**Qué es.** Una medida de asociación entre dos variables, entre −1 y 1.
- **Pearson**: mide relación *lineal* entre los valores crudos; sensible a
  valores extremos y a relaciones curvas.
- **Spearman**: primero convierte cada variable a **rangos** (1º, 2º, 3º…)
  y luego mide Pearson sobre los rangos; por tanto mide *monotonía* (que
  una crezca cuando la otra crece), no linealidad, y es robusta a
  extremos.

**Analogía.** Pearson pregunta "¿suben juntos en la misma proporción?";
Spearman pregunta "¿coinciden en el podio?": basta que el orden coincida.

**Por qué aquí Spearman.** Porque las relaciones son monótonas pero no
necesariamente lineales y las distribuciones tienen colas pesadas: el
Spearman de la similitud del Motor 1 con escolaridad es 0.7213, el del
turnover con el target 0.8984, y el del target con el número de
estaciones apenas 0.1787.

### 2.5 Distribución sesgada y transformación logarítmica

**Qué es.** Una distribución **sesgada** tiene una cola larga: muchos
valores pequeños y pocos enormes (la actividad por estación va de 12.55 a
219.45). Transformar con logaritmo comprime los grandes y expande los
pequeños, acercando la distribución a una campana: facilita que varianza,
correlación y distancias se comporten bien.

**Analogía.** Una foto de noche con un foco encendido: el foco quema la
imagen. Bajar el brillo del foco (el log) deja ver la escena completa.

### 2.6 Estandarización (z-score)

**Qué es.** Reexpresar cada variable restando su media y dividiendo entre
su desviación estándar: z = (x − media)/desviación. Todas las variables
estandarizadas tienen media 0 y desviación 1: compiten en igualdad.

**Por qué el PCA la exige.** Sin estandarizar, la variable con mayor
escala (población en miles frente a porcentajes de 0 a 1) dominaría la
varianza y decidiría los componentes por unidad, no por información.

### 2.7 Valores faltantes e imputación

**Qué es.** Un valor faltante (NaN) es un hueco en los datos.
**Imputar** es rellenarlo con un valor razonable (media, mediana, modelo).
La regla de oro: **faltante no equivale a cero** — 22 filas de AGEB sin
población son rurales sin censo urbano, no AGEBs vacías.

**Por qué importa aquí.** Las 50 candidatas "no proyectables" del diseño
de validación son AGEBs a las que faltan variables para ubicarlas en el
espacio PCA: se excluyen de la puntuación, no se inventan.

### 2.8 Sobreajuste, subajuste y el trade-off sesgo-varianza

- **Sobreajuste (overfitting)**: el modelo memoriza el entrenamiento,
  incluido su ruido; rinde bien en casa y mal fuera. Error bajo en
  entrenamiento, alto en prueba.
- **Subajuste (underfitting)**: el modelo es demasiado simple para el
  fenómeno; rinde mal en ambos.
- **Trade-off sesgo-varianza**: el error total descompone en *sesgo*
  (equivocarse sistemáticamente por simplicidad) más *varianza* (cambiar
  mucho con los datos por complejidad). Reducir uno suele aumentar el
  otro; el buen modelo equilibra.

**Analogía.** El estudiante que memoriza exámenes viejos (sobreajuste:
varianza alta) y el que resume todo en "depende" (subajuste: sesgo alto);
el aprobado aprende el patrón sin memorizar el ruido.

### 2.9 Entrenamiento, validación, prueba y validación cruzada

- **Entrenamiento**: datos con los que el modelo aprende sus parámetros.
- **Validación**: datos usados para decidir (hiperparámetros, paro
  temprano), distintos de los de prueba.
- **Prueba**: datos guardados que el modelo nunca vio y que miden el
  error honesto.
- **Validación cruzada en k pliegues**: dividir los datos en k partes;
  entrenar k veces usando cada parte una vez como prueba; promediar el
  error. Así se usa todo el dato sin contaminar la medición.

**Aquí.** El Motor 2 se evalúa con 5 pliegues espaciales (sección 4.4);
el FT-Transformer usa además una fracción interna de validación del 0.2
para su paro temprano.

### 2.10 Semillas aleatorias, determinismo y reproducibilidad

**Qué es una semilla.** Muchos algoritmos usan azar (elegir remuestras,
inicializar pesos, mutar soluciones). La **semilla** es el número que
inicializa ese azar: misma semilla + mismo código = misma salida exacta.
Fijar semillas vuelve el experimento determinista y reproducible.

**Por qué varias semillas.** Una sola semilla puede dar un resultado
afortunado. Correr con varias ({0,1,2,3,4} en el Motor 2; {42–46} en el
Motor 3) mide la variación debida al azar: la desviación entre semillas
del Transformer (0.0313) es la regla con la que se juzga si su mejora
(−0.0010) es señal o ruido.

### 2.11 Métricas de regresión: RMSE, MAE y R²

Para predecir una cantidad continua (el target de actividad):

- **MAE** (error absoluto medio): promedio de |predicción − real|.
  Fácil de leer, en unidades del target.
- **RMSE** (raíz del error cuadrático medio): como el MAE pero penaliza
  más los errores grandes. Siempre ≥ MAE; cuando importa no fallar
  feo, es la métrica correcta.
- **R²**: fracción de la varianza del target que el modelo explica,
  comparado contra predecir siempre la media. R² = 1 es perfecto; R² = 0
  equivale al modelo constante; **R² negativo significa peor que decir
  la media** — el modelo suma error en vez de restarlo. Por eso el
  modelo constante logra R² = −0.3028 en el esquema espacial: bajo
  separación espacial, ni siquiera "adivinar la media" sirve.

### 2.12 Métricas de ranking: precisión@K, recall@K, NDCG@K y línea base

Cuando lo que importa es un **orden** (qué AGEBs van primero), no un
número:

- **Precisión@K**: de los K primeros de la lista, qué fracción son
  realmente relevantes (etiqueta Golden). Precisión@10 = 0.38 significa
  ~4 de cada 10 recomendados son aciertos.
- **Recall@K**: de todos los relevantes que existen, qué fracción
  capturaron los K primeros.
- **NDCG@K** (ganancia acumulada descontada normalizada): premia acertar
  *y además* poner los mejores arriba; un acierto en la posición 1 vale
  más que en la 10. 1.0 es orden perfecto.
- **Control o línea base (baseline)**: el método tonto de referencia
  (elegir al azar, o la regla simple obvia). Un modelo solo es útil si
  **supera a su línea base**: por eso el dictamen del Transformer lo
  compara contra ridge, el mejor control, y no contra el azar.

**Aquí.** Los motores 1 y 2 se evalúan como rankings con precisión@10 y
NDCG@10 (con K = 10/20/50 en el diseño), contra un control aleatorio y
una heurística de cercanía al Metro.

### 2.13 Target, predictor y fuga de datos

- **Target**: lo que se quiere predecir u ordenar (aquí, la actividad
  media por estación de la AGEB).
- **Predictor**: una variable disponible *antes* de decidir que ayuda a
  predecir el target.
- **Fuga de datos**: usar como predictor algo que se construyó *a partir
  del target* o que no existiría al momento de decidir. Produce modelos
  brillantes en papel e inútiles en producción. Se desarrolla en la
  sección 3.3.

> **Argumentos clave para la defensa**
> - "Toda métrica del estudio tiene su línea base: un modelo se juzga
>   contra su mejor control, no contra el azar ni contra la perfección."
> - "Uso Spearman porque las relaciones son monótonas con colas pesadas;
>   Pearson sobre valores crudos sería frágil aquí."
> - "R² negativo no es 'un poco malo': es peor que predecir la media, y
>   así lo reporto para el constante."
> - "La variación entre semillas es mi regla de medir: una mejora de
>   −0.0010 contra un ruido de 0.0313 no es señal."

---

## 3. Fundamentos del problema geoestadístico

### 3.1 Índice de Gini

**Qué es.** Una medida de desigualdad de una distribución. Vale 0 si el
reparto es perfectamente igual (cada unidad tiene la misma cantidad) y se
acerca a 1 si todo se concentra en unas pocas unidades.

**Analogía.** Repartir fichas entre los salones de una escuela: si cada
salón recibe 10 fichas, el Gini es 0; si un solo salón recibe las 300
fichas, el Gini es casi 1. No dice si hay suficientes fichas ni quién las
usa, solo qué tan desigual es el reparto.

**Cómo se calcula.** Ordena las unidades (aquí, AGEBs) de menor a mayor
cantidad, acumula el porcentaje de unidades en un eje y el porcentaje del
total acumulado en el otro: esa es la curva de Lorenz. El Gini es el doble
del área entre la diagonal (igualdad perfecta) y esa curva.

**Qué hicimos y qué dio.** Medimos la concentración de la red por AGEB con
peso igual por polígono y conteos crudos (no per cápita): Gini de
estaciones = **0.9296** y Gini de actividad = **0.9448**. Sobre 2,452
AGEBs urbanas, solo **243** contienen al menos una estación y **2,209** no
contienen ninguna. El dato describe una red muy concentrada
territorialmente.

**Si te preguntan X, responde Y.**
- *"¿El Gini demuestra inequidad en el acceso al servicio?"* No por sí solo:
  mide concentración de conteos por polígono, no acceso per cápita ni
  demanda insatisfecha. Es la evidencia descriptiva que motiva el estudio,
  no una prueba causal. Eso se declara en los límites.
- *"¿Por qué no per cápita?"* Porque el objetivo era medir la estructura
  espacial de la oferta (dónde está la infraestructura), no el déficit por
  habitante; son preguntas distintas y la tesis lo dice explícitamente.

### 3.2 Autocorrelación espacial e Índice I de Moran

**Qué es.** La autocorrelación espacial es la tendencia de las unidades
cercanas a parecerse entre sí más de lo que dictaría el azar. La I de
Moran es su medida estándar: valores positivos indican vecinos parecidos
(agregación), negativos vecinos distintos, y cerca de 0 ausencia de
patrón espacial.

**Analogía.** Las calificaciones de salones vecinos en una escuela suelen
parecerse porque comparten contexto. Si evalúas a un alumno de un salón
usando el examen de su vecino, "saber la respuesta" no prueba que aprendió:
prueba que los salones se parecen.

**Cómo se calcula.** Para cada unidad se compara su valor con el de sus k
vecinos más cercanos, ponderando por la varianza global: I = (n/W)·ΣᵢΣⱼ
wᵢⱼ(xᵢ−x̄)(xⱼ−x̄)/Σᵢ(xᵢ−x̄)², donde wᵢⱼ marca la vecindad. Basta entenderlo
como "correlación entre un valor y el promedio de sus vecinos".

**Qué hicimos y qué dio.** I de Moran de la actividad = **0.4293**, con
p = 0.001 usando k = 8 vecinos; el signo es robusto a k = 4, 8 y 12. Es
decir, las AGEBs con mucha actividad se agrupan con otras de mucha
actividad: la red tiene estructura espacial fuerte.

**Si te preguntan X, responde Y.**
- *"¿Por qué te importa la autocorrelación si solo predices?"* Porque
  invalida la validación cruzada aleatoria: si entrenamiento y prueba
  comparten vecinos, el error estimado es optimista. Por eso la validación
  es espacial (sección 4.4).
- *"¿La autocorrelación es buena o mala?"* Ninguna de las dos: es un hecho
  del fenómeno. Sirve para detectar estructura (los núcleos de uso son
  reales y contiguos) y obliga a validar de forma espacial.

### 3.3 Fuga de datos y causalidad inversa

**Qué es.** La fuga de datos ocurre cuando el modelo usa información que
no estaría disponible en el momento de decidir o que se construyó a partir
de la propia respuesta. La causalidad inversa es el caso extremo: la
"variable explicativa" es el resultado renombrado.

**Analogía.** Es como estudiar para un examen con la hoja de respuestas
pegada detrás del cuestionario: obtienes una nota perfecta en casa que no
dice nada de lo que aprendiste. El predictor parece brillante porque ya
contiene la respuesta.

**Cómo funciona.** Si defines un predictor como función directa del target
(por ejemplo, `turnover_ratio` = 2 × actividad diaria / capacidad), su
correlación con el target es alta por construcción, no por descubrimiento.
En validación parece un predictor excepcional; fuera de muestra, el
"modelo" solo repite la variable que ya traía dentro.

**Qué hicimos y qué dio.** `turnover_ratio` (2 × actividad diaria /
capacidad de catálogo) y `pagerank` se derivan del target de viajes
diarios y quedaron **excluidos como predictores** (`turnover_ratio`
registrado como no elegible). La correlación de Spearman registrada del
turnover con el target es **0.8984**: alta precisamente porque contiene al
target, no porque informe nada nuevo.

**Nota importante para la defensa.** En los reportes sellados **no existe
ningún R² de 0.98** asociado a estas variables. Esa cifra no debe citarse
en la defensa; el argumento correcto es que un predictor construido a
partir del target produce un ajuste espurio que se desploma fuera de
muestra, y por eso ambas variables fueron excluidas de la ingeniería.

**Si te preguntan X, responde Y.**
- *"¿Por qué descartaste una variable que predice tan bien?"* Porque no es
  un predictor: es el target recodificado. Incluirla no es un atajo, es un
  error de especificación.
- *"¿Cómo te diste cuenta?"* Por el análisis de procedencia de cada
  variable: se revisó qué datos entran en cada predictor y cuál es la
  relación declarada con el target.

### 3.4 Diagnóstico de cobertura territorial

**Qué hicimos y qué dio.** Sobre una superficie de **67,872 celdas de
200 m**, la red existente cubre (con sus radios de 500 m) a
**1,170,299** habitantes y deja sin cobertura a **7,968,089**. Es decir,
la red atiende potencialmente a una fracción pequeña de la población de
las celdas medidas: ese hueco es el espacio de actuación del estudio.
La participación de área de origen desconocido es **0.2532**: para una
cuarta parte del área no se conoce la población de origen con el soporte
disponible, lo cual se declara como límite de medición.

**Si te preguntan X, responde Y.**
- *"¿Entonces el 85 % de la gente no tiene EcoBici cerca?"* La cifra dice
  que 7.97 millones de habitantes están fuera del radio de cobertura de
  la red en las celdas medidas; es una estimación sobre población censal
  2020 y buffers euclidianos, no un conteo de usuarios.

> **Argumentos clave para la defensa**
> - "El Gini de 0.93–0.94 describe una red concentrada: 243 de 2,452 AGEBs
>   tienen estación. Es evidencia descriptiva, no una prueba de inequidad
>   de acceso, y así lo declaro."
> - "La I de Moran de 0.43 demuestra estructura espacial real; por eso la
>   validación no pudo ser aleatoria."
> - "`turnover_ratio` y `pagerank` se excluyeron porque se derivan del
>   target: un Spearman de 0.8984 no es capacidad predictiva, es la
>   respuesta reescrita."
> - "En los reportes no hay ningún R² de 0.98; no lo citaré. El argumento
>   es de diseño, no de magnitud."
> - "La red cubre a ~1.17 millones y deja fuera a ~7.97 millones en las
>   celdas medidas: ese hueco es el problema que los motores atacan."

---

## 4. Ingeniería de variables y diseño de validación

Antes de los métodos: tres problemas distintos que el sínodo puede querer
confundir.

| Problema | Pregunta que hace | Qué se hizo |
|---|---|---|
| MAUP | ¿Cambiaría el resultado con otra división del mapa? | Se fijó la AGEB, se declaró el soporte; mitigado, no resuelto |
| Autocorrelación espacial | ¿Los vecinos se siguen pareciendo? | Se midió (I de Moran 0.4293) |
| Fuga espacial | ¿Entrenamiento y prueba quedaron pegados? | Bloques de Ward + buffer de 500 m |

Son tres cosas diferentes y la defensa debe mantenerlas separadas.

### 4.1 Ingeniería de variables: el contrato de 18

**Qué es la ingeniería de variables.** Transformar los datos crudos en las
variables (features) que los modelos usarán: decidir qué se mide de cada
unidad, con qué fuente y con qué regla. Un **contrato de variables** fija
la lista completa por adelantado —18 variables por AGEB— para que todos
los análisis posteriores hablen del mismo insumo.

**Qué es la procedencia (provenance).** El registro de dónde sale cada
variable: qué tabla, qué transformación, qué filtro. Es lo que permitió
detectar que `turnover_ratio` y `pagerank` derivan del target y debían
quedar fuera como predictores: una variable "elegible como predictor" es
aquella cuya procedencia no toca el target.

**Las familias de variables.** Las 18 se agrupan así:

| Familia | Qué mide | Por qué se incluye |
|---|---|---|
| Densidad | Habitantes por km² | La demanda potencial crece con la densidad |
| Estructura de edad | Composición por edades (adultos mayores, etc.) | El perfil de movilidad cambia con la edad |
| Escolaridad | Grado promedio de estudios | Resume el gradiente socioeconómico de la zona |
| Conectividad | Acceso a internet, auto | Dimensión de equipamiento y modo de vida |
| Vivienda | Rasgos del parque de vivienda | Contexto urbano y socioeconómico |
| Actividad económica | Unidades económicas del DENUE | Los polos de empleo/comercio atraen viajes |
| Infraestructura ciclista | km de ciclovía por km² | Facilita o compite con el modo bicicleta |
| Distancia a transporte pesado | m a la parada Metro/Metrobús más cercana | Complementariedad con el transporte masivo |

**Si te preguntan X, responde Y.**
- *"¿Quién decidió que fueran 18?"* El contrato de variables, fijado a
  priori por procedencia y criterio, no ajustado al resultado.
- *"¿Por qué el DENUE y no empleo real?"* Es la mejor aproximación
  espacial disponible de actividad económica; es un proxy declarado.

### 4.2 El universo de evaluación y la etiqueta

**Qué es el universo de evaluación.** No todas las AGEBs pueden usarse
para evaluar: el universo se definió como AGEBs **proyectables** (con las
18 variables completas), **con al menos una estación** (hay target
observado) y **no candidatas territoriales**. Su tamaño: **242 AGEBs**.
Los roles: 2,111 candidatas sin etiqueta; 98 cubiertas sin estación y sin
etiqueta; 242 con servicio y etiquetadas; 1 con servicio no evaluable.
Las cubiertas sin estación se excluyen de las etiquetas porque su
ausencia de estaciones **no** es evidencia de baja demanda.

**Qué es el target.** La actividad media por estación de la AGEB (media,
no suma: la suma crece con el número de estaciones; la media mide la
intensidad por sitio). Sus cuantiles: mínimo 12.55, Q25 48.39, mediana
66.23, Q75 94.52, P85 **122.38**, máximo 219.45. El Golden del universo
tiene 61 AGEBs, con media de target **129.88** frente a **58.67** en las
no Golden. El Spearman del target con el número de estaciones es solo
**0.1787**: la media por estación no está determinada por cuántas haya.

**La etiqueta.** Una AGEB del universo es "relevante" si su target ≥ P85
—donde el umbral se ajusta **solo con las filas de entrenamiento
retenidas** de cada pliegue. Ajustarlo con todo el conjunto sería fuga:
el umbral "vería" las etiquetas de prueba antes de evaluarlas.

**Si te preguntan X, responde Y.**
- *"¿Por qué media y no suma?"* Porque la suma premia a las AGEBs con más
  estaciones; la media mide la intensidad que queremos replicar.
- *"¿El P85 es arbitrario?"* Es el criterio declarado del Golden Cluster;
  ajustarlo por pliegue solo con entrenamiento evita la fuga en el
  umbral.

### 4.3 MAUP: el problema de la unidad areal modificable

**Qué es.** Los resultados de un análisis espacial dependen de cómo se
divida el territorio: con otra unidad de agregación (o con los límites en
otro lugar) las correlaciones, los promedios y hasta el signo de algunas
relaciones pueden cambiar. Tiene dos caras: la *escala* (qué tan grandes
son las unidades) y la *zonificación* (dónde caen las fronteras).

**Analogía.** Contar goles por "partido" o por "tiempo": el mismo torneo
produce cifras distintas según la unidad. El mapa no cambia; la lectura sí.

**Cómo se aborda.** No existe un remedio general: se mitiga eligiendo una
unidad administrativa con sentido (la AGEB del censo), declarándola como
el soporte del análisis, y fijando las geometrías derivadas (zonas de
captura y celdas de población) para que el resultado sea reproducible. Lo
que no se puede afirmar es invariancia: no se demostró que el resultado se
mantenga bajo otra zonificación.

**Qué hicimos y qué dio.** El soporte es la AGEB urbana (2,452 en el
territorio). Las zonas de captura son **buffers euclidianos proyectados de
500 m** —no áreas de servicio caminables ni isócronas— y la población se
lee en **celdas de 200 m**. El reporte sellado marca el MAUP como
**mitigado, no resuelto**.

**Si te preguntan X, responde Y.**
- *"¿Cambiaste la unidad para obtener tu resultado?"* No: la unidad se
  fijó a priori (AGEB censal) y se declaró; el análisis reconoce
  explícitamente que no se probó invariancia frente a otras zonificaciones.
- *"¿Por qué no usaste isócronas reales?"* Porque no había una red peatonale
  completa calibrada; los buffers euclidianos son una aproximación
  honesta y quedaron declarados como límite del estudio.

### 4.4 Validación espacial: bloques de Ward, buffer y referencias

**Qué es.** La validación cruzada reparte los datos en pliegues para
medir error fuera de muestra. El K-Fold aleatorio mezcla unidades vecinas
entre entrenamiento y prueba: con datos espaciales eso filtra información
(el modelo "ya vio" los vecinos del punto de prueba) y el error estimado
queda optimista. La validación espacial reparte **bloques contiguos** en
vez de puntos sueltos.

**Analogía.** Evaluar a un estudiante de español dictándole palabras de un
párrafo que ya memorizó (K-Fold aleatorio) frente a dictarle un párrafo
completo nuevo (bloque espacial): solo lo segundo mide de verdad.

**Cómo funciona el clustering aglomerativo de Ward.** Es un método
jerárquico: empieza con cada observación como su propio grupo y va
fusionando paso a paso los dos grupos cuya unión aumenta menos la varianza
interna. Al exigir además **conectividad por adyacencia** (solo se fusionan
grupos contiguos en el mapa), produce bloques compactos y contiguos, que
es exactamente lo que una validación espacial necesita.

**Por qué no K-Means.** K-Means minimiza distancias al centroide pero no
conoce la adyacencia: sin restricciones produce "islas" (partes de un
mismo pliegue salpicadas por el mapa), que es justo lo que la fuga
espacial explota. Tampoco garantiza tamaños comparables.

**Qué hicimos y qué dio.** **15 bloques contiguos** construidos por Ward
con restricción de adyacencia —participación de bloques contiguos 1.0,
una sola componente de adyacencia y exactamente una componente por bloque
en los 15—, repartidos en **5 pliegues** (tamaños 55, 39, 47, 52 y 49),
con un **buffer de 500 m** que retira de la evaluación toda AGEB
colindante al pliegue de prueba (278 exclusiones por buffer), sobre un
universo de **242 AGEBs** con servicio. Los pares colindantes
entrenamiento–prueba bajaron de **[95, 57, 59, 50, 59]** a
**[0, 0, 0, 0, 0]** tras el buffer; la distancia mínima retenida es
**500.6 m**. La garantía cubre adyacencia y buffer; no afirma eliminar la
autocorrelación a distancias mayores.

**Las referencias.** El diseño incluye un esquema alternativo por grupos
de AGEB (un GroupKFold sobre la AGEB, equivalente a un KFold barajado sin
aislamiento espacial): tamaños 49, 49, 48, 48, 48, distancia mínima
entrenamiento–prueba **0.0 m** y pares colindantes que no bajan con el
buffer (220 y 232 en los dos primeros pliegues). Sirve como **referencia
optimista declarada**: muestra cuánto infla el error aparente la
vecindad —bajo ese esquema el Random Forest rinde RMSE 0.3558 frente a
0.4288 bajo el esquema espacial— y por qué la lectura honesta es la del
esquema espacial.

**Otros controles del diseño.** La etiqueta por P85 se ajusta solo con el
entrenamiento retenido (mínimo 30 filas de entrenamiento por pliegue);
las métricas de ranking se autoprobaron (42 autopruebas); y se incluyen
dos líneas base de ranking: el **control aleatorio** (ordenar al azar:
marca lo que cualquier método debe superar) y la **heurística de Metro**
(ordenar por cercanía al transporte pesado: la regla "obvia" que un
experto propondría sin modelo).

**Si te preguntan X, responde Y.**
- *"¿Por qué no K-Fold normal como todos?"* Porque con autocorrelación
  espacial (Moran 0.43) el K-Fold aleatorio mezcla vecinos y el error
  reportado queda inflado hacia el optimismo; la validación espacial es la
  respuesta estándar en literatura geográfica, y el estudio incluye el
  esquema por grupos como referencia optimista para mostrar la
  diferencia.
- *"¿Tu buffer de 500 m basta?"* Garantiza cero pares colindantes
  entrenamiento–prueba y una separación mínima de 500.6 m; eso es lo que
  está medido. No afirmo que elimine toda dependencia a mayor distancia.
- *"¿Por qué incluyes un esquema que te hace ver peor?"* Porque el esquema
  por grupos es la referencia optimista: si solo hubiera ese, las métricas
  se verían mejor y serían menos honestas. Reportar ambos es la
  declaración completa.

> **Argumentos clave para la defensa**
> - "MAUP, autocorrelación y fuga espacial son tres problemas distintos:
>   el primero se mitiga declarando el soporte; la segunda se midió; la
>   tercera se atacó con Ward + buffer."
> - "El MAUP queda mitigado, no resuelto: fijé la AGEB como soporte y lo
>   declaré; no afirmo invariancia bajo otra zonificación."
> - "Las zonas de captura son buffers euclidianos de 500 m, no isócronas;
>   es una aproximación declarada, no un área de servicio real."
> - "El buffer dejó los pares colindantes en [0,0,0,0,0] y la distancia
>   mínima en 500.6 m: eso es lo que el arnés garantiza, y no lo extiendo
>   a autocorrelación de mayor escala."
> - "El esquema por grupos se incluye como referencia optimista: sin
>   aislamiento espacial el RMSE aparente es 0.356 frente a 0.429
>   espacial —esa brecha es el costo de ignorar la geografía."
> - "La etiqueta se ajusta solo con el entrenamiento retenido: el umbral
>   de relevancia nunca ve las pruebas."

---

## 5. Motor 1: similitud y compuerta de dominio

El Motor 1 busca AGEBs que "se parezcan" a las que hoy tienen estaciones
de alto uso (el Golden Cluster). Necesita tres piezas: un resumen del
perfil de cada zona (PCA), una medida de parecido (coseno) y una regla
para no puntuar zonas demasiado raras (Mahalanobis con encogimiento).

### 5.1 Análisis de componentes principales (PCA)

**Qué es.** Una técnica que toma muchas variables correlacionadas y las
reescribe como pocos ejes nuevos, llamados componentes, que capturan la
mayor parte de la información con la menor cantidad de dimensiones.

**Analogía.** Describir un departamento con veinte adjetivos redundantes
("amplio, espacioso, grande…") o con tres rasgos independientes
("tamaño, luz, ubicación"). El PCA encuentra los "rasgos" en que de verdad
varían los datos.

**Cómo funciona.** Calcula los **autovectores** de la matriz de covarianza:
las direcciones del espacio de variables en las que los datos varían más.
Cada autovector tiene un **autovalor**: cuánta varianza explica esa
dirección. Los componentes son **ortogonales** por construcción (cada uno
capta algo que los anteriores no captan). Las **cargas** de cada variable
en un componente son coeficientes del autovector: dicen qué tanto participa
esa variable en ese eje, **no** efectos causales.

**Qué hicimos y qué dio.** **18 variables** de entorno → **8 componentes**
que explican el **80.37 %** de la varianza acumulada (el objetivo era 80 %).
La PC1 se interpreta como "Eje de Equipamiento y Composición Socioeconómica
Residencial": sus cargas más grandes son grado de escolaridad promedio
(+0.409), % de viviendas con internet (+0.387), % de viviendas con auto
(+0.346), % de adultos mayores (+0.342) y participación de comercio
(−0.335).

**Si te preguntan X, responde Y.**
- *"¿PCA borra información?"* Retiene el 80.37 % de la varianza; lo que
  descarta es, en su mayoría, redundancia entre variables correlacionadas.
- *"¿Las cargas son efectos?"* No: son coeficientes de una rotación
  estadística. La escolaridad carga fuerte en PC1 porque ese eje resume
  el gradiente socioeconómico, no porque cause nada.

### 5.2 Similitud del coseno

**Qué es.** Una medida de parecido entre dos vectores que compara su
**dirección**, no su longitud: es el coseno del ángulo entre ellos. Vale 1
si apuntan igual, 0 si son ortogonales, −1 si son opuestos.

**Analogía.** Comparar dos recetas por sus *proporciones*: una receta para
4 y otra para 40 personas con los mismos porcentajes son la misma receta,
aunque sus cantidades difieran diez veces.

**Cómo se calcula.** cos(a,b) = (a·b)/(|a||b|). Cada AGEB es un vector en
el espacio de componentes principales; el puntaje de cada candidata es su
coseno medio con las AGEBs del Golden Cluster (o contra su centroide).

**Qué hicimos y qué dio.** Cada AGEB candidata recibe un puntaje de
similitud al núcleo Golden en el espacio PCA; ese puntaje es el criterio
de prioridad del Motor 1 una vez pasada la compuerta de dominio (5.3).
Diagnóstico de sesgo: el puntaje de similitud correlaciona con la
escolaridad de la AGEB (Spearman **0.7213**), con viviendas con internet
(**0.6681**) y con viviendas con auto (**0.5384**). Las medias del top-50
en dominio frente a todas las candidatas: escolaridad **13.00 vs 11.36**,
internet **0.840 vs 0.736**, auto **0.542 vs 0.463** — "parecerse al
Golden" y "ser zona de mayor nivel socioeconómico" van casi juntos.

**Si te preguntan X, responde Y.**
- *"¿Por qué coseno y no distancia euclidiana?"* Porque interesa el perfil
  (la forma del vector), no su magnitud; dos AGEBs con el mismo perfil a
  distinta escala deben puntuar igual — y la comparación empírica lo
  confirmó (la variante euclidiana es claramente peor, ver 5.5).
- *"¿La similitud es causal?"* No: mide coincidencia de perfiles. Es una
  regla de priorización declarada, no un mecanismo.

### 5.3 Distancia de Mahalanobis frente a euclidiana

**Qué es.** La distancia euclidiana mide "qué tan lejos" está un punto de
una referencia en línea recta, tratando todas las direcciones igual. La
distancia de Mahalanobis mide "qué tan raro" es un punto respecto de una
distribución: tiene en cuenta la escala de cada variable y las
correlaciones entre ellas. Formalmente d² = (x−μ)ᵀ Σ⁻¹ (x−μ).

**Analogía.** En un examen, estar a 10 puntos del promedio en la materia
más parejda es mucho más raro que estar a 10 puntos en la materia más
dispersa. La euclidiana trata ambos igual; Mahalanobis pesa lo inusual,
no lo lejano.

**Para qué se usa aquí.** Como **compuerta de dominio**: solo se puntúan
AGEBs cuya distancia de Mahalanobis al centro del Golden Cluster queda
dentro del corte. El corte es sqrt(chi2.ppf(0.9973, p)) —el percentil
99.73 % de una chi-cuadrada con p grados de libertad— **no** el valor
ad hoc de 3.0. "Fuera de dominio" significa fuera de la envolvente
estadística del Golden, **no** que el sitio sea malo.

**Qué hicimos y qué dio.** Con referencia n = 61 (las AGEBs Golden): con
covarianza empírica quedan en dominio 1,057 candidatas; con Ledoit-Wolf
suben a 1,382; fuera de dominio 1,345 y no proyectables 50. El número de
condición de la matriz bajó de **14.32** a **4.97** con el encogimiento;
eigenvalor mínimo 0.2221. Las Golden quedan dentro de su propio dominio
en 59 de 61 casos —solo descriptivo, no demuestra calibración—. En los
portafolios a B=30, la fracción de sitios fuera del dominio quedó en
0.30 para el Motor 1 (la medición completa: M1 0.30, M2 0.23, M3 0.57).

**Si te preguntan X, responde Y.**
- *"¿Por qué Mahalanobis y no un filtro por variable?"* Porque la rareza
  es multivariante: una AGEB puede ser normal en cada variable y rara en
  la combinación. Mahalanobis capta la combinación.
- *"¿El corte es arbitrario?"* Es un percentil chi-cuadrado estándar
  (equivalente probabilístico al criterio 3-sigma en una variante), no un
  número ajustado al resultado.
- *"¿Fuera de dominio es malo?"* No: significa que la AGEB no se parece
  estadísticamente al núcleo de referencia; el Motor 3, por diseño, sale
  más del dominio (0.57) porque su objetivo no es el parecido.

### 5.4 Encogimiento de Ledoit-Wolf

**Qué es una matriz de covarianza.** La tabla que resume cómo varían
juntas las variables: en la diagonal, la varianza de cada una; fuera de la
diagonal, cada covarianza. Mahalanobis necesita su **inversa** (Σ⁻¹), y la
inversa se vuelve inestable cuando hay pocas observaciones respecto al
número de variables: pequeñas perturbaciones en los datos producen
inversas muy distintas (matriz "mal condicionada").

**Analogía.** Afinar un instrumento con un tornillo suelto: cualquier
temblor lo desafina por completo. El encogimiento es apretar el tornillo
con una pieza rígida de repuesto.

**Qué hace el shrinkage.** Mezcla la covarianza empírica S con una matriz
simple bien condicionada (la diagonal): Σ̂ = (1−δ)·S + δ·D. El coeficiente
δ lo elige el método de Ledoit-Wolf de forma cerrada para minimizar el
error cuadrático esperado. Es un trade-off sesgo/varianza: se introduce un
poco de sesgo a cambio de una inversa mucho más estable.

**Qué hicimos y qué dio.** Con una razón n/p entre **2.00 y 2.56** (muy
pocas AGEBs Golden por variable), el encogimiento fue sustancial:
δ entre **0.38 y 0.70**. El número de condición de la matriz bajó de
**33.5–54.9** (empírica, por pliegue) a **2.26–6.44** (con shrinkage).
Consecuencia medida: la cobertura de decisión subió de **0.637** a
**0.901** sin cambiar el NDCG@10 respecto al coseno sin compuerta
(**0.673**): la compuerta estabilizada deja entrar más candidatas sanas
sin degradar el orden.

**Si te preguntan X, responde Y.**
- *"¿Por qué no la covarianza cruda?"* Con n/p ≈ 2, su inversa es tan
  inestable que la compuerta decidía por ruido; el shrinkage hace la
  inversa utilizable.
- *"¿Ledoit-Wolf es arbitrario?"* Es un estimador cerrado y estándar: elige
  δ por teoría, no por gusto.

### 5.5 Las variantes comparadas y sus resultados

El Motor 1 se evaluó como ranking sobre el esquema espacial primario, con
cinco variantes más dos líneas base (precisión@10 / NDCG@10 / cobertura
de decisión):

| Variante | Precisión@10 | NDCG@10 | Cobertura |
|---|---|---|---|
| Control aleatorio | 0.32 | 0.541 | 1.00 |
| Heurística de Metro | 0.30 | 0.674 | 1.00 |
| Coseno sin compuerta | 0.38 | 0.673 | 1.00 |
| **Coseno + compuerta Ledoit-Wolf (primaria)** | **0.38** | **0.673** | **0.901** |
| Coseno + compuerta empírica | 0.34 | 0.679 | 0.637 |
| Euclidiana | 0.18 | 0.574 | 1.00 |

**Cómo se lee.** La variante euclidiana es claramente peor (0.18): el
coseno se justifica empíricamente, no solo por intuición. La compuerta no
mejora el orden (NDCG 0.673 en ambas) pero la versión Ledoit-Wolf sí
repara la cobertura de decisión frente a la empírica (0.901 vs 0.637): la
compuerta mal condicionada se abstenía en demasiadas AGEBs. La heurística
de Metro empata el NDCG del coseno pero con peor precisión@10: el
parecido multivariante ordena mejor el top.

### 5.6 Cobertura de decisión y abstención

**Qué es.** La cobertura de decisión es la fracción de candidatas sobre
las que el motor emite puntaje (no se abstiene). **Abstenerse** —declarar
"esta AGEB está fuera de mi dominio, no la puntúo"— no es un fallo: es
una declaración honesta de que el modelo no sabe. Una cobertura de 0.901
significa que el 9.9 % de las candidatas quedan fuera de la envolvente
estadística y el motor se abstiene en ellas.

**Por qué importa.** Un ranking que puntúa todo siempre parece más
completo, pero asignar puntaje a zonas estadísticamente raras es peor que
declararlas fuera de dominio: la abstención protege la decisión. Es lo
opuesto a una columna de ceros: el motor distingue "no puedo opinar" de
"opino que es mala".

### 5.7 Hiperparámetros y sensibilidad

**La configuración primaria.** Semilla 42; estimador de covarianza
Ledoit-Wolf; cuantil de dominio 0.9973; cuantil de referencia 0.85;
objetivo de varianza PCA 0.80; frontera 1,000 m; vecinos de techo 5; K
evaluados 10/20/50.

**La sensibilidad declarada.** Se barrió el cuantil de dominio
{0.95, 0.99, 0.9973}, el cuantil de referencia {0.75, 0.85, 0.90} y el
objetivo de varianza {0.70, 0.80, 0.90}: los tres hiperparámetros que
podrían acusarse de "ajustados al resultado" fueron sometidos a análisis
de sensibilidad, no elegidos mirando el portafolio.

**El techo por AGEB.** Un diseño alternativo limita cuántas propuestas
puede recibir una misma AGEB para dispersar el portafolio; el análisis 05
**no** lo usa: el ranking del Motor 1 es puro puntaje, y la dispersión
territorial se evalúa después, no se impone.

**Si te preguntan X, responde Y.**
- *"¿Tunelaste los hiperparámetros hasta que gustara?"* No: se fijaron a
  priori y se declaró su análisis de sensibilidad con tres grillas.
- *"¿Por qué tu ranking no se parece al experto (Metro)?"* Le gana en
  precisión@10 (0.38 vs 0.30): el parecido multivariante ordena mejor el
  top que la regla de cercanía al Metro.

> **Argumentos clave para la defensa**
> - "El Motor 1 ordena por parecido al núcleo histórico en el espacio de
>   características, con una compuerta de dominio que excluye las AGEBs
>   estadísticamente raras —y se abstiene en el 9.9 %: abstenerse es
>   declarar que no sabe, no fallar."
> - "PCA reduce 18 variables a 8 ejes con el 80.37 % de la varianza; las
>   cargas son coeficientes, no causas."
> - "El corte de dominio es el percentil chi-cuadrado 99.73 %, no un 3.0
>   ad hoc, y la covarianza se estabilizó con Ledoit-Wolf porque n/p era
>   apenas ~2."
> - "La variante euclidiana quedó en 0.18 de precisión@10 frente a 0.38
>   del coseno: la elección del coseno es empírica, no estética."
> - "El puntaje del Motor 1 correlaciona con escolaridad (Spearman 0.7213):
>   replica el sesgo histórico, y eso es parte de lo que el estudio
>   documenta, no lo esconde."

---

## 6. Motor 2: predicción supervisada

El Motor 2 predice el atractivo de cada AGEB candidata entrenando un modelo
supervisado sobre las AGEBs con servicio y validándolo espacialmente.

### 6.1 Árboles de decisión y Random Forest

**Qué es un árbol de decisión.** Una sucesión de preguntas binarias
("¿escolaridad > 12?", "¿densidad > 15,000?") que divide los datos en
grupos cada vez más homogéneos respecto al target; al final, cada hoja
entrega una predicción. Son flexibles e interpretables pero
**sobreajustan**: un árbol profundo memoriza el ruido del entrenamiento.

**Analogía.** Un alumno que memoriza los ejercicios del libro saca 10 en
tareas y 4 en el examen: aprendió las respuestas, no el método.

**Qué es Random Forest (bagging).** Entrenar muchos árboles, cada uno con
una remuestra aleatoria del entrenamiento y un subconjunto aleatorio de
variables en cada corte, y promediar sus predicciones. La diversidad entre
árboles cancela su varianza individual: el bosque sobreajusta mucho menos
que el árbol solo, a costa de perder interpretabilidad directa.

**Qué hicimos y qué dio.** El despliegue usa **Random Forest**. En la
validación espacial, su RMSE medio fue **0.4288** y su R² medio **0.1720**,
frente a un modelo constante (0.5444 y −0.3028). Sus hiperparámetros se
fijaron a priori junto con los demás modelos (el reporte sellado declara
`hyperparameters_fixed_a_priori` para todo el análisis; la grilla exacta
del bosque no aparece en el reporte y no debe reconstruirse de memoria).

### 6.2 Ridge y el modelo constante: los controles

**Qué es ridge.** Regresión lineal con **regularización L2**: además de
ajustar los coeficientes a los datos, penaliza que sean grandes. La
penalización "encoge" los coeficientes hacia cero y estabiliza el modelo
frente a variables correlacionadas y muestras pequeñas. Es el control
*fuerte*: un modelo lineal difícil de romper.

**Qué es el modelo constante.** Predecir siempre la misma cantidad (la
media del entrenamiento). Es el **piso**: ningún modelo con pretensión
puede quedar por debajo. Que el constante rinda R² = −0.3028 en el
esquema espacial muestra lo difícil que es el problema fuera de la
vecindad.

**Por qué dos controles.** El constante demuestra que el problema no es
trivial; ridge demuestra que la complejidad debe justificarse: si un
modelo de máxima capacidad no vence a una línea regularizada, no hay
evidencia de que la capacidad extra sirva.

### 6.3 Redes neuronales y FT-Transformer

**Qué es una red neuronal.** Una función ajustable compuesta por capas de
unidades simples: cada capa combina las entradas con pesos aprendidos y
una no linealidad, de modo que el conjunto puede aproximar relaciones muy
complejas.

**Qué es la auto-atención y el FT-Transformer.** La auto-atención
(self-attention) hace que cada elemento de la entrada pese a los demás
antes de decidir su representación: en texto, cada palabra "mira" a las
otras; en datos tabulares, cada campo de la fila "mira" a los demás
campos. El FT-Transformer traslada esa idea a tablas: tokeniza cada
feature y procesa las interacciones por atención. Es el modelo de máxima
capacidad que se probó.

**La configuración (fijada a priori).** d_token 32; 2 capas; 4 cabezas de
atención; feedforward 64; dropout 0.1; tasa de aprendizaje 0.001;
decaimiento 0.0001; lote 32; hasta 400 épocas con paciencia 40; fracción
de validación interna 0.2; semillas {0,1,2,3,4}; semilla global 42.
Fijarlos **a priori** es lo que impide la acusación "elegiste la
configuración que te convenía": la arquitectura se declaró antes de ver
los resultados.

**Qué hicimos y qué dio.** El dictamen sellado fue negativo: el
FT-Transformer **no bajó del mejor control** (ridge, RMSE 0.4195 contra
0.4206 del FT); ganó en **3 de 5 pliegues** cuando el criterio exigía 4;
y su mejora condicionada fue **−0.0010** frente a una variación entre
semillas de **0.0313** (razón 0.033): la señal era un treintavo del ruido
experimental. Por eso **se retiró del despliegue** — queda como caso de
estudio, no como modelo del portafolio.

### 6.4 Curva de aprendizaje, importancia por permutación y semillas múltiples

**Qué es una curva de aprendizaje.** Entrenar el modelo con fracciones
crecientes de los datos (aquí 0.5, 0.75 y 1.0, con semillas {0,1,2}) y
ver cómo cambia el error. Responde: "¿más datos ayudarían?". Si el error
ya se estabilizó, el cuello de botella no es volumen. Al 50 % de los
datos: ridge 0.4406, random forest 0.4927, FT-Transformer 0.5054 — el
modelo complejo necesita más datos para arrancar y el lineal aprovecha
antes lo poco que hay.

**Qué es la importancia por permutación.** Medir cuánto empeora el error
del modelo entrenado cuando se desordena ("permite") una variable: si el
error sube, esa variable le importaba. Aquí con 10 repeticiones por
variable. **Su límite con variables correlacionadas**: si dos features
traen la misma información, permutar una no empeora mucho porque la otra
la suplanta — las importaciones se reparten y ambas parecen menos
importantes de lo real. Es una medida de uso, no de causalidad.

**Qué son las semillas múltiples.** Repetir el experimento con semillas
{0,1,2,3,4} mide cuánto del resultado es azar: la desviación entre
semillas del FT (0.0313) es la regla que hace visible que su "mejora"
(−0.0010) es ruido.

### 6.5 Principio de parsimonia (navaja de Ockham)

**Qué es.** Entre modelos que sostienen el desempeño, se prefiere el más
simple: menos partes, menos supuestos, menos cosas que romper en
producción. La regla no es "elige el más simple siempre", sino "la
complejidad extra debe pagarse con desempeño reproducible".

**Aplicación honesta en este estudio.** Aquí la navaja se aplicó al
**Transformer**, no a una comparación de iguales: ridge tiene el mejor
RMSE medio (0.4195), el FT-Transformer está a la par (0.4206) y Random
Forest es el peor de los tres modelos con capacidad (0.4288) —aunque los
tres quedan cerca y muy por encima del control constante (0.5444). En R²
espacial: constante −0.3028, ridge 0.1938, RF 0.1720, FT 0.2148.
La comparación directa RF–ridge: diferencia media de RMSE **0.00924** a
favor de ridge, con el bosque ganando **3 de 5** pliegues. Se desplegó
**Random Forest** por parsimonia y estabilidad una vez que el Transformer
no cumplió las condiciones del dictamen: la frase correcta es "la
complejidad extra no se pagó con desempeño reproducible", no "todos
empataron" — y la brecha con ridge es de nueve milésimas, no una derrota.

**Si te preguntan X, responde Y.**
- *"¿Por qué RF si ridge fue mejor en RMSE medio?"* Concede el dato tal
  cual: ridge 0.4195, RF 0.4288 —la brecha es 0.0092 y ridge es lineal.
  El punto del dictamen es que ni siquiera el modelo de máxima capacidad
  (Transformer) logró una mejora reproducible sobre el control; el
  despliegue privilegió un modelo no lineal estable y de operación simple.
- *"¿El Transformer era mejor y lo tiraste?"* No era mejor: ganó 3/5
  pliegues contra un umbral de 4, y su ventaja neta (−0.0010) fue 30 veces
  menor que la variación entre semillas (0.0313). Retirarlo fue la
  decisión que el propio protocolo dictaba.
- *"¿Cómo sabes que no tuneaste el bosque?"* Los hiperparámetros de todos
  los modelos se fijaron a priori y el reporte lo declara.

> **Argumentos clave para la defensa**
> - "El dictamen del Transformer fue por regla, no por gusto: no bajó del
>   mejor control, ganó 3/5 pliegues contra 4 exigidos, y su mejora fue
>   una treintava parte del ruido entre semillas."
> - "Random Forest se desplegó por parsimonia y estabilidad; no afirmo que
>   empatara en RMSE —ridge fue ligeramente mejor, por 0.0092— sino que
>   la complejidad máxima no se justificó."
> - "El sobreajuste se controla con bagging: muchos árboles diversos
>   votan, y la varianza individual se cancela."
> - "La curva de aprendizaje muestra que el modelo complejo no arrancaba
>   con la mitad de los datos (0.5054 vs 0.4406 de ridge): no era un
>   problema de volumen, era de capacidad sin retorno."
> - "Los hiperparámetros se fijaron a priori y así lo declara el reporte:
>   no hay ajuste al resultado que esconder."

---

## 7. Motor 3: optimización de grafos y prescripción

El Motor 3 no predice: **prescribe**. Dado un presupuesto de B estaciones,
elige el conjunto de sitios que maximiza un objetivo declarado: cobertura
de población nueva más cercanía a la red existente.

### 7.1 Teoría de grafos aplicada a la red

**Qué es.** Un grafo es un conjunto de **nodos** (aquí, estaciones y sitios
candidatos) unidos por **aristas** (enlaces). Una **componente conexa** es
una subred en la que todo nodo alcanza a los demás por aristas; el número
de **saltos** entre dos nodos es el mínimo de aristas que los separa.

**Por qué aristas de ≤500 m.** Es la regla de enlace: una estación nueva
solo "conecta" con la red si está a menos de 500 m de una existente (o de
otra nueva ya incorporada): la distancia caminable operativa con la que la
red crece de forma contigua. La tabla de distancia de enlace justifica el
umbral: a 300 m la red se rompe en **195 componentes** (la mayor con 60
Golden); a 400 m quedan **29 componentes** (la mayor con 100 Golden); a
**500 m la red es una sola componente** de 677 estaciones con las 102
Golden dentro — el umbral donde la red deja de fragmentarse.

**Las reglas compartidas de factibilidad** (el mismo contrato para los
tres motores): CRS EPSG:32614; enlace ≤ **500 m**; separación mínima
**300 m** entre estaciones; alcance máximo **3,000 m**; retícula de
candidatos de **250 m**; radio de cobertura **500 m**; celdas de población
de **200 m**; presupuestos {15, 30, 50} con 30 como primario.

**Las distancias reales de la red.** Cuantiles de la distancia al vecino
más cercano entre estaciones (m): P05 58.8, P10 114.6, P25 167.9, P50
**220.4**, P75 278.8, P90 323.1, P95 345.7, P99 429.4; la mediana entre
estaciones Golden es 249.6 m. La regla de separación mínima de 300 m es
coherente con la estructura real: la mediana de vecino actual es 220 m.

**Qué son los sitios.** Los candidatos son **centros de celdas de una
retícula de 250 m** sobre las AGEBs puntuadas —no ubicaciones de calle y
número—, por eso en los mapas aparecen alineados; son puntos de partida
que requieren validación en campo. En la red base son **1,656** sitios en
**446** AGEBs con sitios (de un universo de 2,064 AGEBs candidatas
puntuadas).

### 7.2 Embeddings y Node2Vec (y por qué se retiró)

**Qué es un embedding.** Una representación vectorial aprendida: cada nodo
del grafo se convierte en un punto de un espacio de baja dimensión, donde
se espera que nodos "parecidos" queden cerca. **Node2Vec** lo aprende con
paseos aleatorios por el grafo: nodos que aparecen juntos en muchos paseos
quedan cerca en el embedding.

**Qué pasó aquí.** La afinidad por embeddings no ordenaba a los sitios por
cercanía al núcleo Golden (la correlación de Spearman con −saltos fue
**−0.095**, un resultado histórico registrado, no recalculado) y añadía un
pipeline complejo sin cambiar la decisión. Se retiró por decisión
metodológica y se reemplazó por una afinidad determinista:
**1/(1 + saltos a una estación Golden)** sobre el grafo.

**Si te preguntan X, responde Y.**
- *"¿Por qué quitar Node2Vec?"* Porque no aportaba lo que el objetivo
  necesita: la métrica resultante no ordenaba por cercanía al núcleo
  (Spearman −0.095) y el término determinista 1/(1+saltos) es transparente,
  reproducible y directo.

### 7.3 Algoritmos genéticos

**Qué es.** Una metaheurística evolutiva: mantiene una población de
soluciones candidatas (portafolios de B sitios), las cruza y muta, y
conserva las que mejor puntaje tienen generación tras generación. Sirve
para problemas combinatorios enormes donde enumerar todo es imposible —
pero es estocástica, lenta y exige tunear parámetros.

**La configuración usada.** Población de 80 individuos; 120 generaciones;
probabilidad de cruza 0.7 (con cx_indpb 0.5); probabilidad de mutación
0.3 (mut_indpb 0.05, sigma 0.2); selección por torneo de 3; elitismo de
2. Semillas primarias {42,43,44,45,46}.

**Qué hicimos y qué dio.** El GA se usó como **comparación**, no como
motor. En la configuración primaria (w = 0.5, B = 30) el greedy tarda
**0.016 s** por corrida frente a **51.4 s** por semilla del GA —**3,193×**
más rápido; el cociente emparejado entre configuraciones va de
**2,786× a 4,422×**. Y con mejor cobertura: B=15 **166,731** (greedy) vs
**161,639** (GA); B=30 **310,288** vs **305,090**; B=50 **481,554** vs
**452,666**. El greedy gana en los tres presupuestos. (Las cifras
304,459 / 509,267 / 7,739 pertenecen a un motor anterior ya retirado y no
deben citarse.)

### 7.4 Greedy, submodularidad y rendimientos decrecientes

**Qué es un greedy.** Construir la solución paso a paso eligiendo en cada
iteración la opción de mayor ganancia inmediata, sin reconsiderar
decisiones anteriores.

**Qué son los rendimientos decrecientes y la submodularidad.** La primera
estación cubre mucha población que nadie cubría; la centésima cubre poca
población nueva porque las anteriores ya cubren su zona. Formalmente, una
función de conjuntos es **submodular** cuando el beneficio marginal de
añadir un elemento decrece al crecer el conjunto. Esa estructura es la que
hace al greedy razonable en cobertura: existe una garantía teórica clásica
(entorno a (1−1/e) del óptimo para objetivos submodulares monótonos bajo
restricción de cardinalidad), y el objetivo aquí combina un término
submodular de cobertura con un término lineal de afinidad, que sigue
siendo submodular.

**El objetivo declarado.** f_w(S) = w · (población nueva / P_norm) +
(1 − w) · (suma de afinidades / B), con **w = 0.5**: mitad cobertura, mitad
cercanía a la red por saltos a Golden. **P_norm** es una cota submodular
de normalización: el valor de referencia que convierte la población en
una fracción comparable con el término de afinidad.

**Precisión para la defensa.** La afinidad por saltos es parte del
objetivo, así que las métricas de "cercanía a Golden" del portafolio
resultante quedan optimizadas **por construcción**: reportarlas como
ventaja no es evidencia independiente, es circularidad. La mediana de
saltos del portafolio es 9.5 en la configuración primaria (8.0 y 11.0 en
otras configuraciones) — se reporta como descripción, no como mérito.
El argumento independiente del Motor 3 es la población cubierta y el
perfil de las zonas elegidas, no su afinidad.

**Nota.** El Motor 3 **no tiene backtest** porque no predice nada: ejecuta
un objetivo declarado; no hay "dato escondido" contra el que validarlo.

### 7.5 Factibilidad, razones de paro, aleatorios y sensibilidad

**Qué es una solución factible.** Un portafolio que cumple todo el
contrato: cada sitio enlazado a ≤500 m de la red (incluyendo las nuevas
que ya lo integran), a ≥300 m de cualquier estación, dentro del alcance de
3,000 m y fuera de AGEBs ocupadas. Cuando el greedy no encuentra más
sitios factibles con valor positivo antes de llegar a B, se detiene y
declara la **razón de paro** — `budget` (entregó B), `no_positive_value`
(se agotaron los sitios con ganancia) u otra causa— en vez de rellenar
con basura.

**Contra el azar.** El motor se comparó con **300 portafolios aleatorios**
factibles (misma semilla base 42): el GA quedó en el percentil **1.0**,
es decir, mejor que todos los aleatorios. Optimizar sí aporta sobre el
azar — la pregunta era si el azar ya resolvía el problema, y no.

**Sensibilidad al peso w.** Se evaluó w ∈ {0.0, 0.25, 0.5, 0.75, 1.0}
con presupuestos {15, 30, 50}; el peso primario es 0.5 y el análisis de
sensibilidad queda declarado, no escondido.

**Qué significa que GA y greedy coincidan o difieran.** El Jaccard entre
sus portafolios varía mucho entre configuraciones (0.875 en una, 0.111 en
otra): cuando casi coinciden, la solución greedy es estable y el GA no
encuentra nada mejor que valga la espera; cuando difieren con valor
parecido, hay muchas soluciones casi equivalentes — el paisaje del
problema tiene muchas buenas respuestas, lo cual es una propiedad
favorable, no un defecto.

**El grafo de flujos origen-destino.** Además del grafo de estaciones, el
análisis describe la comunidad Golden de flujos: participación 0.451 y
mediana intra-comunidad de 1,883.9 m. Es un **diagnóstico descriptivo**:
dice que el núcleo viaja principalmente dentro de sí mismo a distancias
cortas — pero **no entra al optimizador**; informa el contexto, no la
decisión.

**Si te preguntan X, responde Y.**
- *"¿El greedy encuentra el óptimo?"* No se afirma optimalidad; sí es
  determinista, ~3,200× más rápido que el GA y con mejor cobertura en los
  tres presupuestos probados. La estructura submodular del objetivo es lo
  que lo hace defendible.
- *"¿Por qué w = 0.5?"* Es la configuración primaria declarada: equilibrio
  explícito entre cobertura y conectividad, y la sensibilidad se barrió
  en {0.0, 0.25, 0.5, 0.75, 1.0}.
- *"¿Por qué 500 m de enlace?"* Porque a 500 m la red forma una sola
  componente con las 102 Golden; a 300–400 m se rompe en 195/29
  componentes. Es el umbral de coherencia estructural, además de la
  distancia caminable operativa.

> **Argumentos clave para la defensa**
> - "El Motor 3 es prescriptivo, no predictivo: no tiene backtest porque
>   no hay un dato escondido que predecir; ejecuta un objetivo declarado."
> - "La conectividad es parte del objetivo (a diferencia del Motor 1,
>   donde solo es un filtro de factibilidad); por eso sus métricas de
>   cercanía a Golden están optimizadas por construcción y no las uso como
>   evidencia independiente."
> - "El greedy ganó al genético en los tres presupuestos y es ~3,200× más
>   rápido; elegir greedy no es renunciar a calidad, es lo que midieron
>   los experimentos."
> - "El umbral de 500 m no es capricho: es donde la red deja de
>   fragmentarse —a 500 m es una sola componente con las 102 Golden."
> - "Node2Vec se retiró por no aportar: su afinidad no ordenaba por
>   cercanía al núcleo (Spearman −0.095) y añadía complejidad sin cambiar
>   la decisión."
> - "Los sitios son centros de celdas de una retícula de 250 m; no son
>   direcciones y requieren validación en campo."

---

## 8. Resultados e integración

### 8.1 Índice de Jaccard y consenso

**Qué es.** El índice de Jaccard mide el solape entre dos conjuntos:
|A ∩ B| / |A ∪ B|. Vale 1 si son idénticos, 0 si no comparten nada. Aquí
compara los portafolios sitio por sitio.

**Analogía.** Dos personas que deben nombrar 30 lugares de la ciudad:
Jaccard alto = eligieron casi los mismos; Jaccard bajo = cada quien fue a
distritos distintos.

**Qué hicimos y qué dio.** A B=30: Jaccard M1–M2 = **0.176**, M1–M3 =
**0.091**, M2–M3 = **0.250**. El solape M1–M3 casi nulo es la evidencia
concreta de que miden cosas distintas: cercanía en el espacio de
características frente a cercanía en el grafo. El **consenso** cuenta los
sitios elegidos por al menos dos motores: **18** a B=30, de los cuales
**4** aparecen en los tres (los 4 están incluidos en los 18).

### 8.2 El trade-off final

**Las cifras.** A B=30, población nueva cubierta: M1 **202,337**, M2
**282,102**, M3 **310,288** habitantes. Estas cifras son **uniones
espaciales** de celdas de 200 m (cada celda cuenta una sola vez), por eso
son menores que la suma aritmética por sitio. Escolaridad media de las
AGEBs seleccionadas: M1 **13.02**, M2 **11.83**, M3 **11.64**, frente a
**12.23** del universo candidato. Fracción de sitios fuera del dominio del
diseño de validación: M1 **0.30**, M2 **0.23**, M3 **0.57**.

**La lectura.** El Motor 1 maximiza el parecido con las zonas
históricamente exitosas y, en consecuencia, selecciona AGEBs de mayor
escolaridad que el universo (13.02 vs 12.23): **replica el sesgo
histórico** y además cubre menos población. El Motor 3, al incorporar la
conectividad en el objetivo, cubre la mayor población (310,288) y lo hace
seleccionando zonas de **menor** nivel socioeconómico (11.64) —a costa de
ir más lejos del dominio calibrado (57 % fuera de dominio). El Motor 2
queda en medio en ambas dimensiones. Ese es el trade-off que el estudio
documenta: cobertura y equidad frente a permanencia dentro del dominio
medido.

**La población.** Proviene del Censo 2020; la calibración de uso es de
2025. Es el soporte sellado disponible y se declara como límite temporal.

### 8.3 Integración: cómo se comparan los motores

**Identidad de sitio.** La comparación solo es posible porque los tres
motores emiten sitios del mismo catálogo (mismo identificador de sitio,
misma retícula): un Jaccard entre portafolios exige que "el mismo sitio"
signifique lo mismo en los tres. El comparador solo lee los portafolios
publicados y exige que todos referencien el mismo diseño de validación.

**El radar de métricas.** Ningún motor gana en todo: se comparan en
varias dimensiones a la vez —población cubierta, escolaridad de las zonas
elegidas, fracción fuera de dominio, solape— como un radar que dibuja el
perfil de cada portafolio en vez de coronar a uno.

**La tensión cobertura-equidad-dominio.** El resultado central no es un
ganador sino una tensión triangular: el Motor 1 maximiza dominio al costo
de sesgo; el Motor 3 maximiza cobertura y equidad al costo de dominio;
el Motor 2 equilibra. El consenso de 18 sitios es la zona donde las tres
lógicas convergen —los candidatos más robustos para una primera fase.

### 8.4 Pregunta de investigación e hipótesis

**La diferencia.** La pregunta de investigación es una interrogación que
orienta el estudio; la hipótesis es una afirmación refutable que puede
salir falsa. Una formulación del tipo "es posible que…" no es una
hipótesis porque nada podría refutarla: cualquier resultado es compatible
con "es posible". Para que una defensa tenga qué defender, la hipótesis
debe poder fallar.

**Formulación usada.** Pregunta de investigación: "¿Puede un enfoque de
ciencia de datos diseñar una expansión justa y conectada sin replicar el
sesgo histórico?". Hipótesis general (afirmativa): "A igual presupuesto,
un diseño de expansión que incorpora la conectividad con la red existente
en su objetivo cubre más población nueva y selecciona zonas de menor nivel
socioeconómico que un diseño basado solo en la similitud con las zonas
históricamente exitosas." Los datos la apoyan: el Motor 3 cubre 310,288
frente a 202,337 del Motor 1 y selecciona zonas de escolaridad 11.64
frente a 13.02.

### 8.5 Registro de afirmaciones y trazabilidad

**Qué es un registro de afirmaciones.** La tabla final del estudio donde
cada afirmación del documento ("el Gini es 0.9296", "el greedy es
3,193× más rápido") va acompañada de su cifra y de su fuente verificable.
No es burocracia: es lo que permite que un sinodal tome cualquier número
de la tesis y compruebe de dónde salió sin creerlo por fe.

**Por qué importa en la defensa.** La tesis no pide confianza: ofrece
trazabilidad. Cada cifra de esta guía existe en el registro con su
artefacto de origen; las que no existen ahí (como el R² de 0.98 o las
cifras del motor retirado) se declaran explícitamente como no citables.

**Si te preguntan X, responde Y.**
- *"¿Cuál motor recomiendas?"* Depende del objetivo declarado: si la
  prioridad es permanecer en dominio, el 1; si es cobertura con perfil
  más equitativo, el 3; el consenso de 18 es la respuesta cuando se
  quieren ambas.
- *"¿La comparación es justa?"* Los tres comparten el mismo contrato de
  factibilidad, los mismos sitios y los mismos presupuestos; solo cambia
  el criterio de selección.

> **Argumentos clave para la defensa**
> - "Motor 1 y Motor 3 no se solapan (Jaccard 0.091): uno mide parecido
>   en el espacio de características y el otro cercanía en el grafo; la
>   conectividad es filtro en uno y objetivo en el otro."
> - "El trade-off es real y está cuantificado: M1 replica el sesgo (13.02
>   de escolaridad, 202 mil habitantes); M3 cubre más población en zonas
>   de menor nivel (11.64, 310 mil) a cambio de salir más del dominio
>   (0.57)."
> - "Las cifras de población son uniones de celdas de 200 m —cada celda
>   cuenta una vez—, no sumas por sitio."
> - "La hipótesis está en forma afirmativa y es refutable; 'es posible'
>   no lo sería."
> - "Cada afirmación del estudio está en el registro con su fuente; la
>   defensa no pide confianza, ofrece trazabilidad."

---

## 9. Límites y amenazas a la validez

La defensa fuerte no esconde límites: los enumera antes de que el sínodo
los encuentre. Cada uno de estos está declarado en los reportes.

### Límites temporales

- **Censo 2020 frente a uso 2025.** La población y los atributos
  sociodemográficos vienen del censo de 2020; el uso de la red se mide en
  2025. Cinco años de cambio urbano separan ambas mediciones: es el
  soporte disponible y se declara, pero las cifras de "población cubierta"
  reflejan dónde vivía la gente en 2020.
- **El catálogo es un snapshot.** Las 677 estaciones describen la red en
  un momento; no son evidencia de estaciones activas todo el año.

### Límites espaciales

- **MAUP no resuelto.** Se fijó la AGEB como soporte y se declaró; no se
  demostró invariancia frente a otra zonificación ni escala.
- **Autocorrelación más allá de 500 m.** El buffer garantiza cero pares
  colindantes y 500.6 m mínimos entre pliegues; no afirma independencia a
  distancias mayores.

### Límites de medición

- **Buffers euclidianos, no isócronas.** Las zonas de captura de 500 m
  son círculos proyectados, no áreas caminables reales por la red vial.
- **Área de origen desconocida: 0.2532.** Una cuarta parte del área de
  las celdas no tiene población de origen identificable con el soporte
  usado; las cifras de cobertura son sobre el área conocida.
- **El DENUE es un proxy.** La actividad económica se aproxima con el
  directorio de unidades económicas, no con empleo ni ventas reales.

### Límites de diseño

- **Sitios en retícula de 250 m, no direcciones.** Los candidatos son
  centros de celdas; la ubicación final exige validación en campo.
- **Las AGEBs con estación no son candidatas.** Por diseño, las zonas ya
  servidas no compiten por nuevas estaciones; el portafolio expande, no
  densifica.
- **Ingreso no medido directamente.** El nivel socioeconómico se aproxima
  con escolaridad, vivienda y equipamiento; queda declarado el riesgo de
  sesgo de ingreso al usar esos proxies.

### Límites de inferencia

- **Todo es asociación y diseño, no causalidad.** Las cargas del PCA, las
  importancias por permutación y las correlaciones de Spearman describen
  asociaciones; no hay experimento ni contrafactual. El portafolio del
  Motor 3 selecciona zonas de menor escolaridad por construcción del
  objetivo, no porque se demuestre que funcionen mejor.
- **No hay pronóstico de demanda futura.** Los modelos ordenan por
  atractivo observado; nadie afirma cuántos viajes tendrá cada estación
  nueva.

### Límites de alcance

- **No hay modelo de costos, flota ni rebalanceo.** El presupuesto es en
  número de estaciones, no en pesos; la operación (cuántas bicicletas,
  cómo rebalancear) queda fuera del estudio.

### Límites de validación

- **El Motor 3 no tiene backtest.** Es prescriptivo; no hay dato escondido
  contra el que medirlo. Sus únicas validaciones son factibilidad,
  comparación con aleatorios y con el genético.
- **La afinidad está optimizada por construcción.** La mediana de saltos
  a Golden del portafolio del Motor 3 es una salida del objetivo, no una
  prueba independiente de conectividad.

> **Argumentos clave para la defensa**
> - "Los límites están declarados en los reportes, no descubiertos aquí:
>   temporal (censo 2020/uso 2025), espacial (MAUP mitigado), de medición
>   (buffers, no isócronas), de inferencia (asociación, no causalidad)."
> - "Ninguna afirmación del estudio depende de un experimento que no hice;
>   lo que afirmo es diseño y asociación medida."
> - "El Motor 3 no tiene backtest porque no hay target que predecir; su
>   validación es factibilidad y comparación contra 300 aleatorios y el
>   genético."

---

## 10. Trabajo futuro

Qué haría falta para fortalecer cada límite, en el mismo orden:

- **MAUP.** Análisis de sensibilidad frente a zonificaciones alternativas
  (o traslado del análisis a celdas regulares): es la única forma real de
  medir cuánto depende el resultado de la partición.
- **Medición espacial.** Áreas de servicio caminables sobre la red vial
  (isócronas) en lugar de buffers euclidianos de 500 m.
- **Temporalidad.** Incorporar datos censales o de población más recientes
  cuando existan, y repetir la medición de cobertura.
- **Evaluación posterior a la implementación.** Si la red crece por estas
  zonas, medir la demanda observada contra la priorización: el backtest
  verdadero del Motor 3 solo existe después de construir.
- **Modelo de costos y operación.** Traducir el presupuesto B a pesos:
  costo por estación, flota necesaria y rebalanceo esperado.
- **Demanda multimodal explícita.** Integrar los flujos del GTFS como
  componente del objetivo, no solo como contexto descriptivo.
- **Variables de demanda latente.** Encuestas de movilidad o datos de
  telefonía para aproximar viajes potenciales, no solo los observados en
  la red actual.

> **Argumentos clave para la defensa**
> - "El trabajo futuro ataca los límites en el mismo orden en que se
>   declararon: no son un anexo, son la continuación del diseño."
> - "La prueba definitiva del Motor 3 es posterior a la implementación:
>   mientras tanto su honestidad es haber declarado que no tiene
>   backtest."

---

## Glosario

- **AGEB**: Área Geoestadística Básica; unidad censal urbana del INEGI,
  el polígono de análisis del estudio (2,452 urbanas).
- **afinidad (Motor 3)**: término del objetivo que premia la cercanía al
  núcleo; determinista, 1/(1+saltos a Golden).
- **aglomerativo (clustering)**: familia de métodos que parte de cada
  punto como su propio grupo y los va fusionando; Ward es uno.
- **árbol de decisión**: modelo de preguntas binarias sucesivas que
  divide los datos en grupos homogéneos; sobreajusta fácil.
- **arista**: enlace entre dos nodos de un grafo; aquí, dos estaciones a
  ≤500 m.
- **auto-atención (self-attention)**: mecanismo en que cada elemento de
  la entrada pesa a los demás; base del Transformer.
- **autovalor**: cuánta varianza explica cada autovector del PCA.
- **autovector (eigenvector)**: dirección de máxima varianza en el PCA;
  cada componente es un autovector de la covarianza.
- **bagging**: entrenar muchos modelos sobre remuestras y promediar;
  reduce varianza; base de Random Forest.
- **baseline (control, línea base)**: método simple de referencia que
  todo modelo debe superar (constante, aleatorio, heurística de Metro).
- **buffer**: zona a distancia fija alrededor de un punto; aquí, radios
  euclidianos de 500 m.
- **carga (PCA)**: coeficiente de una variable en un componente;
  asociación con el eje, no efecto causal.
- **causalidad inversa**: usar como predictor una variable construida
  desde el propio target.
- **celda de población**: celda de 200 m con conteo censal; unidad de la
  superficie de población (67,872).
- **cohorte / snapshot**: foto de un sistema en un momento; el catálogo
  de estaciones es un snapshot, no un historial.
- **componente (PCA)**: eje nuevo ortogonal que resume variables
  correlacionadas.
- **componente conexa**: subred de un grafo donde todo nodo alcanza a los
  demás por aristas.
- **contrato de datos**: especificación formal de columnas, tipos y
  reglas que una tabla debe cumplir para entrar al pipeline.
- **contrato de factibilidad**: reglas compartidas que todo portafolio
  debe cumplir (enlace ≤500 m, separación ≥300 m, etc.).
- **correlación de Pearson**: asociación lineal entre valores crudos;
  sensible a extremos.
- **correlación de Spearman**: asociación monótona medida sobre rangos;
  robusta a extremos y relaciones curvas.
- **covarianza (matriz de)**: tabla de cómo varían juntas las variables;
  su inversa define la distancia de Mahalanobis.
- **CRS proyectado**: sistema de coordenadas plano en metros; el estudio
  usa EPSG:32614 (UTM 14N).
- **cuantil**: valor que deja una fracción de los datos por debajo; la
  mediana es el cuantil 0.5.
- **cuarentena**: tabla donde van las filas que violan el contrato de
  datos, con su causa.
- **curva de aprendizaje**: error del modelo al entrenar con fracciones
  crecientes de datos; mide si más datos ayudarían.
- **data leakage (fuga de datos)**: usar información no disponible al
  decidir, o derivada del target.
- **DENUE**: directorio de unidades económicas del INEGI; proxy de
  actividad económica (462,732 registros).
- **desviación estándar**: dispersión típica alrededor de la media, en
  unidades del dato.
- **dictamen**: veredicto del protocolo de comparación del Transformer
  contra sus controles (fue negativo).
- **distancia de Mahalanobis**: "rareza" de un punto respecto a una
  distribución, ponderando correlaciones: d² = (x−μ)ᵀΣ⁻¹(x−μ).
- **distancia euclidiana**: longitud de la recta entre dos puntos; no
  ve correlaciones ni escala.
- **embedding**: representación vectorial aprendida de entidades; aquí,
  de nodos del grafo (Node2Vec, retirado).
- **encogimiento (shrinkage)**: mezclar la covarianza empírica con una
  diagonal para estabilizar su inversa (Ledoit-Wolf).
- **estandarización (z-score)**: (x − media)/desviación; pone todas las
  variables en la misma escala.
- **etiqueta**: la marca de relevancia en la evaluación de ranking
  (target ≥ P85 del entrenamiento).
- **FT-Transformer**: Transformer adaptado a datos tabulares: cada
  feature es un token que se atiende entre sí.
- **GA (algoritmo genético)**: metaheurística evolutiva de población,
  cruza, mutación y selección; usado como comparación.
- **Gini**: medida de desigualdad de una distribución entre unidades
  (0 = igual, →1 = concentrado).
- **Golden Cluster**: el núcleo de alto uso: 102 estaciones en 61 AGEBs
  con ≥127.62 viajes/día (P85).
- **grafo**: nodos unidos por aristas; la red es un grafo de estaciones
  con enlaces de 500 m.
- **greedy (voraz)**: algoritmo que elige en cada paso la mejor opción
  inmediata; el optimizador del Motor 3.
- **GroupKFold**: validación cruzada que no parte grupos; el esquema por
  AGEB es la referencia optimista sin aislamiento espacial.
- **GTFS**: formato estándar de datos de transporte público (paradas,
  rutas, viajes, trazados).
- **hash**: huella digital de un archivo; prueba que el insumo no cambió.
- **hiperparámetro**: decisión de diseño fijada antes de entrenar
  (profundidad, semillas, w); aquí, fijados a priori.
- **I de Moran**: medida de autocorrelación espacial (−1 a 1); 0.4293 en
  la actividad.
- **imputación**: rellenar un valor faltante con un estimado; faltante
  no equivale a cero.
- **importancia por permutación**: cuánto sube el error al desordenar
  una variable; frágil con variables correlacionadas.
- **isócrona**: zona alcanzable caminando por la red vial real; el
  estudio usa buffers, no isócronas — límite declarado.
- **Jaccard**: solape entre conjuntos, |A∩B|/|A∪B|; compara portafolios.
- **K-Fold**: validación cruzada en k pliegues; la versión aleatoria es
  optimista con datos espaciales.
- **Ledoit-Wolf**: estimador de covarianza con encogimiento automático;
  estabiliza Σ⁻¹ con pocas observaciones.
- **MAE**: error absoluto medio de una regresión.
- **MAUP**: problema de la unidad areal modificable: los resultados
  dependen de cómo se divide el mapa; mitigado, no resuelto.
- **media**: promedio aritmético; sensible a extremos.
- **mediana**: valor central; robusta a extremos.
- **muestra**: subconjunto observado de la población.
- **NDCG@K**: métrica de ranking que premia acertar y ordenar bien
  (1.0 = perfecto).
- **nodo**: elemento del grafo; aquí, estación o sitio candidato.
- **Node2Vec**: método de embeddings de grafo por paseos aleatorios;
  retirado por no aportar (Spearman −0.095).
- **número de condición**: cuánto se amplifica el error al invertir una
  matriz; bajó de 33.5–54.9 a 2.26–6.44 con shrinkage.
- **Ockham (parsimonia)**: preferir el modelo más simple que sostiene el
  desempeño; la complejidad debe pagarse con resultados.
- **percentil**: cuantil en escala de cien; P85 = deja 85 % abajo.
- **portafolio**: conjunto de B sitios propuestos por un motor.
- **precisión@K**: fracción de aciertos entre los K primeros del ranking.
- **prescriptivo**: modelo que decide (optimiza un objetivo); el
  Motor 3 lo es — no predice, prescribe.
- **procedencia (provenance)**: registro del origen y transformación de
  cada variable.
- **proyección UTM**: aplanar la esfera para medir metros; EPSG:32614
  cubre la CDMX.
- **proxy**: variable que aproxima lo que no se midió directo (DENUE
  por actividad, escolaridad por nivel socioeconómico).
- **R²**: fracción de varianza explicada vs la media; negativo = peor
  que el modelo constante.
- **Random Forest**: bosque de árboles por bagging; modelo desplegado
  del Motor 2.
- **recall@K**: fracción de los relevantes capturados en el top K.
- **registro de afirmaciones**: tabla de cada afirmación del estudio con
  su cifra y fuente verificable.
- **regularización L2 (ridge)**: penalizar coeficientes grandes en una
  regresión lineal; control fuerte del Motor 2.
- **rendimientos decrecientes**: cada elemento añadido aporta menos que
  el anterior; base de la submodularidad.
- **retícula de candidatos**: malla de 250 m cuyos centros son los
  sitios candidatos (1,656).
- **RMSE**: raíz del error cuadrático medio; penaliza los errores
  grandes.
- **salto**: arista recorrida en el grafo; la afinidad usa saltos a la
  Golden más cercana.
- **semilla aleatoria**: número que fija el azar del algoritmo; misma
  semilla = misma salida.
- **sesgo (estadístico)**: error sistemático por simplicidad del modelo;
  contrapeso de la varianza en el trade-off.
- **shrinkage**: ver encogimiento.
- **sobreajuste**: memorizar el ruido del entrenamiento; bien en casa,
  mal fuera.
- **submodularidad**: propiedad de beneficios marginales decrecientes;
  hace al greedy defendible en cobertura.
- **target**: la variable a predecir u ordenar; aquí, actividad media
  por estación de la AGEB.
- **trade-off sesgo-varianza**: reducir el error por simplicidad vs por
  complejidad; equilibrio central del aprendizaje.
- **universo de evaluación**: las 242 AGEBs elegibles para evaluar
  (proyectables, con servicio, no candidatas).
- **validación cruzada espacial**: pliegues de bloques contiguos con
  buffer; el esquema honesto con datos espaciales.
- **varianza**: dispersión alrededor de la media (promedio de desviaciones
  al cuadrado).
- **Ward**: clustering aglomerativo que fusiona minimizando varianza;
  con conectividad produce bloques contiguos.

---

## Preguntas trampa

### Datos y ETL

**"¿Por qué AGEB y no manzana o alcaldía?"**
Porque es la unidad censal urbana de mayor resolución con geometría y
atributos consistentes; se fijó como soporte declarado, y su costo (MAUP)
está reconocido.

**"¿Limpiaste datos a mano?"**
No: toda fila excluida está en cuarentena con su causa (p. ej., 1,360 de
20.1 millones de viajes); la limpieza son reglas de contrato, no edición.

**"¿Por qué EPSG:32614 y no lat/lon?"**
Porque las reglas son en metros (enlace 500 m, separación 300 m, buffers);
lat/lon mide grados y los metros por grado varían. UTM 14N proyecta a
metros sobre la CDMX.

**"¿El DENUE mide demanda?"**
No: es un proxy de actividad económica (462,732 unidades). Se declara
proxy, no medida de demanda.

**"¿El catálogo de 677 prueba que todas operaban en 2025?"**
No: es un snapshot; el reporte lo declara explícitamente y no se usa como
evidencia de actividad.

### Validación

**"¿Tu validación espacial resuelve el MAUP?"**
No. El arnés de Ward + buffer ataca la *fuga espacial* (train y test
pegados); el MAUP se mitiga fijando la AGEB y declarando el soporte, sin
demostrar invariancia bajo otras zonificaciones. Son problemas distintos.

**"¿Por qué no K-Fold normal como todos?"**
Porque con autocorrelación espacial (Moran 0.43) mezcla vecinos entre
pliegues y el error queda optimista: el esquema por grupos lo muestra —
0.356 de RMSE aparente contra 0.429 espacial.

**"¿El buffer de 500 m garantiza independencia?"**
Garantiza lo medido: cero pares colindantes y 500.6 m mínimos; no afirmo
eliminar dependencia a mayor distancia.

**"¿El umbral P85 se ajustó con todo el conjunto?"**
No: se ajusta por pliegue solo con las filas de entrenamiento retenidas;
usar todo el conjunto sería fuga en la etiqueta.

**"¿Por qué media por estación y no total de viajes por AGEB?"**
Porque la suma crece con cuántas estaciones haya (Spearman del target con
número de estaciones: solo 0.1787 con la media); la media mide la
intensidad que se quiere replicar.

**"¿Por qué incluyes un esquema que te hace ver peor?"**
El esquema por grupos es la referencia optimista declarada: distancia
mínima 0.0 m y pares colindantes que no bajan (220, 232). Reportarlo es
honestidad, no torpeza.

### Motor 1

**"¿Las cargas del PCA son efectos causales?"**
No: son coeficientes de una rotación. La escolaridad carga +0.409 en PC1
porque ese eje resume el gradiente socioeconómico, no porque cause nada.

**"¿Por qué coseno y no euclidiana?"**
Por el perfil, no la magnitud — y por evidencia: la variante euclidiana
quedó en 0.18 de precisión@10 frente a 0.38 del coseno.

**"¿Fuera de dominio significa sitio malo?"**
No: significa fuera de la envolvente estadística del Golden. Abstenerse
en ellas es declarar que no se sabe, no condenarlas.

**"¿Por qué no la covarianza cruda?"**
Con n/p ≈ 2 su inversa es inestable; Ledoit-Wolf la hace utilizable
(condición 14.32 → 4.97 en el diseño; 33.5–54.9 → 2.26–6.44 por pliegue).

**"¿Tu ranking no es solo 'poner estaciones en zonas ricas'?"**
En parte sí —ese es el hallazgo: el puntaje correlaciona con escolaridad
(Spearman 0.7213) y el Motor 1 replica el sesgo. Documentarlo es el
punto, no ocultarlo.

### Motor 2

**"¿Por qué descartaste el modelo más moderno (Transformer)?"**
Porque no cumplió el dictamen: no bajó del mejor control (ridge), ganó
3/5 pliegues frente a 4 exigidos, y su mejora neta (−0.0010) fue ~30
veces menor que la variación entre semillas (0.0313).

**"¿Por qué Random Forest y no ridge, que tuvo mejor RMSE medio?"**
Concedo el dato: ridge 0.4195 vs RF 0.4288 —una brecha de 0.0092 y ridge
es lineal. El punto central es que ni el modelo de máxima capacidad logró
ventaja reproducible; el despliegue privilegió un modelo no lineal
estable y simple de operar, no el RMSE mínimo absoluto.

**"¿El modelo constante sirve de algo?"**
Sí: es el piso. Que rinda R² = −0.3028 espacial muestra que ni siquiera
la media ayuda fuera de la vecindad — el problema es duro.

**"¿La importancia por permutación dice qué causa la demanda?"**
No: mide qué usa el modelo, no qué causa el fenómeno, y con variables
correlacionadas reparte importancia entre ellas.

**"¿Tuneaste los hiperparámetros hasta que gustara?"**
No: se fijaron a priori y el reporte lo declara; las semillas múltiples
{0–4} miden el azar, no se escogen a mano.

### Motor 3

**"¿Por qué el Motor 3 no tiene backtest?"**
Porque es prescriptivo: no predice ninguna cantidad, ejecuta un objetivo
declarado. El Motor 1 y el Motor 2 sí se validan contra datos escondidos.

**"¿El greedy es óptimo?"**
No se afirma: es determinista, ~3,200× más rápido que el GA y mejor en
los tres presupuestos (B=15/30/50). La submodularidad del objetivo es la
defensa teórica.

**"¿La afinidad a Golden prueba que tu portafolio quedó conectado?"**
Esa métrica está optimizada por construcción —la afinidad es parte del
objetivo—, así que no es evidencia independiente; lo que sí es evidencia
externa es la población cubierta y el perfil socioeconómico.

**"¿Por qué 500 metros de enlace?"**
Dos razones: es la distancia caminable operativa declarada, y es el
umbral donde la red deja de fragmentarse —a 500 m forma una sola
componente con las 102 Golden (a 300 m son 195 componentes).

**"¿Node2Vec era peor o solo más caro?"**
Peor para lo que se necesitaba: su afinidad no ordenaba por cercanía al
núcleo (Spearman −0.095, resultado histórico) y añadía complejidad sin
cambiar la decisión.

**"¿GA y greedy difiriendo es un problema?"**
No: con valor parecido y Jaccard variable (0.875 en una configuración,
0.111 en otra) indica muchas soluciones casi equivalentes — un paisaje
favorable, no inestabilidad.

### Resultados y alcance

**"¿Motor 3 es mejor que Motor 1 porque cubre más?"**
No es comparación de desempeño predictivo: optimizan objetivos distintos.
El estudio documenta el trade-off —cobertura y equidad frente a dominio—,
no un ganador universal.

**"¿El Gini de 0.93 prueba que el sur no tiene servicio?"**
No: el Gini mide concentración de conteos por AGEB, no acceso per cápita
ni demanda. Es la motivación descriptiva del estudio, no una prueba.

**"¿Los 310,288 habitantes son usuarios nuevos seguros?"**
No: es población nueva potencialmente cubierta según el Censo 2020,
estimada como unión de celdas de 200 m. Es población, no conteo de viajes
ni de adopción.

**"¿La similitud del coseno implica que esas zonas rendirán como el Golden?"**
No: mide coincidencia de perfiles, no un mecanismo causal. Es una regla de
priorización transparente, no una promesa de uso.

**"¿El estudio dice cuánto costará la expansión?"**
No: el presupuesto es en número de estaciones (B); no hay modelo de
costos, flota ni rebalanceo — alcance declarado.

**"¿Puedo replicar tu portafolio?"**
Sí: el contrato de factibilidad, las semillas y los portafolios están
sellados; todo es determinista dado el diseño.

**"¿Tu hipótesis podía salir falsa?"**
Sí: afirma que el diseño con conectividad cubre más y elige zonas de
menor nivel; si el Motor 3 hubiera cubierto menos o elegido zonas más
ricas, la hipótesis caía. "Es posible que" no podía fallar —por eso no
se usa.

**"¿Demuestras que la expansión funcionará?"**
No: demuestro que el portafolio optimiza el objetivo declarado con
validación honesta donde aplica. La prueba de funcionamiento es posterior
a la implementación — trabajo futuro declarado.

**"¿Por qué consenso 18 y no 4?"**
Porque 18 sitios fueron elegidos por al menos dos motores y 4 por los
tres; los 4 están dentro de los 18. El consenso reporta la robustez de
la coincidencia, no el mejor sitio único.

---

## Guion de presentación

Cómo contar el proyecto en 10 minutos: diez bloques, cada uno con su
mensaje y la cifra que lo respalda.

1. **El problema (1 min).** "La red está muy concentrada." Cifras: 243 de
   2,452 AGEBs con estación; Gini 0.9296; ~7.97 millones fuera de
   cobertura.
2. **La pregunta y la hipótesis (1 min).** Leerlas tal cual; recalcar que
   la hipótesis puede fallar — "es posible" no serviría.
3. **Los datos y su disciplina (1 min).** "Más de 20 millones de viajes,
   cinco fuentes, contratos con cuarentena y hash." Cifra: 20,134,900
   filas, 1,360 en cuarentena.
4. **Por qué la validación es espacial (1.5 min).** "La ciudad se parece
   a sí misma (Moran 0.43): un K-Fold aleatorio mentiría." Cifras: 15
   bloques Ward, buffer 500 m, pares colindantes [95…59] → [0…0];
   el esquema optimista infla el RMSE aparente a 0.356 vs 0.429 real.
5. **Motor 1 — el espejo (1 min).** "Replicar el éxito es replicar el
   sesgo." Cifras: precisión@10 0.38 con abstención honesta (cobertura
   0.901); Spearman puntaje–escolaridad 0.7213.
6. **Motor 2 — el medidor honesto (1.5 min).** "Probamos capacidad
   máxima y la parsimonia ganó." Cifras: FT 0.4206 vs ridge 0.4195,
   mejora −0.0010 vs ruido 0.0313; RF desplegado con RMSE 0.4288.
7. **Motor 3 — el arquitecto (1.5 min).** "No predice: optimiza
   cobertura + conectividad (w = 0.5)." Cifras: greedy 310,288
   habitantes en 0.016 s vs GA 305,090 en 51.4 s; umbral 500 m = una
   sola componente.
8. **El trade-off (1 min).** "Ningún motor gana en todo." Cifras: escolaridad
   13.02 / 11.83 / 11.64 vs 12.23 del universo; dominio 0.30 / 0.23 /
   0.57; Jaccard M1–M3 = 0.091.
9. **La respuesta a la hipótesis (30 s).** "Apoyada: a igual B, la
   conectividad en el objetivo cubre +108 mil habitantes y elige zonas
   de menor nivel; el consenso de 18 sitios es la primera fase robusta."
10. **Límites y cierre (30 s).** "Declarados, no escondidos: censo 2020,
    MAUP mitigado, buffers no isócronas, asociación no causalidad, Motor
    3 sin backtest. La prueba final es posterior a la construcción."



