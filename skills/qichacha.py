"""企查查 API 搜索引擎 — 企业工商数据查询"""
import hashlib
import json
import logging
import time
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)

# 企查查 API 端点
_BASE_URL = "https://api.qichacha.com"


class QichachaSearch:
    """
    企查查搜索引擎。
    需要配置 QCC_API_KEY 和 QCC_SECRET_KEY 环境变量。
    未配置时静默降级（返回空结果）。
    """

    def __init__(self, api_key: str = "", secret_key: str = ""):
        if not api_key:
            from utils.env import get_env
            api_key = get_env("QCC_API_KEY", "")
            secret_key = get_env("QCC_SECRET_KEY", "")
        self.api_key = api_key
        self.secret_key = secret_key
        self._available = bool(api_key and secret_key)
        if not self._available:
            logger.debug("企查查 API 未配置（需要 QCC_API_KEY 和 QCC_SECRET_KEY），已禁用")

    @property
    def available(self) -> bool:
        return self._available

    def _sign(self, timespan: str) -> str:
        """生成请求签名: MD5(api_key + timespan + secret_key).upper()"""
        raw = self.api_key + timespan + self.secret_key
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _request(self, path: str, params: dict) -> dict | None:
        """发送 API 请求"""
        if not self._available:
            return None
        timespan = str(int(time.time()))
        params["key"] = self.api_key
        params["timespan"] = timespan
        token = self._sign(timespan)
        url = f"{_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "BDSS/1.0",
            "token": token,
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("Status") != "200":
                logger.warning(f"企查查 API 错误: {data.get('Message', '未知')}")
                return None
            return data
        except Exception as e:
            logger.warning(f"企查查 API 请求失败: {e}")
            return None

    def search(self, company: str, max_results: int = 5) -> list[dict]:
        """
        模糊搜索企业列表。
        返回: [{"title": "...", "url": "...", "snippet": "...", "key_no": "..."}, ...]
        """
        if not self._available:
            return []
        data = self._request("/Search/FuzzySearch", {
            "searchKey": company,
            "pageIndex": "1",
            "pageSize": str(max_results),
        })
        if not data:
            return []
        results = []
        for item in data.get("Result", []):
            results.append({
                "title": item.get("Name", ""),
                "url": f"https://www.qcc.com/firm/{item.get('KeyNo', '')}.html",
                "snippet": f"{item.get('LegalPersonName', '')} | {item.get('Address', '')}",
                "key_no": item.get("KeyNo", ""),
                "credit_code": item.get("CreditCode", ""),
                "legal_person": item.get("LegalPersonName", ""),
            })
        return results

    def get_company_info(self, key_no: str) -> dict | None:
        """获取企业基本信息"""
        if not self._available:
            return None
        data = self._request("/ECIV4/GetBaseProfile", {"keyNo": key_no})
        if not data:
            return None
        return data.get("Result", {})

    def get_contact_info(self, key_no: str) -> dict | None:
        """获取企业联系信息（电话、邮箱等）"""
        if not self._available:
            return None
        time.sleep(0.3)  # 限速保护
        data = self._request("/EnterpriseContact/GetContactInfo", {"keyNo": key_no})
        if not data:
            return None
        return data.get("Result", {})

    def search_and_extract(self, company: str, max_results: int = 3) -> dict:
        """
        搜索并提取电话信息 — 一站式接口。
        返回: {"phones": [...], "sources": [...], "phone_count": N}
        """
        if not self._available:
            return {"phones": [], "sources": [], "phone_count": 0}

        import re
        all_phones = set()
        sources = []

        # 1. 搜索企业列表
        items = self.search(company, max_results=max_results)
        if not items:
            return {"phones": [], "sources": [], "phone_count": 0}

        # 2. 获取第一个匹配企业的联系信息
        best_match = items[0]
        key_no = best_match.get("key_no", "")
        if key_no:
            contact = self.get_contact_info(key_no)
            if contact:
                # 提取电话号码
                phone_fields = []
                if isinstance(contact, dict):
                    for field in ["PhoneNumber", "Telephone", "MobilePhone", "Fax"]:
                        val = contact.get(field, "")
                        if val:
                            phone_fields.append(str(val))
                elif isinstance(contact, list):
                    for item in contact:
                        for field in ["PhoneNumber", "Telephone", "MobilePhone"]:
                            val = item.get(field, "") if isinstance(item, dict) else ""
                            if val:
                                phone_fields.append(str(val))

                for text in phone_fields:
                    for m in re.finditer(r"1[3-9]\d{9}", text):
                        p = m.group()
                        all_phones.add(p)
                        sources.append({
                            "phone": p,
                            "source": "企查查",
                            "title": best_match.get("title", ""),
                            "confidence": "high",
                        })
                    for m in re.finditer(r"0\d{2,3}[-]?\d{7,8}", text):
                        p = m.group().replace("-", "")
                        all_phones.add(p)
                        sources.append({
                            "phone": p,
                            "source": "企查查",
                            "title": best_match.get("title", ""),
                            "confidence": "high",
                        })
                    for m in re.finditer(r"(?:400|800)[-]?\d{3}[-]?\d{4}", text):
                        p = m.group().replace("-", "")
                        all_phones.add(p)
                        sources.append({
                            "phone": p,
                            "source": "企查查",
                            "title": best_match.get("title", ""),
                            "confidence": "high",
                        })

        return {
            "phones": sorted(all_phones),
            "sources": sources,
            "phone_count": len(all_phones),
        }

    def open_result(self, result: dict) -> dict:
        """获取搜索结果详情（兼容其他引擎接口）"""
        if not self._available:
            return {}
        key_no = result.get("key_no", "")
        if not key_no:
            return {}
        info = self.get_company_info(key_no)
        contact = self.get_contact_info(key_no)
        return {"info": info, "contact": contact}

    def search_and_open(self, company: str, max_results: int = 3) -> dict:
        """搜索 + 详情（兼容其他引擎接口）"""
        if not self._available:
            return {"phones": [], "sources": [], "phone_count": 0}
        return self.search_and_extract(company, max_results=max_results)

    def close(self):
        """关闭（兼容其他引擎接口）"""
        pass


# ===== 独立测试 =====
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[企查查 API 搜索] {company}")
    print(f"{'='*50}")

    qcc = QichachaSearch()
    if not qcc.available:
        print("\n  未配置 QCC_API_KEY / QCC_SECRET_KEY")
        print("  请在 .env 中配置后重试")
        sys.exit(0)

    result = qcc.search_and_extract(company)
    print(f"\n  电话数: {result['phone_count']}")
    for p in result["phones"]:
        print(f"    {p}")
    for s in result["sources"]:
        print(f"    来源: {s['source']} - {s['title']}")
