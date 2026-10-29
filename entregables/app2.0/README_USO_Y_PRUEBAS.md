# Planeador de expansión EcoBici · CDMX

Herramienta para decidir **dónde poner estaciones nuevas de EcoBici** a partir
de la red que exista en cada momento. Se usa desde el navegador, sin
instalar nada y sin conexión a internet.

## Contenido de esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `planeador_expansion_ecobici.html` | **La aplicación.** Es un solo archivo; es lo único indispensable. |
| `README_USO_Y_PRUEBAS.md` | Esta guía. |
| `bases_prueba/` | Cuatro redes de ejemplo en CSV para probar la aplicación (ver «Redes de prueba»). |

## Inicio rápido (1 minuto)

1. Haz doble clic en `planeador_expansion_ecobici.html`. Se abre en el
   navegador; no necesita internet. Se probó en Chrome; debería funcionar en
   las versiones recientes de Edge, Firefox y Safari.
2. Elige un motor (por ejemplo **Motor 3**) y un presupuesto B (por ejemplo
   **30** estaciones). El mapa y la tabla se calculan solos.
3. Pasa el cursor por un punto del mapa para ver su ficha, o descarga el plan
   con **[Descargar Plan CSV]**.

Con la red base 2025, el Motor 1 y B = 30 debe dar **202,337** habitantes
nuevos cubiertos, y aparece una insignia verde que lo certifica.

## Qué hace la aplicación

Propone ubicaciones para nuevas estaciones usando tres métodos distintos
(los mismos de la tesis) y permite:

- partir de la red actual de 2025 o de **tu propia red** (archivo CSV);
- pedir de **1 a 100** estaciones;
- repartirlas en **hasta 5 etapas** con colores distintos (por ejemplo,
  Año 1, Año 2, Año 3);
- **fijar** sitios que quieres sí o sí, **vetar** sitios y **excluir
  alcaldías**;
- dar por **construida** una etapa y seguir planeando sobre la red ampliada;
- comparar los tres motores («★ Consenso»);
- guardar el escenario, exportar resultados e imprimir un reporte.

### Los tres motores, en una línea

| Motor | Idea | Se interpreta como |
|---|---|---|
| **Motor 1** | Zonas parecidas a las exitosas | Busca AGEBs con perfil similar al de las zonas donde EcoBici ya funciona mejor. |
| **Motor 2** | Zonas donde se espera mucha actividad | Usa una predicción de actividad (Random Forest) por AGEB. |
| **Motor 3** | Red conectada que cubre más gente | Equilibra población nueva cubierta con qué tan cerca queda cada sitio de la zona exitosa, siguiendo la red. |
| **★ Consenso** | Comparar los tres | Corre los tres al mismo presupuesto y marca los sitios en los que coinciden. |

## Guía de la pantalla

### Panel izquierdo (controles)

1. **Red actual.** *Red base 2025* usa las 677 estaciones reales. *Subir mi
   archivo CSV* permite usar otra red (formato abajo). **[Descargar CSV de
   ejemplo]** baja un archivo pequeño con el formato correcto. Al cargar un
   archivo, la aplicación muestra un diagnóstico: cuántas filas son válidas,
   cuáles se descartaron y por qué, y cuántas AGEBs quedan ocupadas.
2. **Motor.** Cuatro botones (Motor 1, Motor 2, Motor 3, ★ Consenso). Bajo
   ellos hay una frase que explica el motor elegido.
3. **Restricciones.**
   - *Alcaldías incluidas*: desmarca las alcaldías que no quieres considerar.
   - **Fijar / vetar**: haz clic sobre un sitio en el mapa y elige
     **📌 Fijar como obligatoria** o **🚫 Vetar sitio**. Debajo se lleva la
     cuenta (`Fijados · Vetados`) y **[Limpiar]** quita todo.
