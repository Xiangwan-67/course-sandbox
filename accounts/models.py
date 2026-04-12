# -*- coding: utf-8 -*-
from django.db import models
from decimal import Decimal


class WriterAccount(models.Model):
    """写手账号，对应 Excel Sheet1，存储到表「写手」。"""
    账号 = models.CharField(max_length=64, unique=True)
    密码 = models.CharField(max_length=128)
    # 所属平台：0=平台1, 1=平台2，与用户表含义一致，默认平台1
    所属平台 = models.IntegerField(default=0)
    # 粉丝数：关注该写手的用户数量，用户关注/取关时同步更新
    粉丝数 = models.PositiveIntegerField(default=0)
    # 账号健康分：跨轮次累计，默认 100
    健康分 = models.IntegerField(default=100)
    health_tier = models.CharField(max_length=50, blank=True, default='')
    推流系数 = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1.0000'))
    健康分最近更新轮次 = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = '写手'
        verbose_name = '写手'
        verbose_name_plural = '写手'


class UserAccount(models.Model):
    """用户账号，对应 Excel Sheet2，存储到表「用户」。"""
    # 所属平台：0=平台1, 1=平台2
    所属平台 = models.IntegerField(default=0)
    账号 = models.CharField(max_length=64, unique=True)
    密码 = models.CharField(max_length=128)
    # 切换平台后 1 分钟内禁止登录，记录截止时间
    禁止登录截止时间 = models.DateTimeField(null=True, blank=True)
    # 关注数：当前用户关注的写手数量，关注/取关时同步更新
    关注数 = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = '用户'
        verbose_name = '用户'
        verbose_name_plural = '用户'


class PlatformAccount(models.Model):
    """平台负责人账号：用于登录进入平台页面。"""
    账号 = models.CharField(max_length=64, unique=True)
    密码 = models.CharField(max_length=128)
    # 所属平台：0=平台1, 1=平台2
    所属平台 = models.IntegerField(default=0)

    class Meta:
        db_table = '平台账号'
        verbose_name = '平台账号'
        verbose_name_plural = '平台账号'


