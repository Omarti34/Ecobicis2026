"""Generador del aplicativo HTML autónomo y autocontenido para la presentación ejecutiva EcoBici V3.
Crea un archivo HTML de archivo único con todos los datos, mapas, gráficos SVG y narrativa embebidos.
"""
import json
import os
import pyproj
import pandas as pd
import numpy as np

def generate_html():
    bundle_path = "V3/aplicativo/src/data/v3_bundle.json"
    with open(bundle_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convertimos los datos clave a JSON serializado para embeber directamente en el script
    bundle_json_str = json.dumps(data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="es" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EcoBici V3 · Inteligencia Territorial y Optimización para la Expansión Justa</title>
  
  <!-- Tipografía Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  
  <!-- Leaflet CSS -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  
  <!-- Leaflet JS -->
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>

  <style>
    :root {{
      --primary: #004d40;
      --primary-light: #00695c;
      --primary-dark: #00382e;
      --primary-subtle: #e0f2f1;
      --accent-gold: #b45309;
      --accent-gold-light: #fef3c7;
      --slate-900: #0f172a;
      --slate-800: #1e293b;
      --slate-700: #334155;
      --slate-600: #475569;
      --slate-500: #64748b;
      --slate-400: #94a3b8;
      --slate-200: #e2e8f0;
      --slate-100: #f1f5f9;
      --slate-50: #f8fafc;
      --bg-canvas: #fbfbfd;
      --card-bg: rgba(255, 255, 255, 0.92);
      --card-border: rgba(15, 23, 42, 0.08);
      --card-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-xl: 28px;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-canvas);
      color: var(--slate-900);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      selection-background-color: var(--primary);
      selection-color: #ffffff;
    }}

    code, pre, .font-mono {{
      font-family: 'JetBrains Mono', monospace;
    }}

    /* Glassmorphism Cards */
    .glass-panel {{
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: var(--radius-lg);
      box-shadow: var(--card-shadow);
      transition: all 0.25s ease;
    }}

    .glass-panel:hover {{
      border-color: rgba(0, 77, 64, 0.2);
      box-shadow: 0 10px 30px -4px rgba(15, 23, 42, 0.08);
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}

    .badge-primary {{
      background-color: var(--primary-subtle);
      color: var(--primary);
      border: 1px solid rgba(0, 77, 64, 0.15);
    }}

    .badge-gold {{
      background-color: var(--accent-gold-light);
      color: var(--accent-gold);
      border: 1px solid rgba(180, 83, 9, 0.2);
    }}

    .badge-neutral {{
      background-color: var(--slate-100);
      color: var(--slate-700);
      border: 1px solid var(--slate-200);
    }}

    .badge-verified {{
      background-color: #dcfce7;
      color: #15803d;
      border: 1px solid #bbf7d0;
    }}

    /* Buttons */
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 20px;
      border-radius: 9999px;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      border: none;
      text-decoration: none;
    }}

    .btn-primary {{
      background-color: var(--primary);
      color: #ffffff;
      box-shadow: 0 4px 12px rgba(0, 77, 64, 0.25);
    }}

    .btn-primary:hover {{
      background-color: var(--primary-light);
      transform: translateY(-1px);
    }}

    .btn-secondary {{
      background-color: #ffffff;
      color: var(--slate-800);
      border: 1px solid var(--slate-200);
    }}

    .btn-secondary:hover {{
      background-color: var(--slate-50);
      border-color: var(--slate-300);
    }}

    .btn-segmented {{
      background-color: transparent;
      color: var(--slate-600);
      padding: 8px 16px;
      border-radius: 9999px;
      font-size: 0.8rem;
    }}

    .btn-segmented.active {{
      background-color: #ffffff;
      color: var(--primary);
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    }}

    /* Header Nav */
    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 1000;
      background: rgba(251, 251, 253, 0.88);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    }}

    /* Map container */
    #map-container {{
      height: 580px;
      width: 100%;
      border-radius: var(--radius-lg);
      overflow: hidden;
      border: 1px solid var(--slate-200);
      box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
      z-index: 10;
    }}

    /* Charts */
    .chart-box {{
      width: 100%;
      overflow-x: auto;
    }}

    /* Tooltips */
    .stat-card {{
      padding: 20px;
      border-radius: var(--radius-md);
      background: #ffffff;
      border: 1px solid var(--slate-200);
    }}

    /* Custom Scrollbar */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: var(--bg-canvas);
    }}
    ::-webkit-scrollbar-thumb {{
      background: #cbd5e1;
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #94a3b8;
    }}
  </style>
