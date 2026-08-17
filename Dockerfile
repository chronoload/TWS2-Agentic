FROM python:3.12

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    TS2_WORKSPACE=/app/data

WORKDIR /app

# 装系统依赖（poppler 用于 PDF，字体用于 CJK）
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 先装构建工具 + 依赖（利用层缓存）
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements-deploy.txt

# 再拷贝源码
COPY . .

# 数据落盘目录（笔记/课程等），容器内需可写
RUN mkdir -p /app/data && chmod -R 777 /app/data

EXPOSE 7860

CMD ["sh", "-c", "python deploy_start.py"]
