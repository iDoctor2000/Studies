# Registro WILLEM · servidor central para el NAS (Synology Container Manager)
# Solo lleva la aplicación web y el servidor: ni el libro llave ni la estación de informes del Mac.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Madrid

WORKDIR /app
COPY servidor.py demo.py ./
COPY web ./web
COPY diccionario ./diccionario
RUN mkdir -p /datos

VOLUME ["/datos"]
EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/estado', timeout=4)" || exit 1

# --nas: sin libro llave, doble factor obligatorio, cookies solo por HTTPS, copia diaria en /datos/copias
CMD ["python3", "servidor.py", "--nas", "--datos", "/datos", "--puerto", "8765", "--no-navegador"]