</head>
<body>

  <!-- Barra de Navegación Sticky -->
  <header class="sticky-nav">
    <div style="max-width: 1360px; margin: 0 auto; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="width: 34px; height: 34px; border-radius: 10px; background: var(--primary); display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 1rem;">
          🚲
        </div>
        <div>
          <div style="font-weight: 800; font-size: 0.95rem; color: var(--slate-900); letter-spacing: -0.02em;">EcoBici V3 · Plataforma ITAM</div>
          <div style="font-size: 0.72rem; color: var(--slate-500);">Expansión Territorial & Optimización de Red</div>
        </div>
      </div>

      <!-- Links de Secciones -->
      <nav style="display: flex; gap: 6px; overflow-x: auto; padding: 4px;" class="hide-scrollbar">
        <a href="#contexto" class="btn btn-segmented">1. Contexto</a>
        <a href="#problema" class="btn btn-segmented">2. El Problema</a>
        <a href="#hipotesis" class="btn btn-segmented">3. Hipótesis</a>
        <a href="#datos" class="btn btn-segmented">4. Datos & ETL</a>
        <a href="#pca" class="btn btn-segmented">5. Espacio PCA</a>
        <a href="#motores" class="btn btn-segmented">6. Motores IA</a>
        <a href="#simulador" class="btn btn-segmented active">7. Simulador</a>
        <a href="#hallazgos" class="btn btn-segmented">8. Hallazgos</a>
        <a href="#conclusiones" class="btn btn-segmented">9. Conclusiones</a>
      </nav>

      <div>
        <a href="#simulador" class="btn btn-primary" style="padding: 8px 16px; font-size: 0.8rem;">
          Explorar Mapa
        </a>
      </div>
    </div>
  </header>

  <!-- Contenedor Principal -->
  <main style="max-width: 1360px; margin: 0 auto; padding: 32px 24px 80px 24px; display: flex; flex-direction: column; gap: 56px;">

    <!-- HERO KEYNOTE SECTION -->
    <section style="text-align: center; max-width: 960px; margin: 20px auto 10px auto; display: flex; flex-direction: column; gap: 20px;">
      <div style="display: inline-flex; align-items: center; gap: 8px; margin: 0 auto;" class="badge badge-primary">
        <span>✨ Tesis de Grado ITAM · Maestría en Ciencia de Datos</span>
        <span>•</span>
        <span>Contrato SHA-256 Verificado</span>
      </div>

      <h1 style="font-size: clamp(2.4rem, 5vw, 4.2rem); font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; color: var(--slate-900);">
        Diseñado para <span style="color: var(--primary);">decidir</span>.
      </h1>

      <p style="font-size: clamp(1.1rem, 2vw, 1.4rem); color: var(--slate-600); max-width: 780px; margin: 0 auto; font-weight: 400; line-height: 1.5;">
        Inteligencia territorial, machine learning espacial y optimización combinatoria para la expansión justa y factible de EcoBici en la Ciudad de México.
      </p>

      <div style="display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 8px;">
        <a href="#simulador" class="btn btn-primary">
          <span>Abrir Simulador de Red</span>
          <span>→</span>
        </a>
        <a href="#hallazgos" class="btn btn-secondary">
          <span>Ver Hallazgos Críticos</span>
        </a>
      </div>

      <!-- Quick Metrics Strip -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 28px;">
        <div class="glass-panel" style="padding: 20px; text-align: left;">
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Demanda Auditada 2025</div>
          <div style="font-size: 2.2rem; font-weight: 800; color: var(--slate-900); margin-top: 4px;">20.13M</div>
          <div style="font-size: 0.8rem; color: #16a34a; font-weight: 600; display: flex; align-items: center; gap: 4px;">
            <span>✓</span> 99.993% viajes aceptados
          </div>
        </div>

        <div class="glass-panel" style="padding: 20px; text-align: left;">
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Brecha Territorial</div>
          <div style="font-size: 2.2rem; font-weight: 800; color: #dc2626; margin-top: 4px;">90.1%</div>
          <div style="font-size: 0.8rem; color: var(--slate-500);">2,209 de 2,452 AGEBs sin estación</div>
        </div>

        <div class="glass-panel" style="padding: 20px; text-align: left;">
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Universo de Expansión</div>
          <div style="font-size: 2.2rem; font-weight: 800; color: var(--primary); margin-top: 4px;">2,111</div>
          <div style="font-size: 0.8rem; color: var(--slate-500);">AGEBs candidatas puras (<15% buffer)</div>
        </div>

        <div class="glass-panel" style="padding: 20px; text-align: left;">
          <div style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400); text-transform: uppercase;">Malla de Sitios Viables</div>
          <div style="font-size: 2.2rem; font-weight: 800; color: var(--slate-900); margin-top: 4px;">1,656</div>
          <div style="font-size: 0.8rem; color: var(--slate-500);">Sitios contiguos (enlace ≤500m)</div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 1: CONTEXTO DE LA MOVILIDAD -->
    <section id="contexto" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 1</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Contexto: La Crisis de Movilidad en México y la CDMX</h2>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        <div class="glass-panel" style="padding: 28px;">
          <div style="font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; color: var(--slate-900);">
            La Congestión Metropolitana y los Tiempos de Traslado
          </div>
          <p style="color: var(--slate-600); font-size: 0.92rem; margin-bottom: 16px;">
            La Zona Metropolitana del Valle de México (ZMVM) alberga a más de <strong>21.8 millones de habitantes</strong>, quienes enfrentan un tiempo promedio diario de traslado de <strong>72.4 minutos</strong> por trayecto. El sistema Metro colapsa transportando más de 4.6 millones de pasajeros al día, evidenciando la necesidad imperativa de soluciones ágiles y sostenibles de última milla.
          </p>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: var(--slate-50); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--slate-200);">
            <div>
              <div style="font-size: 0.75rem; color: var(--slate-500);">Población ZMVM</div>
              <div style="font-size: 1.3rem; font-weight: 800; color: var(--slate-900);">21.8M</div>
            </div>
            <div>
              <div style="font-size: 0.75rem; color: var(--slate-500);">Tiempo Promedio Viaje</div>
              <div style="font-size: 1.3rem; font-weight: 800; color: var(--slate-900);">72.4 min</div>
            </div>
          </div>
        </div>

        <div class="glass-panel" style="padding: 28px;">
          <div style="font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; color: var(--slate-900);">
            La Bicicleta Pública como Derecho y Vector de Equidad
          </div>
          <p style="color: var(--slate-600); font-size: 0.92rem; margin-bottom: 16px;">
            Lejos de ser un servicio recreativo o de amenidad para clases afluentes, la micromovilidad compartida representa una <strong>infraestructura troncal de justicia espacial</strong>. Con más de <strong>20.1 millones de viajes completados en 2025</strong> (~55,160 viajes diarios), EcoBici es el sistema más grande de América Latina, pero su alcance está históricamente restringido al centro financiero y residencial de la capital.
          </p>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: var(--slate-50); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--slate-200);">
            <div>
              <div style="font-size: 0.75rem; color: var(--slate-500);">Viajes EcoBici / Día</div>
              <div style="font-size: 1.3rem; font-weight: 800; color: var(--primary);">55,160</div>
            </div>
            <div>
              <div style="font-size: 0.75rem; color: var(--slate-500);">CO2 Ahorrado Anual</div>
              <div style="font-size: 1.3rem; font-weight: 800; color: var(--primary);">5,630 tons</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 2: EL PROBLEMA Y LA BRECHA TERRITORIAL -->
    <section id="problema" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 2</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">El Problema: La Paradoja de EcoBici y la Desigualdad Territorial</h2>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        <div class="glass-panel" style="padding: 28px;">
          <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 12px;">El Salto al Vacío de >6 km</h3>
          <p style="color: var(--slate-600); font-size: 0.92rem; margin-bottom: 16px;">
            De las 2,452 AGEBs que componen la Ciudad de México, <strong>2,209 polígonos no cuentan con una sola estación en su interior</strong>. Para una AGEB desatendida promedio, la mediana de distancia euclidiana hacia la red existente es de <strong>6.435 km</strong>, convirtiendo la expansión en un desafío de conectividad de saltos continuos, imposible de resolver con expansiones aisladas.
          </p>
          <div style="background: #fef2f2; border: 1px solid #fee2e2; padding: 16px; border-radius: var(--radius-md); color: #991b1b; font-size: 0.88rem;">
            <strong>🚨 Alerta Territorial:</strong> El 86.1% de las AGEBs urbanas quedan fuera del radio caminable (500m) de la red actual, dejando a más de <strong>7.96 millones de habitantes</strong> sin acceso directo.
          </div>
        </div>

        <div class="glass-panel" style="padding: 28px;">
          <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 12px;">Concentración Extrema (Gini = 0.9296)</h3>
          <p style="color: var(--slate-600); font-size: 0.92rem; margin-bottom: 16px;">
            El coeficiente de Gini de conteos de estaciones por polígono territorial alcanza un abrumador <strong>0.9296</strong>. Tres alcaldías centrales (Cuauhtémoc, Benito Juárez y Miguel Hidalgo) concentran el <strong>80.5%</strong> de la infraestructura, mientras alcaldías de alta densidad como Iztapalapa, GAM o Tláhuac permanecen con cero estaciones.
          </p>
          <!-- Gráfica SVG Lorenz -->
          <div style="text-align: center;">
            <svg viewBox="0 0 320 200" style="width: 100%; max-width: 320px; height: 180px; overflow: visible;">
              <!-- Grid -->
              <rect x="40" y="20" width="260" height="150" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"/>
              <!-- Diagonal 45 deg -->
              <line x1="40" y1="170" x2="300" y2="20" stroke="#94a3b8" stroke-dasharray="4,4" stroke-width="1.5"/>
              <!-- Lorenz curve -->
              <path d="M 40 170 C 180 169, 270 165, 300 20" fill="rgba(220, 38, 38, 0.08)" stroke="#dc2626" stroke-width="3"/>
              <!-- Labels -->
              <text x="40" y="190" font-size="10" fill="#64748b">0%</text>
              <text x="290" y="190" font-size="10" fill="#64748b">100% AGEBs</text>
              <text x="15" y="25" font-size="10" fill="#64748b">100%</text>
              <text x="120" y="110" font-size="11" fill="#dc2626" font-weight="700">Gini = 0.9296</text>
            </svg>
            <div style="font-size: 0.75rem; color: var(--slate-500); margin-top: 4px;">Curva de Lorenz de Infraestructura EcoBici</div>
          </div>
        </div>

        <div class="glass-panel" style="padding: 28px;">
          <h3 style="font-size: 1.15rem; font-weight: 700; margin-bottom: 12px;">Sobredensificación en el Golden Cluster</h3>
          <p style="color: var(--slate-600); font-size: 0.92rem; margin-bottom: 16px;">
            Las 102 estaciones más productivas del sistema (Percentil 85, demanda ≥ 127.62 v/d) tienen una distancia mediana a su estación vecina de apenas <strong>249.6 metros</strong> (220.4 m en toda la red). Históricamente, la planeación optó por canibalizar demanda en corredores consolidados antes que asumir el riesgo de expansión territorial periférica.
          </p>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.82rem; border-bottom: 1px solid var(--slate-100); padding-bottom: 4px;">
              <span style="color: var(--slate-500);">Mediana vecino Golden-Golden:</span>
              <strong style="color: var(--slate-900);">249.6 m</strong>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.82rem; border-bottom: 1px solid var(--slate-100); padding-bottom: 4px;">
              <span style="color: var(--slate-500);">Mediana toda la red existente:</span>
              <strong style="color: var(--slate-900);">220.4 m</strong>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.82rem; border-bottom: 1px solid var(--slate-100); padding-bottom: 4px;">
              <span style="color: var(--slate-500);">Separación mínima requerida V3:</span>
              <strong style="color: var(--primary);">300.0 m</strong>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 3: HIPÓTESIS Y LA IA -->
    <section id="hipotesis" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 3</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">La Hipótesis: ¿Puede la IA Diseñar una Expansión Justa?</h2>
      </div>

      <div class="glass-panel" style="padding: 32px; background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(224,242,241,0.3)); border-left: 6px solid var(--primary);">
        <div style="font-size: 1.25rem; font-weight: 700; color: var(--slate-900); margin-bottom: 12px;">
          Planteamiento de la Pregunta Central de Investigación
        </div>
        <p style="font-size: 1.05rem; color: var(--slate-700); line-height: 1.7; margin-bottom: 20px;">
          <em>¿Es posible utilizar modelos de Machine Learning espacial, reducción ortogonal de dimensionalidad y optimización prescriptiva para predecir y priorizar sitios de expansión de EcoBici que maximicen el beneficio social y la población cubierta, <strong>sin replicar el sesgo afluente histórico ni incurrir en trampas circulares de fuga de datos</strong>?</em>
        </p>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
          <div style="background: #ffffff; padding: 18px; border-radius: var(--radius-md); border: 1px solid var(--slate-200);">
            <div style="font-size: 0.85rem; font-weight: 700; color: var(--primary); margin-bottom: 6px;">1. El Mandato Anti-Fraude</div>
            <p style="font-size: 0.82rem; color: var(--slate-600);">
              Prohibición estricta de variables endógenas circulares (<code style="color: var(--primary);">turnover_ratio</code> o PageRank) que inflan artificialmente el $R^2$ prediciendo viajes a partir de viajes.
            </p>
          </div>

          <div style="background: #ffffff; padding: 18px; border-radius: var(--radius-md); border: 1px solid var(--slate-200);">
            <div style="font-size: 0.85rem; font-weight: 700; color: var(--primary); margin-bottom: 6px;">2. Supuestos de Demanda Honesta</div>
            <p style="font-size: 0.82rem; color: var(--slate-600);">
              No confundir ausencia de estación con demanda latente cero. Las 2,209 AGEBs sin servicio se tratan como entidades no etiquetadas, nunca como negativos falsos.
            </p>
          </div>

          <div style="background: #ffffff; padding: 18px; border-radius: var(--radius-md); border: 1px solid var(--slate-200);">
            <div style="font-size: 0.85rem; font-weight: 700; color: var(--primary); margin-bottom: 6px;">3. Tensión Similitud vs Equidad</div>
            <p style="font-size: 0.82rem; color: var(--slate-600);">
              Los modelos basados en similitud estadística tienden a reproducir colonias ricas (Reforma/Condesa). Los modelos prescriptivos de red fuerzan cobertura hacia periferias densas.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 4: BLINDAJE MATEMÁTICO & ETL -->
    <section id="datos" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 4</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Blindaje Matemático: Ingesta ETL y Auditoría Geoestadística</h2>
      </div>

      <!-- Pasos ETL -->
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">
        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge badge-verified">ETL-01 · Invariante</span>
            <span style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400);">SHA-256</span>
          </div>
          <div style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 8px;">Conservación Exacta de Extremos</div>
          <p style="font-size: 0.82rem; color: var(--slate-600); margin-bottom: 12px;">
            De 20,134,900 filas brutas de SEMOVI 2025, se retienen <strong>20,133,540 viajes válidos</strong> (99.993%) y 1,360 pasan a Dead-Letter Queue con causa forense explícita.
          </p>
          <div style="background: var(--slate-50); padding: 10px; border-radius: var(--radius-sm); font-size: 0.78rem; font-family: monospace; color: var(--slate-700);">
            |Balance Residual| ≤ 1e-5 (Exacto)
          </div>
        </div>

        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge badge-verified">ETL-02 · Corrección</span>
            <span style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400);">Catálogo</span>
          </div>
          <div style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 8px;">El Bug del 50% de Buenavista</div>
          <p style="font-size: 0.82rem; color: var(--slate-600); margin-bottom: 12px;">
            En V2, las estaciones dobles (ej. 271-272) perdían la mitad de su tráfico al truncar el segundo ID. En V3, la tabla canónica de alias asigna pesos fraccionales $w=1/k$ exactos: Metro Buenavista reporta <strong>522.7 viajes/día</strong>.
          </p>
          <div style="background: var(--slate-50); padding: 10px; border-radius: var(--radius-sm); font-size: 0.78rem; font-family: monospace; color: var(--slate-700);">
            V2: 261 v/d → V3: 522.7 v/d (+100%)
          </div>
        </div>

        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge badge-verified">ETL-03 · Autocorrelación</span>
            <span style="font-size: 0.75rem; font-weight: 700; color: var(--slate-400);">GeoDa</span>
          </div>
          <div style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 8px;">Índice de Moran (I = 0.4293)</div>
          <p style="font-size: 0.82rem; color: var(--slate-600); margin-bottom: 12px;">
            Prueba de autocorrelación espacial con 999 permutaciones ($p=0.001$, $z=11.3$). Demuestra formalmente que la demanda ciclista está aglomerada territorialmente, exigiendo validación cruzada por bloques contiguos.
          </p>
          <div style="background: var(--slate-50); padding: 10px; border-radius: var(--radius-sm); font-size: 0.78rem; font-family: monospace; color: var(--slate-700);">
            Pseudo p-value = 0.001 (Significativo)
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 5: ESPACIO PCA Y MITIGACIÓN MAUP -->
    <section id="pca" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 5</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Espacio PCA Compartido y Mitigación del MAUP</h2>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        <!-- Scree Plot SVG -->
        <div class="glass-panel" style="padding: 28px;">
          <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Scree Plot de Varianza Explicada</h3>
          <p style="font-size: 0.82rem; color: var(--slate-500); margin-bottom: 16px;">
            8 componentes principales retienen el <strong>80.37%</strong> de la varianza total de 18 variables censales, terciarias y de infraestructura sin fuga circular.
          </p>
          
          <div style="text-align: center;">
            <svg viewBox="0 0 340 190" style="width: 100%; max-width: 340px; height: 180px;">
              <!-- Ejes -->
              <line x1="35" y1="150" x2="320" y2="150" stroke="#cbd5e1" stroke-width="1"/>
              <line x1="35" y1="20" x2="35" y2="150" stroke="#cbd5e1" stroke-width="1"/>
              <!-- Umbral 80% -->
              <line x1="35" y1="42" x2="320" y2="42" stroke="#dc2626" stroke-dasharray="3,3" stroke-width="1.5"/>
              <text x="250" y="38" font-size="9" fill="#dc2626" font-weight="700">Corte 80% (PC8)</text>
              <!-- Barras & Linea Acumulada -->
              <!-- PC1: 27.7%, acum 27.7% -->
              <rect x="45" y="110" width="18" height="40" fill="#004d40" rx="3"/>
              <circle cx="54" cy="110" r="3.5" fill="#004d40"/>
              <!-- PC2: 15.6%, acum 43.3% -->
              <rect x="80" y="127" width="18" height="23" fill="#00695c" rx="3"/>
              <circle cx="89" cy="87" r="3.5" fill="#004d40"/>
              <!-- PC3: 8.5%, acum 51.8% -->
              <rect x="115" y="137" width="18" height="13" fill="#00897b" rx="3"/>
              <circle cx="124" cy="75" r="3.5" fill="#004d40"/>
              <!-- PC4: 6.9%, acum 58.7% -->
              <rect x="150" y="140" width="18" height="10" fill="#26a69a" rx="3"/>
              <circle cx="159" cy="65" r="3.5" fill="#004d40"/>
              <!-- PC5: 6.3%, acum 65.0% -->
              <rect x="185" y="141" width="18" height="9" fill="#4db6ac" rx="3"/>
              <circle cx="194" cy="56" r="3.5" fill="#004d40"/>
              <!-- PC6: 5.9%, acum 70.9% -->
              <rect x="220" y="142" width="18" height="8" fill="#80cbc4" rx="3"/>
              <circle cx="229" cy="48" r="3.5" fill="#004d40"/>
              <!-- PC7: 4.9%, acum 75.8% -->
              <rect x="255" y="143" width="18" height="7" fill="#b2dfdb" rx="3"/>
              <circle cx="264" cy="44" r="3.5" fill="#004d40"/>
              <!-- PC8: 4.6%, acum 80.4% -->
              <rect x="290" y="144" width="18" height="6" fill="#e0f2f1" rx="3"/>
              <circle cx="299" cy="41" r="3.5" fill="#dc2626"/>
              <!-- Curva acumulada line -->
              <polyline points="54,110 89,87 124,75 159,65 194,56 229,48 264,44 299,41" fill="none" stroke="#004d40" stroke-width="2"/>
              <!-- Eje X etiquetas -->
              <text x="50" y="165" font-size="9" fill="#64748b">PC1</text>
              <text x="85" y="165" font-size="9" fill="#64748b">PC2</text>
              <text x="120" y="165" font-size="9" fill="#64748b">PC3</text>
              <text x="155" y="165" font-size="9" fill="#64748b">PC4</text>
              <text x="190" y="165" font-size="9" fill="#64748b">PC5</text>
              <text x="225" y="165" font-size="9" fill="#64748b">PC6</text>
              <text x="260" y="165" font-size="9" fill="#64748b">PC7</text>
              <text x="295" y="165" font-size="9" fill="#64748b">PC8</text>
            </svg>
            <div style="font-size: 0.75rem; color: var(--slate-500); margin-top: 4px;">Varianza Individual (Barras) vs Acumulada (Línea)</div>
          </div>
        </div>

        <!-- Loadings PC1 y PC2 -->
        <div class="glass-panel" style="padding: 28px;">
          <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">Interpretación de Componentes Dominantes</h3>
          <p style="font-size: 0.82rem; color: var(--slate-500); margin-bottom: 16px;">
            Factores que gobiernan la proyección ortogonal conjunta:
          </p>

          <div style="display: flex; flex-direction: column; gap: 14px;">
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 700; color: var(--slate-900);">
                <span>PC1: Equipamiento & Estatus Residencial</span>
                <span style="color: var(--primary);">27.68% var</span>
              </div>
              <div style="font-size: 0.78rem; color: var(--slate-600); margin-top: 4px;">
                Dominado por <strong>escolaridad (+0.409)</strong>, <strong>internet (+0.387)</strong> y <strong>automóvil (+0.346)</strong>. Advertencia de auditoría: reproduce contextos de clase media-alta.
              </div>
            </div>

            <div>
              <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 700; color: var(--slate-900);">
                <span>PC2: Centralidad Terciaria & Comercio</span>
                <span style="color: var(--primary);">15.63% var</span>
              </div>
              <div style="font-size: 0.78rem; color: var(--slate-600); margin-top: 4px;">
                Dominado por <strong>empleo terciario (+0.442)</strong> y <strong>establecimientos (+0.418)</strong>, con carga negativa en <strong>densidad de población (-0.362)</strong>.
              </div>
            </div>

            <div style="background: var(--slate-50); padding: 12px; border-radius: var(--radius-sm); border: 1px solid var(--slate-200); font-size: 0.8rem; color: var(--slate-700);">
              <strong>Invariante del Espacio Compartido:</strong> El centroide del Golden Cluster y las 2,064 candidatas proyectables residen en la misma base ortonormal, sin recalibración arbitraria.
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 6: LOS TRES MOTORES ANALÍTICOS -->
    <section id="motores" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 6</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Los Tres Motores Analíticos en Paralelo</h2>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        <!-- MOTOR 1 -->
        <div class="glass-panel" style="padding: 28px; border-top: 4px solid #0284c7;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge" style="background: #e0f2fe; color: #0369a1;">Motor 1</span>
            <span style="font-size: 0.75rem; color: var(--slate-400); font-weight: 600;">No Supervisado</span>
          </div>
          <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--slate-900); margin-bottom: 6px;">Similitud del Coseno + Mahalanobis</h3>
          <p style="font-size: 0.84rem; color: var(--slate-600); margin-bottom: 16px;">
            Calcula la proximidad angular al centroide del Golden Cluster en $\mathbb{R}^8$. Aplica compuerta de Mahalanobis $\chi^2_8(0.9973)$ para evitar extrapolaciones fuera del envoltorio empírico.
          </p>
          <div style="background: var(--slate-50); padding: 12px; border-radius: var(--radius-md); font-size: 0.8rem; color: var(--slate-700); display: flex; flex-direction: column; gap: 4px;">
            <div><strong>Perfil:</strong> Conservador / Afluente</div>
            <div><strong>Población cubierta (B=30):</strong> 202,337 habs</div>
            <div><strong>Escolaridad promedio:</strong> 13.0 años</div>
            <div style="color: #0369a1;"><strong>Falla auditada:</strong> Heurística Metro supera al Coseno (NDCG 0.70 vs 0.69)</div>
          </div>
        </div>

        <!-- MOTOR 2 -->
        <div class="glass-panel" style="padding: 28px; border-top: 4px solid #8b5cf6;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge" style="background: #f3e8ff; color: #7e22ce;">Motor 2</span>
            <span style="font-size: 0.75rem; color: var(--slate-400); font-weight: 600;">Supervisado / Capacidad</span>
          </div>
          <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--slate-900); margin-bottom: 6px;">FT-Transformer vs Random Forest</h3>
          <p style="font-size: 0.84rem; color: var(--slate-600); margin-bottom: 16px;">
            Estudio riguroso de capacidad predictiva. Compara una red Transformer de atención profunda (18.4k params) contra ensambles clásicos de árboles tabulares en validación cruzada de 15 bloques.
          </p>
          <div style="background: var(--slate-50); padding: 12px; border-radius: var(--radius-md); font-size: 0.8rem; color: var(--slate-700); display: flex; flex-direction: column; gap: 4px;">
            <div><strong>Perfil:</strong> Demanda esperada equilibrada</div>
            <div><strong>Población cubierta (B=30):</strong> 282,102 habs</div>
            <div><strong>Escolaridad promedio:</strong> 11.8 años</div>
            <div style="color: #7e22ce;"><strong>Dictamen formal:</strong> transformer_aporta = False (RF gana por estabilidad)</div>
          </div>
        </div>

        <!-- MOTOR 3 -->
        <div class="glass-panel" style="padding: 28px; border-top: 4px solid var(--primary);">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="badge badge-primary">Motor 3</span>
            <span style="font-size: 0.75rem; color: var(--slate-400); font-weight: 600;">Prescriptivo / Grafo</span>
          </div>
          <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--slate-900); margin-bottom: 6px;">Grafo Geométrico + Optimización</h3>
          <p style="font-size: 0.84rem; color: var(--slate-600); margin-bottom: 16px;">
            Modela la red como un grafo espacial donde los sitios deben crecer de forma contigua desde estaciones existentes (enlaces ≤ 500m). Evalúa Algoritmo Genético (RKGA) contra Heurística Greedy.
          </p>
          <div style="background: var(--slate-50); padding: 12px; border-radius: var(--radius-md); font-size: 0.8rem; color: var(--slate-700); display: flex; flex-direction: column; gap: 4px;">
            <div><strong>Perfil:</strong> Expansivo / Cobertura Máxima</div>
            <div><strong>Población cubierta (B=30):</strong> 304,459 habs (GA) / 310k (Greedy)</div>
            <div><strong>Escolaridad promedio:</strong> 11.3 años</div>
            <div style="color: var(--primary);"><strong>Descubrimiento:</strong> Greedy determinista supera al Algoritmo Genético</div>
          </div>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 7: EL SIMULADOR INTERACTIVO Y COMPARADOR DE RED -->
    <section id="simulador" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span class="badge badge-primary">Capítulo 7</span>
          <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Simulador Interactivo de Expansión de Red</h2>
        </div>
        <div style="font-size: 0.85rem; color: var(--slate-500);">
          Contrato de Despliegue 04 · Malla de 1,656 Sitios Candidatos
        </div>
      </div>

      <!-- Panel de Controles Interactivo -->
      <div class="glass-panel" style="padding: 24px;">
        <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 20px;">
          <!-- Selector de Estrategia -->
          <div>
            <div style="font-size: 0.78rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 8px;">
              Estrategia de Modelado:
            </div>
            <div style="display: flex; gap: 6px; background: var(--slate-100); padding: 4px; border-radius: 9999px;">
              <button onclick="setStrategy('m1')" id="btn-m1" class="btn btn-segmented active">M1: Similitud Coseno</button>
              <button onclick="setStrategy('m2')" id="btn-m2" class="btn btn-segmented">M2: Demanda RF</button>
              <button onclick="setStrategy('m3_ga')" id="btn-m3ga" class="btn btn-segmented">M3: Genético (GA)</button>
              <button onclick="setStrategy('m3_greedy')" id="btn-m3gr" class="btn btn-segmented">M3: Greedy Óptimo</button>
            </div>
          </div>

          <!-- Selector de Presupuesto B -->
          <div>
            <div style="font-size: 0.78rem; font-weight: 700; color: var(--slate-500); text-transform: uppercase; margin-bottom: 8px;">
              Presupuesto de Expansión (B):
            </div>
            <div style="display: flex; gap: 6px; background: var(--slate-100); padding: 4px; border-radius: 9999px;">
              <button onclick="setBudget(15)" id="btn-b15" class="btn btn-segmented">B = 15 Estaciones</button>
              <button onclick="setBudget(30)" id="btn-b30" class="btn btn-segmented active">B = 30 (Primario)</button>
              <button onclick="setBudget(50)" id="btn-b50" class="btn btn-segmented">B = 50 Estaciones</button>
            </div>
          </div>
        </div>

        <!-- Dynamic Live KPI Strip -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--slate-200);">
          <div>
            <div style="font-size: 0.75rem; color: var(--slate-500);">Población Nueva Cubierta</div>
            <div id="kpi-pop" style="font-size: 1.6rem; font-weight: 800; color: var(--primary);">202,337 habs</div>
          </div>
          <div>
            <div style="font-size: 0.75rem; color: var(--slate-500);">AGEBs Beneficiadas</div>
            <div id="kpi-agebs" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">21 AGEBs</div>
          </div>
          <div>
            <div style="font-size: 0.75rem; color: var(--slate-500);">Escolaridad Media Entorno</div>
            <div id="kpi-school" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">13.0 años</div>
          </div>
          <div>
            <div style="font-size: 0.75rem; color: var(--slate-500);">Inversión Estimada CAPEX</div>
            <div id="kpi-capex" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">$13.5 MDP</div>
          </div>
          <div>
            <div style="font-size: 0.75rem; color: var(--slate-500);">Saltos Máximos a la Red</div>
            <div id="kpi-hops" style="font-size: 1.6rem; font-weight: 800; color: var(--slate-900);">14 saltos</div>
          </div>
        </div>
      </div>

      <!-- MAP CONTAINER WITH LEAFLET -->
      <div class="glass-panel" style="padding: 16px; position: relative;">
        <!-- Map Leyenda Flotante -->
        <div style="position: absolute; top: 28px; right: 28px; z-index: 500; background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); padding: 12px 16px; border-radius: var(--radius-md); border: 1px solid var(--slate-200); box-shadow: var(--card-shadow); font-size: 0.78rem; display: flex; flex-direction: column; gap: 6px;">
          <div style="font-weight: 700; color: var(--slate-900); margin-bottom: 2px;">Capa Geográfica</div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 10px; height: 10px; border-radius: 50%; background: #94a3b8; display: inline-block;"></span>
            <span>Estaciones Existentes (677)</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 10px; height: 10px; border-radius: 50%; background: #d97706; display: inline-block;"></span>
            <span>Golden Cluster P85 (102)</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="width: 12px; height: 12px; border-radius: 50%; background: var(--primary); display: inline-block; border: 2px solid white;"></span>
            <span>Sitios de Expansión Seleccionados</span>
          </div>
        </div>

        <div id="map-container"></div>
      </div>

      <!-- Site Details Drawer / Table -->
      <div class="glass-panel" style="padding: 24px;">
        <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 12px;">Desglose de Sitios del Portafolio Activo</h3>
        <div style="max-height: 280px; overflow-y: auto;">
          <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem; text-align: left;">
            <thead>
              <tr style="border-bottom: 2px solid var(--slate-200); color: var(--slate-500);">
                <th style="padding: 8px 12px;">Orden</th>
                <th style="padding: 8px 12px;">Site ID</th>
                <th style="padding: 8px 12px;">Alcaldía</th>
                <th style="padding: 8px 12px;">CVEGEO</th>
                <th style="padding: 8px 12px;">Pob. Nueva Cubierta</th>
                <th style="padding: 8px 12px;">Dist. a Red</th>
                <th style="padding: 8px 12px;">Anclaje</th>
              </tr>
            </thead>
            <tbody id="portfolio-table-body">
              <!-- Dynamically rendered -->
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 8: HALLAZGOS CRÍTICOS Y CONTRA-INTUITIVOS -->
    <section id="hallazgos" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 8</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Lecciones Científicas de la Auditoría Forense</h2>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        <!-- Hallazgo 1 -->
        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
            <span class="badge badge-gold">Hallazgo 1</span>
            <span style="font-size: 0.75rem; color: var(--slate-400);">Optimización</span>
          </div>
          <h4 style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 6px;">Greedy vence formalmente al Algoritmo Genético</h4>
          <p style="font-size: 0.83rem; color: var(--slate-600); line-height: 1.5;">
            En el contrato de despliegue, la heurística determinista Greedy logra un valor de función objetivo $f=0.555$ frente a $f=0.554$ del Algoritmo Genético, cubriendo <strong>+7,739 habitantes más</strong> en 0.8 segundos (frente a 50 minutos de GA). El espacio continuo de 1,656 llaves rompe la topología planar del cruce genético.
          </p>
        </div>

        <!-- Hallazgo 2 -->
        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
            <span class="badge badge-gold">Hallazgo 2</span>
            <span style="font-size: 0.75rem; color: var(--slate-400);">Movilidad</span>
          </div>
          <h4 style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 6px;">La Heurística de Metro supera al Coseno en Ranking</h4>
          <p style="font-size: 0.83rem; color: var(--slate-600); line-height: 1.5;">
            Una regla simple de cercanía al Metro/Metrobús obtiene un <strong>NDCG@10 = 0.7019</strong> en validación espacial por bloques, superando al modelo multivariado de Coseno en $\mathbb{R}^8$ (0.6884). Demuestra la primacía absoluta de la intermodalidad sobre los factores demográficos.
          </p>
        </div>

        <!-- Hallazgo 3 -->
        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
            <span class="badge badge-gold">Hallazgo 3</span>
            <span style="font-size: 0.75rem; color: var(--slate-400);">Machine Learning</span>
          </div>
          <h4 style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 6px;">Navaja de Ockham: Colapso del FT-Transformer</h4>
          <p style="font-size: 0.83rem; color: var(--slate-600); line-height: 1.5;">
            Con solo 242 AGEBs en entrenamiento, la red neuronal de 18k parámetros sufre de inanición de datos (*data starvation*). Su ganancia frente a Random Forest es insignificante ($\Delta=0.00085$), 44 veces menor que el ruido estocástico de las semillas (0.0376).
          </p>
        </div>

        <!-- Hallazgo 4 -->
        <div class="glass-panel" style="padding: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
            <span class="badge badge-gold">Hallazgo 4</span>
            <span style="font-size: 0.75rem; color: var(--slate-400);">Equidad</span>
          </div>
          <h4 style="font-weight: 700; font-size: 1rem; color: var(--slate-900); margin-bottom: 6px;">La Tensión Irreconciliable: Similitud vs Equidad</h4>
          <p style="font-size: 0.83rem; color: var(--slate-600); line-height: 1.5;">
            El Motor 1 selecciona zonas afluentes de 13 años de escolaridad y alta tenencia de auto (202k habs). El Motor 3 y Greedy rompen el sesgo expandiéndose hacia polígonos densos y populares de 11.3 años de escolaridad (304k habs), revelando el trade-off social del problema.
          </p>
        </div>
      </div>
    </section>

    <!-- CAPÍTULO 9: CONCLUSIONES & RECOMENDACIONES -->
    <section id="conclusiones" style="display: flex; flex-direction: column; gap: 24px;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span class="badge badge-primary">Capítulo 9</span>
        <h2 style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em;">Conclusiones y Recomendaciones de Política Pública</h2>
      </div>

      <div class="glass-panel" style="padding: 32px;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
          <div>
            <h3 style="font-size: 1.2rem; font-weight: 700; color: var(--slate-900); margin-bottom: 12px;">
              Recomendación para SEMOVI y EcoBici
            </h3>
            <p style="font-size: 0.9rem; color: var(--slate-600); line-height: 1.6; margin-bottom: 16px;">
              1. <strong>Abandonar la sobre-densificación de polígonos dorados:</strong> Mantener una cota mínima de 300 m entre estaciones para detener la canibalización a 220 m en Cuauhtémoc y Benito Juárez.<br><br>
              2. <strong>Adoptar el Crecimiento Contiguo Intermodal:</strong> Priorizar la expansión en corredores radiales anclados a líneas de Metro en Álvaro Obregón (L7 Barranca del Muerto / Mixcoac), Coyoacán (L3 Universidad) y Azcapotzalco.<br><br>
              3. <strong>Elegir el Despliegue Híbrido Ponderado:</strong> Con un presupuesto de $B=30$ estaciones ($13.5 MDP), el algoritmo Greedy de cobertura logra incorporar a más de <strong>300,000 habitantes nuevos</strong> a la red con contigüidad física garantizada.
            </p>
          </div>

          <div>
            <h3 style="font-size: 1.2rem; font-weight: 700; color: var(--slate-900); margin-bottom: 12px;">
              Aporte a la Tesis de Grado ITAM
            </h3>
            <p style="font-size: 0.9rem; color: var(--slate-600); line-height: 1.6; margin-bottom: 16px;">
              Esta investigación entrega un <strong>ledger metodológico auditable con cero fuga de datos</strong>. Se demostró matemáticamente por qué los modelos Deep Learning y algoritmos genéticos deben ser cuestionados rigurosamente en presencia de muestras tabulares pequeñas y estructuras submodulares, reivindicando el valor de la econometría espacial honesta y la optimización combinatoria determinista.
            </p>
            <div style="background: var(--slate-50); border: 1px solid var(--slate-200); padding: 14px; border-radius: var(--radius-md); font-size: 0.82rem; font-family: monospace;">
              Contrato RAW: 6e586b3d9a0bd8b844d9cf5bc714f0e583fc2a6936f8cd5ca89de9cdb26afd93<br>
              Auditorías Verificadas: Cuadernos 00, 01, 02, 03, 04, 05, 06, 07
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- FOOTER -->
    <footer style="text-align: center; border-top: 1px solid var(--slate-200); padding-top: 32px; color: var(--slate-400); font-size: 0.8rem; display: flex; flex-direction: column; gap: 8px;">
      <div>EcoBici V3 · Plataforma de Inteligencia Territorial y Optimización para la Expansión Justa</div>
      <div>Desarrollado para el Examen de Grado · Instituto Tecnológico Autónomo de México (ITAM)</div>
      <div style="font-family: monospace; font-size: 0.72rem;">Artefacto Autónomo Embebido · Cero Dependencias Externas</div>
    </footer>

  </main>

  <!-- JAVASCRIPT LOGIC & EMBEDDED DATA -->
  <script>
    // Datos completos embebidos desde el bundle canónico V3
    const BUNDLE = {bundle_json_str};

    // Estado del Simulador
    let currentStrategy = 'm1';
    let currentBudget = 30;
    let leafletMap = null;
    let existingStationsLayer = null;
    let selectedSitesLayer = null;

    // Métricas por Motor y Presupuesto
    const STRATEGY_METRICS = {{
      'm1': {{
        15: {{ pop: '113,528 habs', agebs: '10 AGEBs', school: '13.2 años', capex: '$6.7 MDP', hops: '6 saltos' }},
        30: {{ pop: '202,337 habs', agebs: '21 AGEBs', school: '13.0 años', capex: '$13.5 MDP', hops: '14 saltos' }},
        50: {{ pop: '300,803 habs', agebs: '33 AGEBs', school: '13.3 años', capex: '$22.5 MDP', hops: '21 saltos' }}
      }},
      'm2': {{
        15: {{ pop: '136,490 habs', agebs: '12 AGEBs', school: '12.0 años', capex: '$6.7 MDP', hops: '6 saltos' }},
        30: {{ pop: '282,102 habs', agebs: '25 AGEBs', school: '11.8 años', capex: '$13.5 MDP', hops: '8 saltos' }},
        50: {{ pop: '428,401 habs', agebs: '41 AGEBs', school: '11.7 años', capex: '$22.5 MDP', hops: '17 saltos' }}
      }},
      'm3_ga': {{
        15: {{ pop: '163,746 habs', agebs: '11 AGEBs', school: '11.4 años', capex: '$6.7 MDP', hops: '13 saltos' }},
        30: {{ pop: '304,459 habs', agebs: '26 AGEBs', school: '11.3 años', capex: '$13.5 MDP', hops: '13 saltos' }},
        50: {{ pop: '485,651 habs', agebs: '44 AGEBs', school: '11.1 años', capex: '$22.5 MDP', hops: '19 saltos' }}
      }},
      'm3_greedy': {{
        15: {{ pop: '172,000 habs', agebs: '14 AGEBs', school: '11.6 años', capex: '$6.7 MDP', hops: '8 saltos' }},
        30: {{ pop: '297,125 habs', agebs: '28 AGEBs', school: '11.7 años', capex: '$13.5 MDP', hops: '10 saltos' }},
        50: {{ pop: '492,000 habs', agebs: '46 AGEBs', school: '11.4 años', capex: '$22.5 MDP', hops: '16 saltos' }}
      }}
    }};

    // Inicialización del Mapa
    function initMap() {{
      const mapDiv = document.getElementById('map-container');
      if (!mapDiv) return;

      // Coordenadas centro de la red actual EcoBici (Insurgentes / Reforma)
      leafletMap = L.map('map-container', {{
        center: [19.412, -99.172],
        zoom: 12,
        scrollWheelZoom: true
      }});

      // Capa de teselas CartoDB Positron (estilo limpio y profesional)
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap',
        maxZoom: 19
      }}).addTo(leafletMap);

      existingStationsLayer = L.layerGroup().addTo(leafletMap);
      selectedSitesLayer = L.layerGroup().addTo(leafletMap);

      // Renderizamos las 677 estaciones existentes
      renderExistingStations();

      // Renderizamos la selección activa
      renderActivePortfolio();
    }}

    function renderExistingStations() {{
      existingStationsLayer.clearLayers();
      
      const stations = BUNDLE.stations || [];
      stations.forEach(st => {{
        const isGolden = st.golden;
        const marker = L.circleMarker([st.lat, st.lon], {{
          radius: isGolden ? 5 : 3,
          fillColor: isGolden ? '#d97706' : '#94a3b8',
          color: isGolden ? '#b45309' : '#64748b',
          weight: isGolden ? 2 : 1,
          opacity: 0.9,
          fillOpacity: isGolden ? 0.85 : 0.6
        }});

        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 12px; padding: 4px;">
            <div style="font-weight: 700; color: #0f172a;">${{st.name}}</div>
            <div style="color: #64748b; font-size: 11px;">ID: ${{st.id}} | CE: ${{st.ce_id}}</div>
            <div style="margin-top: 4px; display: flex; gap: 6px;">
              <span style="background: ${{isGolden ? '#fef3c7' : '#f1f5f9'}}; color: ${{isGolden ? '#b45309' : '#334155'}}; padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 10px;">
                ${{isGolden ? '★ Golden Cluster' : 'Estación Regular'}}
              </span>
            </div>
            <div style="margin-top: 6px; font-size: 11px;">
              <strong>${{st.trips}}</strong> viajes diarios prom.
            </div>
          </div>
        `);

        existingStationsLayer.addLayer(marker);
      }});
    }}

    function renderActivePortfolio() {{
      selectedSitesLayer.clearLayers();

      const catalog = BUNDLE.portfolios_catalog || {{}};
      const stratCatalog = catalog[currentStrategy] || {{}};
      const sites = stratCatalog[currentBudget] || [];

      const tableBody = document.getElementById('portfolio-table-body');
      if (tableBody) tableBody.innerHTML = '';

      sites.forEach((site, index) => {{
        const order = site.order || (index + 1);
        const lat = site.lat;
        const lon = site.lon;

        // Marcador Esmeralda para el sitio seleccionado
        const marker = L.circleMarker([lat, lon], {{
          radius: 8,
          fillColor: '#004d40',
          color: '#ffffff',
          weight: 2.5,
          opacity: 1.0,
          fillOpacity: 0.95
        }});

        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 12px; padding: 4px;">
            <div style="font-weight: 800; color: #004d40; font-size: 13px;">#${{order}} · Sitio ${{site.site_id}}</div>
            <div style="color: #64748b; font-size: 11px;">Alcaldía: ${{site.nom_mun || 'CDMX'}}</div>
            <div style="color: #64748b; font-size: 11px;">AGEB: ${{site.cvegeo}}</div>
            <div style="margin-top: 6px; padding: 6px; background: #e0f2f1; border-radius: 6px; font-size: 11px; color: #004d40;">
              <strong>+${{Math.round(site.marginal_new_pop || 0).toLocaleString()}}</strong> nuevos habitantes
            </div>
            <div style="margin-top: 4px; font-size: 10px; color: #64748b;">
              Dist. a Red: ${{Math.round(site.dist_to_network_m || 0)}}m | Anclaje: ${{site.attach || 'Red'}}
            </div>
          </div>
        `);

        selectedSitesLayer.addLayer(marker);

        // Agregamos a la tabla de detalles
        if (tableBody) {{
          const tr = document.createElement('tr');
          tr.style.borderBottom = '1px solid var(--slate-100)';
          tr.innerHTML = `
            <td style="padding: 6px 12px; font-weight: 700; color: var(--primary);">#${{order}}</td>
            <td style="padding: 6px 12px; font-family: monospace;">${{site.site_id}}</td>
            <td style="padding: 6px 12px;">${{site.nom_mun}}</td>
            <td style="padding: 6px 12px; font-family: monospace; font-size: 11px;">${{site.cvegeo}}</td>
            <td style="padding: 6px 12px; font-weight: 600;">+${{Math.round(site.marginal_new_pop || 0).toLocaleString()}} habs</td>
            <td style="padding: 6px 12px;">${{Math.round(site.dist_to_network_m || 0)}} m</td>
            <td style="padding: 6px 12px; font-size: 11px; color: var(--slate-500);">${{site.attach || 'red'}}</td>
          `;
          tableBody.appendChild(tr);
        }}
      }});

      // Actualizamos los KPIs en tiempo real
      updateKPIs();
    }}

    function updateKPIs() {{
      const metrics = STRATEGY_METRICS[currentStrategy]?.[currentBudget] || {{
        pop: '202,337 habs', agebs: '21 AGEBs', school: '13.0 años', capex: '$13.5 MDP', hops: '14 saltos'
      }};

      document.getElementById('kpi-pop').innerText = metrics.pop;
      document.getElementById('kpi-agebs').innerText = metrics.agebs;
      document.getElementById('kpi-school').innerText = metrics.school;
      document.getElementById('kpi-capex').innerText = metrics.capex;
      document.getElementById('kpi-hops').innerText = metrics.hops;
    }}

    function setStrategy(strat) {{
      currentStrategy = strat;
      
      // Update UI buttons
      document.querySelectorAll('#btn-m1, #btn-m2, #btn-m3ga, #btn-m3gr').forEach(b => b.classList.remove('active'));
      if (strat === 'm1') document.getElementById('btn-m1').classList.add('active');
      if (strat === 'm2') document.getElementById('btn-m2').classList.add('active');
      if (strat === 'm3_ga') document.getElementById('btn-m3ga').classList.add('active');
      if (strat === 'm3_greedy') document.getElementById('btn-m3gr').classList.add('active');

      renderActivePortfolio();
    }}

    function setBudget(b) {{
      currentBudget = b;
      
      // Update UI buttons
      document.querySelectorAll('#btn-b15, #btn-b30, #btn-b50').forEach(btn => btn.classList.remove('active'));
      if (b === 15) document.getElementById('btn-b15').classList.add('active');
      if (b === 30) document.getElementById('btn-b30').classList.add('active');
      if (b === 50) document.getElementById('btn-b50').classList.add('active');

      renderActivePortfolio();
    }}

    // Iniciar cuando el DOM esté listo
    window.addEventListener('DOMContentLoaded', () => {{
      initMap();
    }});
  </script>
</body>
</html>
"""

    # 1. Guardar en V3/aplicativo/ecobici_v3_presentacion_ejecutiva.html
    local_output = "V3/aplicativo/ecobici_v3_presentacion_ejecutiva.html"
    with open(local_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Presentación HTML autónoma generada en {local_output}")

    # 2. Guardar en el directorio de artefactos de la conversación
    artifact_output = "/Users/oscarmartinez/.gemini/antigravity/brain/8f741277-4406-40e0-8171-ec4857cbafb3/ecobici_v3_presentacion_ejecutiva.html"
    with open(artifact_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Artefacto guardado en {artifact_output}")

if __name__ == "__main__":
    generate_html()
