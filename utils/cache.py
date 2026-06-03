"""
BDSS 结果缓存 — 基于 SQLite

自动缓存公司搜索结果，相同查询直接返回缓存结果，避免重复请求。

使用：
    from utils.cache import SearchCache
    cache = SearchCache()
    cache.get(company, engine)  # 命中返回 dict, 否则 None
    cache.set(company, engine, result)  # 存入缓存
"""
import json
import sqlite3
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 默认缓存有效期（秒）：24 小时
DEFAULT_TTL = 86400


class SearchCache:
    """公司搜索结果缓存"""

    def __init__(self, db_path: Optional[str] = None, ttl: int = DEFAULT_TTL):
        self._db_path = db_path or str(Path(__file__).parent.parent / ".bdss_cache.db")
        self._ttl = ttl
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    company TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    result TEXT NOT NULL,
                    cached_at REAL NOT NULL,
                    PRIMARY KEY (company, engine)
                )
            """)
            self._conn.commit()
        return self._conn

    def get(self, company: str, engine: str) -> Optional[dict]:
        """获取缓存结果，过期返回 None"""
        row = self.conn.execute(
            "SELECT result, cached_at FROM search_cache WHERE company=? AND engine=?",
            (company, engine),
        ).fetchone()
        if not row:
            return None
        result_json, cached_at = row
        if time.time() - cached_at > self._ttl:
            logger.debug(f"[cache] 过期: {company} ({engine})")
            self.delete(company, engine)
            return None
        logger.info(f"[cache] 命中: {company} ({engine})")
        return json.loads(result_json)

    def set(self, company: str, engine: str, result: dict):
        """存入缓存"""
        self.conn.execute(
            "INSERT OR REPLACE INTO search_cache (company, engine, result, cached_at) VALUES (?, ?, ?, ?)",
            (company, engine, json.dumps(result, ensure_ascii=False), time.time()),
        )
        self.conn.commit()
        logger.debug(f"[cache] 写入: {company} ({engine})")

    def delete(self, company: str, engine: str):
        """删除指定缓存"""
        self.conn.execute(
            "DELETE FROM search_cache WHERE company=? AND engine=?",
            (company, engine),
        )
        self.conn.commit()

    def clear_expired(self):
        """清理过期缓存"""
        self.conn.execute("DELETE FROM search_cache WHERE cached_at < ?",
                          (time.time() - self._ttl,))
        self.conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
