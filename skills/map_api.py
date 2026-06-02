"""通过百度地图 API 直接查询 POI 数据（无需浏览器渲染）"""
import requests, json, re

def search_baidu_map_poi(company: str) -> list[dict]:
    """
    通过百度地图的搜索 API 查询公司 POI 数据。
    返回 POI 列表，每个包含 name, address, phone, uid。
    """
    import urllib.parse
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://map.baidu.com/",
    }
    
    # 第一步：搜索建议API，获取POI列表
    params = {
        "wd": company,
        "cid": 131,  # 全国
        "pn": 0,
        "rn": 10,
        "type": 0,
    }
    
    url = f"https://map.baidu.com/su?wd={urllib.parse.quote(company)}&cid=131&pn=0&rn=10&type=0"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        
        results = []
        pois = data.get("s", [])  # 搜索建议列表
        
        for poi in pois[:5]:
            name = poi.get("name", "")
            addr = poi.get("addr", "")
            phone = poi.get("tel", "")
            uid = poi.get("uid", "")
            
            results.append({
                "name": name,
                "address": addr,
                "phone": phone,
                "uid": uid,
            })
        
        return results
        
    except Exception as e:
        print(f"  [!] API查询失败: {e}")
        return []


def get_poi_detail(uid: str) -> dict:
    """通过 POI uid 获取详细信息（可能包含电话）"""
    import urllib.parse
    
    url = f"https://map.baidu.com/detail?qt=ninf&uid={uid}&detail=1"
    
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://map.baidu.com/",
        }, timeout=10)
        data = resp.json()
        
        content = data.get("content", {})
        return {
            "name": content.get("name", ""),
            "address": content.get("addr", ""),
            "phone": content.get("tel", ""),
            "ext": content.get("ext", {}),
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import sys
    company = sys.argv[1] if len(sys.argv) > 1 else "山东金泉水处理有限公司"
    print(f"\n[百度地图 API 查询] {company}")
    print("=" * 50)
    
    pois = search_baidu_map_poi(company)
    
    if pois:
        for poi in pois:
            print(f"\n  POI: {poi['name']}")
            print(f"  地址: {poi['address']}")
            print(f"  电话: {poi['phone']}")
            if poi.get('uid'):
                print(f"  -> 查询详情...")
                detail = get_poi_detail(poi['uid'])
                if detail.get('phone'):
                    print(f"  详情电话: {detail['phone']}")
    else:
        print("  未找到 POI 数据")
        print("  尝试直接搜索...")
    
    # 也尝试详情查询
    print(f"\n{'='*50}")
    print(f"[尝试直接查询]")
    # 百度地图 POI 搜索
    try:
        r = requests.get(
            f"https://map.baidu.com/?newmap=1&s=inf%7C0%7C{company}%7C0%7C0%7C1",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://map.baidu.com/"},
            timeout=10
        )
        print(f"  状态: {r.status_code}")
        if r.text:
            phones = re.findall(r'1[3-9]\d{9}|0\d{2,3}-?\d{7,8}', r.text)
            if phones:
                print(f"  发现电话: {', '.join(set(phones))}")
    except Exception as e:
        print(f"  错误: {e}")
