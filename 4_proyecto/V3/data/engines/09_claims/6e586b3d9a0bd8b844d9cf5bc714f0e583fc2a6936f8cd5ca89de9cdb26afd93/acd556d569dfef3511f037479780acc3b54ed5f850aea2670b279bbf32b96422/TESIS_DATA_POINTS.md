# TESIS_DATA_POINTS — registro de afirmaciones con fuente

Documento generado mecánicamente desde el registro sellado `v3-claims-1` (analysis_id `acd556d569dfef3511f037479780acc3b54ed5f850aea2670b279bbf32b96422`). Cada cifra lleva en el registro la ruta JSON de su fuente; este texto solo las formatea. Nada aquí es demanda observada: las cifras de cobertura son población dentro de áreas de captura de 500 m con interpolación areal.

## 1. Cobertura poblacional por motor y presupuesto

A B=30: el Motor 1 cubre 202,337 habitantes nuevos en 21 AGEBs, el Motor 2 282,102 en 25 y el Motor 3 310,288 en 28, siempre bajo el mismo contrato de despliegue y sin techos por AGEB. Respecto a la publicación previa con techos, los portafolios B=30 de los motores 1 y 2 crecieron +48,528 y +6,159 habitantes: el aumento proviene de retirar un tope que el backtest no validó, no de un método mejor. Es población en captura, no demanda observada, y las diferencias son entre portafolios heurísticos sin prueba estadística.

| Motor | B | Población nueva | % pobl. | AGEBs | 1/2/3+ |
|---|---|---|---|---|---|
| Motor 1 | 15 | 113,528 | 1.42% | 10 | 8/1/1 |
| Motor 2 | 15 | 136,490 | 1.71% | 12 | 10/1/1 |
| Motor 3 | 15 | 166,731 | 2.09% | 14 | 13/1/0 |
| Motor 1 | 30 | 202,337 | 2.54% | 21 | 15/5/1 |
| Motor 2 | 30 | 282,102 | 3.54% | 25 | 21/3/1 |
| Motor 3 | 30 | 310,288 | 3.89% | 28 | 26/2/0 |
| Motor 1 | 50 | 300,803 | 3.78% | 33 | 20/11/2 |
| Motor 2 | 50 | 428,401 | 5.38% | 41 | 33/7/1 |
| Motor 3 | 50 | 481,554 | 6.04% | 46 | 42/4/0 |

Los portafolios divergen territorialmente: a B=30 el Jaccard de sitios es 0.176 (M1–M2), 0.091 (M1–M3) y 0.250 (M2–M3), y de AGEBs 0.150, 0.089 y 0.262; 18 sitios aparecen en al menos 2 motores y 4 en los 3. La divergencia es descriptiva: los objetivos difieren por diseño.

## 2. Navaja de Ockham

**Motor 3 — greedy frente a GA.** Con la misma función objetivo y las mismas reglas de factibilidad, en la configuración primaria (w=0.5, B=30) el greedy toma 0.016 s por corrida frente a 51.4 s por semilla del GA (3,193x; rango emparejado 2,786x–4,422x entre configuraciones). Los totales no emparejados —greedy 0.123 s en una pasada por configuración, GA 1,302.6 s en 3–5 semillas por configuración— no definen un cociente. En el objetivo, el greedy iguala o supera a la mejor corrida del GA en 7 de 7 configuraciones: en 5 configuraciones la ventaja del greedy excede la variación entre semillas del GA; en 2 la diferencia es menor que esa variación (empate práctico); el GA nunca supera al greedy; la mejor corrida del GA queda entre 0.0009 y 0.0158 por debajo del greedy en la función objetivo. Es un hallazgo empírico: la garantía (1−1/e) de cobertura submodular no aplica formalmente bajo contigüidad y espaciamiento, y el GA es una heurística sin garantía de optimalidad.

**Motor 2 — modelos tabulares.** En el esquema espacial primario el RMSE medio es 0.5444 (constante), 0.4195 (ridge), 0.4288 (bosque aleatorio) y 0.4206 (FT-Transformer). Frente al mejor control (Ridge) el Transformer no mejora: su diferencia de RMSE es de +0.0010 a favor de Ridge, que equivale a 0.033 veces la variación entre semillas (0.0313). Ridge tiene el RMSE medio más bajo por esa diferencia mínima, pero el FT-Transformer muestra R² (0.215 vs 0.194) y Spearman (0.585 vs 0.531) ligeramente superiores: ninguno de los dos domina; el resultado es un empate práctico y la complejidad del Transformer no se justifica. El dictamen mecánico lo retira del despliegue y el bosque aleatorio se despliega por parsimonia y estabilidad, no por superioridad acreditada: RF vs Ridge difiere en +0.0092 de RMSE medio con R² espacial ≤ ~0.22 en todos los modelos.