4. **Presupuesto y etapas.**
   - Un deslizador o un campo numérico elige **B** (de 1 a 100).
   - **Etapas**: con **−** y **+** eliges de 1 a 5 etapas. Cada una tiene una
     etiqueta que puedes editar (por ejemplo «Año 1») y una cuota de
     estaciones. La aplicación avisa en rojo si las cuotas no suman B (por
     ejemplo, «faltan 5»). **Si hay varias etapas, el plan usa la suma de las
     cuotas**; ajusta las cuotas hasta ver «✓ suma = B».
   - **Cortar el orden** o **Recursivo** (botón **?** con la explicación).
     Ver «Etapas: los dos modos».
5. **Simulación temporal.** Elige una etapa y pulsa **[Marcar etapa como
   construida]**: sus estaciones pasan a formar parte de la red actual y se
   vuelven grises. **[Calcular plan]** fuerza un recálculo (normalmente no
   hace falta: el plan se actualiza solo al cambiar un parámetro).

En la barra superior están **[Guardar escenario (.json)]**, **[Cargar
escenario]** e **[Imprimir / Exportar PDF]**.

### Panel derecho (resultados)

- **Mapa de decisión.** Gris: estaciones actuales. Dorado: las del Golden
  Cluster (zona de mayor actividad). Círculos de color con número: sitios
  propuestos, un color por etapa y su orden de selección. Rueda del ratón o
  pellizco para acercar, arrastrar para mover; **⌂** encuadra la red y las
  propuestas, **◱** muestra toda la CDMX. En **Capas** puedes activar:
  Metro y Metrobús (568 paradas), ciclovías, población sin cubrir, lazos de
  conexión (línea punteada de cada sitio nuevo a la estación a la que se
  conecta), radios de captura de 500 m y sitios candidatos (apagada al inicio
  para no saturar el mapa).
- **Resumen.** Población nueva cubierta (cada habitante cuenta una sola vez,
  aunque lo cubran varias estaciones), sitios entregados de B,
  escolaridad media del portafolio, porcentaje de sitios fuera del dominio de
  los modelos y el desglose por etapa. Incluye la gráfica de
  **rendimientos decrecientes** (población acumulada contra número de
  estación) y los avisos de la aplicación.
- **Sitios del plan.** Tabla con etapa, orden, ID del sitio, alcaldía, AGEB,
  población nueva marginal, estación a la que se conecta, distancia a la red,
  escolaridad de la AGEB y si está dentro del dominio. Se puede filtrar y
  ordenar.
- **Exportar:** **[Descargar Plan CSV]**, **[Descargar GeoJSON]** y
  **[Descargar Red Actualizada CSV]** (la red activa más lo marcado como
  construido; sirve para volver a cargarla después).

## Cómo leer los resultados

- **Población nueva cubierta**: habitantes (Censo 2020) que viven a menos de
  500 m de algún sitio propuesto y que antes no estaban cubiertos por ninguna
  estación. Se calcula sobre celdas de 200 m, sin contar dos veces a nadie.
- **Pob. nueva marginal** (tabla): lo que aporta cada sitio en el momento en
  que se elige, dado lo que ya cubrían los anteriores. Por eso los primeros
  sitios aportan más y la gráfica se aplana.
- **Conectado a**: la estación existente o el sitio previo del plan al que
  queda enlazado (a 500 m o menos). Todo sitio nuevo debe poder crecer desde
  la red existente.
- **Escolaridad media**: años promedio de escolaridad de las AGEBs elegidas.
  Se compara con el promedio de todos los sitios candidatos (12.23 en la red
  base): un portafolio muy por encima sugiere que el motor favorece zonas más
  acomodadas.
- **Fuera de dominio**: porcentaje de sitios en AGEBs muy distintas de las que
  vieron los modelos al calibrarse; en ellas la predicción es menos confiable.
- **Razón de paro**: si se entregan menos sitios que B, la aplicación explica
  por qué (ya no hay sitios factibles conectados, o los restantes no aportan
  población nueva). No inventa sitios para completar.

