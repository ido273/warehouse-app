FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
RUN useradd app && mkdir -p /app/uploads && chown -R app:app /app/uploads
USER app
CMD ["python", "app.py"]