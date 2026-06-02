# utils/helpers.py
import re
import json
import sys
from pathlib import Path


def extract_phone_numbers(text: str) -> list[dict]:
    """
    从文本中提取各种格式的电话号码。
    返回格式: [{"type": "mobile/landline/400", "number": "..."}]
    """
    results = []

    # 中国手机号: 1开头的11位数字
    mobile_pattern = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
    for m in mobile_pattern.finditer(text):
        results.append({
            "type": "mobile",
            "number": m.group(),
            "position": m.start()
        })

    # 中国固话: 区号(3-4位)-号码(7-8位)
    landline_pattern = re.compile(r'(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)')
    for m in landline_pattern.finditer(text):
        results.append({
            "type": "landline",
            "number": m.group(),
            "position": m.start()
        })

    # 400/800 电话
    service_pattern = re.compile(r'(?<!\d)(?:400|800)[- ]?\d{3}[- ]?\d{4}(?!\d)')
    for m in service_pattern.finditer(text):
        results.append({
            "type": "service",
            "number": m.group(),
            "position": m.start()
        })

    return results


def extract_nearby_phone(text: str, keywords: list[str] = None) -> list[str]:
    """
    在"电话：""联系电话""Tel:"等关键词附近优先提取号码。
    返回去重后的号码列表。
    """
    if keywords is None:
        keywords = ["电话", "手机", "联系电话", "联系方式", "Tel",
                     "tel", "PHONE", "Phone", "客服", "热线", "固话"]

    lines = text.split('\n')
    found = set()

    for i, line in enumerate(lines):
        for kw in keywords:
            if kw in line:
                # 从该行提取号码
                phones = extract_phone_numbers(line)
                for p in phones:
                    found.add(p["number"])
                # 也检查上下各一行
                for di in [-1, 1]:
                    idx = i + di
                    if 0 <= idx < len(lines):
                        phones = extract_phone_numbers(lines[idx])
                        for p in phones:
                            found.add(p["number"])
                break

    return list(found)


def save_result(company: str, results: list[dict], output_path: str | None = None):
    """保存结果到 JSON 文件"""
    data = {
        "company": company,
        "results": results
    }
    if output_path:
        path = Path(output_path)
        # 如果输出是已存在的目录，自动生成文件名
        if path.is_dir():
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', company)
            path = path / f"{safe_name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)
    else:
        # 默认输出到当前目录
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', company)
        path = Path(safe_name + '.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)


def load_companies_from_file(filepath: str) -> list[str]:
    """从文件加载公司名称列表（每行一个）"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")
    companies = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                companies.append(line)
    return companies


def safe_print(text: str, end: str = '\n'):
    """
    Windows GBK 终端安全的打印函数。
    自动替换无法编码的字符。
    """
    try:
        print(text, end=end)
    except UnicodeEncodeError:
        safe = text.encode('gbk', errors='replace').decode('gbk')
        print(safe, end=end)