## Etapas: los dos modos

- **Cortar el orden.** El motor se corre una sola vez para B estaciones y la
  lista ordenada se parte por cuotas (las primeras N son la etapa 1, etc.).
- **Recursivo.** La etapa 1 se calcula primero; se incorpora temporalmente a la
  red; la etapa 2 se calcula sobre la red ya ampliada, y así hasta la última.
  En los Motores 1 y 2 da exactamente el mismo portafolio que cortar el orden.
  En el Motor 3 puede diferir, porque la cercanía a la zona exitosa se
  recalcula en cada etapa.
- Las etapas son un **orden de prioridad de construcción**, no un pronóstico
  de tiempo: la aplicación no estima costos, demanda futura ni calendarios.
  Las etiquetas («Año 1»…) las pones tú.
- **[Marcar etapa como construida]** es distinto: es permanente en la sesión.
  Los sitios pasan a ser estaciones y su AGEB queda ocupada (ya no se
  proponen más sitios en ella). Úsalo para simular «ya se construyó la etapa 1,
  ¿qué sigue?»; después puedes descargar la **Red Actualizada** y volver a
  cargarla otro día.

## Formato del archivo de estaciones (CSV)

Cabecera: `latitud,longitud,nombre,id` (coordenadas decimales WGS84).
`nombre` e `id` son opcionales. También se aceptan los nombres de columna
`lat`, `lon`, `latitude`, `longitude` y `lng`, y el separador `;`.

```
latitud,longitud,nombre,id
19.433785,-99.167987,"CE-001 Río Sena-Río Balsas",292
```

La aplicación descarta y reporta, con la fila exacta: coordenadas vacías o no
numéricas, filas duplicadas (mismo `id` o mismas coordenadas) y estaciones
fuera de la CDMX. Además indica en cuántos grupos conectados (a 500 m) se
divide la red y avisa si la red cargada **no tiene ninguna estación del Golden
Cluster** (en ese caso el Motor 3 optimiza solo cobertura).

## Qué significa la insignia verde

Con la **red base 2025**, un motor individual, sin restricciones manuales y
B = 15, 30 o 50, el plan debe coincidir sitio por sitio y en el mismo orden
con el portafolio publicado en el análisis de la tesis. Cuando coincide aparece
«✓ Coincide exactamente con el análisis sellado de la tesis (Registro 09)»:

| Motor | B=15 | B=30 | B=50 |
|---|---|---|---|
| Motor 1 | 113,528 | 202,337 | 300,803 |
| Motor 2 | 136,490 | 282,102 | 428,401 |
| Motor 3 | 166,731 | 310,288 | 481,554 |

(población nueva cubierta, en habitantes). La insignia **no** aparece con otro
presupuesto (p. ej. B = 40), con una red subida —aunque sea idéntica a la
base—, con etapas ya construidas, ni con sitios fijados, vetados o alcaldías
excluidas: en todos esos casos el portafolio ya no es el publicado.

En **★ Consenso** con B = 30 sobre la red base debe verse
**«≥2: 18 · 3: 4»**: 18 sitios propuestos por al menos dos motores, de los
cuales 4 son propuestos por los tres (los 4 están incluidos en los 18). A
B = 15 son 9 y 3, y a B = 50 son 32 y 6.

## Redes de prueba (`bases_prueba/`)

Las estaciones con prefijo `SIM-` son **simuladas para prueba, no reales**.
Cada demostración toma 3–5 minutos: en el paso 1 elige *Subir mi archivo CSV*,
selecciona el archivo y revisa el diagnóstico.

### 01 · `01_red_base_2025_canonica.csv` — la red base como archivo

