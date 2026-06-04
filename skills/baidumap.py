import os, sys, json, logging, re
import urllib.request
from pathlib import Path
from urllib.parse import quote
from extractors.phone import PhoneExtractor

logger = logging.getLogger(__name__)

_BASE = "https://map.baidu.com"
from utils.env import get_ak
_AK = get_ak()


def query_baidu_map_poi(company: str) -> dict:
    """
    通过百度地图官方 API 查询公司 POI 电话。
    使用 Place API v2: https://lbsyun.baidu.com/
    """
    result = {"name": company, "address": "", "phone": "", "uid": "",
              "source": "", "all_phones": []}
    extractor = PhoneExtractor(prefer_nearby=True)

    # ===== 方式1: 官方 Place API =====
    wd = quote(company, safe='')
    search_url = (f"https://api.map.baidu.com/place/v2/search"
                  f"?query={wd}&region=%E5%85%A8%E5%9B%BD&output=json&ak={_AK}")
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
        results = data.get("results", [])
        if results:
            poi = results[0]
            result["name"] = poi.get("name", company)
            result["address"] = poi.get("address", "")
            result["uid"] = poi.get("uid", "")
            phone = poi.get("telephone", "") or poi.get("phone", "")
            if phone:
                phones = extractor.extract(phone)
                result["all_phones"] = phones
                if phones:
                    result["phone"] = phones[0]
                    result["source"] = "百度地图官方API"
                    logger.info(f"    [OK] 百度地图官方API: {result['name']} - {', '.join(result['all_phones'])}")
                    return result
    except Exception as e:
        logger.warning(f"    [!] 官方API请求失败: {e}")

    return result


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n{'='*50}")
    print(f"[百度地图 POI 查询] {company}")
    print(f"{'='*50}")

    r = query_baidu_map_poi(company)

    print(f"\n  名称: {r.get('name', '')}")
    print(f"  地址: {r.get('address', '')}")
    print(f"  来源: {r.get('source', '无')}")
    print(f"\n  电话:")
    if r.get('all_phones'):
        for p in r['all_phones']:
            print(f"    [电话] {p}")
    else:
        print(f"    未找到")
