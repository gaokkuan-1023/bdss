"""
BDSS 电话提取器单元测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extractors.phone import PhoneExtractor


def test_mobile_phone():
    pe = PhoneExtractor()
    assert "13800138000" in pe.extract("联系电话：13800138000")
    assert "13912345678" in pe.extract("手机 13912345678")
    assert "15000001111" in pe.extract("联系手机：15000001111")


def test_landline():
    pe = PhoneExtractor()
    phones = pe.extract("Tel: 010-88886666")
    assert any("010-88886666" in p for p in phones), f"Got: {phones}"
    phones = pe.extract("电话：0755-86013388")
    assert any("0755-86013388" in p for p in phones), f"Got: {phones}"


def test_service_hotline():
    pe = PhoneExtractor()
    phones = pe.extract("客服热线：400-123-4567")
    assert any("400-123-4567" in p for p in phones), f"Got: {phones}"
    phones = pe.extract("服务热线 800-123-4567")
    assert any("800" in p for p in phones), f"Got: {phones}"


def test_international():
    pe = PhoneExtractor()
    phones = pe.extract("+86 13800138000")
    assert any("13800138000" in p for p in phones), f"Got: {phones}"


def test_multiple_phones():
    pe = PhoneExtractor()
    text = """
    公司名称：测试有限公司
    电话：010-88886666
    手机：13800138000
    客服：400-123-4567
    """
    phones = pe.extract(text)
    assert len(phones) >= 3, f"Expected >=3 phones, got {phones}"
    assert "010-88886666" in phones
    assert "13800138000" in phones


def test_no_phones():
    pe = PhoneExtractor()
    phones = pe.extract("这是一段没有任何电话号码的文本")
    assert phones == [], f"Expected empty, got {phones}"


def test_extract_all():
    pe = PhoneExtractor()
    results = pe.extract_all("手机 13800138000，座机 010-88886666")
    types = {r["type"] for r in results}
    assert "mobile" in types, f"No mobile found: {results}"
    assert "landline" in types, f"No landline found: {results}"


def test_nearby_keywords():
    pe = PhoneExtractor(prefer_nearby=True)
    text = """联系我们
电话：13800138000
地址：北京市朝阳区"""
    phones = pe.extract(text)
    assert "13800138000" in phones, f"Expected phone, got {phones}"


def test_format_confusing_numbers():
    """应过滤掉明显不是电话号码的噪声"""
    pe = PhoneExtractor()
    text = "版本号 v1.0.0.1 已发布，更新时间 2024-01-15"
    phones = pe.extract(text)
    assert phones == [], f"Expected no phones from noise, got {phones}"


def test_phone_dedup():
    pe = PhoneExtractor()
    text = "电话：13800138000，手机：13800138000（同号）"
    phones = pe.extract(text)
    assert phones.count("13800138000") == 1, f"Duplicate not deduped: {phones}"


if __name__ == "__main__":
    test_mobile_phone()
    test_landline()
    test_service_hotline()
    test_international()
    test_multiple_phones()
    test_no_phones()
    test_extract_all()
    test_nearby_keywords()
    test_format_confusing_numbers()
    test_phone_dedup()
    print("✅ All 10 tests passed!")
