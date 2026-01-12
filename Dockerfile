# Usa un'immagine Python leggera ufficiale
FROM python:3.9-slim

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia il file dei requisiti e installa le librerie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice nell'immagine
COPY . .

# Espone la porta che useremo
EXPOSE 5000

# Comando di avvio per produzione

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "Vision2_0:app"]
