"""通用重试装饰器 + 简易熔断器"""
import functools
import logging
import time
import threading
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable = None,
):
    """
    重试装饰器，支持指数退避。
    
    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟（秒）
        backoff: 退避倍数
        exceptions: 需要重试的异常类型
        on_retry: 重试回调 (func, attempt, exception) -> None
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.debug(f"[retry] {func.__name__} 第{attempt}次失败: {e}, {current_delay:.1f}s后重试")
                        if on_retry:
                            on_retry(func, attempt, e)
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.warning(f"[retry] {func.__name__} 已达最大重试次数({max_attempts}): {e}")
            raise last_exception
        return wrapper
    return decorator


class CircuitBreaker:
    """
    简易熔断器 — 连续失败 N 次后暂停一段时间。
    
    状态:
      CLOSED   — 正常放行
      OPEN     — 熔断中，直接拒绝
      HALF_OPEN — 冷却期满，允许一次试探
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = self.CLOSED
        self._lock = threading.Lock()
    
    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
            return self._state
    
    def call(self, func: Callable, *args, **kwargs):
        """通过熔断器调用函数"""
        state = self.state
        if state == self.OPEN:
            raise CircuitBreakerOpenError(
                f"熔断器开启，{self.recovery_timeout - (time.time() - self._last_failure_time):.0f}s后恢复"
            )
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED
    
    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                logger.warning(f"[circuit] 连续失败{self._failure_count}次，熔断{self.recovery_timeout}s")


class CircuitBreakerOpenError(Exception):
    """熔断器开启时抛出"""
    pass