Las 677 estaciones reales de 2025. Sirve para comprobar que la carga
reproduce la red integrada. Debe verse: **677 válidas · 0 descartadas · 1
grupo conectado · 243 AGEBs ocupadas · 1,656 sitios elegibles**. Con el Motor 1
y B = 30 se obtienen **202,337 hab** y el mismo portafolio que con la red
base, aunque sin insignia verde (la insignia solo certifica la red integrada).

### 02 · `02_red_expandida_oriente_conectada.csv` — red ampliada al oriente

Las 677 reales más 25 estaciones simuladas `SIM-E##` en una cadena contigua
hacia el oriente (Iztacalco / Venustiano Carranza / norte de Iztapalapa), cada
una a menos de 500 m de la anterior. Debe verse: **702 válidas · 1 grupo ·
264 AGEBs ocupadas · 1,851 sitios elegibles**. Con B = 30: Motor 1
**217,490 hab**, Motor 2 **264,764 hab**, Motor 3 **302,777 hab**; el
consenso cambia a **≥2: 17 · 3: 6**. Observa que ninguna propuesta cae a menos
de 300 m de una estación ni en una AGEB ya ocupada: la zona oriente ya cubierta
se esquiva y las nuevas propuestas se mueven hacia otras fronteras.

### 03 · `03_red_semilla_sur_coyoacan.csv` — red pequeña sin Golden

80 estaciones reales del sur (Coyoacán / Benito Juárez sur) en un solo grupo
conectado y **sin ninguna estación Golden**: simula una red local que quiere
crecer. Debe verse: **80 válidas · 1 grupo · 31 AGEBs ocupadas · 212 AGEBs
liberadas sin puntaje (excluidas) · 429 elegibles** y el aviso «sin Golden en
la red». Con B = 30: Motor 1 entrega **20 sitios** (115,441 hab) y explica que
los restantes no aportan población nueva con puntaje positivo; Motor 2 entrega
30 (215,928 hab); Motor 3 entrega 30 (269,015 hab), optimizando solo
cobertura.

### 04 · `04_red_estres_validador_errores.csv` — prueba del validador

60 filas: 50 estaciones reales válidas (un grupo conectado en la frontera este
de la red, Cuauhtémoc / Benito Juárez) y 10 filas defectuosas a propósito.
Debe reportar **50 válidas · 10 descartadas**: **3 fuera de la CDMX, 2
coordenadas vacías, 1 NaN / no numérica, 2 id duplicado, 2 coordenadas
duplicadas**, con las primeras filas rechazadas y un enlace «ver todas». La red
válida queda en **1 grupo · 25 AGEBs ocupadas · 218 AGEBs liberadas sin puntaje
· 352 sitios elegibles · 1 conectado inicialmente**. Con B = 30 los tres motores
entregan el presupuesto completo: Motor 1 **178,618 hab**, Motor 2
**258,302 hab**, Motor 3 **267,479 hab**; consenso **≥2: 25 · 3: 6**.


## Límites que conviene conocer

- **Los motores no se reentrenan en el navegador.** El Golden Cluster y las
  predicciones corresponden a la calibración con datos de 2025, y la población
  al Censo 2020. Las estaciones nuevas no tienen viajes registrados, así que no
  modifican la calibración.
- **La validación geográfica** de «fuera de la CDMX» usa el polígono formado
  por las AGEBs urbanas del análisis más un margen de 1 km; no se dispone de
  una capa estatal oficial en los datos.
- **No hay costos ni presupuesto en pesos:** B es solo un número de
  estaciones. Tampoco se estima el tamaño de la flota ni la demanda futura.
- **Anclas (📌):** un sitio fijado entra primero en el portafolio y cuenta
  dentro de B. Si no es factible (queda desconectado de la red o a menos de
  300 m de otra estación o sitio), la aplicación lo reporta en «Anclas no
  factibles» en lugar de forzarlo.
- **El Consenso no usa etapas:** cada motor corre al presupuesto B completo.
- Los sitios son candidatos para **validar en campo**; no sustituyen un
  estudio de factibilidad de calle.
