FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# 再拷贝源码
COPY . .

# 数据落盘目录（笔记/课程等），容器内需可写
RUN mkdir -p /app/data && chmod -R 777 /app/data

EXPOSE 7860

CMD ["sh", "-c", "python deploy_start.py"]
