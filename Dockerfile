# ============================================
# BDSS 轻量部署镜像 — 无需 Playwright
# ============================================
FROM python:3.11-slim

LABEL description="BDSS - 工业品 B2B 获客工具"
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 健康检查（API 服务模式）
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5300/api/dashboard')" || exit 1

# 默认入口：API 服务
CMD ["python", "bdss-app/app.py"]
