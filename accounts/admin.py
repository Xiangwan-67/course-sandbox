from django.contrib import admin

from accounts import approval_actions
from accounts.platform_scope import validate_regulator_platform_list
from .models import (
    WriterAccount, UserAccount, PlatformAccount, RegulatorAccount,
    RegulationActionApplication, RegulationAction, PlatformSpotCheckResult,
    PlatformPatrolApplication, PlatformPatrolResult,
    PlatformSelfPatrolApplication, PlatformSelfPatrolResult,
    AdminBaseConfig,
    RegulatorFineApplication, RegulatorFineRecord,
    ProfitWeightConfig, PlatformCycleProfitRecord,
    PlatformGovernanceMeasure, PlatformPerformanceScheme,
    AccountHealthConfig, AccountHealthLevelConfig, WriterNoticeRead, WriterGovernanceNotice, WriterHealthScoreLog,
    Article, Comment, PlatformSwitchSurvey,
    UserFollowWriter, UnfollowSurvey, ArticlePushDetail, ArticlePush,
    UserArticleLike, UserArticleCollect, UserArticleReadComplete,
    ClickbaitDetectionConfig, ClickbaitDetectionResult,
    TrafficPenaltyConfig, ArticleTraffic,
    UserReportConfig, ArticleReport,
    RevenuePenaltyConfig, ArticleRevenueSettlement,
    SimulationRound,
    RoundSnapshotBatch,
    RoundSnapshotPlatform,
    RoundSnapshotWriter,
    RoundSnapshotWriterFan,
)


@admin.register(SimulationRound)
class SimulationRoundAdmin(admin.ModelAdmin):
    list_display = ['id', '当前轮次']
    readonly_fields = ['当前轮次']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WriterAccount)
class WriterAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台', '粉丝数', '健康分', 'health_tier', '推流系数']


@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台', '关注数', '禁止登录截止时间']


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '所属平台']


@admin.register(RegulatorAccount)
class RegulatorAccountAdmin(admin.ModelAdmin):
    list_display = ['id', '账号', '密码', '负责平台编号列表']

    def save_model(self, request, obj, form, change):
        raw = list(getattr(obj, '负责平台编号列表', None) or [])
        err = validate_regulator_platform_list(raw, exclude_pk=obj.pk if obj.pk else None)
        if err:
            from django.contrib import messages
            messages.error(request, err)
            return
        super().save_model(request, obj, form, change)


@admin.register(AdminBaseConfig)
class AdminBaseConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', '自动巡查比例',
        '罚款轻微监管成本', '罚款基础监管成本', '罚款中等监管成本', '罚款严格监管成本',
        '写作成本映射',
        '更新时间',
    ]

    def has_add_permission(self, request):
        return not AdminBaseConfig.objects.exists()


@admin.register(RegulatorFineApplication)
class RegulatorFineApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'id', '申请轮次', '平台编号', '平台名称', '罚款档次', '申请状态',
        '申请人账号', '管理员确认账号', '管理员确认时间', '创建时间',
    ]
    list_filter = ['申请状态', '罚款档次', '平台编号']
    actions = ['approve_fine_applications', 'reject_fine_applications']

    @admin.action(description='审核通过：生成罚款记录并生效')
    def approve_fine_applications(self, request, queryset):
        approval_actions.approve_regulator_fine_queryset(request, queryset)

    @admin.action(description='驳回：罚款申请不通过')
    def reject_fine_applications(self, request, queryset):
        approval_actions.reject_regulator_fine_queryset(request, queryset)


@admin.register(RegulatorFineRecord)
class RegulatorFineRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', '执行轮次', '平台编号', '平台名称', '罚款档次', '监管成本数值', '申请记录', '创建时间',
    ]
    list_filter = ['平台编号', '罚款档次']


@admin.register(RegulationActionApplication)
class RegulationActionApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'id', '行动编号', '当前轮次', '整治持续轮次',
        '整治原因', '申请状态', '申请人账号', '管理员确认账号', '管理员确认时间', '创建时间',
    ]
    list_filter = ['申请状态', '当前轮次', '整治持续轮次', '整治原因']
    actions = ['approve_applications', 'reject_applications']

    @admin.action(description='审核通过：生成正式专项行动')
    def approve_applications(self, request, queryset):
        approval_actions.approve_regulation_action_queryset(request, queryset)

    @admin.action(description='驳回：专项行动申请不通过')
    def reject_applications(self, request, queryset):
        approval_actions.reject_regulation_action_queryset(request, queryset)


