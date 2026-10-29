# Demostración de reproducibilidad — Tabla 5 (cobertura por presupuesto).
# Imagen ligera: solo instala el núcleo del pipeline y ejecuta el script
# que verifica la firma sha256 del artefacto sellado y reconstruye la tabla.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Solo lo necesario para la demo: script + artefactos sellados.
COPY src/generar_tabla5_resultados.py src/generar_tabla5_resultados.py
COPY data/resultados/ data/resultados/
COPY data/audits/08_comparacion_portafolios.json data/audits/08_comparacion_portafolios.json

CMD ["python", "src/generar_tabla5_resultados.py"]
