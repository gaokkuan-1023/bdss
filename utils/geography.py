"""
地理信息工具 — 提取地址、匹配区号、校验电话归属
"""

import re

# ===== 中国城市 → 电话区号映射表 =====
# key: (省份, 城市) 或 (城市) 模糊匹配
CITY_AREA_CODES: dict[str, list[str]] = {
    # 北京
    "北京": ["010"],
    # 上海
    "上海": ["021"],
    # 天津
    "天津": ["022"],
    # 重庆
    "重庆": ["023"],
    # 山东
    "济南": ["0531"],
    "青岛": ["0532"],
    "淄博": ["0533"],
    "德州": ["0534"],
    "烟台": ["0535"],
    "潍坊": ["0536"],
    "济宁": ["0537"],
    "泰安": ["0538"],
    "临沂": ["0539"],
    "菏泽": ["0530"],
    "枣庄": ["0632"],
    "东营": ["0546"],
    "威海": ["0631"],
    "日照": ["0633"],
    "莱芜": ["0634"],
    "聊城": ["0635"],
    "滨州": ["0543"],
    # 广东
    "广州": ["020"],
    "深圳": ["0755"],
    "珠海": ["0756"],
    "东莞": ["0769"],
    "佛山": ["0757"],
    "惠州": ["0752"],
    "中山": ["0760"],
    "汕头": ["0754"],
    "湛江": ["0759"],
    "肇庆": ["0758"],
    # 浙江
    "杭州": ["0571"],
    "宁波": ["0574"],
    "温州": ["0577"],
    "嘉兴": ["0573"],
    "湖州": ["0572"],
    "绍兴": ["0575"],
    "金华": ["0579"],
    "台州": ["0576"],
    # 江苏
    "南京": ["025"],
    "苏州": ["0512"],
    "无锡": ["0510"],
    "常州": ["0519"],
    "镇江": ["0511"],
    "扬州": ["0514"],
    "南通": ["0513"],
    "徐州": ["0516"],
    "淮安": ["0517"],
    "盐城": ["0515"],
    "连云港": ["0518"],
    # 四川
    "成都": ["028"],
    "绵阳": ["0816"],
    "德阳": ["0838"],
    "宜宾": ["0831"],
    # 湖北
    "武汉": ["027"],
    "宜昌": ["0717"],
    "襄阳": ["0710"],
    # 湖南
    "长沙": ["0731"],
    "株洲": ["0733"],
    "湘潭": ["0732"],
    # 河北
    "石家庄": ["0311"],
    "唐山": ["0315"],
    "保定": ["0312"],
    "邯郸": ["0310"],
    # 河南
    "郑州": ["0371"],
    "洛阳": ["0379"],
    "南阳": ["0377"],
    # 福建
    "福州": ["0591"],
    "厦门": ["0592"],
    "泉州": ["0595"],
    # 辽宁
    "沈阳": ["024"],
    "大连": ["0411"],
    # 安徽
    "合肥": ["0551"],
    # 陕西
    "西安": ["029"],
    # 所有其他省份的地级市可按需补充
}


def extract_cities_from_text(text: str) -> list[str]:
    """
    从文本中提取所有可能的地级市名称（带或不带"市"字）。
    返回去重后的城市名列表。
    """
    found = []
    # 直接匹配 "XX市" 模式（如"枣庄市"）
    city_pattern = re.findall(r'([\u4e00-\u9fa5]{2,4})市', text)
    for c in city_pattern:
        if c in CITY_AREA_CODES and c not in found:
            found.append(c)

    # 匹配 "山东省XX" 等省份+城市模式
    province_city = re.findall(r'(?:山东|广东|浙江|江苏|北京|上海|天津|重庆|四川|湖北|湖南|河北|河南|福建|辽宁|安徽|陕西|山西|江西|广西|云南|贵州|甘肃|吉林|黑龙江|内蒙古|新疆|西藏|宁夏|青海|海南)(?:省|市|自治区)?([\u4e00-\u9fa5]{2,4})(?:市|区|县)', text)
    for c in province_city:
        if c in CITY_AREA_CODES and c not in found:
            found.append(c)

    return found