@admin.register(RegulationAction)
class RegulationActionAdmin(admin.ModelAdmin):
    list_display = [
        'id', '行动编号', '当前轮次', '整治平台编号', '整治平台名称',
        '整治持续轮次', '开始轮次', '结束轮次', '整治原因', '状态',
        '配套自动巡查已执行', '创建时间',
    ]
    list_filter = ['状态', '整治平台编号', '当前轮次', '整治原因', '配套自动巡查已执行']


@admin.register(PlatformSpotCheckResult)
class PlatformSpotCheckResultAdmin(admin.ModelAdmin):
    list_display = [
        'id', '行动编号', '整治平台编号', '整治平台名称', '是否查看', '专项行动',
    ]
    list_filter = ['是否查看', '行动编号']


@admin.register(PlatformPatrolApplication)
class PlatformPatrolApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'id', '申请轮次', '平台编号', '平台名称', '巡查比例',
        '起始轮次', '终止轮次', '申请状态', '申请人账号',
        '管理员确认账号', '管理员确认时间', '创建时间',
    ]
    list_filter = ['申请状态', '平台编号', '申请轮次']
    actions = ['approve_patrol_applications', 'reject_patrol_applications']

    @admin.action(description='审核通过：执行平台巡查并写入结果')
    def approve_patrol_applications(self, request, queryset):
        approval_actions.approve_platform_patrol_queryset(request, queryset, message_user=self.message_user)

    @admin.action(description='驳回：平台巡查申请不通过')
    def reject_patrol_applications(self, request, queryset):
        approval_actions.reject_platform_patrol_queryset(request, queryset)


@admin.register(PlatformPatrolResult)
class PlatformPatrolResultAdmin(admin.ModelAdmin):
    list_display = [
        'id', '巡查类型', '申请记录', '专项行动', '平台编号', '平台名称', '巡查比例',
        '起始轮次', '终止轮次', '执行轮次', '用户数', '抽查文章数', '标题党率', '创建时间',
    ]
    list_filter = ['平台编号', '巡查类型']


@admin.register(PlatformSelfPatrolApplication)
class PlatformSelfPatrolApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'id', '申请轮次', '平台编号', '平台名称', '巡查比例',
        '起始轮次', '终止轮次', '申请状态', '申请人账号',
        '管理员确认账号', '管理员确认时间', '创建时间',
    ]
    list_filter = ['申请状态', '平台编号', '申请轮次']
    actions = ['approve_self_patrol_applications', 'reject_self_patrol_applications']

    @admin.action(description='审核通过：执行平台巡查并写入结果')
    def approve_self_patrol_applications(self, request, queryset):
        approval_actions.approve_platform_self_patrol_queryset(request, queryset, message_user=self.message_user)

    @admin.action(description='驳回：平台巡查申请不通过')
    def reject_self_patrol_applications(self, request, queryset):
        approval_actions.reject_platform_self_patrol_queryset(request, queryset)


@admin.register(PlatformSelfPatrolResult)
class PlatformSelfPatrolResultAdmin(admin.ModelAdmin):
    list_display = [
        'id', '申请记录', '平台编号', '平台名称', '巡查比例',
        '起始轮次', '终止轮次', '执行轮次', '用户数', '抽查文章数', '标题党率', '创建时间',
    ]
    list_filter = ['平台编号']


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
    list_display = ['id', '平台', '轮次', '生效轮次', '取消轮次', '措施类型', 'config_id', 'status', '管理员确认账号', '管理员确认时间', '发布人账号', '创建时间']
    list_filter = ['平台', '轮次', '措施类型', '生效轮次', '取消轮次', 'status']
    actions = ['approve_measures', 'reject_measures']

    @admin.action(description='审核通过：使选中的治理措施生效')
    def approve_measures(self, request, queryset):
        approval_actions.approve_platform_governance_measure_queryset(request, queryset)

    @admin.action(description='驳回：选中的治理措施不通过')
    def reject_measures(self, request, queryset):
        approval_actions.reject_platform_governance_measure_queryset(request, queryset)


