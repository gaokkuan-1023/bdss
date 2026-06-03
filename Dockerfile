# ============================================
# BDSS 多阶段构建
# ============================================
# 构建阶段: 安装 Python 包
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================
# 运行阶段: 仅保留运行时产物，缩小镜像
FROM python:3.11-slim AS runtime

LABEL description="公司联系电话爬虫 - Company Contact Crawler"

# 安装 Playwright 浏览器系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libu2f-udev \
    libvulkan1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制 Python 包（从构建阶段）
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 安装 Playwright 浏览器
RUN python -m playwright install chromium && \
    python -m playwright install-deps chromium

# 复制项目代码
COPY . .

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

# 默认入口
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