class ProfitWeightConfig(models.Model):
    """平台利润计算：因子权重配置（管理员维护，按平台独立配置）。"""

    平台 = models.IntegerField(null=True, blank=True)  # 0=平台1, 1=平台2；null 表示旧全局配置

    生效轮次起 = models.PositiveIntegerField(default=1)
    生效轮次止 = models.PositiveIntegerField(null=True, blank=True)

    点击率权重 = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    收藏率权重 = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    阅读完成率权重 = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    平台粉丝数权重 = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    监管成本权重 = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    利润展示窗口轮数 = models.PositiveIntegerField(default=4)
    配置人 = models.CharField(max_length=100, blank=True)
    配置时间 = models.DateTimeField(null=True, blank=True)
    备注 = models.TextField(blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '平台利润权重配置'
        verbose_name = '平台利润权重配置'
        verbose_name_plural = '平台利润权重配置'
        ordering = ['-创建时间', '-id']


class PlatformCycleProfitRecord(models.Model):
    """平台周期利润记录（每周期末一次性计算）。"""

    platform_id = models.IntegerField()
    cycle_index = models.PositiveIntegerField()  # 第几个周期
    cycle_start_round = models.PositiveIntegerField()
    cycle_end_round = models.PositiveIntegerField()

    total_click = models.PositiveIntegerField(default=0)
    total_collect = models.PositiveIntegerField(default=0)
    total_finish = models.PositiveIntegerField(default=0)
    fans_snapshot = models.PositiveIntegerField(default=0)

    supervision_cost_level = models.CharField(max_length=32, blank=True)
    supervision_cost_value = models.DecimalField(max_digits=18, decimal_places=6, default=0)

    profit_total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    profit_prev_cycle = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    calculated_at = models.DateTimeField(auto_now_add=True)
    weight_config_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '平台周期利润记录'
        verbose_name = '平台周期利润记录'
        verbose_name_plural = '平台周期利润记录'
        unique_together = [['platform_id', 'cycle_index']]
        ordering = ['-cycle_index', 'platform_id', '-id']


class PlatformGovernanceMeasure(models.Model):
    """平台治理措施发布记录（平台负责人发布后进入通知栏）。"""

    MEASURE_TYPE_CHOICES = [
        ('account_health_rule', '账号健康分规则'),
        ('clickbait_detection', '标题党检测'),
        ('user_report', '用户举报机制'),
        ('traffic_penalty', '流量惩罚'),
        ('revenue_penalty', '收益惩罚'),
        ('performance_rule', '绩效规则'),
    ]

    平台 = models.IntegerField()  # 0=平台1, 1=平台2
    轮次 = models.PositiveIntegerField()
    生效轮次 = models.PositiveIntegerField(default=1)
    取消轮次 = models.PositiveIntegerField(null=True, blank=True)
    措施类型 = models.CharField(max_length=64, choices=MEASURE_TYPE_CHOICES)
    措施内容 = models.JSONField(default=dict, blank=True)  # 规则细则占位
    config_id = models.IntegerField(null=True, blank=True)  # 指向各功能包参数子表 PK
    发布人账号 = models.CharField(max_length=64, blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '平台治理措施记录'
        verbose_name = '平台治理措施记录'
        verbose_name_plural = '平台治理措施记录'
        ordering = ['-轮次', '-创建时间', '-id']


class AccountHealthLevelConfig(models.Model):
    """账号健康分档位与推流比例配置（管理员维护）。

    区间为“前开后闭”：(下界开, 上界闭]。
    可推流比例用于发现列表推送抽样比例（0~1）。
    """

    生效轮次起 = models.PositiveIntegerField(default=1)
    生效轮次止 = models.PositiveIntegerField(null=True, blank=True)

    下界开 = models.IntegerField(default=0)
    上界闭 = models.IntegerField(default=100)
    可推流比例 = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal('0.7000'))
    排序 = models.PositiveIntegerField(default=0)
    备注 = models.TextField(blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '账号健康分档位配置'
        verbose_name = '账号健康分档位配置'
        verbose_name_plural = '账号健康分档位配置'
        ordering = ['排序', '下界开', '上界闭', '-id']


class WriterNoticeRead(models.Model):
    """写手平台通知已读记录（用于红点提示）。"""

    写手账号 = models.CharField(max_length=64)
    通知 = models.ForeignKey(PlatformGovernanceMeasure, on_delete=models.CASCADE, related_name='已读记录')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '写手通知已读'
        verbose_name = '写手通知已读'
        verbose_name_plural = '写手通知已读'
        unique_together = [['写手账号', '通知']]
        ordering = ['-read_at', '-id']


class WriterHealthScoreLog(models.Model):
    """写手健康分变更审计（例如标题党命中扣分）。"""

    写手账号 = models.CharField(max_length=64)
    轮次 = models.PositiveIntegerField()
    文章编号 = models.PositiveIntegerField(null=True, blank=True)
    变更值 = models.IntegerField()
    原因 = models.CharField(max_length=128, blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '写手健康分变更审计'
        verbose_name = '写手健康分变更审计'
        verbose_name_plural = '写手健康分变更审计'
        ordering = ['-创建时间', '-id']


class PlatformPerformanceScheme(models.Model):
    """平台绩效规则（方案）选择记录。

    说明：该方案后续将联动写手文章报酬计算函数；当前先做“可选方案 + 记录生效轮次 + 回显”。
    """

    SCHEME_CODE_CHOICES = [
        ('S1_balanced', '方案1：均衡'),
        ('S2_click_first', '方案2：点击优先'),
        ('S3_quality_first', '方案3：质量优先'),
    ]

    平台 = models.IntegerField()  # 0=平台1, 1=平台2
    生效轮次 = models.PositiveIntegerField()
    方案编号 = models.CharField(max_length=64, choices=SCHEME_CODE_CHOICES)
    方案内容 = models.JSONField(default=dict, blank=True)  # 预留：未来可存放对报酬函数的权重调整等
    发布人账号 = models.CharField(max_length=64, blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '平台绩效方案记录'
        verbose_name = '平台绩效方案记录'
        verbose_name_plural = '平台绩效方案记录'
        ordering = ['-生效轮次', '-创建时间', '-id']


class SimulationRound(models.Model):
    """模拟轮次：单行表（id=1），存储当前轮次。用户阶段结束后「结束本轮」将当前轮次+1，实现清空列表（不删库）。"""
    当前轮次 = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = '模拟轮次'
        verbose_name = '模拟轮次'
        verbose_name_plural = '模拟轮次'


class Article(models.Model):
    """写手发布的文章，记录选中标题/正文及对应夸张度、相关度的初始值与校准值。"""
    写手账号 = models.CharField(max_length=64)
    轮次 = models.PositiveIntegerField(default=1)  # 发布时所处模拟轮次，用户列表只展示本轮
    标题 = models.TextField(blank=True)
    标题夸张度_初始值 = models.IntegerField(null=True, blank=True)   # 写手拖动滑块后点「提交」时的夸张度
    标题夸张度_校准值 = models.IntegerField(null=True, blank=True)   # 写手选中的标题对应的实际夸张度
    正文 = models.TextField(blank=True)
    内容相关度_初始值 = models.IntegerField(null=True, blank=True)   # 写手拖动滑块后点「提交」时的相关度
    内容相关度_校准值 = models.IntegerField(null=True, blank=True)   # 写手选中的正文对应的实际相关度
    创建时间 = models.DateTimeField(auto_now_add=True)
    # 文章数据：已推送用户数、点击量、点赞量、收藏量、吸粉数、取关数、阅读完成量
    已推送 = models.PositiveIntegerField(default=0)   # 推送给了几个用户
    点击量 = models.PositiveIntegerField(default=0)   # 点击标题进入正文的用户数
    点赞量 = models.PositiveIntegerField(default=0)
    收藏量 = models.PositiveIntegerField(default=0)
    吸粉数 = models.PositiveIntegerField(default=0)   # 通过该文章关注写手的用户数
    取关数 = models.PositiveIntegerField(default=0)   # 通过该文章取消关注写手的用户数
    阅读完成量 = models.PositiveIntegerField(default=0)
    报酬 = models.IntegerField(default=0)   # 该文章对应报酬，历史列表中展示

    is_clickbait = models.BooleanField(null=True, blank=True, default=None)
    clickbait_detected_at = models.IntegerField(null=True, blank=True)
    method_auto_rule = models.BooleanField(null=True, blank=True, default=None)
    method_user = models.BooleanField(null=True, blank=True, default=None)
    report_count_current_round = models.IntegerField(default=0)

    class Meta:
        db_table = '文章'
        verbose_name = '文章'
        verbose_name_plural = '文章'


class Comment(models.Model):
    """文章评论。"""
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='评论列表')
    内容 = models.TextField()
    评论者 = models.CharField(max_length=64, blank=True)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '评论'
        verbose_name = '评论'
        verbose_name_plural = '评论'


class UserFollowWriter(models.Model):
    """用户关注的写手。用户表通过反向关联 关注列表 访问本表对应行。"""
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='关注列表')
    写手账号 = models.CharField(max_length=64)

    class Meta:
        db_table = '用户关注写手'
        verbose_name = '用户关注写手'
        verbose_name_plural = '用户关注写手'
        unique_together = [['用户', '写手账号']]


class ArticlePush(models.Model):
    """文章推送记录：某文章推送到某用户的某列表（关注列表=0 / 发现列表=1），用于平台浏览展示。"""
    列表类型 = models.PositiveSmallIntegerField()  # 0=关注列表，1=发现列表
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='推送记录')
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='被推送文章')

    class Meta:
        db_table = '文章推送记录'
        unique_together = [['文章', '用户']]
        ordering = ['文章__创建时间']


