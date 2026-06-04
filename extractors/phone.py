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
                # 400/800 服务热线
                elif num_clean.startswith(('400', '800')) and len(num_clean) == 10:
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
            # 400/800
            elif num_clean.startswith(('400', '800')) and len(num_clean) == 10:
                seen.add(num_clean)
                phones.append(p['number'])

        return phones

    # ========== 号码验证与分类 ==========

    @staticmethod
    def validate(phone: str) -> dict:
        """验证号码合法性，返回 { valid, type, carrier, region, reason }"""
        result = {"valid": False, "type": "unknown", "carrier": "", "region": "", "reason": ""}
        clean = phone.replace("-", "").replace(" ", "").replace("+86", "")
        digits = re.sub(r"\D", "", clean)

        if len(digits) < 7:
            result["reason"] = "号码过短"
            return result

        # 手机号 (11位)
        if len(digits) == 11 and digits.startswith("1"):
            result["type"] = "mobile"
            result["carrier"] = PhoneExtractor._get_mobile_carrier(digits)
            result["region"] = PhoneExtractor._get_mobile_region(digits)
            result["valid"] = result["carrier"] != "未知"
            if not result["valid"]:
                result["reason"] = f"号段不存在: {digits[:7]}"
            return result

        # 固话
        if digits.startswith("0") and 10 <= len(digits) <= 12:
            area = digits[:3] if digits.startswith("010") or digits.startswith("020") else digits[:4]
            result["type"] = "landline"
            result["region"] = PhoneExtractor._get_area_name(area)
            result["valid"] = result["region"] != ""
            if not result["valid"]:
                result["reason"] = f"区号不存在: {area}"
            return result

        # 400/800
        if digits.startswith(("400", "800")) and len(digits) == 10:
            result["type"] = "service"
            result["valid"] = True
            return result

        result["reason"] = "格式不识别"
        return result

    _MOBILE_PREFIXES = {
        "13": {"0":"中国联通","1":"中国移动","2":"中国移动","3":"中国电信","4":"中国电信",
               "5":"中国移动","6":"中国联通","7":"中国移动","8":"中国移动","9":"中国移动"},
        "14": {"0":"中国电信","1":"中国联通","2":"中国电信","3":"中国电信",
               "5":"中国移动","6":"中国联通","7":"中国电信","8":"中国移动","9":"中国电信"},
        "15": {"0":"中国移动","1":"中国移动","2":"中国移动","3":"中国电信","5":"中国移动",
               "6":"中国联通","7":"中国联通","8":"中国移动","9":"中国移动"},
        "16": {"6":"中国联通","7":"中国联通","8":"中国联通","9":"中国联通"},
        "17": {"0":"中国联通","1":"中国移动","2":"中国电信","3":"中国电信",
               "5":"中国移动","6":"中国联通","8":"中国移动","9":"中国电信"},
        "18": {"0":"中国移动","1":"中国移动","2":"中国移动","3":"中国电信",
               "5":"中国移动","6":"中国移动","7":"中国移动","8":"中国移动","9":"中国移动"},
        "19": {"0":"中国电信","1":"中国联通","2":"中国移动","3":"中国电信",
               "5":"中国移动","6":"中国移动","7":"中国移动","8":"中国移动","9":"中国电信"},
    }

    @staticmethod
    def _get_mobile_carrier(phone: str) -> str:
        """获取手机号运营商"""
        prefix3 = phone[:3]
        prefix2 = phone[:2]
        prefix4 = phone[:4]
        if prefix3 in ("170", "171", "166", "167", "165"):
            return "中国联通"
        if prefix3 in ("1700", "1701", "1702"):
            return "中国电信"
        if prefix3 in ("1704", "1707", "1708", "1709"):
            return "中国联通"
        if prefix3 in ("1703", "1705", "1706"):
            return "中国移动"
        # 通用号段
        mapping = PhoneExtractor._MOBILE_PREFIXES.get(prefix2, {})
        third_digit = phone[2] if len(phone) > 2 else ""
        return mapping.get(third_digit, "未知")

    @staticmethod
    def _get_mobile_region(phone: str) -> str:
        """获取手机号归属地（简化版 — 仅返回号段归属）"""
        return "中国"

    @staticmethod
    def _get_area_name(code: str) -> str:
        """获取区号对应城市名"""
        AREA_CODES = {
            "010":"北京","020":"广州","021":"上海","022":"天津","023":"重庆",
            "024":"沈阳","025":"南京","027":"武汉","028":"成都","029":"西安",
            "0311":"石家庄","0312":"保定","0315":"唐山","0316":"廊坊",
            "0411":"大连","0412":"鞍山","0415":"丹东",
            "0510":"无锡","0511":"镇江","0512":"苏州","0513":"南通",
            "0514":"扬州","0515":"盐城","0516":"徐州",
            "0531":"济南","0532":"青岛","0533":"淄博","0534":"德州",
            "0535":"烟台","0536":"潍坊","0537":"济宁","0538":"泰安","0539":"临沂",
            "0543":"滨州","0546":"东营",
            "0551":"合肥","0555":"马鞍山","0566":"池州",
            "0571":"杭州","0572":"湖州","0573":"嘉兴","0575":"绍兴",
            "0576":"台州","0577":"温州","0578":"丽水","0579":"金华",
            "0580":"舟山",
            "0591":"福州","0592":"厦门","0593":"宁德","0594":"莆田",
            "0595":"泉州","0596":"漳州","0597":"龙岩","0598":"三明","0599":"南平",
            "0631":"威海","0632":"枣庄","0633":"日照","0634":"莱芜","0635":"聊城",
            "0660":"汕尾","0662":"阳江","0663":"揭阳","0668":"茂名",
            "0710":"襄阳","0711":"鄂州","0712":"孝感","0713":"黄冈",
            "0714":"黄石","0715":"咸宁","0716":"荆州","0717":"宜昌",
            "0718":"恩施","0719":"十堰",
            "0731":"长沙","0734":"衡阳","0735":"郴州","0736":"常德",
            "0737":"益阳","0738":"娄底","0739":"邵阳",
            "0743":"湘西","0744":"张家界","0745":"怀化","0746":"永州",
            "0750":"江门","0751":"韶关","0752":"惠州","0753":"梅州",
            "0754":"汕头","0755":"深圳","0756":"珠海","0757":"佛山",
            "0758":"肇庆","0759":"湛江",
            "0760":"中山","0762":"河源","0763":"清远","0766":"云浮",
            "0768":"潮州","0769":"东莞",
            "0771":"南宁","0772":"柳州","0774":"梧州","0775":"贵港",
            "0776":"百色","0777":"钦州","0778":"河池","0779":"北海",
            "0790":"新余","0791":"南昌","0792":"九江","0793":"上饶",
            "0795":"宜春","0796":"吉安","0797":"赣州","0798":"景德镇","0799":"萍乡",
            "0816":"绵阳","0817":"南充","0818":"达州",
            "0825":"遂宁","0826":"广安","0827":"巴中",
            "0830":"泸州","0831":"宜宾","0832":"内江","0833":"乐山",
            "0834":"凉山","0835":"雅安","0836":"阿坝","0837":"甘孜",
            "0838":"德阳","0839":"广元",
            "0851":"贵阳","0854":"黔南","0855":"黔东南","0856":"铜仁",
            "0857":"毕节","0858":"六盘水","0859":"黔西南",
            "0870":"昭通","0871":"昆明","0872":"大理","0873":"红河",
            "0874":"曲靖","0875":"保山","0876":"文山","0877":"玉溪",
            "0878":"楚雄","0879":"普洱",
            "0883":"临沧","0886":"怒江","0887":"迪庆","0888":"丽江",
            "0891":"拉萨","0892":"日喀则","0898":"三亚",
            "0911":"延安","0912":"榆林","0913":"渭南","0914":"商洛",
            "0915":"安康","0916":"汉中","0917":"宝鸡","0919":"铜川",
            "0930":"临夏","0931":"兰州","0932":"定西","0933":"平凉",
            "0934":"庆阳","0935":"武威","0936":"张掖","0937":"酒泉",
            "0938":"天水","0941":"甘南","0943":"白银",
            "0951":"银川","0952":"石嘴山","0953":"吴忠","0954":"固原",
            "0955":"中卫",
            "0971":"西宁","0972":"海东","0973":"黄南","0974":"海南",
            "0975":"果洛","0976":"玉树","0977":"海西","0979":"格尔木",
            "0991":"乌鲁木齐","0992":"克拉玛依","0993":"吐鲁番",
            "0996":"库尔勒","0997":"阿克苏","0998":"喀什","0999":"伊犁",
        }
        return AREA_CODES.get(code, "")

    @staticmethod
    def format_result(company: str, phones: list[str], sources: list[str] = None) -> dict:
        """格式化最终输出"""
        return {
            "company": company,
            "phones": phones,
            "phone_count": len(phones),
            "sources": sources or [],
        }
