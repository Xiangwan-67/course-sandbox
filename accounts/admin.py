from django.contrib import admin
from .models import (
    WriterAccount, UserAccount, PlatformAccount, ProfitWeightConfig, PlatformCycleProfitRecord,
    PlatformGovernanceMeasure, PlatformPerformanceScheme,
    AccountHealthLevelConfig, WriterNoticeRead, WriterHealthScoreLog,
    Article, Comment, PlatformSwitchSurvey,
    UserFollowWriter, UnfollowSurvey, ArticlePushDetail, ArticlePush,
    UserArticleLike, UserArticleCollect, UserArticleReadComplete,
    ClickbaitDetectionConfig, ClickbaitDetectionResult,
    TrafficPenaltyConfig, ArticleTraffic,
    UserReportConfig, ArticleReport,
    RevenuePenaltyConfig, ArticleRevenueSettlement,
)


@admin.register(WriterAccount)
class WriterAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台', '粉丝数', '健康分', 'health_tier', '推流系数']


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台', '关注数', '禁止登录截止时间']


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台']


@admin.register(ProfitWeightConfig)
class ProfitWeightConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', '平台', '生效轮次起', '生效轮次止',
        '点击率权重', '收藏率权重', '阅读完成率权重', '平台粉丝数权重', '监管成本权重',
        '利润展示窗口轮数', '配置人', '配置时间', '创建时间',
    ]
    list_filter = ['平台']


@admin.register(PlatformCycleProfitRecord)
class PlatformCycleProfitRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'platform_id', 'cycle_index', 'cycle_start_round', 'cycle_end_round',
        'total_click', 'total_collect', 'total_finish', 'fans_snapshot',
        'supervision_cost_level', 'supervision_cost_value',
        'profit_total', 'profit_prev_cycle', 'calculated_at',
    ]
    list_filter = ['platform_id', 'cycle_index']


@admin.register(PlatformGovernanceMeasure)
class PlatformGovernanceMeasureAdmin(admin.ModelAdmin):
    list_display = ['id', '平台', '轮次', '生效轮次', '取消轮次', '措施类型', 'config_id', '发布人账号', '创建时间']
    list_filter = ['平台', '轮次', '措施类型', '生效轮次', '取消轮次']


@admin.register(AccountHealthLevelConfig)
class AccountHealthLevelConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', '生效轮次起', '生效轮次止', '下界开', '上界闭', '可推流比例', '排序', '创建时间',
    ]
    list_filter = ['生效轮次起']


@admin.register(WriterNoticeRead)
class WriterNoticeReadAdmin(admin.ModelAdmin):
    list_display = ['id', '写手账号', '通知', 'read_at']
    list_filter = ['写手账号']


@admin.register(WriterHealthScoreLog)
class WriterHealthScoreLogAdmin(admin.ModelAdmin):
    list_display = ['id', '写手账号', '轮次', '文章编号', '变更值', '原因', '创建时间']
    list_filter = ['轮次', '写手账号']


@admin.register(PlatformPerformanceScheme)
class PlatformPerformanceSchemeAdmin(admin.ModelAdmin):
    list_display = ['id', '平台', '生效轮次', '方案编号', '发布人账号', '创建时间']
    list_filter = ['平台', '生效轮次', '方案编号']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = [
        'id', '写手账号', '标题', '标题夸张度_初始值', '标题夸张度_校准值', '正文',
        '内容相关度_初始值', '内容相关度_校准值', '已推送', '点击量', '点赞量', '收藏量',
        '吸粉数', '取关数', '阅读完成量', '报酬',
        'is_clickbait', 'method_auto_rule', 'method_user', 'report_count_current_round',
        '创建时间',
    ]
    list_filter = ['写手账号', 'is_clickbait']
    search_fields = ['标题', '正文']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', '文章', '内容', '评论者', '创建时间']
    list_filter = ['文章']


@admin.register(ArticlePushDetail)
class ArticlePushDetailAdmin(admin.ModelAdmin):
    list_display = ['id', '文章', '用户', '是否粉丝']
    list_filter = ['是否粉丝', '文章']


@admin.register(ArticlePush)
class ArticlePushAdmin(admin.ModelAdmin):
    list_display = ['id', '文章', '用户', '列表类型']
    list_filter = ['列表类型', '文章']


@admin.register(UserArticleLike)
class UserArticleLikeAdmin(admin.ModelAdmin):
    list_display = ['id', '用户', '文章']
    list_filter = ['文章']


@admin.register(UserArticleCollect)
class UserArticleCollectAdmin(admin.ModelAdmin):
    list_display = ['id', '用户', '文章']
    list_filter = ['文章']


