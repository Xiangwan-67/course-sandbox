# 写手类：标题党四方博弈沙盘 - 创作者实体
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from article import Article
    from user import User


class Writer(ABC):
    """写手类：创作者属性及生成标题/内容、发布、核算收入等行为。"""

    def __init__(
        self,
        wid: int,
        name: str,
        account_type: str = "",
        personality: str = "",
        attitude: str = "",
        platform_id: int = 0,
    ) -> None:
        self.wid: int = wid
        self.name: str = name
        self.history_articles: List[List["Article"]] = []  # 历史文章，每轮一个文章列表
        self.fans: List["User"] = []  # 粉丝列表
        self.account_type: str = account_type  # 写手账号类型，如教育类、游戏类
        self.personality: str = personality  # 性格文本描述--问卷1
        self.attitude: str = attitude  # 态度文本描述--问卷2
        self.platform_id: int = platform_id  # 平台 id
        # 文章策略轨迹：每元素为 [x,y,z,m] 标题夸张度滑块/实际值、内容相关度滑块/实际值
        self.strategy_trajectory: List[List[float]] = []

    @abstractmethod
    def generate_title(self) -> str:
        """根据写手输入的标题夸张度滑块值，生成标题。"""
        ...

    @abstractmethod
    def generate_content(self) -> str:
        """根据写手输入的内容相关度滑块值，生成内容。"""
        ...

    @abstractmethod
    def broadcast_article(self) -> "Article":
        """发布文章。"""
        ...

    @abstractmethod
    def check_income(self, rule: Any) -> float:
        """根据历史文章属性和平台绩效规则，计算写手收入。"""
        ...
