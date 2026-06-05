"""utils/retry pytest 测试"""
import time
import pytest
from utils.retry import retry, CircuitBreaker, CircuitBreakerOpenError


class TestRetry:
    def test_success_first_try(self):
        @retry(max_attempts=3, delay=0.01)
        def ok():
            return 42
        assert ok() == 42
    
    def test_success_after_retry(self):
        counter = {"n": 0}
        @retry(max_attempts=3, delay=0.01)
        def fail_then_ok():
            counter["n"] += 1
            if counter["n"] < 3:
                raise ValueError("not yet")
            return "ok"
        assert fail_then_ok() == "ok"
        assert counter["n"] == 3
    
    def test_max_attempts_exceeded(self):
        @retry(max_attempts=2, delay=0.01)
        def always_fail():
            raise RuntimeError("fail")
        with pytest.raises(RuntimeError, match="fail"):
            always_fail()
    
    def test_specific_exception(self):
        @retry(max_attempts=3, delay=0.01, exceptions=(ValueError,))
        def type_error():
            raise TypeError("wrong type")
        with pytest.raises(TypeError):
            type_error()


class TestCircuitBreaker:
    def test_normal_operation(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.state == CircuitBreaker.CLOSED
    
    def test_opens_after_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass
        assert cb.state == CircuitBreaker.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: 42)
    
    def test_recovery(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2)
        for _ in range(2):
            try:
                cb.call(lambda: 1/0)
            except ZeroDivisionError:
                pass
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.3)
        assert cb.state == CircuitBreaker.HALF_OPEN
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitBreaker.CLOSED
