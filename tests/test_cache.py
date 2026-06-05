"""SearchCache pytest 测试"""
import os
import time
import pytest
from utils.cache import SearchCache


class TestSearchCache:
    
    def setup_method(self, tmp_path=None):
        self.tmpdir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "bdss_cache_test")
        os.makedirs(self.tmpdir, exist_ok=True)
        self.db_path = os.path.join(self.tmpdir, "test.db")
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_set_and_get(self):
        cache = SearchCache(db_path=self.db_path)
        cache.set("测试公司", "baidu", {"phones": ["13800138000"]})
        result = cache.get("测试公司", "baidu")
        assert result is not None
        assert result["phones"] == ["13800138000"]
        cache.close()
    
    def test_cache_miss(self):
        cache = SearchCache(db_path=self.db_path)
        result = cache.get("不存在", "baidu")
        assert result is None
        cache.close()
    
    def test_ttl_expired(self):
        cache = SearchCache(db_path=self.db_path, ttl=0)
        cache.set("过期", "baidu", {"phones": []})
        time.sleep(0.1)
        result = cache.get("过期", "baidu")
        assert result is None
        cache.close()
    
    def test_delete(self):
        cache = SearchCache(db_path=self.db_path)
        cache.set("删除", "baidu", {"data": 1})
        cache.delete("删除", "baidu")
        assert cache.get("删除", "baidu") is None
        cache.close()
    
    def test_clear_expired(self):
        cache = SearchCache(db_path=self.db_path)
        cache.clear_expired()  # 不应抛异常
        cache.close()
