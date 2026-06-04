"""公司名称智能处理 — 标准化/匹配/去重"""
import re
from typing import Optional

# 企业后缀映射
SUFFIXES = [
    "股份有限公司", "有限责任公司", "有限公司", "股份公司",
    "集团",
]

# 常见无意义词（匹配时可忽略）
STOP_WORDS = [
    "中国", "山东省", "江苏省", "浙江省", "广东省",
    "北京市", "上海市", "深圳市",
    "（普通合伙）", "(普通合伙)",
]


def normalize(name: str) -> str:
    """标准化公司名：统一括号、去除多余空格"""
    if not name:
        return name
    name = name.strip()
    # 全角括号 → 半角
    name = name.replace("（", "(").replace("）", ")")
    name = name.replace("【", "[").replace("】", "]")
    # 全角空格 → 半角
    name = name.replace("\u3000", " ").replace("\xa0", " ")
    # 多个空格 → 一个
    name = re.sub(r"\s+", " ", name)
    return name


def shorten(name: str) -> str:
    """生成简称：去除前后缀/括号"""
    name = normalize(name)
    # 去除所有企业后缀（无论位置）
    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if suffix in name:
            name = name.replace(suffix, "")
    # 去除开头通用词
    for prefix in ["中国", "山东省", "江苏省", "浙江省", "广东省"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # 去除括号及其内容
    name = re.sub(r"\(.*?\)", "", name)
    return name.strip()


def get_key(name: str) -> str:
    """提取匹配关键词：取最短的可用名称"""
    n = normalize(name)
    s = shorten(n)
    # 如果简称太短，用原名前4字
    if len(s) < 3:
        s = n[:4]
    return s


def is_similar(name1: str, name2: str, threshold: float = 0.6) -> bool:
    """判断两个公司名是否相似（用于去重）"""
    k1 = get_key(name1)
    k2 = get_key(name2)
    
    # 直接包含关系
    if k1 in k2 or k2 in k1:
        return True
    
    # 编辑距离判断（简化：首4字匹配）
    if len(k1) >= 4 and len(k2) >= 4 and k1[:4] == k2[:4]:
        return True
    
    return False


def deduplicate(names: list[str]) -> list[str]:
    """对批量名单去重，保留最完整的名称"""
    normalized = [(normalize(n), n) for n in names if n]
    result = []
    seen = set()
    
    for norm, orig in normalized:
        key = get_key(norm)
        if key not in seen:
            # 检查是否与现有条目相似
            is_dup = False
            for i, existing in enumerate(result):
                if is_similar(norm, existing):
                    # 保留较长名称
                    if len(norm) > len(existing):
                        result[i] = norm
                    is_dup = True
                    break
            if not is_dup:
                result.append(norm)
                seen.add(key)
    
    return result
