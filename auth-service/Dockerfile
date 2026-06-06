FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
RUN useradd app && chown -R app:app /app
USER app
CMD ["python", "app.py"]
