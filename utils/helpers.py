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


def extract_nearby_phone(text: str, keywords: list[str] = None) -> list[str]:
    """已废弃，请使用 PhoneExtractor.extract()"""
    return _phone_extractor.extract(text)


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
                        '手机' if not phone.startswith('0') and not phone.startswith('4') else '固话' if phone.startswith('0') else '服务热线',
                        s.get('url', ''),
                        s.get('title', ''),
                        s.get('warning', ''),
                    ])
            else:
                writer.writerow([phone, '', '', '', ''])
    return str(path)
