FROM python:3.9-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/logs
EXPOSE 5050

CMD ["python", "-u", "src/main.py"]