class ArticlePushDetail(models.Model):
    """文章推送明细：记录每篇文章分别推送给了哪些用户，以及该用户是否为写手粉丝。"""
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='推送明细')
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='被推送文章明细')
    是否粉丝 = models.BooleanField(default=False)  # 推送时该用户是否关注了该写手

    class Meta:
        db_table = '文章推送明细'
        unique_together = [['文章', '用户']]
        verbose_name = '文章推送明细'
        verbose_name_plural = '文章推送明细'


class PlatformSwitchSurvey(models.Model):
    """切换平台问卷调查。"""
    用户编号 = models.PositiveIntegerField()  # 用户表主键 id
    切换前平台 = models.IntegerField()       # 0=平台1, 1=平台2
    切换后平台 = models.IntegerField()
    轮次 = models.PositiveIntegerField()
    切换平台原因 = models.TextField()

    class Meta:
        db_table = '切换平台问卷调查'
        verbose_name = '切换平台问卷调查'
        verbose_name_plural = '切换平台问卷调查'


class UserArticleLike(models.Model):
    """用户对文章的点赞记录，用于点赞切换。"""
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='文章点赞记录')
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='点赞用户记录')

    class Meta:
        db_table = '用户文章点赞'
        unique_together = [['用户', '文章']]


class UserArticleCollect(models.Model):
    """用户对文章的收藏记录，用于收藏切换。"""
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='文章收藏记录')
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='收藏用户记录')

    class Meta:
        db_table = '用户文章收藏'
        unique_together = [['用户', '文章']]


class UserArticleReadComplete(models.Model):
    """用户对文章的阅读完成记录，用于阅读完成切换。"""
    用户 = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='文章阅读完成记录')
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='阅读完成用户记录')

    class Meta:
        db_table = '用户文章阅读完成'
        unique_together = [['用户', '文章']]


class UnfollowSurvey(models.Model):
    """取关/拉黑账号问卷调查。"""
    用户编号 = models.PositiveIntegerField()
    写手账号 = models.CharField(max_length=64)
    当前轮次 = models.PositiveIntegerField()
    取关原因 = models.TextField()
    文章编号 = models.PositiveIntegerField()

    class Meta:
        db_table = '取关拉黑账号问卷调查'
        verbose_name = '取关/拉黑账号问卷调查'
        verbose_name_plural = '取关/拉黑账号问卷调查'