@admin.register(UserArticleReadComplete)
class UserArticleReadCompleteAdmin(admin.ModelAdmin):
    list_display = ['id', '用户', '文章']
    list_filter = ['文章']


def _update_fans_after_follow_change(writer_account_str, user_obj, delta):
    """关注记录变化时，同步更新写手与用户的粉丝数。delta: +1 为新增关注，-1 为取消关注。"""
    from .models import WriterAccount
    w = WriterAccount.objects.filter(账号=writer_account_str).first()
    if w:
        w.粉丝数 = max(0, w.粉丝数 + delta)
        w.save(update_fields=['粉丝数'])
    if user_obj:
        user_obj.关注数 = max(0, user_obj.关注数 + delta)
        user_obj.save(update_fields=['关注数'])


@admin.register(UserFollowWriter)
class UserFollowWriterAdmin(admin.ModelAdmin):
    list_display = ['id', '用户', '写手账号']
    list_filter = ['写手账号']

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)
        if is_new:
            _update_fans_after_follow_change(obj.写手账号, obj.用户, 1)

    def delete_model(self, request, obj):
        writer_account_str = obj.写手账号
        user_obj = obj.用户
        super().delete_model(request, obj)
        _update_fans_after_follow_change(writer_account_str, user_obj, -1)

    def delete_queryset(self, request, queryset):
        # 批量删除时先记下涉及的写手账号与用户 id，再删除，最后统一重算粉丝数
        from .models import WriterAccount
        writer_accounts = set(queryset.values_list('写手账号', flat=True))
        user_ids = set(queryset.values_list('用户_id', flat=True))
        queryset.delete()
        for account in writer_accounts:
            w = WriterAccount.objects.filter(账号=account).first()
            if w:
                w.粉丝数 = UserFollowWriter.objects.filter(写手账号=account).count()
                w.save(update_fields=['粉丝数'])
        for uid in user_ids:
            u = UserAccount.objects.filter(pk=uid).first()
            if u:
                u.关注数 = u.关注列表.count()
                u.save(update_fields=['关注数'])


@admin.register(UnfollowSurvey)
class UnfollowSurveyAdmin(admin.ModelAdmin):
    list_display = ['id', '用户编号', '写手账号', '当前轮次', '文章编号', '取关原因']
    list_filter = ['写手账号', '当前轮次']


@admin.register(PlatformSwitchSurvey)
class PlatformSwitchSurveyAdmin(admin.ModelAdmin):
    list_display = ['id', '用户编号', '切换前平台', '切换后平台', '轮次', '切换平台原因']
    list_filter = ['轮次', '切换前平台', '切换后平台']


# ===== P-03: 标题党检测 + 流量惩罚 Admin =====

@admin.register(ClickbaitDetectionConfig)
class ClickbaitDetectionConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '判定阈值', '判定概率值', '创建时间']
    list_filter = ['platform_id']


@admin.register(ClickbaitDetectionResult)
class ClickbaitDetectionResultAdmin(admin.ModelAdmin):
    list_display = ['id', '文章', '轮次', '平台', '标题夸张度X', '内容相关度Y', '自动检测是否执行', '检测结果', '创建时间']
    list_filter = ['平台', '轮次', '检测结果']


@admin.register(TrafficPenaltyConfig)
class TrafficPenaltyConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '降权系数alpha', '创建时间']
    list_filter = ['platform_id']


@admin.register(ArticleTraffic)
class ArticleTrafficAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'platform_id', '文章', '轮次', '基础流量',
        'penalty_applied', 'penalty_coefficient', 'health_tier_coefficient',
        '最终流量', '创建时间',
    ]
    list_filter = ['platform_id', '轮次', 'penalty_applied']


# ===== P-04: 用户举报 + 收益惩罚 + 收益结算 Admin =====

@admin.register(UserReportConfig)
class UserReportConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '举报触发阈值', '审核方式', '创建时间']
    list_filter = ['platform_id', '审核方式']


@admin.register(ArticleReport)
class ArticleReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '文章', '举报人', '举报轮次', '审核状态', '创建时间']
    list_filter = ['platform_id', '举报轮次', '审核状态']


@admin.register(RevenuePenaltyConfig)
class RevenuePenaltyConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '惩罚系数beta', '创建时间']
    list_filter = ['platform_id']


@admin.register(ArticleRevenueSettlement)
class ArticleRevenueSettlementAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'platform_id', '写手账号', '文章', '轮次',
        '点击量', '阅读完成量', '收藏量', '满意度均分',
        'w1', 'w2', 'w3', 'w4',
        '原始收益', 'penalty_applied', 'penalty_coefficient', '最终收益', '结算时间',
    ]
    list_filter = ['platform_id', '轮次', 'penalty_applied']
