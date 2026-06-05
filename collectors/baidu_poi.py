"""采集器: 百度地图 POI 查询（步骤1-2）

步骤1: 用完整公司名查百度地图 Place API
步骤2: 若未找到电话，缩短公司名后再查一次
"""
import json
import os
import urllib.parse
import urllib.request

from collectors.base import BaseCollector


class BaiduPOICollector(BaseCollector):
    """通过百度地图 Place API 查询公司 POI 电话"""

    name = "百度地图POI"
    confidence = "high"

    def collect(self, company: str, existing_phones: set = None) -> dict:
        """
        查询百度地图 Place API，先原名搜索，无结果则缩短名称再搜。

        Args:
            company: 公司名称
            existing_phones: 已发现的电话集合（用于去重）

        Returns:
            {"phones": set, "sources": list, "log": str}
        """
        existing_phones = existing_phones or set()
        new_phones = set()
        sources = []
        log_lines = []

        # 步骤1: 原名查询
        log_lines.append(f"1/5 百度地图POI查询: {company}")
        self._query_poi(company, existing_phones, new_phones, sources, log_lines, label="百度地图POI")

        # 步骤2: 若原名无结果，缩短公司名再查
        if not new_phones:
            short_name = self._shorten_name(company)
            if short_name != company:
                log_lines.append(f"2/5 缩短名称查询: {short_name}")
                self._query_poi(short_name, existing_phones, new_phones, sources, log_lines, label="百度地图POI")
            else:
                log_lines.append("2/5 公司名无需缩短，跳过")

        return {
            "phones": new_phones,
            "sources": sources,
            "log": "\n".join(log_lines),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _query_poi(
        self,
        keyword: str,
        existing_phones: set,
        new_phones: set,
        sources: list,
        log_lines: list,
        label: str = "",
    ) -> None:
        """执行单次百度地图 Place API 查询，结果追加到 new_phones / sources。"""
        from extractors.phone import PhoneExtractor

        ak = self._get_ak()
        if not ak:
            log_lines.append("  ✗ 未配置 BAIDU_MAP_AK，跳过百度地图查询")
            return

        query = urllib.parse.quote(keyword)
        region = urllib.parse.quote("全国")
        url = (
            f"https://api.map.baidu.com/place/v2/search"
            f"?query={query}&region={region}&output=json&ak={ak}"
        )

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            extractor = PhoneExtractor(prefer_nearby=False)
            for poi in data.get("results", []):
                phone_raw = poi.get("telephone", "") or poi.get("phone", "")
                if not phone_raw:
                    continue
                poi_name = poi.get("name", "")
                for p in extractor.extract(phone_raw):
                    if p not in existing_phones and p not in new_phones:
                        new_phones.add(p)
                        sources.append(
                            self._make_source(p, source=f"百度地图POI/{poi_name}", title=poi_name)
                        )

            if new_phones:
                log_lines.append(f"  ✓ {label}找到电话: {' | '.join(new_phones)}")
            else:
                log_lines.append(f"  ✗ {label}未找到电话")

        except Exception as ex:
            log_lines.append(f"  ✗ {label}查询失败: {str(ex)[:60]}")
            self.logger.debug(f"百度地图API查询失败: {ex}")

    @staticmethod
    def _shorten_name(company: str) -> str:
        """缩短公司名称：去掉'有限公司'、'股份有限公司'、'集团'、括号等。"""
        short = company
        for token in ("有限公司", "股份有限公司", "集团", "(", ")", "（", "）"):
            short = short.replace(token, "")
        return short

    @staticmethod
    def _get_ak() -> str:
        """获取百度地图 AK，优先环境变量，其次 .env / utils.env。"""
        ak = os.environ.get("BAIDU_MAP_AK", "")
        if ak:
            return ak
        try:
            from utils.env import get_ak
            return get_ak()
        except ImportError:
            return ""