@admin.register(AccountHealthConfig)
class AccountHealthConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'platform_id', 'status', '初始健康分', '每次违规扣减分值',
        '是否启用恢复机制', '恢复所需连续无违规轮次', '每次恢复分值', '创建时间',
    ]
    list_filter = ['platform_id', 'status', '是否启用恢复机制']
    actions = ['approve_health_configs', 'reject_health_configs']

    @admin.action(description='审核通过：使选中的账号健康分配置生效')
    def approve_health_configs(self, request, queryset):
        approval_actions.approve_account_health_config_queryset(request, queryset)

    @admin.action(description='驳回：选中的账号健康分配置不通过')
    def reject_health_configs(self, request, queryset):
        approval_actions.reject_account_health_config_queryset(request, queryset)


@admin.register(AccountHealthLevelConfig)
class AccountHealthLevelConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', '平台', 'config', '档位标签',
        '生效轮次起', '生效轮次止', '下界开', '上界闭', '可推流比例', '排序', '创建时间',
    ]
    list_filter = ['平台', '生效轮次起']


@admin.register(WriterNoticeRead)
class WriterNoticeReadAdmin(admin.ModelAdmin):
    list_display = ['id', '写手账号', '通知', 'read_at']
    list_filter = ['写手账号']


@admin.register(WriterGovernanceNotice)
class WriterGovernanceNoticeAdmin(admin.ModelAdmin):
    list_display = ['id', '写手账号', 'measure', '投递轮次', '是否已读', 'read_at']
    list_filter = ['是否已读', '投递轮次']


@admin.register(WriterHealthScoreLog)
class WriterHealthScoreLogAdmin(admin.ModelAdmin):
    list_display = ['id', '写手账号', '轮次', 'event_type', '文章编号', '变更值', '原因', '创建时间']
    list_filter = ['轮次', '写手账号', 'event_type']


@admin.register(PlatformPerformanceScheme)
class PlatformPerformanceSchemeAdmin(admin.ModelAdmin):
    list_display = [
        'id', '平台', '生效轮次', '方案编号',
        'w1_click', 'w2_finish', 'w3_collect',
        'status', '管理员确认账号', '管理员确认时间',
        '发布人账号', '创建时间',
    ]
    list_filter = ['平台', '生效轮次', '方案编号', 'status']
    actions = ['confirm_scheme', 'reject_scheme']

    @admin.action(description='确认选中的绩效方案生效')
    def confirm_scheme(self, request, queryset):
        approval_actions.approve_platform_performance_scheme_queryset(request, queryset)

    @admin.action(description='驳回：取消待审核的绩效方案')
    def reject_scheme(self, request, queryset):
        approval_actions.reject_platform_performance_scheme_queryset(request, queryset)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = [
        'id', '写手账号', '标题', '标题夸张度_初始值', '标题夸张度_校准值', '正文',
        '内容相关度_初始值', '内容相关度_校准值', '已推送', '点击量', '点赞量', '收藏量',
        '吸粉数', '取关数', '阅读完成量', '报酬',
        'is_clickbait', 'clickbait_source', 'clickbait_auto_executed', 'report_count_current_round',
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
    list_display = ['id', '平台', '文章', '用户', '是否粉丝']
    list_filter = ['平台', '是否粉丝', '文章']


@admin.register(ArticlePush)
class ArticlePushAdmin(admin.ModelAdmin):
    list_display = ['id', '平台', '文章', '用户', '列表类型']
    list_filter = ['平台', '列表类型', '文章']


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
    list_display = ['id', 'platform_id', '标题夸张度阈值X', '内容相关度阈值Y', 'status', '提交人账号', '管理员确认账号', '管理员确认时间', '创建时间']
    list_filter = ['platform_id', 'status']
    actions = ['approve_configs', 'reject_configs']

    @admin.action(description='审核通过：使选中的配置生效')
    def approve_configs(self, request, queryset):
        approval_actions.approve_clickbait_config_queryset(request, queryset)

    @admin.action(description='驳回：选中的配置不通过')
    def reject_configs(self, request, queryset):
        approval_actions.reject_clickbait_config_queryset(request, queryset)


@admin.register(ClickbaitDetectionResult)
class ClickbaitDetectionResultAdmin(admin.ModelAdmin):
    list_display = [
        'id', '文章', '轮次', '平台', '判定来源', '标题夸张度X', '内容相关度Y',
        '判定阈值X', '判定阈值Y', '自动检测是否执行', '检测结果', '创建时间',
    ]
    list_filter = ['平台', '轮次', '判定来源', '检测结果']


@admin.register(TrafficPenaltyConfig)
class TrafficPenaltyConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '降权系数alpha', 'status', '提交人账号', '管理员确认账号', '管理员确认时间', '创建时间']
    list_filter = ['platform_id', 'status']
    actions = ['approve_configs', 'reject_configs']

    @admin.action(description='审核通过：使选中的配置生效')
    def approve_configs(self, request, queryset):
        approval_actions.approve_traffic_penalty_config_queryset(request, queryset)

    @admin.action(description='驳回：选中的配置不通过')
    def reject_configs(self, request, queryset):
        approval_actions.reject_traffic_penalty_config_queryset(request, queryset)


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
    list_display = ['id', 'platform_id', '举报触发阈值', '审核方式', 'status', '提交人账号', '管理员确认账号', '管理员确认时间', '创建时间']
    list_filter = ['platform_id', '审核方式', 'status']
    actions = ['approve_configs', 'reject_configs']

    @admin.action(description='审核通过：使选中的配置生效')
    def approve_configs(self, request, queryset):
        approval_actions.approve_user_report_config_queryset(request, queryset)

    @admin.action(description='驳回：选中的配置不通过')
    def reject_configs(self, request, queryset):
        approval_actions.reject_user_report_config_queryset(request, queryset)


