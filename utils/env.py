"""BDSS 环境变量工具 — 统一从 .env 或环境变量读取配置"""

import os
from pathlib import Path


def get_env(key: str, default: str = "") -> str:
    """获取配置，优先环境变量，其次 .env 文件"""
    val = os.environ.get(key, "")
    if val:
        return val
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("\"'")
                if k == key:
                    return v
        except Exception:
            pass
    return default


def get_ak() -> str:
    """获取百度地图 API Key"""
    return get_env("BAIDU_MAP_AK", "")


def get_ai_api_key() -> str:
    """获取 AI API Key"""
    return get_env("BDSS_AI_API_KEY", "")


def get_ai_model() -> str:
    """获取 AI 模型名"""
    return get_env("BDSS_AI_MODEL", "gpt-4o-mini")


def get_ai_base_url() -> str:
    """获取 AI API 地址"""
    return get_env("BDSS_AI_BASE_URL", "https://api.openai.com/v1")
