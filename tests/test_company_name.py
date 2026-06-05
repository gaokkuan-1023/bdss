"""utils/company_name pytest 测试"""
import pytest
from utils.company_name import normalize, shorten, get_key, is_similar, deduplicate


class TestNormalize:
    def test_fullwidth_brackets(self):
        assert "(" in normalize("公司（普通合伙）")
    
    def test_strip_spaces(self):
        assert normalize("  公司名  ") == "公司名"
    
    def test_multi_spaces(self):
        assert "  " not in normalize("公司  名称")


class TestShorten:
    def test_remove_suffix(self):
        s = shorten("北京某某科技有限公司")
        assert "有限公司" not in s
    
    def test_remove_prefix(self):
        s = shorten("山东省某某公司")
        assert not s.startswith("山东省")
    
    def test_remove_brackets(self):
        s = shorten("某某科技(普通合伙)")
        assert "(" not in s


class TestSimilar:
    def test_same_company(self):
        assert is_similar("某某科技有限公司", "某某科技")
    
    def test_different_company(self):
        assert not is_similar("腾讯科技", "阿里巴巴")


class TestDeduplicate:
    def test_exact_dup(self):
        result = deduplicate(["某某科技有限公司", "某某科技有限公司"])
        assert len(result) == 1
    
    def test_similar_dup(self):
        result = deduplicate(["某某科技有限公司", "某某科技"])
        assert len(result) == 1
    
    def test_no_dup(self):
        result = deduplicate(["腾讯科技", "阿里巴巴"])
        assert len(result) == 2