# ===== P-03: 标题党检测 + 流量惩罚 模型 =====

class ClickbaitDetectionConfig(models.Model):
    """标题党检测功能包参数配置（按平台独立）。"""

    platform_id = models.IntegerField()
    判定阈值 = models.IntegerField(default=2)
    判定概率值 = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.80'))
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '标题党检测配置'
        verbose_name = '标题党检测配置'
        verbose_name_plural = '标题党检测配置'
        ordering = ['-创建时间', '-id']


class ClickbaitDetectionResult(models.Model):
    """标题党检测结果记录（每篇文章一条）。"""

    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='标题党检测结果')
    轮次 = models.PositiveIntegerField()
    平台 = models.IntegerField()
    标题夸张度X = models.IntegerField()
    内容相关度Y = models.IntegerField()
    自动检测是否执行 = models.BooleanField(default=False)
    检测结果 = models.BooleanField(null=True, blank=True)  # True=标题党, False=非标题党, null=未执行
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '标题党检测结果'
        verbose_name = '标题党检测结果'
        verbose_name_plural = '标题党检测结果'
        ordering = ['-创建时间', '-id']


class TrafficPenaltyConfig(models.Model):
    """流量惩罚功能包参数配置（按平台独立）。"""

    platform_id = models.IntegerField()
    降权系数alpha = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.50'))
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '流量惩罚配置'
        verbose_name = '流量惩罚配置'
        verbose_name_plural = '流量惩罚配置'
        ordering = ['-创建时间', '-id']


class ArticleTraffic(models.Model):
    """文章流量分发记录（含惩罚系数明细）。"""

    platform_id = models.IntegerField()
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='流量记录')
    轮次 = models.PositiveIntegerField()
    基础流量 = models.PositiveIntegerField(default=0)
    penalty_applied = models.BooleanField(default=False)
    penalty_coefficient = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1.0000'))
    health_tier_coefficient = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1.0000'))
    最终流量 = models.PositiveIntegerField(default=0)
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '文章流量记录'
        verbose_name = '文章流量记录'
        verbose_name_plural = '文章流量记录'
        ordering = ['-创建时间', '-id']


# ===== P-04: 用户举报 + 收益惩罚 + 收益结算 模型 =====

class UserReportConfig(models.Model):
    """用户举报机制功能包参数配置（按平台独立）。"""

    REVIEW_METHOD_CHOICES = [
        ('auto', '自动审核'),
        ('manual', '人工审核'),
    ]

    platform_id = models.IntegerField()
    举报触发阈值 = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.30'))
    审核方式 = models.CharField(max_length=20, choices=REVIEW_METHOD_CHOICES, default='auto')
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '用户举报配置'
        verbose_name = '用户举报配置'
        verbose_name_plural = '用户举报配置'
        ordering = ['-创建时间', '-id']


class ArticleReport(models.Model):
    """用户举报记录。"""

    REVIEW_STATUS_CHOICES = [
        ('pending', '待审核'),
        ('approved', '审核通过'),
        ('rejected', '审核驳回'),
    ]

    platform_id = models.IntegerField()
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='举报记录')
    举报人 = models.CharField(max_length=100)
    举报轮次 = models.PositiveIntegerField()
    审核状态 = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='pending')
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '用户举报记录'
        verbose_name = '用户举报记录'
        verbose_name_plural = '用户举报记录'
        ordering = ['-创建时间', '-id']


class RevenuePenaltyConfig(models.Model):
    """收益惩罚功能包参数配置（按平台独立）。"""

    platform_id = models.IntegerField()
    惩罚系数beta = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.50'))
    创建时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '收益惩罚配置'
        verbose_name = '收益惩罚配置'
        verbose_name_plural = '收益惩罚配置'
        ordering = ['-创建时间', '-id']


class ArticleRevenueSettlement(models.Model):
    """文章收益结算明细（含惩罚信息）。"""

    platform_id = models.IntegerField()
    写手账号 = models.CharField(max_length=100)
    文章 = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='收益结算记录')
    轮次 = models.PositiveIntegerField()

    点击量 = models.PositiveIntegerField(default=0)
    阅读完成量 = models.PositiveIntegerField(default=0)
    收藏量 = models.PositiveIntegerField(default=0)
    满意度均分 = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    w1 = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    w2 = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    w3 = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    w4 = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    原始收益 = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    penalty_applied = models.BooleanField(default=False)
    penalty_coefficient = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('1.0000'))
    最终收益 = models.DecimalField(max_digits=18, decimal_places=6, default=0)

    结算时间 = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '文章收益结算'
        verbose_name = '文章收益结算'
        verbose_name_plural = '文章收益结算'
        ordering = ['-结算时间', '-id']
