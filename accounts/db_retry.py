# -*- coding: utf-8 -*-
"""
数据库写操作在 SQLite 并发下可能遇到 OperationalError (database is locked)。
对写手发布流程等关键写操作做有限次重试，避免因短暂锁等待导致丢失操作记录。
"""
import time
import functools
from django.db import OperationalError


def retry_on_db_locked(max_retries=3, delay=0.5):
    """装饰器：对视图函数在发生 OperationalError 时重试，保证高并发下尽量不丢数据。"""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return view_func(request, *args, **kwargs)
                except OperationalError as e:
                    last_exc = e
                    if attempt < max_retries:
                        time.sleep(delay)
                        continue
                    raise
            if last_exc is not None:
                raise last_exc
        return wrapper
    return decorator