@admin.register(ArticleReport)
class ArticleReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '文章', '举报人', '举报轮次', '审核状态', '创建时间']
    list_filter = ['platform_id', '举报轮次', '审核状态']


@admin.register(RevenuePenaltyConfig)
class RevenuePenaltyConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'platform_id', '惩罚系数beta', 'status', '提交人账号', '管理员确认账号', '管理员确认时间', '创建时间']
    list_filter = ['platform_id', 'status']
    actions = ['approve_configs', 'reject_configs']

    @admin.action(description='审核通过：使选中的配置生效')
    def approve_configs(self, request, queryset):
        approval_actions.approve_revenue_penalty_config_queryset(request, queryset)

    @admin.action(description='驳回：选中的配置不通过')
    def reject_configs(self, request, queryset):
        approval_actions.reject_revenue_penalty_config_queryset(request, queryset)


@admin.register(ArticleRevenueSettlement)
class ArticleRevenueSettlementAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'platform_id', '写手账号', '文章', '轮次',
        '点击量', '阅读完成量', '收藏量', '写作成本数值', '写作成本系数',
        '因子_点击量', '因子_阅读完成', '因子_收藏', '因子_写作成本',
        'w1', 'w2', 'w3',
        '原始收益', 'penalty_applied', 'penalty_coefficient', '最终收益', '结算时间',
    ]
    list_filter = ['platform_id', '轮次', 'penalty_applied']


@admin.register(RoundSnapshotBatch)
class RoundSnapshotBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'round_num', 'captured_at', 'trigger']
    readonly_fields = ['round_num', 'captured_at', 'trigger']


@admin.register(RoundSnapshotPlatform)
class RoundSnapshotPlatformAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'round_num', 'platform_id', 'user_count',
        'clickbait_count_article_field', 'clickbait_count_by_rule',
        'cycle_index', 'cycle_profit_total',
    ]
    list_filter = ['round_num', 'platform_id']


@admin.register(RoundSnapshotWriter)
class RoundSnapshotWriterAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'round_num', 'writer_account', 'platform_id', 'fan_count',
        'round_revenue_total', 'revenue_penalty_deduction',
        'traffic_penalty_article_count', 'health_score',
    ]
    list_filter = ['round_num', 'platform_id']


@admin.register(RoundSnapshotWriterFan)
class RoundSnapshotWriterFanAdmin(admin.ModelAdmin):
    list_display = ['id', 'round_num', 'writer_account', 'user_account', 'user_platform_id']
    list_filter = ['round_num', 'writer_account']