def extract_address_from_text(text: str) -> str | None:
    """
    从文本中提取地址字符串。
    尝试匹配 "地址：..." 等常见模式，返回第一段匹配到的地址。
    """
    patterns = [
        r'地址[：:]\s*([^\n。；;，]{5,80})',
        r'公司地址[：:]\s*([^\n。；;，]{5,80})',
        r'联系地址[：:]\s*([^\n。；;，]{5,80})',
        r'办公地址[：:]\s*([^\n。；;，]{5,80})',
        r'注册地址[：:]\s*([^\n。；;，]{5,80})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            addr = m.group(1).strip()
            if len(addr) >= 6:
                return addr
    return None


def get_area_codes_for_city(city: str) -> list[str]:
    """获取城市对应的电话区号列表。"""
    return CITY_AREA_CODES.get(city, [])


def validate_landline_phone(phone: str, city_codes: list[str]) -> str | None:
    """
    校验固定电话区号是否与目标城市匹配。

    Args:
        phone: 电话号码字符串（如 "0632-3587789" 或 "0536-8121808"）
        city_codes: 目标城市允许的区号列表（如 ["0632"]）

    Returns:
        匹配返回 None，不匹配返回提示信息字符串
    """
    # 提取区号（前3-4位）
    clean = phone.replace('-', '').replace(' ', '')
    if not clean.startswith('0'):
        return None  # 手机号不校验

    # 取前3-4位作为区号
    area_code = None
    if len(clean) >= 10:
        # 可能是 3 位区号 或 4 位区号
        if clean[:4] in city_codes:
            return None  # 匹配4位区号
        if clean[:3] in city_codes:
            return None  # 匹配3位区号
        # 都不匹配 → 可疑
        code_3 = clean[:3]
        code_4 = clean[:4]
        return f"区号 {code_4 if code_4.startswith('0') else code_3} 与目标城市 {city_codes} 不匹配"

    return None


def check_phone_consistency(
    phones: list[str],
    detected_cities: list[str],
    page_texts: list[str],
) -> dict:
    """
    综合校验：检查电话号码是否与检测到的城市一致。

    Args:
        phones: 所有找到的电话号码
        detected_cities: 从页面文本中提取到的城市名列表
        page_texts: 所有打开页面的文本（用于提取地址）

    Returns:
        {
            "valid": [...],       # 通过校验的号码
            "suspicious": [...],  # 可疑号码（区号不匹配）
            "unchecked": [...],   # 无法校验（未检测到城市）
            "detected_cities": [...],
            "address_found": str | None
        }
    """
    # 提取地址
    address_found = None
    for t in page_texts:
        addr = extract_address_from_text(t)
        if addr:
            address_found = addr
            break

    # 提取城市
    all_cities = list(detected_cities)
    for t in page_texts:
        all_cities.extend(extract_cities_from_text(t))
    all_cities = list(set(all_cities))
    all_cities.sort()

    # 获取所有可能的区号
    valid_codes = set()
    for city in all_cities:
        valid_codes.update(get_area_codes_for_city(city))

    # 校验每个电话
    valid = []
    suspicious = []
    unchecked = []

    for phone in phones:
        clean = phone.replace('-', '').replace(' ', '')
        if not clean.startswith('0'):
            valid.append(phone)  # 手机号不校验
            continue

        if not valid_codes:
            unchecked.append(phone)
            continue

        # 提取区号校验
        matched = False
        for code_len in [4, 3]:
            if len(clean) >= code_len:
                code = clean[:code_len]
                if code in valid_codes:
                    matched = True
                    break

        if matched:
            valid.append(phone)
        else:
            suspicious.append(phone)

    return {
        "valid": valid,
        "suspicious": suspicious,
        "unchecked": unchecked,
        "detected_cities": all_cities,
        "address_found": address_found,
    }
