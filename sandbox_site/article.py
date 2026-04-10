# 文章类：标题党四方博弈沙盘 - 文章实体
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from writer import Writer
    from user import User


class Article:
    """文章类：存储单篇文章的作者、标题、内容及阅读相关指标。"""

    def __init__(
        self,
        author: "Writer",
        title: str = "",
        content: str = "",
        publish_date: str = "",
        title_exaggeration: float = 0.0,
        content_relevance: float = 0.0,
    ) -> None:
        self.author: "Writer" = author
        self.title: str = title
        self.content: str = content
        self.readers: List["User"] = []
        self.publish_date: str = publish_date  # 发布日期（仅精确到周）
        self.click_rate: float = 0.0  # 点击率 [0, 1]
        self.collect_rate: float = 0.0  # 收藏率 [0, 1]
        self.completion_rate: float = 0.0  # 阅读完成率 [0, 1]
        self.title_exaggeration: float = title_exaggeration  # 标题夸张度 [0, 1]
        self.content_relevance: float = content_relevance  # 内容相关度 [0, 1]
        self.push_targets: Dict[int, bool] = {}  # 键：用户编号；值：用户是否点击文章
