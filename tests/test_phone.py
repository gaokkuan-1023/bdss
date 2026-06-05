"""PhoneExtractor pytest 测试"""
import pytest
from extractors.phone import PhoneExtractor


class TestExtract:
    """电话提取测试"""
    
    def setup_method(self):
        self.pe = PhoneExtractor(prefer_nearby=True)
    
    def test_mobile(self):
        phones = self.pe.extract("请拨打13800138000联系我们")
        assert "13800138000" in phones
    
    def test_landline(self):
        phones = self.pe.extract("办公电话0531-88888888")
        assert any("0531" in p for p in phones)
    
    def test_400_hotline(self):
        phones = self.pe.extract("客服热线400-123-4567")
        assert any("400" in p for p in phones)
    
    def test_800_hotline(self):
        phones = self.pe.extract("免费电话800-888-9999")
        assert any("800" in p for p in phones)
    
    def test_dedup(self):
        phones = self.pe.extract("电话13800138000，也是13800138000")
        assert phones.count("13800138000") == 1
    
    def test_international(self):
        phones = self.pe.extract("联系 +86-13912345678")
        assert any("13912345678" in p for p in phones)
    
    def test_empty_text(self):
        phones = self.pe.extract("")
        assert phones == []
    
    def test_no_phones(self):
        phones = self.pe.extract("这是一段没有电话的文本")
        assert phones == []


class TestValidate:
    """电话验证测试"""
    
    def test_valid_mobile(self):
        v = PhoneExtractor.validate("13800138000")
        assert v["valid"] is True
        assert v["type"] == "mobile"
    
    def test_valid_landline(self):
        v = PhoneExtractor.validate("053188888888")
        assert v["type"] == "landline"
    
    def test_valid_400(self):
        v = PhoneExtractor.validate("4001234567")
        assert v["type"] == "service"
        assert v["valid"] is True
    
    def test_too_short(self):
        v = PhoneExtractor.validate("123")
        assert v["valid"] is False


class TestCarrier:
    """运营商识别测试"""
    
    def test_china_mobile(self):
        carrier = PhoneExtractor._get_mobile_carrier("1380013")
        assert "移动" in carrier
    
    def test_china_unicom(self):
        carrier = PhoneExtractor._get_mobile_carrier("1300013")
        assert "联通" in carrier
    
    def test_china_telecom(self):
        carrier = PhoneExtractor._get_mobile_carrier("1330013")
        assert "电信" in carrier


class TestAreaCode:
    """区号城市匹配测试"""
    
    def test_beijing(self):
        assert PhoneExtractor._get_area_name("010") == "北京"
    
    def test_shanghai(self):
        assert PhoneExtractor._get_area_name("021") == "上海"
    
    def test_jinan(self):
        assert PhoneExtractor._get_area_name("0531") == "济南"
    
    def test_unknown(self):
        assert PhoneExtractor._get_area_name("0000") == ""
