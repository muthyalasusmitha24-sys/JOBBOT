# Full auto-apply hosting (Hugging Face Spaces "Docker" SDK, Render, Railway, Fly.io, any VPS)
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw HOME=/home/user
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && playwright install --with-deps chromium \
 && chmod -R a+rX /opt/pw
COPY --chown=user . /app
USER user
EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableCORS=false", "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false"]