## 3. Certificación del arnés espacial

El esquema primario `fold_spatial_block` deja 0 pares colindantes prueba–entrenamiento tras el buffer de 500 m en los 5 folds (antes del buffer: [95, 57, 59, 50, 59]); la distancia mínima retenida es 500.6 m y los 15 bloques forman un solo componente de adyacencia (1) con contigüidad 1.00. El conteo fue recomputado de forma independiente desde los artefactos publicados y coincide con el reporte. La garantía es sobre colindancia poligonal (≤1 m) y buffer de 500 m; no descarta autocorrelación espacial a mayor distancia.

## 4. Otros hallazgos de método

- **Ledoit-Wolf (Motor 1):** con n/p de 2.00–2.56 el encogimiento (0.38–0.70) lleva el número de condición de 33–55 a 2.26–6.44 y la cobertura de decisión de 0.637 a 0.901; el NDCG@10 (0.673) no cambia respecto al coseno sin compuerta. El umbral chi-cuadrado es nominal bajo encogimiento.
- **Remoción del techo por análogos:** en 05 el análogo pierde en MAE (1.678 vs 1.256) y en Spearman (0.274 vs 0.307); en 06 pierde en MAE (1.438 vs 1.256) aunque su Spearman queda marginalmente por encima (0.312 vs 0.307). Reproduce densidad histórica de planeación, no demanda observada.
- **Retiro de Node2Vec:** la afinidad por embeddings no ordenaba por cercanía al núcleo (histórico v3-motor3-3, no recalculado: Spearman con −saltos -0.095 / -0.095 con q=0.5; razón de norma del centroide 0.735). La afinidad vigente es determinista, 1/(1+saltos a Golden), y por ello la cercanía a Golden del portafolio está optimizada por construcción —no es evidencia independiente—.
- **Tensión similitud–equidad:** a B=30 la escolaridad media de las AGEBs seleccionadas es 13.02 (M1), 11.83 (M2) y 11.64 (M3) frente a 12.23 en todos los sitios; la fracción fuera del dominio del 04 es 0.30 / 0.23 / 0.57. Son covariables ecológicas de AGEB, sin lectura causal.

## 5. Salvedades que deben acompañar cada cifra

- (C01, C02) Población dentro de áreas de captura de 500 m con interpolación areal; no es demanda observada
- (C01, C02) Los motores 1 y 2 ya no usan techos por AGEB
- (C01, C02) El Motor 3 optimiza afinidad por saltos a Golden; sus métricas de cercanía están por construcción
- (C01, C02) Diferencias entre portafolios heurísticos a presupuesto fijo, sin prueba estadística
- (C03) Jaccard descriptivo sobre conjuntos de sitios y de AGEBs; sin umbral de 'alto/bajo' declarado
- (C03) Los objetivos de los motores difieren por diseño
- (C04) Covariables a nivel AGEB (lectura ecológica), sin causalidad
- (C04) Fuera de dominio no implica mal sitio: el dominio del 04 es el soporte de AGEBs con servicio
- (C04) La semejanza a entornos afluentes no es demanda
- (C05) Tiempos de pared de una sola máquina y una sola medición por configuración
- (C05) Speedup emparejado por configuración (misma f y mismas reglas); los totales no emparejados se reportan aparte y no definen un cociente
- (C05) El GA corre con los parámetros publicados del 07 (población 80, 120 generaciones)
- (C06) La garantía (1-1/e) de cobertura submodular no aplica formalmente bajo contigüidad y espaciamiento; es un hallazgo empírico, no un teorema
- (C06) El GA es una heurística sin garantía de optimalidad (3-5 semillas por configuración)
- (C06) El resultado depende de los parámetros GA declarados en el 07
- (C07) R^2 espacial <= ~0.22 en todos los modelos: ninguno es predictivamente fuerte
- (C07) RF vs Ridge es una diferencia pequeña (RF gana en 3 de 5 folds)
- (C07) 5 folds espaciales; variación entre semillas del Transformer documentada como caso de estudio
- (C07) La importancia predictiva no es causalidad
- (C08) La garantía es sobre colindancia poligonal (<=1 m) y buffer de 500 m en el universo de AGEBs evaluadas; no implica ausencia de autocorrelación espacial a mayores distancias.
- (C09) El umbral chi-cuadrado es nominal bajo encogimiento: las distancias de entrenamiento no son exactamente chi
- (C09) ndcg_cond > ndcg indica abstención en casos difíciles y se lee junto con decision_coverage
- (C09) No hay mejora de NDCG@10 respecto al coseno sin compuerta
- (C10) El backtest del techo es evidencia de la remoción, no una regla de asignación activa
- (C10) En 06 el Spearman del análogo queda marginalmente por encima del baseline aunque el MAE es peor; el resultado no se simplifica a 'perdió en todo'
- (C11) Los números citados son de la publicación histórica v3-motor3-3 (analysis_id 69a83e61…); no se recalculan
- (C11) La nueva afinidad 1/(1+saltos) es determinista pero hace que la cercanía a Golden esté optimizada por construcción
- (C11) La afinidad estructural no es demanda ni evidencia causal
- (C12) La consistencia verifica reproducibilidad de métricas publicadas; no valida los supuestos del contrato

