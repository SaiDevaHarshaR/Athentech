# Sahasra AI Agent - Linux container, IIS remains the external HTTPS gateway.
# IMPORTANT: Set PYTHON_VERSION to the version actually running Sahasra in IIS/NSSM.
# The source archive does not pin the deployed Python version.
ARG PYTHON_VERSION=3.12.7
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/home/sahasra
WORKDIR /app

# pyodbc needs unixODBC, the Microsoft ODBC Driver 18 and Microsoft TLS stack.
# PDF generation calls Playwright Chromium (reports/pdf_generator.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg unixodbc unixodbc-dev build-essential \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
       -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin sahasra \
    && mkdir -p /app/audit /app/exports /home/sahasra \
    && chown -R sahasra:sahasra /app /home/sahasra /ms-playwright

# Copy only the application files allowed by .dockerignore.
COPY --chown=sahasra:sahasra . /app
USER sahasra
EXPOSE 8000
# Container-local health only; IIS external routing will be configured later.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# A single worker avoids duplicate in-process scheduled jobs until those jobs
# are moved to a distributed/shared scheduler in a future stage.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
