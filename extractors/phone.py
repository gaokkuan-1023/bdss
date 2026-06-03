"""电话号码提取器"""

import re


class PhoneExtractor:
    """
    电话号码提取器。
    支持: 手机号、固定电话、400/800热线、带标签的电话号码。
    """

    # ========== 正则模式 ==========

    # 中国手机号: 1开头的11位数字，第2位3-9
    MOBILE_RE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')

    # 中国固话: 区号(3-4位) 连接符(可选) 号码(7-8位)
    # 排除 000 等非法区号
    LANDLINE_RE = re.compile(r'(?<!\d)0(?!0{2,3}\d)[1-9]\d{1,2}[- ]?\d{7,8}(?!\d)')

    # 400/800 热线
    SERVICE_RE = re.compile(r'(?<!\d)(?:400|800)[- ]?\d{3}[- ]?\d{4}(?!\d)')

    # 带国际区号的中国号码: +86 ...
    INTNL_RE = re.compile(r'\+86[- ]?1[3-9]\d{9}(?!\d)')

    # ========== 电话号码上下文关键词 ==========

    PHONE_KEYWORDS = [
        "电话", "手机", "联系电话", "联系方式", "联系手机",
        "Tel", "tel", "TEL", "Phone", "phone", "PHONE",
        "客服", "热线", "服务热线", "咨询热线",
        "固话", "座机", "号码", "联系号码",
        "业务电话", "公司电话", "办公电话",
    ]

    def __init__(self, prefer_nearby: bool = True):
        """
        Args:
            prefer_nearby: 是否优先提取"电话：""Tel:"等关键词附近的号码
        """
        self.prefer_nearby = prefer_nearby
        self._all_patterns = [
            (self.INTNL_RE, "international"),
            (self.MOBILE_RE, "mobile"),
            (self.LANDLINE_RE, "landline"),
            (self.SERVICE_RE, "service"),
        ]

    def extract_all(self, text: str) -> list[dict]:
        """
        从文本中提取所有电话号码（带位置和类型）。
        返回: [{"type": "mobile", "number": "13800138000", "position": 123}, ...]
        """
        results = []
        seen = set()

        for pattern, ptype in self._all_patterns:
            for m in pattern.finditer(text):
                num = m.group().replace('-', '').replace(' ', '').replace('+86', '')
                if num not in seen:
                    seen.add(num)
                    results.append({
                        "type": ptype,
                        "number": m.group(),
                        "position": m.start(),
                    })

        # 按出现位置排序
        results.sort(key=lambda x: x["position"])
        return results

    def extract_nearby_keywords(self, text: str, window: int = 1) -> list[dict]:
        """
        只在"电话""Tel""客服"等关键词附近查找号码。
        window: 关键词上下各取多少行
        """
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        found = set()
        results = []

        for i, line in enumerate(lines):
            has_kw = any(kw in line for kw in self.PHONE_KEYWORDS)
            if not has_kw:
                continue

            # 检查当前行及上下 window 行
            for di in range(-window, window + 1):
                idx = i + di
                if idx < 0 or idx >= len(lines):
                    continue
                for pattern, ptype in self._all_patterns:
                    for m in pattern.finditer(lines[idx]):
                        num = m.group().replace('-', '').replace(' ', '').replace('+86', '')
                        if num not in found:
                            found.add(num)
                            results.append({
                                "type": ptype,
                                "number": m.group(),
                                "context": lines[idx].strip()[:80],
                                "source_line": idx,
                            })
        return results

    def extract(self, text: str) -> list[str]:
        """
        简易接口：返回去重后的纯号码列表。
        过滤条件：
        - 手机号必须 11 位（1xx xxxx xxxx）
        - 固话必须 10-12 位（含区号和连接符）
        - 400 必须完整
        - 跳过纯 0 开头且小于 7 位的号码
        """
        seen = set()
        phones = []

        if self.prefer_nearby:
            nearby = self.extract_nearby_keywords(text)
            for p in nearby:
                num_clean = p['number'].replace('-', '').replace(' ', '').replace('+86', '')
                # 过滤：手机号必须11位且以1开头
                if len(num_clean) == 11 and num_clean.startswith('1'):
                    if num_clean not in seen:
                        seen.add(num_clean)
                        phones.append(p['number'])
                # 固话：以0开头，总长度10-12位
                elif num_clean.startswith('0') and 10 <= len(num_clean) <= 12:
                    if num_clean not in seen:
                        seen.add(num_clean)
                        phones.append(p['number'])
                # 400号码
                elif num_clean.startswith('400') and len(num_clean) == 10:
                    if num_clean not in seen:
                        seen.add(num_clean)
                        phones.append(p['number'])

        # 补充提取全文中额外的号码
        all_phones = self.extract_all(text)
        for p in all_phones:
            num_clean = p['number'].replace('-', '').replace(' ', '').replace('+86', '')
            if num_clean in seen:
                continue
            # 手机号11位
            if len(num_clean) == 11 and num_clean.startswith('1'):
                seen.add(num_clean)
                phones.append(p['number'])
            # 固话
            elif num_clean.startswith('0') and 10 <= len(num_clean) <= 12:
                seen.add(num_clean)
                phones.append(p['number'])
            # 400
            elif num_clean.startswith('400') and len(num_clean) == 10:
                seen.add(num_clean)
                phones.append(p['number'])

        return phones

    @staticmethod
    def format_result(company: str, phones: list[str], sources: list[str] = None) -> dict:
        """格式化最终输出"""
        return {
            "company": company,
            "phones": phones,
            "phone_count": len(phones),
            "sources": sources or [],
        }
