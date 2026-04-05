FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install LibreOffice for DOCX → PDF conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/cookies output "data/CVs enviados/CVs"

CMD ["python", "run.py"]
