"""
ConcurrencySemaphore — Sub-Agent 并发控制

限制同时运行的 Sub-Agent 数量，确保不超过 MAX_CONCURRENT_AGENTS。
MasterAgent 在 dispatch_task() 前调用 try_acquire() 或使用 with 语句，
任务完成后调用 release() 释放槽位。

使用方式：
    sem = ConcurrencySemaphore(max_count=3)
    if sem.try_acquire():
        try:
            agent = factory.create(role_name)
            agent.run(task)
        finally:
            sem.release()

    # 或使用上下文管理器
    with sem:
        agent = factory.create(role_name)
        agent.run(task)
"""

import logging
from threading import Lock

logger = logging.getLogger(__name__)


class ConcurrencySemaphore:
    """Sub-Agent 并发信号量

    控制同时运行的 Sub-Agent 数量上限。
    线程安全：通过 threading.Lock 保护内部计数。

    Attributes:
        max_count: 最大并发 Agent 数
        available: 当前可用槽位数
        active_count: 当前活跃 Agent 数
    """

    def __init__(self, max_count: int = 3) -> None:
        """初始化并发信号量

        Args:
            max_count: 最大并发 Agent 数（必须 >= 1）

        Raises:
            ValueError: max_count <= 0
        """
        if max_count <= 0:
            raise ValueError(
                f"max_count must be positive, got {max_count}"
            )
        self._max_count = max_count
        self._available = max_count
        self._lock = Lock()

    # ── 属性 ──────────────────────────────────────────────

    @property
    def max_count(self) -> int:
        """最大并发数"""
        return self._max_count

    @property
    def available(self) -> int:
        """当前可用槽位数"""
        return self._available

    @property
    def active_count(self) -> int:
        """当前活跃 Agent 数"""
        return self._max_count - self._available

    @property
    def is_full(self) -> bool:
        """是否已达最大并发"""
        return self._available <= 0

    @property
    def is_empty(self) -> bool:
        """是否无活跃 Agent"""
        return self._available >= self._max_count

    # ── 核心方法 ──────────────────────────────────────────

    def acquire(self) -> None:
        """获取一个并发槽位（阻塞）

        如果没有可用槽位，抛出 RuntimeError。
        通常用法是先用 try_acquire() 检查，或用 with 语句。

        Raises:
            RuntimeError: 无可用槽位
        """
        with self._lock:
            if self._available <= 0:
                raise RuntimeError(
                    f"No available slots (max={self._max_count}, "
                    f"active={self.active_count})"
                )
            self._available -= 1
            logger.debug(
                "Semaphore acquired (available=%d/%d)",
                self._available,
                self._max_count,
            )

    def try_acquire(self) -> bool:
        """尝试获取并发槽位（非阻塞）

        Returns:
            True 获取成功，False 无可用槽位
        """
        with self._lock:
            if self._available <= 0:
                return False
            self._available -= 1
            logger.debug(
                "Semaphore acquired via try (available=%d/%d)",
                self._available,
                self._max_count,
            )
            return True

    def release(self) -> None:
        """释放一个并发槽位

        即使 available == max_count，调用也不会抛异常（幂等）。
        """
        with self._lock:
            if self._available < self._max_count:
                self._available += 1
                logger.debug(
                    "Semaphore released (available=%d/%d)",
                    self._available,
                    self._max_count,
                )
            else:
                logger.debug(
                    "Semaphore release skipped (already at max)"
                )

    def reset(self) -> None:
        """重置信号量到初始状态（满槽位）"""
        with self._lock:
            self._available = self._max_count
            logger.debug(
                "Semaphore reset to %d/%d",
                self._available,
                self._max_count,
            )

    # ── 上下文管理器 ──────────────────────────────────────

    def __enter__(self) -> "ConcurrencySemaphore":
        """进入上下文：获取槽位"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文：释放槽位（即使抛异常）"""
        self.release()
        return False  # 不吞异常
