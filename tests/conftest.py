"""pytest 全局 fixtures"""
import os
import sys
import tempfile
import shutil
import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置测试环境变量
os.environ["BAIDU_MAP_AK"] = ""
os.environ["BDSS_AI_API_KEY"] = ""
os.environ["QCC_API_KEY"] = ""
os.environ["QCC_SECRET_KEY"] = ""


@pytest.fixture
def tmp_dir():
    """临时目录，测试结束后自动清理"""
    d = tempfile.mkdtemp(prefix="bdss_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_phones():
    """测试用电话数据"""
    return {
        "mobile": "13800138000",
        "landline": "0531-88888888",
        "hotline_400": "400-123-4567",
        "hotline_800": "800-888-9999",
    }


@pytest.fixture
def sample_company():
    return "深圳腾讯计算机系统有限公司"


@pytest.fixture
def sample_sources():
    return [
        {"phone": "13800138000", "url": "http://example.com", "title": "测试来源", "warning": ""},
    ]
