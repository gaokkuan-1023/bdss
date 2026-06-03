"""AI 搜索技能 — 调用 LLM 获取公司联系电话

通过 AI API（OpenAI / Claude / DeepSeek 等）直接搜索公司联系电话，
无需启动 Playwright 浏览器。

支持代理配置:
    # .env 文件
    BDSS_AI_API_KEY=sk-xxx
    BDSS_AI_MODEL=gpt-4o-mini
    BDSS_AI_BASE_URL=https://api.openai.com/v1

环境变量同样支持（优先级高于 .env）。
"""
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _get_config(key: str, default: str = "") -> str:
    """从环境变量或 .env 文件读取配置"""
    val = os.environ.get(key, "")
    if not val:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            try:
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
    return val or default


class AISearch:
    """AI 搜索引擎 — 使用 LLM 直接获取公司联系电话"""

    engine_name = "ai"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None, temperature: float = 0.1,
                 **kwargs):
        """
        Args:
            api_key: AI API Key（默认从环境变量 BDSS_AI_API_KEY 读取）
            model:   模型名（默认从环境变量 BDSS_AI_MODEL 读取，兜底 gpt-4o-mini）
            base_url: API 地址（默认从环境变量 BDSS_AI_BASE_URL 读取，兜底 OpenAI）
            temperature: 生成温度，越小越确定（默认 0.1）
        """
        self.api_key = api_key or _get_config("BDSS_AI_API_KEY")
        self.model = model or _get_config("BDSS_AI_MODEL", _DEFAULT_MODEL)
        self.base_url = base_url or _get_config("BDSS_AI_BASE_URL", _DEFAULT_BASE_URL)
        self.temperature = temperature

    def _call_llm(self, messages: list[dict]) -> str:
        """调用 LLM API 并返回响应文本"""
        if not self.api_key:
            logger.error("未配置 AI API Key，请设置 BDSS_AI_API_KEY 环境变量或在 .env 中填写")
            return ""

        import urllib.request

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 1024,
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return content.strip()
        except Exception as e:
            logger.error(f"AI API 调用失败: {e}")
            return ""

    # ============ 搜索公司信息 ============

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        """
        搜索公司联系电话。

        Args:
            query: 公司名称
            max_results: 保留兼容，实际由 AI 决定返回多少

        Returns:
            格式同其他搜索引擎: [{"title", "url", "snippet", "index"}, ...]
        """
        prompt = f"""你是一个专业的中国企业信息查询助手。请帮我查询以下公司的联系电话。

公司名称：{query}

请通过你的知识或联网搜索，找到这家公司的：
1. 官方联系电话（手机号、座机、400/800 热线均可）
2. 信息来源（公司官网、天眼查、百度百科等）
3. 公司全称（如果查询的是简称）

请以 JSON 数组格式返回，每个元素包含 title、url、snippet 三个字段：
[
  {{
    "title": "公司全称",
    "url": "信息源 URL",
    "snippet": "联系电话：xxx-xxxxxxx（来源：xxx）"
  }}
]

如果找到多个电话，返回多个元素。
如果未找到任何电话，返回空数组 []。
只返回 JSON，不要额外说明。"""

        content = self._call_llm([
            {"role": "system", "content": "你是一个专业的中国企业信息查询助手。返回严格有效的 JSON。"},
            {"role": "user", "content": prompt},
        ])

        # 解析 JSON 响应
        results = self._parse_json_response(content)
        if not results:
            logger.info(f"  [AI] 未找到电话或解析失败")
            return []

        # 格式化为标准结果
        formatted = []
        for item in results[:max_results]:
            title = item.get("title", query)
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            if snippet:
                formatted.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "index": len(formatted) + 1,
                })

        logger.info(f"  [AI] {query} → {len(formatted)} 条结果")
        return formatted

    # ============ 打开结果（AI 模式 = 合并到 search 中，无需实际打开） ============

    def open_result(self, url: str) -> str:
        """AI 模式下 open_result 是空操作，数据已在 search 的 snippet 中"""
        return ""

    # ============ 一站式搜索（跳过浏览器初始化） ============

    def search_and_open(self, query: str, max_results: int = 5) -> tuple:
        """AI 一站式搜索，无需启动浏览器"""
        results = self.search(query, max_results=50)
        opened = []
        search_page_text = ""

        for r in results[:max_results]:
            opened.append({**r, "page_text": r.get("snippet", "")})
            if r.get("snippet"):
                search_page_text += r["snippet"] + "\n"

        return opened, search_page_text

    def close(self):
        """AI 无浏览器资源，无需关闭"""
        pass

    # ============ 辅助方法 ============

    @staticmethod
    def _parse_json_response(content: str) -> list[dict]:
        """从 LLM 响应中提取 JSON"""
        if not content:
            return []

        # 尝试直接解析
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        # 尝试提取 [ ... ] 数组
        m = re.search(r"(\[.*?\])", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        return []

    @staticmethod
    def extract_phones_from_ai_response(results: list[dict]) -> list[str]:
        """从 AI 搜索结果中提取电话（供外部使用）"""
        import re as _re
        phones = []
        for r in results:
            snippet = r.get("snippet", "")
            if not snippet:
                continue
            # 提取电话
            found = _re.findall(r'(?<!\d)1[3-9]\d{9}(?!\d)', snippet)
            found += _re.findall(r'(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)', snippet)
            found += _re.findall(r'(?<!\d)(?:400|800)[- ]?\d{3}[- ]?\d{4}(?!\d)', snippet)
            for p in found:
                p_clean = p.replace("-", "").replace(" ", "")
                if p_clean not in phones:
                    phones.append(p_clean)
        return phones
