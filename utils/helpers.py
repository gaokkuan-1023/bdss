from typing import Optional, List
# utils/helpers.py
import re
import json
import sys
import logging
from pathlib import Path


def setup_logger(name: str = "bdss", level: int = logging.INFO) -> logging.Logger:
    """
    设置并返回带控制台 Handler 的 Logger。

    日志格式: [时间] [级别] [模块] 消息
    默认 INFO 级别，--verbose 模式下使用 DEBUG 级别。
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 避免重复添加

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    return logger


# 电话提取功能已在 extractors.phone.PhoneExtractor 中统一实现
# extract_phone_numbers 和 extract_nearby_phone 已废除
# 历史导入兼容：保留引用指向 PhoneExtractor
from extractors.phone import PhoneExtractor
_phone_extractor = PhoneExtractor(prefer_nearby=True)


def extract_phone_numbers(text: str) -> list[dict]:
    """已废弃，请使用 PhoneExtractor.extract_all()"""
    return _phone_extractor.extract_all(text)


def extract_nearby_phone(text: str, keywords: Optional[list[str]] = None) -> list[str]:
    """已废弃，请使用 PhoneExtractor.extract()"""
    return _phone_extractor.extract(text)


def save_result(company: str, results: list[dict], output_path: Optional[str] = None):
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


def _classify_phone(phone: str) -> str:
    """根据号码前缀判断类型：手机/固话/服务热线"""
    if phone.startswith(('400', '800')):
        return '服务热线'
    if phone.startswith('0'):
        return '固话'
    return '手机'


def export_excel(company: str, phones: list[str], sources: list[dict], output_path: str) -> str:
    """导出结果为 Excel 文件"""
    from openpyxl import Workbook
    path = Path(output_path)
    if path.is_dir() or path.suffix == '':
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', company)
        path = path / f"{safe_name}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "电话列表"
    ws.append(['电话', '类型', '来源URL', '来源标题', '警告'])
    for phone in phones:
        related = [s for s in sources if s['phone'] == phone]
        if related:
            for s in related:
                ws.append([
                    phone,
                    _classify_phone(phone),
                    s.get('url', ''),
                    s.get('title', ''),
                    s.get('warning', ''),
                ])
        else:
            ws.append([phone, '', '', '', ''])
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 50
    ws.column_dimensions['D'].width = 40
    wb.save(str(path))
    return str(path)


def export_csv(company: str, phones: list[str], sources: list[dict], output_path: str) -> str:
    """导出结果为 CSV 文件"""
    import csv
    from pathlib import Path
    path = Path(output_path)
    if path.is_dir():
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', company)
        path = path / f"{safe_name}.csv"
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['电话', '类型', '来源URL', '来源标题', '警告'])
        for phone in phones:
            # 找所有该电话的来源
            related = [s for s in sources if s['phone'] == phone]
            if related:
                for s in related:
                    writer.writerow([
                        phone,
                        _classify_phone(phone),
                        s.get('url', ''),
                        s.get('title', ''),
                        s.get('warning', ''),
                    ])
            else:
                writer.writerow([phone, '', '', '', ''])
    return str(path)


# ===== 批量搜索 Excel 增强导出 =====

_CONFIDENCE_LEVELS = {
    "招标数据库": "高",
    "百度地图POI": "高",
    "百度地图官方API": "高",
    "企查查": "高",
    "天眼查": "高",
    "顺企网": "中",
    "AI搜索": "中",
}


def _get_confidence(source: str) -> str:
    """根据来源名称判断可信度"""
    for prefix, level in _CONFIDENCE_LEVELS.items():
        if source.startswith(prefix):
            return level
    return "低"


def export_batch_excel(companies_results: list[dict], output_path: str) -> str:
    """
    批量搜索 Excel 增强导出 — 三工作表输出。

    companies_results: [{"company": "xxx", "phones": [...], "sources": [...], ...}, ...]
    工作表1: 搜索结果（公司名/电话/类型/来源/可信度）
    工作表2: 统计汇总（成功率/平均电话数/各引擎统计）
    工作表3: 未找到（未搜到电话的公司列表）
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")

    # ===== Sheet 1: 搜索结果 =====
    ws1 = wb.active
    ws1.title = "搜索结果"
    headers1 = ["公司名称", "电话", "类型", "来源", "可信度"]
    ws1.append(headers1)
    for cell in ws1[1]:
        cell.font = header_font
        cell.fill = header_fill
    ws1.auto_filter.ref = "A1:E1"

    for cr in companies_results:
        company = cr.get("company", "")
        phones = cr.get("phones", [])
        sources = cr.get("sources", [])
        if not phones:
            ws1.append([company, "（未找到）", "", "", ""])
            continue
        for phone in phones:
            # 找匹配的来源
            matched = [s for s in sources if s.get("phone") == phone]
            if matched:
                for s in matched:
                    src_name = s.get("source", "")
                    ws1.append([
                        company, phone, _classify_phone(phone),
                        src_name, _get_confidence(src_name),
                    ])
            else:
                ws1.append([company, phone, _classify_phone(phone), "", ""])

    ws1.column_dimensions['A'].width = 30
    ws1.column_dimensions['B'].width = 20
    ws1.column_dimensions['C'].width = 10
    ws1.column_dimensions['D'].width = 30
    ws1.column_dimensions['E'].width = 10

    # ===== Sheet 2: 统计汇总 =====
    ws2 = wb.create_sheet("统计汇总")
    ws2.append(["指标", "数值"])
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = header_fill

    total = len(companies_results)
    found = sum(1 for cr in companies_results if cr.get("phones"))
    not_found = total - found
    all_phones = [p for cr in companies_results for p in cr.get("phones", [])]
    avg_phones = len(all_phones) / total if total > 0 else 0
    success_rate = (found / total * 100) if total > 0 else 0

    ws2.append(["搜索公司总数", total])
    ws2.append(["找到电话", found])
    ws2.append(["未找到电话", not_found])
    ws2.append(["成功率", f"{success_rate:.1f}%"])
    ws2.append(["电话总数", len(all_phones)])
    ws2.append(["平均电话数", f"{avg_phones:.1f}"])

    # 按来源统计
    source_counts = {}
    for cr in companies_results:
        for s in cr.get("sources", []):
            src = s.get("source", "未知").split("/")[0]
            source_counts[src] = source_counts.get(src, 0) + 1
    if source_counts:
        ws2.append([])
        ws2.append(["来源分布", "数量"])
        for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
            ws2.append([src, cnt])

    ws2.column_dimensions['A'].width = 20
    ws2.column_dimensions['B'].width = 15

    # ===== Sheet 3: 未找到 =====
    ws3 = wb.create_sheet("未找到")
    ws3.append(["公司名称", "备注"])
    for cell in ws3[1]:
        cell.font = header_font
        cell.fill = header_fill
    for cr in companies_results:
        if not cr.get("phones"):
            ws3.append([cr.get("company", ""), "未找到任何电话"])

    ws3.column_dimensions['A'].width = 30
    ws3.column_dimensions['B'].width = 20

    # 保存
    path = Path(output_path)
    if path.is_dir() or path.suffix == '':
        path = path / "batch_results.xlsx"
    wb.save(str(path))
    return str(path)