### Límites registrados por los cuadernos 04–08

Citados textualmente de los reportes publicados (en inglés).

- [validation] Engine rankings themselves (cuadernos 05/06/07)
- [validation] Sensitivity of in_domain to the Mahalanobis quantile
- [validation] Sensitivity of metrics to the label quantile
- [validation] Alternative NDCG gains (binary vs linear vs log)
- [validation] Buffer distance sensitivity (500 m declared)
- [motor1] Sensitivity of deployment ranking to domain/reference quantiles beyond one-at-a-time
- [motor2] Analog-ceiling backtest is removal evidence, not an active allocation rule
- [motor2] Capacity study says nothing about latent demand
- [motor2] RF is the deployment model by parsimony, not by proven dominance; no model is predictively strong
- [motor2] Deployment predictions are extrapolation outside the observed activity scale
- [motor3] Affinity is a deterministic function of hops to the golden core: golden-proximity portfolio metrics are optimized by construction and are not independent evidence
- [motor3] Structural affinity is proximity to the golden core, not observed demand
- [motor3, comparacion] Areal interpolation and 500 m catchments are assumptions, not observed demand
- [motor3, comparacion] No street network, cost, or field validation
- [motor3] The GA is a heuristic without optimality guarantee; its best run is published only as a sensitivity portfolio
- [comparacion] Comparison is descriptive: no aggregate winner is declared
- [comparacion] Radar area is not a score; axes encode different objectives
- [comparacion] Motor 3 optimizes golden-hop affinity directly: its proximity-to-golden metrics are by construction, not independent evidence
- [comparacion] Motors 1 and 2 dropped analog ceilings; their portfolios changed relative to the previous publications
- [comparacion] Motor 3 has no AGEB backtest: its score is structural affinity, not an activity model

## 6. Procedencia

Registro `v3-claims-1` · contrato `6e586b3d9a0bd8b844d9cf5bc714f0e583fc2a6936f8cd5ca89de9cdb26afd93` · puntero `audits/09_final_claims_registry.json` · analysis_id del registro (hash de identidad de contenido): `acd556d569dfef3511f037479780acc3b54ed5f850aea2670b279bbf32b96422`.

| Cuaderno | Esquema | analysis_id |
|---|---|---|
| 01_ETL_Reproducible.ipynb | — | `sin analysis_id` |
| 02_EDA_y_Equidad.ipynb | v3-eda-2 | `d77ab12f05e9025f438921b34e8688e1a75628262964277af62250cdbafa8e67` |
| 03_Feature_Engineering.ipynb | v3-features-2 | `7565adda3bc4eb91514247d2a1213f0b1c934821e762ac9d3aae010031dbb05c` |
| 04_Diseno_Validacion_Backtest.ipynb | v3-backtest-4 | `ed7bf47bafab10ca2b3144e9d38f1d06e5024ee9ba6af353b37603324ad2ab32` |
| 05_Motor1_Baseline_Estadistico.ipynb | v3-motor1-3 | `879ae45d46b56fc5504c9817be154eee0e78ab0e13ddfdcef4435a58d32de29d` |
| 06_Motor2_Transformer_Honesto.ipynb | v3-motor2-3 | `4027385dff30ab79689dfdeb3c468260176080e83b1abd21f5c605efcce30a8f` |
| 07_Motor3_Grafo_y_Genetico.ipynb | v3-motor3-4 | `3aa53121add31f2ea2381259d0b44fa7f603fa758b4a731dcc08fd143b074b87` |
| 08_Evaluacion_Comparativa.ipynb | v3-comparacion-2 | `fdba0469ee4d2a42ce8bc5f75d53e95930207bfe3152faad5fbedd6ddc790f69` |
