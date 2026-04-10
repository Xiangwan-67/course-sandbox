# 用户类：标题党四方博弈沙盘 - 读者/用户实体
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from article import Article
    from writer import Writer


class User(ABC):
    """用户类：读者属性及阅读、换平台等行为。"""

    def __init__(
        self,
        uid: int,
        name: str,
        gender: str = "",
        age: int = 0,
        interest: str = "",
        platform_id: int = 0,
    ) -> None:
        self.uid: int = uid
        self.name: str = name
        self.gender: str = gender
        self.age: int = age
        self.interest: str = interest  # 感兴趣的领域，可选
        self.platform_id: int = platform_id  # 平台 id
        self.following_writers: List["Writer"] = []  # 关注写手列表

    @abstractmethod
    def read_article(
        self,
        follow_article: List["Article"],
        random_article: List["Article"],
    ) -> None:
        """阅读文章。衡量点击率、阅读完成率、收藏率，更新文章数据。"""
        ...

    @abstractmethod
    def transform_platform(self) -> None:
        """转换平台。"""
        ...
