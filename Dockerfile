FROM docker.io/library/python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libssl-dev libffi-dev python3-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# 使用pip安装所有依赖，优先预编译wheels
RUN pip install --no-cache-dir -r requirements.txt

COPY fetch_and_push.py ./
COPY keywords.txt ./

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python", "fetch_and_push.py"]
