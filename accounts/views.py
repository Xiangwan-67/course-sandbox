# -*- coding: utf-8 -*-
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from django.db.models import F, Sum, Q
from decimal import Decimal
from django.views.decorators.csrf import ensure_csrf_cookie
import json, time
import random
import threading
from django.conf import settings
from accounts.action_logger import action_log, regulator_action_log
from accounts.db_retry import retry_on_db_locked
from accounts.models import (
    WriterAccount, UserAccount, PlatformAccount, RegulatorAccount,
    RegulationActionApplication, RegulationAction, PlatformSpotCheckResult,
    PlatformPatrolApplication, PlatformPatrolResult,
    ProfitWeightConfig, PlatformCycleProfitRecord, PlatformGovernanceMeasure, PlatformPerformanceScheme, Article, Comment, PlatformSwitchSurvey,
    UserFollowWriter, UnfollowSurvey, ArticlePush, ArticlePushDetail,
    UserArticleLike, UserArticleCollect, UserArticleReadComplete,
    SimulationRound,
    AccountHealthConfig, AccountHealthLevelConfig, WriterNoticeRead, WriterHealthScoreLog,
    ClickbaitDetectionConfig, ClickbaitDetectionResult,
    TrafficPenaltyConfig, ArticleTraffic,
    UserReportConfig, ArticleReport,
    RevenuePenaltyConfig, ArticleRevenueSettlement,
)

PLATFORM_NAMES = {0: '平台1', 1: '平台2'}

_SANDBOX_SQLITE_WRITE_LOCK = threading.Lock()


def _serialize_sqlite_writes(view_func):
    """
    测试/沙盘场景下 sqlite 对并发写非常敏感（尤其 Django TestClient + 多线程）。
    可选：通过 settings.SANDBOX_SQLITE_SERIALIZE_WRITES=True 将关键写路径串行化，
    语义不变，但显著降低 sqlite lock 误报。
    """

    def wrapper(request, *args, **kwargs):
        if getattr(settings, "SANDBOX_SQLITE_SERIALIZE_WRITES", False):
            with _SANDBOX_SQLITE_WRITE_LOCK:
                return view_func(request, *args, **kwargs)
        return view_func(request, *args, **kwargs)

    return wrapper

# 当前模拟轮次从 DB 表「模拟轮次」读取，持久化；结束本轮时仅做 轮次+1，不删任何数据


@require_http_methods(['GET', 'POST'])
def login_view(request):
    """登录页：输入账号与密码，校验写手/用户表并跳转对应页面。"""
    if request.method == 'GET':
        return render(request, 'accounts/login.html')

    account = (request.POST.get('account') or '').strip()
    password = (request.POST.get('password') or '').strip()
    if not account:
        return render(request, 'accounts/login.html', {'error': '请输入账号。'})

    # 先查写手表
    try:
        writer = WriterAccount.objects.get(**{'账号': account})
        if writer.密码 == password:
            request.session['account'] = account
            request.session['role'] = 'writer'
            return redirect('accounts:writer_home')
        return render(request, 'accounts/login.html', {'error': '密码错误。'})
    except WriterAccount.DoesNotExist:
        pass

    # 再查用户表
    try:
        user = UserAccount.objects.get(**{'账号': account})
        if user.密码 == password:
            now = timezone.now()
            if user.禁止登录截止时间 and now < user.禁止登录截止时间:
                remain = (user.禁止登录截止时间 - now).seconds
                return render(request, 'accounts/login.html', {
                    'error': f'您已切换平台，需等待约 {max(1, remain // 60)} 分钟后才能再次登录。'
                })
            request.session['account'] = account
            request.session['role'] = 'user'
            return redirect('accounts:user_home')
        return render(request, 'accounts/login.html', {'error': '密码错误。'})
    except UserAccount.DoesNotExist:
        pass

    # 再查平台账号表
    try:
        platform_user = PlatformAccount.objects.get(**{'账号': account})
        if platform_user.密码 == password:
            request.session['account'] = account
            request.session['role'] = 'platform'
            return redirect('accounts:platform_home')
        return render(request, 'accounts/login.html', {'error': '密码错误。'})
    except PlatformAccount.DoesNotExist:
        pass

    # 再查监管机构账号表
    try:
        regulator_user = RegulatorAccount.objects.get(**{'账号': account})
        if regulator_user.密码 == password:
            request.session['account'] = account
            request.session['role'] = 'regulator'
            return redirect('accounts:regulator_home')
        return render(request, 'accounts/login.html', {'error': '密码错误。'})
    except RegulatorAccount.DoesNotExist:
        pass

    return render(request, 'accounts/login.html', {'error': '账号不存在。'})


@ensure_csrf_cookie
def writer_home(request):
    """写手首页：显示「写手xx，您好！」、上一轮文章榜单（同平台）、同平台账号榜单、历史文章入口。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'writer':
        return redirect('accounts:login')
    writer = WriterAccount.objects.filter(账号=account).first()
    writer_platform = getattr(writer, '所属平台', 0) if writer else 0
    current_round = _get_current_round()
    prev_round = current_round - 1
    # 文章榜单：上一轮(n-1)中，属于平台 x 的写手们的全部文章，按点击量降序，仅展示不可点击
    writer_accounts_same_platform = list(
        WriterAccount.objects.filter(所属平台=writer_platform).values_list('账号', flat=True)
    )
    if prev_round >= 1 and writer_accounts_same_platform:
        article_ranking = list(
            Article.objects.filter(轮次=prev_round, 写手账号__in=writer_accounts_same_platform)
            .exclude(标题='').filter(标题__isnull=False)
            .order_by('-点击量')
        )
    else:
        article_ranking = []
    # 账号榜单：同平台写手，按粉丝数降序
    account_ranking = list(
        WriterAccount.objects.filter(所属平台=writer_platform).order_by('-粉丝数')
    )
    notices = list(
        PlatformGovernanceMeasure.objects.filter(平台=writer_platform).order_by('-轮次', '-创建时间')[:20]
    )
    read_ids = set(
        WriterNoticeRead.objects
        .filter(写手账号=account, 通知__in=notices)
        .values_list('通知_id', flat=True)
    ) if notices else set()
    has_unread = any(n.pk not in read_ids for n in notices)
    return render(request, 'accounts/writer_home.html', {
        'name': account,
        'article_ranking': article_ranking,
        'account_ranking': account_ranking,
        'prev_round': prev_round,
        'has_unread_notice': has_unread,
    })


def writer_notices(request):
    """写手通知列表：展示本平台治理通知，并支持标记已读。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'writer':
        return redirect('accounts:login')
    writer = WriterAccount.objects.filter(账号=account).first()
    writer_platform = getattr(writer, '所属平台', 0) if writer else 0
    current_round = _get_current_round()
    notices = list(
        PlatformGovernanceMeasure.objects.filter(平台=writer_platform).order_by('-轮次', '-创建时间')[:50]
    )
    read_ids = set(
        WriterNoticeRead.objects
        .filter(写手账号=account, 通知__in=notices)
        .values_list('通知_id', flat=True)
    ) if notices else set()
    for n in notices:
        n.is_unread = n.pk not in read_ids
    return render(request, 'accounts/writer_notices.html', {
        'name': account,
        'platform_name': PLATFORM_NAMES.get(writer_platform, '平台1'),
        'current_round': current_round,
        'notices': notices,
    })


@require_http_methods(['POST'])
def writer_notice_read(request, notice_id: int):
    """写手标记通知已读：写入 WriterNoticeRead。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'writer':
        return JsonResponse({'error': '未登录或非写手'}, status=403)
    try:
        notice = PlatformGovernanceMeasure.objects.get(pk=notice_id)
    except PlatformGovernanceMeasure.DoesNotExist:
        return JsonResponse({'error': '通知不存在'}, status=404)
    WriterNoticeRead.objects.get_or_create(写手账号=account, 通知=notice)
    return JsonResponse({'ok': True})


def writer_article_history(request):
    """写手历史文章列表：该写手全部文章，按轮次升序；展示标题、所属轮次、报酬，可点击进入文章页。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'writer':
        return redirect('accounts:login')
    articles = list(
        Article.objects.filter(写手账号=account).order_by('轮次', '创建时间')
    )
    return render(request, 'accounts/writer_article_history.html', {
        'name': account,
        'articles': articles,
    })


def user_home(request):
    """用户首页：显示「用户xx，您好！」及平台图标。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return redirect('accounts:login')
    try:
        user = UserAccount.objects.get(账号=account)
        current_platform = user.所属平台 if user.所属平台 in (0, 1) else 0
    except UserAccount.DoesNotExist:
        current_platform = 0
    return render(request, 'accounts/user_home.html', {
        'name': account,
        'current_platform': current_platform,
        'platform_name': PLATFORM_NAMES.get(current_platform, '平台1'),
    })


def platform_home(request):
    """平台首页：平台负责人登录后进入，展示利润看板、同比增减与财务分析占位。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()

    cfg = _get_effective_profit_config(current_round, platform_id) or ProfitWeightConfig.objects.order_by('-id').first()
    period = int(getattr(cfg, '利润展示窗口轮数', 4) or 4)
    period = max(1, min(50, period))

    # 利润看板：按“完整周期”展示，非周期末轮次显示上一完整周期并提示“数据收集中”
    latest_complete_cycle_index = max(0, (current_round - 1) // period)
    current_cycle = (
        PlatformCycleProfitRecord.objects
        .filter(platform_id=platform_id, cycle_index=latest_complete_cycle_index)
        .first()
    ) if latest_complete_cycle_index >= 1 else None

    cycle_profit_total = _decimal(current_cycle.profit_total) if current_cycle else Decimal('0')
    profit_delta_abs = None
    profit_delta_pct = None
    if current_cycle and current_cycle.profit_prev_cycle is not None:
        prev = _decimal(current_cycle.profit_prev_cycle)
        profit_delta_abs = cycle_profit_total - prev
        if prev != 0:
            profit_delta_pct = (profit_delta_abs / prev) * Decimal('100')

    factor_details = []
    if current_cycle:
        snapshot = current_cycle.weight_config_snapshot or {}
        factor_details = [
            {
                'name': '点击量',
                'raw': current_cycle.total_click,
                'weight': _decimal(snapshot.get('点击率权重', 0)),
            },
            {
                'name': '收藏量',
                'raw': current_cycle.total_collect,
                'weight': _decimal(snapshot.get('收藏率权重', 0)),
            },
            {
                'name': '阅读完成量',
                'raw': current_cycle.total_finish,
                'weight': _decimal(snapshot.get('阅读完成率权重', 0)),
            },
            {
                'name': '平台粉丝数',
                'raw': current_cycle.fans_snapshot,
                'weight': _decimal(snapshot.get('平台粉丝数权重', 0)),
            },
            {
                'name': '监管成本',
                'raw': _decimal(current_cycle.supervision_cost_value),
                'weight': _decimal(snapshot.get('监管成本权重', 0)),
            },
        ]
        for row in factor_details:
            row['contribution'] = _decimal(row['raw']) * _decimal(row['weight'])

    history_cycles_qs = PlatformCycleProfitRecord.objects.filter(platform_id=platform_id).order_by('-cycle_index', '-id')
    history_cycles = []
    for rec in history_cycles_qs:
        rec_profit = _decimal(rec.profit_total)
        delta_abs = None
        delta_pct = None
        if rec.profit_prev_cycle is not None:
            prev = _decimal(rec.profit_prev_cycle)
            delta_abs = rec_profit - prev
            if prev != 0:
                delta_pct = (delta_abs / prev) * Decimal('100')
        history_cycles.append({
            'cycle_index': rec.cycle_index,
            'cycle_start_round': rec.cycle_start_round,
            'cycle_end_round': rec.cycle_end_round,
            'profit_total': rec_profit,
            'delta_abs': delta_abs,
            'delta_pct': delta_pct,
        })

    collecting_message = None
    if current_round % period != 0:
        collecting_message = f"本周期（{(latest_complete_cycle_index * period) + 1}~{(latest_complete_cycle_index + 1) * period}轮）数据收集中"
    financial_analysis = "财务分析功能待接入（后续由大模型生成）"

    # 治理总览区：当前生效功能包 + 参数摘要 + 上轮关键结果
    current_performance_scheme = (
        PlatformPerformanceScheme.objects.filter(平台=platform_id, 生效轮次__lte=current_round, status='active')
        .order_by('-生效轮次', '-id')
        .first()
    )
    enabled_measure_defs = [
        ('account_health_rule', '账号健康分', '🩺', 'accounts:platform_governance'),
        ('clickbait_detection', '标题党检测', '🧪', 'accounts:platform_clickbait_detection'),
        ('user_report', '用户举报', '📣', 'accounts:platform_report'),
        ('traffic_penalty', '流量惩罚', '📉', 'accounts:platform_traffic_penalty'),
        ('revenue_penalty', '收益惩罚', '💰', 'accounts:platform_revenue_penalty'),
        ('performance_rule', '绩效规则', '⚙️', 'accounts:platform_performance'),
    ]
    governance_status = []
    for m_type, m_name, m_icon, config_url in enabled_measure_defs:
        measure = (
            PlatformGovernanceMeasure.objects
            .filter(平台=platform_id, 措施类型=m_type, 生效轮次__lte=current_round)
            .filter(Q(取消轮次__isnull=True) | Q(取消轮次__gt=current_round))
            .order_by('-生效轮次', '-id')
            .first()
        )
        if not measure:
            continue
        summary = '参数待补充'
        if m_type == 'account_health_rule':
            health_cfg = AccountHealthConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
            if health_cfg:
                summary = (
                    f"初始={health_cfg.初始健康分}，扣减={health_cfg.每次违规扣减分值}，"
                    f"恢复={'开' if health_cfg.是否启用恢复机制 else '关'}"
                )
        elif m_type == 'clickbait_detection':
            c_cfg = ClickbaitDetectionConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
            if c_cfg:
                summary = (
                    f"标题夸张度阈值X={getattr(c_cfg, '标题夸张度阈值X', 4)}，"
                    f"内容相关度阈值Y={getattr(c_cfg, '内容相关度阈值Y', 3)}"
                )
        elif m_type == 'user_report':
            r_cfg = UserReportConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
            if r_cfg:
                summary = f"阈值={r_cfg.举报触发阈值}，审核方式={r_cfg.get_审核方式_display()}"
        elif m_type == 'traffic_penalty':
            t_cfg = TrafficPenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
            if t_cfg:
                summary = f"降权系数 α={t_cfg.降权系数alpha}"
        elif m_type == 'revenue_penalty':
            rv_cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
            if rv_cfg:
                summary = f"惩罚系数 β={rv_cfg.惩罚系数beta}"
        elif m_type == 'performance_rule':
            if current_performance_scheme:
                summary = (
                    f"w1={current_performance_scheme.w1_click}, w2={current_performance_scheme.w2_finish}, "
                    f"w3={current_performance_scheme.w3_collect}, w4={current_performance_scheme.w4_satisfaction}"
                )
            else:
                summary = "暂无生效方案"

        governance_status.append({
            'type': m_type,
            'name': m_name,
            'icon': m_icon,
            'summary': summary,
            'config_url': config_url,
            'effective_round': measure.生效轮次,
        })

    prev_round = max(0, current_round - 1)
    writers = WriterAccount.objects.filter(所属平台=platform_id)
    writer_accounts = set(writers.values_list('账号', flat=True))
    prev_articles = Article.objects.filter(写手账号__in=writer_accounts, 轮次=prev_round) if prev_round > 0 else Article.objects.none()
    prev_agg = prev_articles.aggregate(
        total_click=Sum('点击量'),
        total_finish=Sum('阅读完成量'),
        total_collect=Sum('收藏量'),
    )
    prev_round_summary = {
        'round': prev_round,
        'article_count': prev_articles.count() if prev_round > 0 else 0,
        'clickbait_count': prev_articles.filter(is_clickbait=True).count() if prev_round > 0 else 0,
        'report_count': ArticleReport.objects.filter(platform_id=platform_id, 举报轮次=prev_round).count() if prev_round > 0 else 0,
        'traffic_penalized_articles': ArticleTraffic.objects.filter(platform_id=platform_id, 轮次=prev_round, penalty_applied=True).count() if prev_round > 0 else 0,
        'violated_writer_count': WriterHealthScoreLog.objects.filter(
            轮次=prev_round, event_type='violation', 写手账号__in=writer_accounts
        ).values('写手账号').distinct().count() if prev_round > 0 else 0,
        'total_click': int(prev_agg.get('total_click') or 0),
        'total_finish': int(prev_agg.get('total_finish') or 0),
        'total_collect': int(prev_agg.get('total_collect') or 0),
    }

    return render(request, 'accounts/platform_home.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'profit_period': period,
        'current_cycle': current_cycle,
        'cycle_profit_total': cycle_profit_total,
        'profit_delta_abs': profit_delta_abs,
        'profit_delta_pct': profit_delta_pct,
        'factor_details': factor_details,
        'history_cycles': history_cycles,
        'collecting_message': collecting_message,
        'financial_analysis': financial_analysis,
        'governance_status': governance_status,
        'prev_round_summary': prev_round_summary,
        'governance_notices': list(
            PlatformGovernanceMeasure.objects
            .filter(平台=platform_id)
            .order_by('-轮次', '-创建时间')[:20]
        ),
        'current_performance_scheme': current_performance_scheme,
    })


def platform_round_result(request):
    """本轮治理结果查看页：支持 ?round=N，默认上一轮。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    try:
        target_round = int(request.GET.get('round', current_round - 1))
    except (TypeError, ValueError):
        target_round = current_round - 1
    if target_round < 1:
        target_round = 1
    if target_round > current_round:
        target_round = current_round

    writers = WriterAccount.objects.filter(所属平台=platform_id)
    writer_accounts = set(writers.values_list('账号', flat=True))
    round_articles = Article.objects.filter(写手账号__in=writer_accounts, 轮次=target_round)
    article_count = round_articles.count()

    auto_clickbait_articles = (
        ClickbaitDetectionResult.objects
        .filter(平台=platform_id, 轮次=target_round, 检测结果=True)
        .values('文章_id')
        .distinct()
        .count()
    )
    approved_report_articles = (
        ArticleReport.objects
        .filter(platform_id=platform_id, 举报轮次=target_round, 审核状态='approved')
        .values('文章_id')
        .distinct()
        .count()
    )
    final_violation_articles = round_articles.filter(is_clickbait=True).count()
    traffic_penalized_articles = (
        ArticleTraffic.objects
        .filter(platform_id=platform_id, 轮次=target_round, penalty_applied=True)
        .values('文章_id')
        .distinct()
        .count()
    )
    revenue_penalized_articles = (
        ArticleRevenueSettlement.objects
        .filter(platform_id=platform_id, 轮次=target_round, penalty_applied=True)
        .values('文章_id')
        .distinct()
        .count()
    )
    violated_writer_count = (
        WriterHealthScoreLog.objects
        .filter(轮次=target_round, event_type='violation', 写手账号__in=writer_accounts)
        .values('写手账号')
        .distinct()
        .count()
    )

    interaction_agg = round_articles.aggregate(
        total_click=Sum('点击量'),
        total_finish=Sum('阅读完成量'),
        total_collect=Sum('收藏量'),
    )
    writer_revenue_total = (
        ArticleRevenueSettlement.objects
        .filter(platform_id=platform_id, 轮次=target_round)
        .aggregate(total=Sum('最终收益'))
        .get('total') or Decimal('0')
    )

    enabled_types = [
        ('clickbait_detection', '标题党检测'),
        ('user_report', '用户举报'),
        ('traffic_penalty', '流量惩罚'),
        ('revenue_penalty', '收益惩罚'),
        ('account_health_rule', '账号健康分'),
        ('performance_rule', '绩效规则'),
    ]
    config_review = []
    for m_type, m_name in enabled_types:
        measure = (
            PlatformGovernanceMeasure.objects
            .filter(平台=platform_id, 措施类型=m_type, 生效轮次__lte=target_round)
            .filter(Q(取消轮次__isnull=True) | Q(取消轮次__gt=target_round))
            .order_by('-生效轮次', '-id')
            .first()
        )
        if not measure:
            continue
        summary = '参数待补充'
        if m_type == 'clickbait_detection':
            cfg = ClickbaitDetectionConfig.objects.filter(pk=measure.config_id).first() if measure.config_id else None
            if cfg:
                summary = (
                    f"标题夸张度阈值X={getattr(cfg, '标题夸张度阈值X', 4)}，"
                    f"内容相关度阈值Y={getattr(cfg, '内容相关度阈值Y', 3)}"
                )
        elif m_type == 'user_report':
            cfg = UserReportConfig.objects.filter(pk=measure.config_id).first() if measure.config_id else None
            if cfg:
                summary = f"阈值={cfg.举报触发阈值}，审核方式={cfg.get_审核方式_display()}"
        elif m_type == 'traffic_penalty':
            cfg = TrafficPenaltyConfig.objects.filter(pk=measure.config_id).first() if measure.config_id else None
            if cfg:
                summary = f"降权系数 α={cfg.降权系数alpha}"
        elif m_type == 'revenue_penalty':
            cfg = RevenuePenaltyConfig.objects.filter(pk=measure.config_id).first() if measure.config_id else None
            if cfg:
                summary = f"惩罚系数 β={cfg.惩罚系数beta}"
        elif m_type == 'account_health_rule':
            cfg = AccountHealthConfig.objects.filter(pk=measure.config_id).first() if measure.config_id else None
            if cfg:
                summary = (
                    f"初始={cfg.初始健康分}，扣减={cfg.每次违规扣减分值}，"
                    f"恢复={'开' if cfg.是否启用恢复机制 else '关'}"
                )
        elif m_type == 'performance_rule':
            cfg = (
                PlatformPerformanceScheme.objects
                .filter(平台=platform_id, 生效轮次__lte=target_round, status='active')
                .order_by('-生效轮次', '-id')
                .first()
            )
            if cfg:
                summary = f"w1={cfg.w1_click}, w2={cfg.w2_finish}, w3={cfg.w3_collect}, w4={cfg.w4_satisfaction}"
        config_review.append({
            'name': m_name,
            'type': m_type,
            'summary': summary,
            'effective_round': measure.生效轮次,
        })

    stats = {
        'article_count': article_count,
        'auto_clickbait_articles': auto_clickbait_articles,
        'approved_report_articles': approved_report_articles,
        'final_violation_articles': final_violation_articles,
        'traffic_penalized_articles': traffic_penalized_articles,
        'revenue_penalized_articles': revenue_penalized_articles,
        'violated_writer_count': violated_writer_count,
        'total_click': int(interaction_agg.get('total_click') or 0),
        'total_finish': int(interaction_agg.get('total_finish') or 0),
        'total_collect': int(interaction_agg.get('total_collect') or 0),
        'writer_revenue_total': writer_revenue_total,
        'user_report_rate': '—',
        'platform_switch_rate': '—',
    }

    return render(request, 'accounts/platform_round_result.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'target_round': target_round,
        'stats': stats,
        'config_review': config_review,
    })


def _regulator_monitoring_boxes(current_round: int):
    """监管主页「平台监测系统」各平台框：取该平台最新一条已落库的 PlatformPatrolResult。"""
    boxes = []
    for item in _all_platform_choices():
        pid = item['id']
        latest = (
            PlatformPatrolResult.objects.filter(平台编号=pid)
            .order_by('-创建时间', '-id')
            .first()
        )
        patrol_pending = PlatformPatrolApplication.objects.filter(
            平台编号=pid, 申请状态='pending'
        ).exists()
        row = {
            'platform_id': pid,
            'platform_name': item['name'],
            'has_patrol': latest is not None,
            'current_round': current_round,
            'has_pending': patrol_pending,
        }
        if latest:
            exec_r = int(latest.执行轮次)
            rounds_ago = max(0, int(current_round) - exec_r)
            rate_pct = float(latest.标题党率) * 100.0
            row['user_count'] = latest.用户数
            row['article_count'] = latest.抽查文章数
            row['title_rate_display'] = f'{rate_pct:.2f}%'
            row['period_display'] = f'第{latest.起始轮次}–{latest.终止轮次}轮'
            row['rounds_since_update'] = rounds_ago
        boxes.append(row)
    return boxes


def _regulator_progress_tables(current_round: int):
    """拆分为进行中 / 已完成 表格数据；并同步过期状态、补建抽查结果行。"""
    _sync_regulation_actions_finished(current_round)
    ongoing_rows = []
    completed_rows = []
    qs = RegulationAction.objects.all().order_by('-开始轮次', '-id')
    for ra in qs:
        start = int(ra.开始轮次)
        end = int(ra.结束轮次)
        total = max(1, int(ra.整治持续轮次 or 1))
        elapsed = _regulation_progress_elapsed(current_round, start, total)

        if current_round > end:
            spot = _ensure_spot_check_result(ra)
            completed_rows.append({
                '行动编号': ra.行动编号,
                'platform_name': ra.整治平台名称,
                'status_label': '已完成',
                'start_round': start,
                'progress': f'{total}/{total}轮',
                'spot_check_id': spot.pk,
            })
            continue

        if getattr(ra, '状态', None) != 'active':
            continue

        if current_round < start:
            status_label = '待开始'
            progress_str = f'0/{total}轮'
        else:
            status_label = '进行中'
            progress_str = f'{elapsed}/{total}轮'

        ongoing_rows.append({
            '行动编号': ra.行动编号,
            'platform_name': ra.整治平台名称,
            'status_label': status_label,
            'start_round': start,
            'progress': progress_str,
            'spot_check_id': None,
        })

    ongoing_count = RegulationAction.objects.filter(
        状态='active',
        开始轮次__lte=current_round,
        结束轮次__gte=current_round,
    ).count()

    return {
        'ongoing_rows': ongoing_rows,
        'completed_rows': completed_rows,
        'ongoing_count': ongoing_count,
    }


@ensure_csrf_cookie
def regulator_home(request):
    """监管机构主页：平台监测系统 + 专项整治行动管理。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return redirect('accounts:login')

    current_round = _get_current_round()
    progress = _regulator_progress_tables(current_round)
    return render(request, 'accounts/regulator_home.html', {
        'name': account,
        'current_round': current_round,
        'ongoing_rows': progress['ongoing_rows'],
        'completed_rows': progress['completed_rows'],
        'ongoing_count': progress['ongoing_count'],
        'monitoring_boxes': _regulator_monitoring_boxes(current_round),
    })


@ensure_csrf_cookie
def regulator_platform_patrol(request):
    """平台巡查参数配置页（从监测系统「启动巡查」进入）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return redirect('accounts:login')

    current_round = _get_current_round()
    raw_pid = request.GET.get('platform_id', '0')
    try:
        platform_id = int(raw_pid)
    except (TypeError, ValueError):
        platform_id = 0
    valid_ids = {item['id'] for item in _all_platform_choices()}
    if platform_id not in valid_ids:
        platform_id = 0
    pname = _platform_name(platform_id)
    patrol_pending = PlatformPatrolApplication.objects.filter(
        平台编号=platform_id, 申请状态='pending'
    ).exists()
    return render(request, 'accounts/regulator_platform_patrol.html', {
        'name': account,
        'current_round': current_round,
        'platform_id': platform_id,
        'platform_name': pname,
        'patrol_pending': patrol_pending,
    })


@require_http_methods(['POST'])
def platform_spot_check_open(request, pk: int):
    """监管用户打开抽查结果：更新是否查看、记日志，跳转占位页。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return redirect('accounts:login')

    spot = PlatformSpotCheckResult.objects.filter(pk=pk).select_related('专项行动').first()
    if not spot:
        return redirect('accounts:regulator_home')

    spot.是否查看 = True
    spot.save(update_fields=['是否查看'])

    current_round = _get_current_round()
    regulator_action_log(
        f"监管机构查看抽查结果 当前轮次：{current_round}，行动编号：{spot.行动编号}，平台：{spot.整治平台名称}"
    )
    return redirect('accounts:platform_spot_check_detail', pk=pk)


@ensure_csrf_cookie
@require_http_methods(['GET'])
def platform_spot_check_detail(request, pk: int):
    """平台抽查结果页（占位，后续实现具体内容）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return redirect('accounts:login')

    spot = PlatformSpotCheckResult.objects.filter(pk=pk).first()
    if not spot:
        return redirect('accounts:regulator_home')

    return render(request, 'accounts/platform_spot_check_detail.html', {
        'name': account,
        'spot': spot,
    })


@ensure_csrf_cookie
def regulator_special_action(request):
    """监管机构发起专项整治页面。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return redirect('accounts:login')

    current_round = _get_current_round()
    platform_items = []
    for item in _all_platform_choices():
        is_active = _is_platform_under_regulation(item['id'], current_round)
        platform_items.append({
            'id': item['id'],
            'name': item['name'],
            'disabled': is_active,
            'status_text': '整治中' if is_active else '可选',
        })

    latest_applications = list(
        RegulationActionApplication.objects.order_by('-创建时间', '-id')[:20]
    )
    return render(request, 'accounts/regulator_special_action.html', {
        'name': account,
        'current_round': current_round,
        'platform_items': platform_items,
        'duration_options': [4, 8, 12],
        'reason_options': ['定期整治', '标题党率过高', '用户投诉激增', '其他'],
        'latest_applications': latest_applications,
    })


@require_http_methods(['POST'])
def regulator_special_action_submit(request):
    """监管机构提交专项整治申请（待管理员审核）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return JsonResponse({'error': '未登录或非监管机构角色'}, status=403)

    payload = {}
    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads((request.body or b'').decode('utf-8') or '{}')
        except Exception:
            payload = {}
    else:
        raw_ids = request.POST.getlist('platform_ids') or request.POST.get('platform_ids') or '[]'
        if isinstance(raw_ids, str):
            try:
                parsed = json.loads(raw_ids)
                if not isinstance(parsed, list):
                    parsed = [raw_ids]
            except Exception:
                parsed = [x for x in raw_ids.split(',') if x.strip()]
        else:
            parsed = raw_ids
        payload = {
            'platform_ids': parsed,
            'duration_rounds': request.POST.get('duration_rounds'),
            'reason': request.POST.get('reason'),
            'reason_other': request.POST.get('reason_other'),
        }

    try:
        selected_platform_ids = sorted({int(x) for x in (payload.get('platform_ids') or [])})
    except Exception:
        selected_platform_ids = []
    if not selected_platform_ids:
        return JsonResponse({'error': '请至少选择一个整治平台'}, status=400)

    valid_platform_ids = {item['id'] for item in _all_platform_choices()}
    if any(pid not in valid_platform_ids for pid in selected_platform_ids):
        return JsonResponse({'error': '整治平台编号非法'}, status=400)

    try:
        duration_rounds = int(payload.get('duration_rounds') or 8)
    except (TypeError, ValueError):
        duration_rounds = 8
    if duration_rounds not in (4, 8, 12):
        return JsonResponse({'error': '整治持续轮次仅支持 4/8/12'}, status=400)

    reason = (payload.get('reason') or '').strip()
    valid_reasons = {'定期整治', '标题党率过高', '用户投诉激增', '其他'}
    if reason not in valid_reasons:
        return JsonResponse({'error': '整治原因非法'}, status=400)
    reason_other = (payload.get('reason_other') or '').strip()
    if reason == '其他' and not reason_other:
        return JsonResponse({'error': '选择“其他”时请填写原因说明'}, status=400)

    current_round = _get_current_round()
    blocked_platforms = []
    for pid in selected_platform_ids:
        if _is_platform_under_regulation(pid, current_round):
            blocked_platforms.append(_platform_name(pid))
    if blocked_platforms:
        return JsonResponse(
            {'error': f"以下平台处于整治中，不能重复发起：{', '.join(blocked_platforms)}"},
            status=400,
        )

    action_id = _next_regulation_action_id()
    platform_names = [_platform_name(pid) for pid in selected_platform_ids]
    app = RegulationActionApplication.objects.create(
        行动编号=action_id,
        当前轮次=current_round,
        整治平台编号列表=selected_platform_ids,
        整治平台名称列表=platform_names,
        整治持续轮次=duration_rounds,
        整治原因=reason,
        其他原因说明=reason_other,
        申请状态='pending',
        申请人账号=account,
    )

    start_round = current_round + 1
    end_round = start_round + duration_rounds - 1
    regulator_action_log(
        f"监管机构确认发起专项整治 action_id={action_id} round={current_round} "
        f"platforms={platform_names} active_range={start_round}-{end_round} "
        f"reason={reason} reason_other={reason_other or '-'} operator={account} app_id={app.pk}"
    )
    action_log(
        f"监管机构提交专项整治申请 action_id={action_id} round={current_round} "
        f"platforms={platform_names} duration={duration_rounds} reason={reason} operator={account}"
    )
    return JsonResponse({
        'ok': True,
        'application_id': app.pk,
        'action_id': action_id,
        'status': app.申请状态,
        'active_round_range': {'start_round': start_round, 'end_round': end_round},
    })


@require_http_methods(['POST'])
def regulator_platform_patrol_submit(request):
    """监管机构提交平台巡查申请（待管理员审核）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'regulator':
        return JsonResponse({'error': '未登录或非监管机构角色'}, status=403)

    payload = {}
    if request.content_type and 'application/json' in request.content_type:
        try:
            payload = json.loads((request.body or b'').decode('utf-8') or '{}')
        except Exception:
            payload = {}
    else:
        return JsonResponse({'error': '请使用 application/json'}, status=400)

    try:
        platform_id = int(payload.get('platform_id'))
    except (TypeError, ValueError):
        return JsonResponse({'error': '平台编号非法'}, status=400)

    valid_platform_ids = {item['id'] for item in _all_platform_choices()}
    if platform_id not in valid_platform_ids:
        return JsonResponse({'error': '平台编号非法'}, status=400)

    try:
        patrol_ratio = Decimal(str(payload.get('patrol_ratio', '0.5')))
    except Exception:
        return JsonResponse({'error': '巡查比例非法'}, status=400)
    if patrol_ratio < 0 or patrol_ratio > 1:
        return JsonResponse({'error': '巡查比例须在 0～1 之间'}, status=400)

    try:
        start_round = int(payload.get('start_round'))
        end_round = int(payload.get('end_round'))
    except (TypeError, ValueError):
        return JsonResponse({'error': '起始/终止轮次须为整数'}, status=400)

    current_round = _get_current_round()
    if start_round > end_round:
        return JsonResponse({'error': '起始轮次不能大于终止轮次'}, status=400)
    if end_round >= current_round:
        return JsonResponse({'error': '终止轮次须严格小于当前轮次'}, status=400)

    if PlatformPatrolApplication.objects.filter(平台编号=platform_id, 申请状态='pending').exists():
        return JsonResponse({'error': '该平台已有待审核的平台巡查申请'}, status=400)

    pname = _platform_name(platform_id)
    app = PlatformPatrolApplication.objects.create(
        申请轮次=current_round,
        平台编号=platform_id,
        平台名称=pname,
        巡查比例=patrol_ratio,
        起始轮次=start_round,
        终止轮次=end_round,
        申请状态='pending',
        申请人账号=account,
    )

    regulator_action_log(
        f"监管机构申请平台巡查 申请编号：{app.pk}、平台编号：{platform_id}、平台名称：{pname}、"
        f"巡查比例：{patrol_ratio}、起始轮次：{start_round}、终止轮次：{end_round}"
    )
    return JsonResponse({
        'ok': True,
        'application_id': app.pk,
        'status': app.申请状态,
    })


@ensure_csrf_cookie
def platform_governance(request):
    """平台治理：展示可选措施。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    health_cfg = _get_latest_account_health_config(platform_id)
    health_levels = []
    if health_cfg:
        health_levels = _get_effective_health_level_configs(current_round, platform_id=platform_id, config_id=health_cfg.pk)
    def _is_measure_published(m_type):
        rec = (
            PlatformGovernanceMeasure.objects
            .filter(平台=platform_id, 措施类型=m_type)
            .order_by('-轮次', '-id')
            .first()
        )
        return bool(rec and rec.取消轮次 is None)

    measures = [
        {
            'type': 'account_health_rule',
            'name': '账号健康分规则',
            'desc': '对平台所有写手账号设置健康分（初始100分），按梯度惩罚。发布后进入通知栏。',
            'published': _is_measure_published('account_health_rule'),
            'config_url': None,
            'health_config': health_cfg,
            'health_levels': health_levels,
        },
        {
            'type': 'clickbait_detection',
            'name': '标题党检测',
            'desc': '自动检测写手文章是否为标题党。默认参数由管理员维护，平台侧仅开关。',
            'published': _is_measure_published('clickbait_detection'),
            'config_url': 'accounts:platform_clickbait_detection',
        },
        {
            'type': 'user_report',
            'name': '用户举报',
            'desc': '允许用户举报疑似标题党文章，达到阈值后自动/人工审核。需先配置参数再发布。',
            'published': _is_measure_published('user_report'),
            'config_url': 'accounts:platform_report',
        },
        {
            'type': 'traffic_penalty',
            'name': '流量惩罚',
            'desc': '对标题党文章进行流量降权（α系数）。需先配置降权系数，再发布启用。',
            'published': _is_measure_published('traffic_penalty'),
            'config_url': 'accounts:platform_traffic_penalty',
        },
        {
            'type': 'revenue_penalty',
            'name': '收益惩罚',
            'desc': '对标题党文章进行收益惩罚（β系数）。需先配置参数再发布。',
            'published': _is_measure_published('revenue_penalty'),
            'config_url': 'accounts:platform_revenue_penalty',
        },
        {
            'type': 'performance_rule',
            'name': '绩效规则',
            'desc': '配置写手绩效考核权重方案，需管理员审批。',
            'published': _is_measure_published('performance_rule'),
            'config_url': None,
        },
    ]
    return render(request, 'accounts/platform_governance.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'measures': measures,
    })


@require_http_methods(['POST'])
def platform_governance_publish(request):
    """提交发布平台治理措施（待管理员审核）：写入记录表。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    measure_type = (request.POST.get('measure_type') or '').strip()
    VALID_MEASURE_TYPES = ('account_health_rule', 'clickbait_detection', 'user_report', 'traffic_penalty', 'revenue_penalty', 'performance_rule')
    if measure_type not in VALID_MEASURE_TYPES:
        return JsonResponse({'error': '未知措施类型'}, status=400)
    round_num = _get_current_round()
    effective_round = round_num + 1
    config_id = None
    content = {}
    # 防重复：若存在“未安排取消”的 pending/active 记录，则不允许重复提交发布
    # 允许场景：已经点过取消（取消轮次=下一轮），此时再次发布应新建一条记录，使下一轮重新生效
    exists_pending_or_active_not_cancelled = PlatformGovernanceMeasure.objects.filter(
        平台=platform_id,
        措施类型=measure_type,
        status__in=['pending', 'active'],
        取消轮次__isnull=True,
    ).exists()
    if exists_pending_or_active_not_cancelled:
        return JsonResponse({'error': '该措施已有待审核或已生效记录，不能重复提交发布。'}, status=400)

    if measure_type == 'account_health_rule':
        # 账号健康分配置若不存在，先创建 draft 作为默认草稿；但发布仍需要先“提交配置”
        cfg = AccountHealthConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
        if not cfg:
            cfg = AccountHealthConfig.objects.create(
                platform_id=platform_id,
                初始健康分=100,
                每次违规扣减分值=10,
                是否启用恢复机制=False,
                恢复所需连续无违规轮次=3,
                每次恢复分值=5,
                status='draft',
                提交人账号=account,
            )
        # 必须存在已提交(待审/已生效)的配置才允许提交发布
        if cfg.status not in ('pending', 'active'):
            return JsonResponse({'error': '请先提交账号健康分配置，等待管理员审核后再提交发布。'}, status=400)
        config_id = int(cfg.pk)
        content = {
            '初始健康分': cfg.初始健康分,
            '每次违规扣减分值': cfg.每次违规扣减分值,
            '是否启用恢复机制': cfg.是否启用恢复机制,
            '恢复所需连续无违规轮次': cfg.恢复所需连续无违规轮次,
            '每次恢复分值': cfg.每次恢复分值,
        }
    elif measure_type == 'clickbait_detection':
        # 平台侧不提交参数；必须由管理员在后台创建并激活默认配置
        cfg = (
            ClickbaitDetectionConfig.objects
            .filter(platform_id=platform_id, status='active')
            .order_by('-id')
            .first()
        )
        if not cfg:
            return JsonResponse({'error': '管理员尚未配置标题党检测默认参数，请联系管理员在后台添加并审核生效后再开启。'}, status=400)
        config_id = int(cfg.pk)
        content = {
            '标题夸张度阈值X': int(getattr(cfg, '标题夸张度阈值X', 4) or 4),
            '内容相关度阈值Y': int(getattr(cfg, '内容相关度阈值Y', 3) or 3),
        }
    elif measure_type == 'traffic_penalty':
        cfg = TrafficPenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
        if not cfg or cfg.status not in ('pending', 'active'):
            return JsonResponse({'error': '请先提交流量惩罚配置，等待管理员审核后再提交发布。'}, status=400)
        config_id = int(cfg.pk)
        content = {'降权系数alpha': str(cfg.降权系数alpha)}
    elif measure_type == 'user_report':
        cfg = UserReportConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
        if not cfg or cfg.status not in ('pending', 'active'):
            return JsonResponse({'error': '请先提交用户举报配置，等待管理员审核后再提交发布。'}, status=400)
        config_id = int(cfg.pk)
        content = {'举报触发阈值': str(cfg.举报触发阈值), '审核方式': cfg.审核方式}
    elif measure_type == 'revenue_penalty':
        cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
        if not cfg or cfg.status not in ('pending', 'active'):
            return JsonResponse({'error': '请先提交收益惩罚配置，等待管理员审核后再提交发布。'}, status=400)
        config_id = int(cfg.pk)
        content = {'惩罚系数beta': str(cfg.惩罚系数beta)}
    rec = PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=round_num,
        生效轮次=effective_round,
        措施类型=measure_type,
        措施内容=content,
        config_id=config_id,
        发布人账号=account,
        status='pending',
    )
    action_log(f"平台 {platform_id} 提交治理措施待审 type={measure_type} round={round_num} effective_round={effective_round} rec_id={rec.pk} config_id={config_id}")
    return JsonResponse({'ok': True, 'id': rec.pk})


@require_http_methods(['POST'])
def platform_governance_cancel(request):
    """取消平台治理措施（账号健康分规则）：写入取消轮次，下一轮起不再执行。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    measure_type = (request.POST.get('measure_type') or '').strip()
    if not measure_type or measure_type not in ('account_health_rule', 'clickbait_detection', 'user_report', 'traffic_penalty', 'revenue_penalty', 'performance_rule'):
        return JsonResponse({'error': '未知措施类型'}, status=400)
    round_num = _get_current_round()
    cancel_round = round_num + 1
    rec = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型=measure_type)
        .order_by('-轮次', '-id')
        .first()
    )
    if not rec:
        return JsonResponse({'error': '未找到可取消的规则记录'}, status=404)
    if rec.取消轮次 is not None and rec.取消轮次 <= cancel_round:
        return JsonResponse({'ok': True, 'id': rec.pk, 'cancel_round': rec.取消轮次})
    # 已被驳回/已取消的记录无需再取消
    if getattr(rec, 'status', None) in ('rejected', 'cancelled'):
        return JsonResponse({'error': '该措施已驳回或已取消，无需重复取消。'}, status=400)
    rec.取消轮次 = cancel_round
    # 若本轮立即取消待审核申请，则直接标记为 cancelled
    if getattr(rec, 'status', None) == 'pending':
        rec.status = 'cancelled'
        rec.save(update_fields=['取消轮次', 'status'])
    else:
        rec.save(update_fields=['取消轮次'])
    action_log(f"平台 {platform_id} 取消治理措施 type={measure_type} round={round_num} cancel_round={cancel_round} rec_id={rec.pk}")
    return JsonResponse({'ok': True, 'id': rec.pk, 'cancel_round': cancel_round})


@ensure_csrf_cookie
def platform_clickbait_detection(request):
    """标题党检测开关页：平台侧不展示参数配置，仅开关。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    cfg = (
        ClickbaitDetectionConfig.objects
        .filter(platform_id=platform_id, status='active')
        .order_by('-id')
        .first()
    )
    measure = _get_effective_governance_measure(platform_id, 'clickbait_detection', current_round)
    latest_measure = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='clickbait_detection')
        .order_by('-轮次', '-id')
        .first()
    )
    is_published = bool(latest_measure and latest_measure.取消轮次 is None and latest_measure.status in ('pending', 'active'))
    return render(request, 'accounts/platform_clickbait_detection.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'config': cfg,
        'is_published': is_published,
        'is_effective': bool(measure),
        'latest_measure': latest_measure,
    })


@require_http_methods(['POST'])
def platform_clickbait_detection_save(request):
    """标题党检测参数配置接口已停用：平台侧不允许配置参数。"""
    return JsonResponse({'error': '平台侧不允许配置标题党检测参数，请由管理员在后台维护默认参数。'}, status=410)


@ensure_csrf_cookie
def platform_traffic_penalty(request):
    """流量惩罚配置页：GET 展示当前配置 + 启用状态。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    cfg = TrafficPenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
    measure = _get_effective_governance_measure(platform_id, 'traffic_penalty', current_round)
    latest_measure = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='traffic_penalty')
        .order_by('-轮次', '-id')
        .first()
    )
    is_published = bool(latest_measure and latest_measure.取消轮次 is None and latest_measure.status in ('pending', 'active'))
    return render(request, 'accounts/platform_traffic_penalty.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'config': cfg,
        'is_published': is_published,
        'is_effective': bool(measure),
        'latest_measure': latest_measure,
    })


@require_http_methods(['POST'])
def platform_traffic_penalty_save(request):
    """提交流量惩罚配置参数（α 值）到管理员审核。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    if TrafficPenaltyConfig.objects.filter(platform_id=platform_id, status__in=['pending', 'active']).exists():
        return JsonResponse({'error': '该配置已提交待审或已生效，不能再次修改。'}, status=400)
    try:
        alpha = Decimal(request.POST.get('alpha', '0.50'))
    except Exception:
        alpha = Decimal('0.50')
    alpha = max(Decimal('0'), min(Decimal('1'), alpha))
    cfg = TrafficPenaltyConfig.objects.create(
        platform_id=platform_id,
        降权系数alpha=alpha,
        status='pending',
        提交人账号=account,
    )
    action_log(
        f"平台 {platform_id} 提交流量惩罚配置待审 config_id={cfg.pk} "
        f"alpha={alpha} 操作人={account}"
    )
    return JsonResponse({'ok': True, 'config_id': cfg.pk})


@ensure_csrf_cookie
def platform_report(request):
    """用户举报机制配置页：GET 展示当前配置 + 启用状态。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    cfg = UserReportConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
    measure = _get_effective_governance_measure(platform_id, 'user_report', current_round)
    latest_measure = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='user_report')
        .order_by('-轮次', '-id')
        .first()
    )
    is_published = bool(latest_measure and latest_measure.取消轮次 is None and latest_measure.status in ('pending', 'active'))
    return render(request, 'accounts/platform_report.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'config': cfg,
        'is_published': is_published,
        'is_effective': bool(measure),
        'latest_measure': latest_measure,
    })


@require_http_methods(['POST'])
def platform_report_save(request):
    """提交用户举报配置参数（阈值、审核方式）到管理员审核。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    if UserReportConfig.objects.filter(platform_id=platform_id, status__in=['pending', 'active']).exists():
        return JsonResponse({'error': '该配置已提交待审或已生效，不能再次修改。'}, status=400)
    try:
        threshold = Decimal(request.POST.get('threshold', '0.30'))
    except Exception:
        threshold = Decimal('0.30')
    threshold = max(Decimal('0'), min(Decimal('1'), threshold))
    review_method = (request.POST.get('review_method') or 'auto').strip()
    if review_method not in ('auto', 'manual'):
        review_method = 'auto'
    cfg = UserReportConfig.objects.create(
        platform_id=platform_id,
        举报触发阈值=threshold,
        审核方式=review_method,
        status='pending',
        提交人账号=account,
    )
    action_log(
        f"平台 {platform_id} 提交用户举报配置待审 config_id={cfg.pk} "
        f"阈值={threshold} 审核方式={review_method} 操作人={account}"
    )
    return JsonResponse({'ok': True, 'config_id': cfg.pk})


@ensure_csrf_cookie
def platform_revenue_penalty(request):
    """收益惩罚配置页：GET 展示当前配置 + 启用状态。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
    measure = _get_effective_governance_measure(platform_id, 'revenue_penalty', current_round)
    latest_measure = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='revenue_penalty')
        .order_by('-轮次', '-id')
        .first()
    )
    is_published = bool(latest_measure and latest_measure.取消轮次 is None and latest_measure.status in ('pending', 'active'))
    return render(request, 'accounts/platform_revenue_penalty.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'config': cfg,
        'is_published': is_published,
        'is_effective': bool(measure),
        'latest_measure': latest_measure,
    })


@require_http_methods(['POST'])
def platform_revenue_penalty_save(request):
    """提交收益惩罚配置参数（β 值）到管理员审核。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    if RevenuePenaltyConfig.objects.filter(platform_id=platform_id, status__in=['pending', 'active']).exists():
        return JsonResponse({'error': '该配置已提交待审或已生效，不能再次修改。'}, status=400)
    try:
        beta = Decimal(request.POST.get('beta', '0.50'))
    except Exception:
        beta = Decimal('0.50')
    beta = max(Decimal('0'), min(Decimal('1'), beta))
    cfg = RevenuePenaltyConfig.objects.create(
        platform_id=platform_id,
        惩罚系数beta=beta,
        status='pending',
        提交人账号=account,
    )
    action_log(
        f"平台 {platform_id} 提交收益惩罚配置待审 config_id={cfg.pk} "
        f"beta={beta} 操作人={account}"
    )
    return JsonResponse({'ok': True, 'config_id': cfg.pk})


def platform_performance(request):
    """平台绩效：展示当前生效方案、待审核方案，提供 w1-w4 输入表单。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    active_scheme = (
        PlatformPerformanceScheme.objects
        .filter(平台=platform_id, status='active')
        .order_by('-生效轮次', '-id')
        .first()
    )
    pending_scheme = (
        PlatformPerformanceScheme.objects
        .filter(平台=platform_id, status='pending')
        .order_by('-创建时间', '-id')
        .first()
    )
    return render(request, 'accounts/platform_performance.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'active_scheme': active_scheme,
        'pending_scheme': pending_scheme,
    })


@require_http_methods(['POST'])
def platform_performance_apply(request):
    """DEPRECATED: 旧版应用绩效方案接口，已废弃，请使用 platform_performance_submit。"""
    return JsonResponse({'error': '该接口已废弃，请使用新的提交接口'}, status=410)


@require_http_methods(['POST'])
def platform_performance_submit(request):
    """提交绩效方案：平台输入 w1-w4 权重，状态为 pending，等待管理员审核。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    try:
        w1 = Decimal(request.POST.get('w1', '0.25'))
        w2 = Decimal(request.POST.get('w2', '0.25'))
        w3 = Decimal(request.POST.get('w3', '0.25'))
        w4 = Decimal(request.POST.get('w4', '0.25'))
    except Exception:
        return JsonResponse({'error': '权重参数格式错误'}, status=400)
    total = w1 + w2 + w3 + w4
    if total <= 0:
        return JsonResponse({'error': '权重之和必须大于 0'}, status=400)
    round_num = _get_current_round()
    effective_round = round_num + 1
    rec = PlatformPerformanceScheme.objects.create(
        平台=platform_id,
        生效轮次=effective_round,
        方案编号='S1_balanced',
        方案内容={'w1': str(w1), 'w2': str(w2), 'w3': str(w3), 'w4': str(w4)},
        发布人账号=account,
        w1_click=w1,
        w2_finish=w2,
        w3_collect=w3,
        w4_satisfaction=w4,
        status='pending',
    )
    action_log(
        f"平台 {platform_id} 提交绩效方案 scheme_id={rec.pk} "
        f"w1={w1} w2={w2} w3={w3} w4={w4} status=pending "
        f"生效轮次={effective_round} 操作人={account}"
    )
    return JsonResponse({'ok': True, 'scheme_id': rec.pk, 'effective_round': effective_round})


def user_platform_check(request):
    """用户点击平台图标时：校验当前所属平台与点击平台是否一致，返回是否匹配及当前平台名。"""
    if request.session.get('role') != 'user':
        return JsonResponse({'error': '未登录或非用户'}, status=403)
    account = request.session.get('account', '')
    try:
        target = int(request.GET.get('target_platform', 0))
    except (TypeError, ValueError):
        target = 0
    target = 0 if target != 1 else 1
    try:
        user = UserAccount.objects.get(账号=account)
        current = user.所属平台 if user.所属平台 in (0, 1) else 0
    except UserAccount.DoesNotExist:
        current = 0
    match = current == target
    return JsonResponse({
        'match': match,
        'current_platform': current,
        'current_platform_name': PLATFORM_NAMES.get(current, '平台1'),
        'target_platform': target,
    })


def _get_current_round():
    """获取当前模拟轮次（从表「模拟轮次」读取，无行则创建 id=1 且 当前轮次=1）。"""
    obj, _ = SimulationRound.objects.get_or_create(pk=1, defaults={'当前轮次': 1})
    return obj.当前轮次


def _platform_name(platform_id: int) -> str:
    return PLATFORM_NAMES.get(platform_id, f'平台{platform_id + 1}')


def _all_platform_choices():
    """当前系统内可供整治的平台列表。"""
    return [{'id': 0, 'name': _platform_name(0)}, {'id': 1, 'name': _platform_name(1)}]


def _sync_regulation_actions_finished(current_round: int):
    """将已超过结束轮次且仍为 active 的专项行动标记为 finished。"""
    RegulationAction.objects.filter(
        状态='active',
        结束轮次__lt=current_round,
    ).update(状态='finished')


def _is_platform_under_regulation(platform_id: int, current_round: int) -> bool:
    """某平台在当前轮次是否处于专项整治中。"""
    RegulationAction.objects.filter(
        整治平台编号=platform_id,
        结束轮次__lt=current_round,
        状态='active',
    ).update(状态='finished')
    return RegulationAction.objects.filter(
        整治平台编号=platform_id,
        开始轮次__lte=current_round,
        结束轮次__gte=current_round,
        状态='active',
    ).exists()


def _ensure_spot_check_result(reg_action: RegulationAction) -> PlatformSpotCheckResult:
    """为专项行动行补建抽查结果记录（兼容历史数据）。"""
    obj, _created = PlatformSpotCheckResult.objects.get_or_create(
        专项行动=reg_action,
        defaults={
            '行动编号': reg_action.行动编号,
            '整治平台编号': reg_action.整治平台编号,
            '整治平台名称': reg_action.整治平台名称,
            '是否查看': False,
        },
    )
    return obj


def _regulation_progress_elapsed(current_round: int, start_round: int, total_duration: int) -> int:
    """已持续轮次（不超过总持续轮次）。"""
    total_duration = max(1, int(total_duration or 1))
    return min(max(0, int(current_round) - int(start_round)), total_duration)


def _next_regulation_action_id() -> str:
    """生成监管专项行动编号，格式 0001 递增。"""
    last_app = RegulationActionApplication.objects.order_by('-id').first()
    if not last_app:
        return '0001'
    try:
        next_value = int(str(last_app.行动编号).strip()) + 1
    except Exception:
        next_value = int(last_app.pk) + 1
    return f"{next_value:04d}"


def _get_effective_profit_config(round_num: int, platform_id: int = None):
    """获取指定轮次生效的利润权重配置（若无则返回 None）。"""
    qs = (
        ProfitWeightConfig.objects
        .filter(生效轮次起__lte=round_num)
        .filter(Q(生效轮次止__isnull=True) | Q(生效轮次止__gte=round_num))
    )
    if platform_id is not None:
        result = qs.filter(平台=platform_id).order_by('-生效轮次起', '-id').first()
        if result:
            return result
    return qs.order_by('-生效轮次起', '-id').first()


def _decimal(v) -> Decimal:
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except Exception:
        return Decimal('0')


def _settle_article_revenue(platform_id: int, round_num: int):
    """收益结算：遍历本轮该平台所有文章，计算原始收益，若为标题党且启用了收益惩罚则乘以 β。

    公式：
        原始收益 = w1×点击量 + w2×阅读完成量 + w3×收藏量 + w4×满意度均分
        最终收益 = 原始收益 × β（若标题党且启用惩罚），否则 = 原始收益

    由 end_round 结算流程调用。
    """
    from accounts.models import (
        Article, PlatformPerformanceScheme, RevenuePenaltyConfig,
        ArticleRevenueSettlement, WriterAccount,
    )

    # 同轮重复结束本轮时先清旧明细，避免 ArticleRevenueSettlement 重复行
    ArticleRevenueSettlement.objects.filter(platform_id=platform_id, 轮次=round_num).delete()

    active_scheme = (
        PlatformPerformanceScheme.objects
        .filter(平台=platform_id, status='active', 生效轮次__lte=round_num)
        .order_by('-生效轮次', '-id')
        .first()
    )
    w1 = Decimal(str(active_scheme.w1_click or 0)) if active_scheme else Decimal('0.25')
    w2 = Decimal(str(active_scheme.w2_finish or 0)) if active_scheme else Decimal('0.25')
    w3 = Decimal(str(active_scheme.w3_collect or 0)) if active_scheme else Decimal('0.25')
    w4 = Decimal(str(active_scheme.w4_satisfaction or 0)) if active_scheme else Decimal('0.25')

    revenue_penalty_measure = _get_effective_governance_measure(platform_id, 'revenue_penalty', round_num)
    beta = Decimal('1.0')
    if revenue_penalty_measure:
        rp_cfg = RevenuePenaltyConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
        if rp_cfg:
            beta = rp_cfg.惩罚系数beta

    writers = WriterAccount.objects.filter(所属平台=platform_id)
    writer_accounts = set(writers.values_list('账号', flat=True))

    articles = Article.objects.filter(写手账号__in=writer_accounts, 轮次=round_num)

    for art in articles:
        clicks = art.点击量 or 0
        finish_count = UserArticleReadComplete.objects.filter(文章=art).count()
        collect_count = UserArticleCollect.objects.filter(文章=art).count()
        satisfaction = Decimal('0')

        raw_revenue = (
            w1 * Decimal(str(clicks))
            + w2 * Decimal(str(finish_count))
            + w3 * Decimal(str(collect_count))
            + w4 * satisfaction
        )

        penalty_applied = False
        penalty_coeff = Decimal('1.0')
        if art.is_clickbait and revenue_penalty_measure:
            penalty_applied = True
            penalty_coeff = beta

        final_revenue = raw_revenue * penalty_coeff

        art.报酬 = int(final_revenue)
        art.save(update_fields=['报酬'])

        ArticleRevenueSettlement.objects.create(
            platform_id=platform_id,
            写手账号=art.写手账号,
            文章=art,
            轮次=round_num,
            点击量=clicks,
            阅读完成量=finish_count,
            收藏量=collect_count,
            满意度均分=satisfaction,
            w1=w1, w2=w2, w3=w3, w4=w4,
            原始收益=raw_revenue,
            penalty_applied=penalty_applied,
            penalty_coefficient=penalty_coeff,
            最终收益=final_revenue,
        )

        action_log(
            f"文章收益结算 article_id={art.pk} writer={art.写手账号} "
            f"round={round_num} platform={platform_id} "
            f"clicks={clicks} finish={finish_count} collect={collect_count} "
            f"w1={w1} w2={w2} w3={w3} w4={w4} "
            f"raw={raw_revenue} is_clickbait={art.is_clickbait} "
            f"penalty={'1' if penalty_applied else '0'} beta={penalty_coeff} final={final_revenue}"
        )


def _submit_user_report(user_account: str, article_id: int, platform_id: int, round_num: int):
    """用户提交举报 — 落库 ArticleReport。
    在用户点击举报按钮时调用，若平台已启用用户举报功能包则写入记录。
    """
    from accounts.models import ArticleReport
    rec = ArticleReport.objects.create(
        platform_id=platform_id,
        文章_id=article_id,
        举报人=user_account,
        举报轮次=round_num,
        审核状态='pending',
    )
    article = Article.objects.filter(pk=article_id).first()
    writer_account = getattr(article, '写手账号', '')
    action_log(
        f"{PLATFORM_NAMES.get(platform_id, f'平台{platform_id}')}用户{user_account}"
        f"在{round_num}轮次举报了{writer_account}写手的{article_id}文章 "
        f"report_id={rec.pk}"
    )
    return rec


def _process_article_reports(platform_id: int, round_num: int):
    """每轮结算时处理举报 — 统计举报数、判断是否达阈值、触发审核。

    逻辑：
    1. 统计每篇文章本轮的 ArticleReport 数量 → 更新 Article.report_count_current_round
    2. 若 report_count / 阅读次数 >= 阈值：触发审核
    3. 审核通过：更新 Article.is_clickbait=True, method_user=True
    4. 无论自动检测还是用户举报，只要 is_clickbait=True，后续已启用的惩罚措施均自动生效。

    由 end_round 结算流程调用。当前为预留接口，待 end_round 改造时集成。
    """
    from accounts.models import UserReportConfig, ArticleReport, Article
    from django.db.models import Count

    # 仅当该平台该轮次启用了用户举报机制时，才触发达阈值审核流程
    measure = _get_effective_governance_measure(platform_id, 'user_report', round_num)
    if not measure:
        return

    cfg = None
    if getattr(measure, 'config_id', None):
        cfg = UserReportConfig.objects.filter(pk=measure.config_id).first()
    if not cfg:
        cfg = UserReportConfig.objects.filter(platform_id=platform_id).order_by('-id').first()
    if not cfg:
        return

    threshold = cfg.举报触发阈值
    review_method = cfg.审核方式

    reports_by_article = (
        ArticleReport.objects
        .filter(platform_id=platform_id, 举报轮次=round_num)
        .values('文章_id')
        .annotate(cnt=Count('id'))
    )

    for item in reports_by_article:
        art_id = item['文章_id']
        cnt = item['cnt']
        try:
            art = Article.objects.get(pk=art_id)
        except Article.DoesNotExist:
            continue

        art.report_count_current_round = cnt
        art.save(update_fields=['report_count_current_round'])

        read_count = art.点击量 or 1
        ratio = Decimal(str(cnt)) / Decimal(str(read_count))
        if ratio >= threshold:
            confirmed = False
            if review_method == 'auto':
                confirmed = True
            # manual: 留待管理员在 admin 后台审核，此处不自动确认

            if confirmed:
                art.is_clickbait = True
                art.method_user = True
                art.save(update_fields=['is_clickbait', 'method_user'])
                ArticleReport.objects.filter(
                    platform_id=platform_id, 文章_id=art_id, 举报轮次=round_num
                ).update(审核状态='approved')
                action_log(
                    f"举报达阈值自动审核通过 article_id={art_id} platform={platform_id} "
                    f"round={round_num} report_count={cnt} read_count={read_count} "
                    f"ratio={str(ratio)} threshold={str(threshold)}"
                )
            else:
                action_log(
                    f"举报达阈值待人工审核 article_id={art_id} platform={platform_id} "
                    f"round={round_num} report_count={cnt} read_count={read_count} "
                    f"ratio={str(ratio)} threshold={str(threshold)}"
                )


def _get_effective_governance_measure(platform_id: int, measure_type: str, round_num: int):
    """获取某平台某措施类型在指定轮次是否有效（生效且未取消），返回 PlatformGovernanceMeasure 或 None。"""
    return (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型=measure_type, 生效轮次__lte=round_num, status='active')
        .filter(Q(取消轮次__isnull=True) | Q(取消轮次__gt=round_num))
        .order_by('-生效轮次', '-id')
        .first()
    )


def is_clickbait(article, platform_id: int, round_num: int) -> bool:
    """标题党检测 — 可插拔接口。

    判定规则（使用管理员生效配置）：
    当 写手文章的 标题夸张度_校准值 >= 标题夸张度阈值X 且 内容相关度_校准值 < 内容相关度阈值Y 时，
    判定为标题党。

    返回 True 表示该文章被判定为标题党，False 表示非标题党。
    若平台未启用标题党检测功能包，直接返回 False。
    """
    measure = _get_effective_governance_measure(platform_id, 'clickbait_detection', round_num)
    if not measure:
        return False
    cfg = (
        ClickbaitDetectionConfig.objects
        .filter(platform_id=platform_id, status='active')
        .order_by('-id')
        .first()
    )
    if not cfg:
        return False

    try:
        X_threshold = int(getattr(cfg, '标题夸张度阈值X', 4) or 4)
    except Exception:
        X_threshold = 4
    try:
        Y_threshold = int(getattr(cfg, '内容相关度阈值Y', 3) or 3)
    except Exception:
        Y_threshold = 3

    X = int(article.标题夸张度_校准值 or article.标题夸张度_初始值 or 0)
    Y = int(article.内容相关度_校准值 or article.内容相关度_初始值 or 0)

    return (X >= X_threshold) and (Y < Y_threshold)


def _execute_platform_patrol(application):
    """
    执行平台巡查并写入 PlatformPatrolResult。
    返回 (result, None) 成功，或 (None, error_message)。
    """
    current_round = _get_current_round()
    if application.起始轮次 > application.终止轮次:
        return None, '起始轮次不能大于终止轮次'
    if application.终止轮次 >= current_round:
        return None, '终止轮次须严格小于当前轮次'

    if PlatformPatrolResult.objects.filter(申请记录=application).exists():
        return None, '该申请已存在巡查结果'

    platform_id = application.平台编号
    writers = list(WriterAccount.objects.filter(所属平台=platform_id).values_list('账号', flat=True))
    id_list = list(
        Article.objects.filter(
            写手账号__in=writers,
            轮次__gte=application.起始轮次,
            轮次__lte=application.终止轮次,
        ).values_list('id', flat=True)
    )
    total = len(id_list)
    ratio = float(application.巡查比例)
    sample_count = max(0, int(round(total * ratio)))

    rng = random.Random(application.pk)
    if total == 0:
        sampled_ids = []
    else:
        k = min(sample_count, total)
        sampled_ids = rng.sample(id_list, k)

    articles = Article.objects.filter(id__in=sampled_ids)
    art_by_id = {a.id: a for a in articles}
    ordered = [art_by_id[i] for i in sampled_ids if i in art_by_id]

    clickbait_n = 0
    for art in ordered:
        if art.is_clickbait is True:
            clickbait_n += 1
        elif art.is_clickbait is False:
            pass
        else:
            if is_clickbait(art, platform_id, art.轮次):
                clickbait_n += 1

    n = len(sampled_ids)
    if n == 0:
        rate = Decimal('0')
    else:
        rate = Decimal(clickbait_n) / Decimal(n)

    user_count = UserAccount.objects.filter(所属平台=platform_id).count()

    result = PlatformPatrolResult.objects.create(
        申请记录=application,
        平台编号=platform_id,
        平台名称=application.平台名称,
        巡查比例=application.巡查比例,
        起始轮次=application.起始轮次,
        终止轮次=application.终止轮次,
        用户数=user_count,
        抽查文章数=n,
        抽查文章列表=sampled_ids,
        标题党率=rate,
        执行轮次=current_round,
    )
    return result, None


def _get_effective_health_rule(platform_id: int, round_num: int):
    """获取某平台在某轮次是否存在有效的账号健康分规则（返回 PlatformGovernanceMeasure 或 None）。"""
    rec = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='account_health_rule')
        .order_by('-轮次', '-id')
        .first()
    )
    if not rec:
        return None
    if getattr(rec, 'status', None) and rec.status != 'active':
        return None
    if rec.生效轮次 and rec.生效轮次 > round_num:
        return None
    if rec.取消轮次 is not None and round_num >= rec.取消轮次:
        return None
    return rec


def _get_latest_account_health_config(platform_id: int):
    """获取平台最新健康分配置。"""
    return AccountHealthConfig.objects.filter(platform_id=platform_id).order_by('-id').first()


def _get_effective_health_level_configs(round_num: int, platform_id: int = None, config_id: int = None):
    """获取指定轮次生效的健康分档位配置列表（按排序优先）。

    查询优先级：
    1) 平台+配置专属档位；
    2) 平台专属默认档位（config 为空）；
    3) 全局默认档位（平台为空，config 为空）。
    """
    base_qs = AccountHealthLevelConfig.objects.filter(
        生效轮次起__lte=round_num
    ).filter(
        Q(生效轮次止__isnull=True) | Q(生效轮次止__gte=round_num)
    )

    if platform_id is not None:
        base_qs = base_qs.filter(Q(平台=platform_id) | Q(平台__isnull=True))

    def _ordered(qs):
        return list(qs.order_by('排序', '下界开', '上界闭', 'id'))

    if config_id is not None:
        preferred = _ordered(base_qs.filter(config_id=config_id))
        if preferred:
            return preferred

    platform_default = _ordered(base_qs.filter(平台=platform_id, config_id__isnull=True)) if platform_id is not None else []
    if platform_default:
        return platform_default

    return _ordered(base_qs.filter(平台__isnull=True, config_id__isnull=True))


def _resolve_health_tier_and_ratio(score: int, configs):
    """按(下界开,上界闭]匹配健康档位标签和推流系数；未匹配返回默认值。"""
    s = int(score or 0)
    for c in configs or []:
        if s > int(c.下界开) and s <= int(c.上界闭):
            return (c.档位标签 or '', _decimal(c.可推流比例))
    return ('', Decimal('0.7000'))


def _match_push_ratio(score: int, configs):
    return _resolve_health_tier_and_ratio(score, configs)[1]


def _recover_writer_health_for_platform(platform_id: int, round_num: int):
    """按平台执行健康分恢复机制（在结束本轮时调用）。"""
    # 与扣分口径保持一致：仅在“账号健康分治理措施处于生效中”时，才允许执行恢复。
    health_rule = _get_effective_health_rule(platform_id, round_num)
    if not health_rule:
        return

    cfg = _get_latest_account_health_config(platform_id)
    if not cfg or not cfg.是否启用恢复机制:
        return
    clean_rounds = max(1, int(cfg.恢复所需连续无违规轮次 or 1))
    recover_value = max(0, int(cfg.每次恢复分值 or 0))
    if recover_value <= 0:
        return
    start_round = max(1, int(round_num) - clean_rounds + 1)
    writers = WriterAccount.objects.filter(所属平台=platform_id)
    level_configs = _get_effective_health_level_configs(round_num, platform_id=platform_id, config_id=cfg.pk)
    for writer in writers:
        has_violation = WriterHealthScoreLog.objects.filter(
            写手账号=writer.账号,
            event_type='violation',
            轮次__gte=start_round,
            轮次__lte=round_num,
        ).exists()
        if has_violation:
            continue
        before = int(getattr(writer, '健康分', cfg.初始健康分 or 100))
        after = before + recover_value
        tier, ratio = _resolve_health_tier_and_ratio(after, level_configs)
        writer.健康分 = after
        writer.health_tier = tier
        writer.推流系数 = ratio
        writer.健康分最近更新轮次 = round_num
        writer.save(update_fields=['健康分', 'health_tier', '推流系数', '健康分最近更新轮次'])
        WriterHealthScoreLog.objects.create(
            写手账号=writer.账号,
            轮次=round_num,
            event_type='recovery',
            文章编号=None,
            变更值=recover_value,
            原因='consecutive_clean_rounds',
        )
        action_log(
            f"健康分恢复 writer={writer.账号} round={round_num} clean_rounds={clean_rounds} "
            f"recover={recover_value} before={before} after={after} tier={tier} gamma={str(ratio)}"
        )


def _settle_cycle_profit(platform_id: int, cycle_index: int, start_round: int, end_round: int):
    """按周期结算平台利润并写入 PlatformCycleProfitRecord。"""
    cfg = _get_effective_profit_config(end_round, platform_id) or ProfitWeightConfig.objects.order_by('-id').first()
    if not cfg:
        action_log(
            f"周期利润结算跳过 platform={platform_id} cycle={cycle_index} "
            f"rounds={start_round}-{end_round} reason=missing_profit_config"
        )
        return None

    writers = WriterAccount.objects.filter(所属平台=platform_id)
    writer_accounts = set(writers.values_list('账号', flat=True))
    article_qs = Article.objects.filter(
        写手账号__in=writer_accounts,
        轮次__gte=start_round,
        轮次__lte=end_round,
    )
    agg = article_qs.aggregate(
        total_click=Sum('点击量'),
        total_collect=Sum('收藏量'),
        total_finish=Sum('阅读完成量'),
    )
    total_click = int(agg.get('total_click') or 0)
    total_collect = int(agg.get('total_collect') or 0)
    total_finish = int(agg.get('total_finish') or 0)
    fans_snapshot = UserAccount.objects.filter(所属平台=platform_id).count()

    # 监管成本预留：当前先置 0
    supervision_cost_level = '无'
    supervision_cost_value = Decimal('0')

    click_w = _decimal(cfg.点击率权重)
    collect_w = _decimal(cfg.收藏率权重)
    finish_w = _decimal(cfg.阅读完成率权重)
    fans_w = _decimal(cfg.平台粉丝数权重)
    supervision_w = _decimal(cfg.监管成本权重)

    profit_total = (
        _decimal(total_click) * click_w
        + _decimal(total_collect) * collect_w
        + _decimal(total_finish) * finish_w
        + _decimal(fans_snapshot) * fans_w
        + _decimal(supervision_cost_value) * supervision_w
    )

    prev = PlatformCycleProfitRecord.objects.filter(
        platform_id=platform_id, cycle_index=cycle_index - 1
    ).first()
    prev_profit = _decimal(prev.profit_total) if prev else None

    weight_snapshot = {
        'config_id': cfg.pk,
        '平台': cfg.平台,
        '生效轮次起': cfg.生效轮次起,
        '生效轮次止': cfg.生效轮次止,
        '利润展示窗口轮数': cfg.利润展示窗口轮数,
        '点击率权重': str(click_w),
        '收藏率权重': str(collect_w),
        '阅读完成率权重': str(finish_w),
        '平台粉丝数权重': str(fans_w),
        '监管成本权重': str(supervision_w),
    }

    rec, _ = PlatformCycleProfitRecord.objects.update_or_create(
        platform_id=platform_id,
        cycle_index=cycle_index,
        defaults={
            'cycle_start_round': start_round,
            'cycle_end_round': end_round,
            'total_click': total_click,
            'total_collect': total_collect,
            'total_finish': total_finish,
            'fans_snapshot': fans_snapshot,
            'supervision_cost_level': supervision_cost_level,
            'supervision_cost_value': supervision_cost_value,
            'profit_total': profit_total,
            'profit_prev_cycle': prev_profit,
            'weight_config_snapshot': weight_snapshot,
        },
    )

    action_log(
        f"周期利润结算 platform={platform_id} cycle={cycle_index} rounds={start_round}-{end_round} "
        f"total_click={total_click} total_collect={total_collect} total_finish={total_finish} "
        f"fans={fans_snapshot} supervision={supervision_cost_level}:{str(supervision_cost_value)} "
        f"profit_total={str(profit_total)}"
    )
    return rec


# 问卷选项文案，与前端一致
SURVEY_OPTIONS = {
    'A': 'A. 环境污染：标题党太多，心烦。',
    'B': 'B. 内容枯竭：没好文章看。',
    'C': 'C. 好奇心：单纯想去隔壁平台看看。',
    'D_PREFIX': 'D. 其他：',
}


@require_http_methods(['POST'])
def user_switch_platform(request):
    """用户提交问卷后切换平台：先写入切换平台问卷调查，再更新所属平台并设置 1 分钟内禁止登录。"""
    if request.session.get('role') != 'user':
        return JsonResponse({'error': '未登录或非用户'}, status=403)
    account = request.session.get('account', '')
    try:
        target = int(request.POST.get('target_platform', 0))
    except (TypeError, ValueError):
        target = 0
    target = 0 if target != 1 else 1
    try:
        from_platform = int(request.POST.get('from_platform', 0))
    except (TypeError, ValueError):
        from_platform = 0
    from_platform = 0 if from_platform != 1 else 1
    switch_reason = (request.POST.get('switch_reason') or '').strip()
    if not switch_reason:
        return JsonResponse({'error': '请选择切换平台原因'}, status=400)
    try:
        user = UserAccount.objects.get(账号=account)
    except UserAccount.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=400)
    round_num = _get_current_round()
    PlatformSwitchSurvey.objects.create(
        用户编号=user.pk,
        切换前平台=from_platform,
        切换后平台=target,
        轮次=round_num,
        切换平台原因=switch_reason,
    )
    user.所属平台 = target
    user.禁止登录截止时间 = timezone.now() + timedelta(minutes=1)
    user.save(update_fields=['所属平台', '禁止登录截止时间'])
    from_platform_name = PLATFORM_NAMES.get(from_platform, f'平台{from_platform}')
    to_platform_name = PLATFORM_NAMES.get(target, f'平台{target}')
    action_log(f"用户 {account} 切换平台 从 {from_platform_name} 到 {to_platform_name} 原因={switch_reason!r}")
    request.session.flush()
    return JsonResponse({'ok': True, 'redirect': '/'})


def user_browse(request, platform_id):
    """平台浏览界面：关注列表/发现列表来自文章推送记录，仅展示推送给当前用户的文章，按发布先后从上到下排列。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return redirect('accounts:login')
    platform_id = 0 if platform_id not in (0, 1) else platform_id
    request.session['user_browse_platform_id'] = platform_id
    name = PLATFORM_NAMES.get(platform_id, '平台1')
    try:
        user = UserAccount.objects.get(账号=account)
    except UserAccount.DoesNotExist:
        user = None
    current_round = _get_current_round()
    if not user:
        follow_list = []
        discover_list = []
    else:
        # 只展示当前轮次的推送；关注列表/发现列表按文章创建时间升序（先发布的在上）
        follow_list = [
            p.文章 for p in
            ArticlePush.objects.filter(用户=user, 列表类型=0, 文章__轮次=current_round)
            .exclude(文章__标题='').filter(文章__标题__isnull=False)
            .select_related('文章')
            .order_by('文章__创建时间')
        ]
        discover_list = [
            p.文章 for p in
            ArticlePush.objects.filter(用户=user, 列表类型=1, 文章__轮次=current_round)
            .exclude(文章__标题='').filter(文章__标题__isnull=False)
            .select_related('文章')
            .order_by('文章__创建时间')
        ]
    visited_article_ids = request.session.get('visited_article_ids') or []
    return render(request, 'accounts/user_browse.html', {
        'platform_name': name,
        'platform_id': platform_id,
        'follow_list': follow_list,
        'discover_list': discover_list,
        'visited_article_ids': visited_article_ids,
    })


def user_article_view(request, article_id):
    """用户点击文章进入：点击量+1，记录已访问，展示文章页（右侧数据同步更新）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return redirect('accounts:login')
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return redirect('accounts:user_home')
    # 记录本会话中已进入过的文章，浏览页将对应标题变灰且不可再点
    visited = request.session.get('visited_article_ids') or []
    if article_id not in visited:
        visited = list(visited) + [article_id]
        request.session['visited_article_ids'] = visited
    article.点击量 += 1
    article.save(update_fields=['点击量'])
    title_short = (article.标题 or '')[:50] + ('...' if len(article.标题 or '') > 50 else '')
    action_log(f"用户 {account} 点击进入文章 article_id={article_id} 标题={title_short!r}")
    comments = list(article.评论列表.all().order_by('创建时间'))
    platform_id = request.session.get('user_browse_platform_id', 0)
    has_liked = has_collected = has_read_complete = has_reported = False
    try:
        user = UserAccount.objects.get(账号=account)
        is_following = user.关注列表.filter(写手账号=article.写手账号).exists()
        has_liked = UserArticleLike.objects.filter(用户=user, 文章=article).exists()
        has_collected = UserArticleCollect.objects.filter(用户=user, 文章=article).exists()
        has_read_complete = UserArticleReadComplete.objects.filter(用户=user, 文章=article).exists()
        has_reported = ArticleReport.objects.filter(
            platform_id=getattr(user, '所属平台', 0),
            文章=article,
            举报人=account,
            举报轮次=_get_current_round(),
        ).exists()
    except UserAccount.DoesNotExist:
        pass
    return render(request, 'accounts/article_detail.html', {
        'article': article,
        'comments': comments,
        'comment_count': len(comments),
        'is_user_view': True,
        'platform_id': platform_id,
        'is_following': is_following,
        'has_liked': has_liked,
        'has_collected': has_collected,
        'has_read_complete': has_read_complete,
        'has_reported': has_reported,
    })


def _require_user_article(request, article_id):
    """要求用户角色，返回 (user, article) 或 (None, None)。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return None, None
    try:
        user = UserAccount.objects.get(账号=account)
        article = Article.objects.get(pk=article_id)
        return user, article
    except (UserAccount.DoesNotExist, Article.DoesNotExist):
        return None, None


@require_http_methods(['POST'])
def user_article_like(request, article_id):
    """文章点赞：切换。已点赞则取消（-1），否则点赞（+1）。"""
    user, article = _require_user_article(request, article_id)
    if not user or not article:
        return JsonResponse({'error': '未登录或文章不存在'}, status=403)
    rec, created = UserArticleLike.objects.get_or_create(用户=user, 文章=article)
    if created:
        article.点赞量 += 1
        article.save(update_fields=['点赞量'])
        action_log(f"用户 {user.账号} 对文章 id={article_id} 点赞")
        return JsonResponse({'ok': True, '点赞量': article.点赞量, '已点赞': True})
    rec.delete()
    article.点赞量 = max(0, article.点赞量 - 1)
    article.save(update_fields=['点赞量'])
    action_log(f"用户 {user.账号} 对文章 id={article_id} 取消点赞")
    return JsonResponse({'ok': True, '点赞量': article.点赞量, '已点赞': False})


@require_http_methods(['POST'])
def user_article_collect(request, article_id):
    """文章收藏：切换。已收藏则取消（-1），否则收藏（+1）。"""
    user, article = _require_user_article(request, article_id)
    if not user or not article:
        return JsonResponse({'error': '未登录或文章不存在'}, status=403)
    rec, created = UserArticleCollect.objects.get_or_create(用户=user, 文章=article)
    if created:
        article.收藏量 += 1
        article.save(update_fields=['收藏量'])
        action_log(f"用户 {user.账号} 收藏文章 id={article_id}")
        return JsonResponse({'ok': True, '收藏量': article.收藏量, '已收藏': True})
    rec.delete()
    article.收藏量 = max(0, article.收藏量 - 1)
    article.save(update_fields=['收藏量'])
    action_log(f"用户 {user.账号} 取消收藏文章 id={article_id}")
    return JsonResponse({'ok': True, '收藏量': article.收藏量, '已收藏': False})


@require_http_methods(['POST'])
def user_article_read_complete(request, article_id):
    """全文阅读完成：切换。已阅读完成则取消（-1），否则+1。"""
    user, article = _require_user_article(request, article_id)
    if not user or not article:
        return JsonResponse({'error': '未登录或文章不存在'}, status=403)
    rec, created = UserArticleReadComplete.objects.get_or_create(用户=user, 文章=article)
    if created:
        article.阅读完成量 += 1
        article.save(update_fields=['阅读完成量'])
        action_log(f"用户 {user.账号} 阅读完成 文章 id={article_id}")
        return JsonResponse({'ok': True, '阅读完成量': article.阅读完成量, '已阅读完成': True})
    rec.delete()
    article.阅读完成量 = max(0, article.阅读完成量 - 1)
    article.save(update_fields=['阅读完成量'])
    action_log(f"用户 {user.账号} 取消阅读完成 文章 id={article_id}")
    return JsonResponse({'ok': True, '阅读完成量': article.阅读完成量, '已阅读完成': False})


@require_http_methods(['POST'])
def user_article_follow(request, article_id):
    """关注写手：用户关注列表新增写手，文章吸粉数+1。"""
    user, article = _require_user_article(request, article_id)
    if not user or not article:
        return JsonResponse({'error': '未登录或文章不存在'}, status=403)
    if user.关注列表.filter(写手账号=article.写手账号).exists():
        return JsonResponse({'ok': True, 'is_following': True, '吸粉数': article.吸粉数})
    UserFollowWriter.objects.create(用户=user, 写手账号=article.写手账号)
    article.吸粉数 += 1
    article.save(update_fields=['吸粉数'])
    writer = WriterAccount.objects.filter(账号=article.写手账号).first()
    if writer:
        writer.粉丝数 += 1
        writer.save(update_fields=['粉丝数'])
    action_log(f"用户 {user.账号} 关注写手 {article.写手账号} 文章 id={article_id}")
    return JsonResponse({'ok': True, 'is_following': True, '吸粉数': article.吸粉数})


@require_http_methods(['POST'])
def user_article_unfollow(request, article_id):
    """取消关注。quick_unfollow=1 时仅删除关注并吸粉数-1（同页内手滑取关）；否则需问卷，取关数+1。"""
    user, article = _require_user_article(request, article_id)
    if not user or not article:
        return JsonResponse({'error': '未登录或文章不存在'}, status=403)
    quick_unfollow = request.POST.get('quick_unfollow') == '1'
    if quick_unfollow:
        UserFollowWriter.objects.filter(用户=user, 写手账号=article.写手账号).delete()
        article.吸粉数 = max(0, article.吸粉数 - 1)
        article.save(update_fields=['吸粉数'])
        writer = WriterAccount.objects.filter(账号=article.写手账号).first()
        if writer and writer.粉丝数 > 0:
            writer.粉丝数 -= 1
            writer.save(update_fields=['粉丝数'])
        action_log(f"用户 {user.账号} 取消关注写手 {article.写手账号} 文章 id={article_id} (同页手滑取关)")
        return JsonResponse({'ok': True, 'is_following': False, '吸粉数': article.吸粉数, 'quick': True})
    reason = (request.POST.get('unfollow_reason') or '').strip()
    if not reason:
        return JsonResponse({'error': '请选择取关原因'}, status=400)
    UserFollowWriter.objects.filter(用户=user, 写手账号=article.写手账号).delete()
    article.取关数 += 1
    article.save(update_fields=['取关数'])
    writer = WriterAccount.objects.filter(账号=article.写手账号).first()
    if writer and writer.粉丝数 > 0:
        writer.粉丝数 -= 1
        writer.save(update_fields=['粉丝数'])
    UnfollowSurvey.objects.create(
        用户编号=user.pk,
        写手账号=article.写手账号,
        当前轮次=_get_current_round(),
        取关原因=reason,
        文章编号=article.pk,
    )
    action_log(f"用户 {user.账号} 取消关注写手 {article.写手账号} 文章 id={article_id} 问卷取关原因={reason!r}")
    return JsonResponse({'ok': True, 'is_following': False, '取关数': article.取关数})


@require_http_methods(['POST'])
@_serialize_sqlite_writes
@retry_on_db_locked(max_retries=3, delay=0.5)
def user_article_report(request, article_id):
    """用户举报文章：始终记录举报；达阈值审核仅在平台启用机制时触发。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return JsonResponse({'error': '未登录或非用户角色'}, status=403)
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return JsonResponse({'error': '文章不存在'}, status=404)

    user = UserAccount.objects.filter(账号=account).first()
    if not user:
        return JsonResponse({'error': '用户不存在'}, status=404)

    platform_id = getattr(user, '所属平台', 0)
    round_num = _get_current_round()

    already = ArticleReport.objects.filter(
        platform_id=platform_id, 文章=article, 举报人=account, 举报轮次=round_num
    ).exists()
    if already:
        return JsonResponse({'error': '本轮已举报过该文章'}, status=400)

    rec = _submit_user_report(account, article_id, platform_id, round_num)
    # 举报后即时更新文章举报计数（并发场景使用原子自增避免 count() 锁表）
    Article.objects.filter(pk=article.pk).update(
        report_count_current_round=F('report_count_current_round') + 1
    )
    return JsonResponse({'ok': True, 'report_id': rec.pk})


@require_http_methods(['POST'])
def user_article_add_comment(request, article_id):
    """发布评论：新增评论，评论数+1。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'user':
        return JsonResponse({'error': '未登录'}, status=403)
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return JsonResponse({'error': '文章不存在'}, status=404)
    content = (request.POST.get('content') or '').strip()
    if not content:
        return JsonResponse({'error': '评论内容不能为空'}, status=400)
    Comment.objects.create(文章=article, 内容=content, 评论者=account)
    content_short = (content[:100] + '...') if len(content) > 100 else content
    action_log(f"用户 {account} 对文章 id={article_id} 评论 内容={content_short!r}")
    count = article.评论列表.count()
    return JsonResponse({'ok': True, 'comment_count': count})


def logout_view(request):
    """登出并回到登录页。"""
    request.session.flush()
    return redirect('accounts:login')


@require_http_methods(['POST'])
def end_round(request):
    """结束本轮：
    1) 按平台结算本轮文章收益（绩效 w1-w4 + 收益惩罚 β），落库 ArticleRevenueSettlement，更新 Article.报酬。
    2) 若命中周期末，结算平台周期利润并写 PlatformCycleProfitRecord。
    3) 再将当前模拟轮次 +1，不删任何文章/推送数据。

    用户端列表只查当前轮次，故等效于清空列表进入下一轮。可由管理员或脚本在用户们退出后调用。
    """
    round_to_settle = _get_current_round()
    # 目前平台编码沿用 0/1；后续扩展更多平台时，可改为从平台表/配置表读取
    settled = []
    settled_cycle_profit = []
    for pid in (0, 1):
        _recover_writer_health_for_platform(pid, round_to_settle)
        # 先处理用户举报（若该轮启用），再做收益结算，保证后续惩罚链路可见。
        _process_article_reports(pid, round_to_settle)
        _settle_article_revenue(pid, round_to_settle)
        cfg = _get_effective_profit_config(round_to_settle, pid) or ProfitWeightConfig.objects.order_by('-id').first()
        period = int(getattr(cfg, '利润展示窗口轮数', 4) or 4)
        period = max(1, period)
        if round_to_settle % period == 0:
            cycle_index = round_to_settle // period
            start_round = round_to_settle - period + 1
            rec = _settle_cycle_profit(pid, cycle_index, start_round, round_to_settle)
            if rec:
                settled_cycle_profit.append({'platform_id': pid, 'cycle_index': cycle_index})
        settled.append({'platform_id': pid})

    SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
    new_round = _get_current_round()
    action_log(
        f"结束本轮 round={round_to_settle} -> {new_round} | 已文章收益结算={settled} "
        f"| 周期利润结算={settled_cycle_profit}"
    )
    return JsonResponse({
        'ok': True,
        'current_round': new_round,
        'settled_revenue': settled,
        'settled_cycle_profit': settled_cycle_profit,
    })


@require_http_methods(['POST'])
@_serialize_sqlite_writes
@retry_on_db_locked(max_retries=3, delay=0.5)
def writer_start_article(request):
    """写手点击「发布文章」时创建文章对象，并将 article_id 存入 session。"""
    if request.session.get('role') != 'writer':
        return JsonResponse({'error': '未登录或非写手'}, status=403)
    account = request.session.get('account', '')
    if not account:
        return JsonResponse({'error': '未登录'}, status=403)
    article = Article.objects.create(写手账号=account)
    request.session['writer_article_id'] = article.pk
    action_log(f"写手 {account} 点击发布文章 article_id={article.pk}")
    return JsonResponse({'article_id': article.pk})


def _get_writer_article(request):
    """从 session 获取当前写手正在编辑的文章，不存在则返回 None。"""
    article_id = request.session.get('writer_article_id')
    if not article_id:
        return None
    try:
        return Article.objects.get(pk=article_id, 写手账号=request.session.get('account', ''))
    except Article.DoesNotExist:
        return None


def _do_article_push(article, discover_ratio: Decimal = Decimal('0.5')):
    """文章推送：仅推送给与写手同平台的用户。

    流量公式：final_discover_ratio = base_ratio × penalty_coeff(α) × health_tier_coeff(γ)
    - 关注列表：粉丝 100% 推送
    - 发现列表：非粉丝按 final_discover_ratio 随机抽样推送
    """
    import random
    from accounts.models import TrafficPenaltyConfig, ArticleTraffic

    writer = WriterAccount.objects.filter(账号=article.写手账号).first()
    if not writer:
        return
    writer_platform = getattr(writer, '所属平台', 0)
    users_same_platform = list(UserAccount.objects.filter(所属平台=writer_platform))
    if not users_same_platform:
        return
    round_num = article.轮次 or 0

    # 流量惩罚系数 α：仅当平台启用流量惩罚且文章为标题党时生效
    penalty_coeff = Decimal('1.0')
    penalty_applied = False
    traffic_penalty_measure = _get_effective_governance_measure(writer_platform, 'traffic_penalty', round_num)
    if traffic_penalty_measure and article.is_clickbait:
        tp_cfg = TrafficPenaltyConfig.objects.filter(platform_id=writer_platform).order_by('-id').first()
        if tp_cfg:
            penalty_coeff = tp_cfg.降权系数alpha
            penalty_applied = True

    # 健康档位推流系数 γ
    gamma = Decimal(str(getattr(writer, '推流系数', Decimal('1.0'))))

    base_ratio = max(Decimal('0'), min(Decimal('1'), _decimal(discover_ratio)))
    final_ratio = max(Decimal('0'), min(Decimal('1'), base_ratio * penalty_coeff * gamma))

    fan_ids = set(
        UserFollowWriter.objects.filter(写手账号=article.写手账号, 用户__in=users_same_platform)
        .values_list('用户_id', flat=True)
    )
    fans = [u for u in users_same_platform if u.pk in fan_ids]
    non_fans = [u for u in users_same_platform if u.pk not in fan_ids]
    for u in fans:
        ArticlePush.objects.get_or_create(文章=article, 用户=u, defaults={'列表类型': 0})
        ArticlePushDetail.objects.get_or_create(文章=article, 用户=u, defaults={'是否粉丝': True})
    n_non = int(Decimal(len(non_fans)) * final_ratio)
    rng = random.SystemRandom()
    chosen_non_fans = rng.sample(non_fans, min(n_non, len(non_fans)))
    for u in chosen_non_fans:
        ArticlePush.objects.get_or_create(文章=article, 用户=u, defaults={'列表类型': 1})
        ArticlePushDetail.objects.get_or_create(文章=article, 用户=u, defaults={'是否粉丝': False})

    total_pushed = ArticlePush.objects.filter(文章=article).count()
    article.已推送 = total_pushed
    article.save(update_fields=['已推送'])

    # 写入 ArticleTraffic 记录
    base_traffic = len(fans) + len(non_fans)
    final_traffic = len(fans) + len(chosen_non_fans)
    ArticleTraffic.objects.create(
        platform_id=writer_platform,
        文章=article,
        轮次=round_num,
        基础流量=base_traffic,
        penalty_applied=penalty_applied,
        penalty_coefficient=penalty_coeff,
        health_tier_coefficient=gamma,
        最终流量=final_traffic,
    )

    action_log(
        f"文章推送完成 article_id={article.pk} 平台={writer_platform} "
        f"fans={len(fans)} non_fans_total={len(non_fans)} "
        f"base_ratio={str(base_ratio)} penalty_coeff={str(penalty_coeff)} "
        f"gamma={str(gamma)} final_ratio={str(final_ratio)} "
        f"discover_chosen={len(chosen_non_fans)} total_pushed={total_pushed}"
    )


@require_http_methods(['POST'])
@_serialize_sqlite_writes
@retry_on_db_locked(max_retries=3, delay=0.5)
def writer_select_title(request):
    """写手选择标题后：存标题文本，并将该标题对应的实际夸张度存为 标题夸张度_校准值。"""
    if request.session.get('role') != 'writer':
        return JsonResponse({'error': '未登录或非写手'}, status=403)
    article = _get_writer_article(request)
    if not article:
        return JsonResponse({'error': '请先点击发布文章'}, status=400)
    title_text = (request.POST.get('title_text') or '').strip()
    try:
        position = int(request.POST.get('position', 1))
    except (TypeError, ValueError):
        position = 1
    position = max(0, min(2, position))
    try:
        initial = int(request.POST.get('title_exaggeration_level', 3))
    except (TypeError, ValueError):
        initial = 3
    initial = max(1, min(5, initial))
    # 五档模式：left/center/right 分别对应 X-1 / X / X+1
    title_exaggeration_calibrated = initial + (position - 1)
    if title_exaggeration_calibrated < 1 or title_exaggeration_calibrated > 5:
        return JsonResponse({'error': '所选标题档次越界（该位置应为空）'}, status=400)
    article.标题 = title_text
    article.标题夸张度_校准值 = title_exaggeration_calibrated
    article.save(update_fields=['标题', '标题夸张度_校准值'])
    account = request.session.get('account', '')
    title_short = (title_text[:50] + '...') if len(title_text) > 50 else title_text
    action_log(
        f"写手 {account} 选择标题 位置={position} 标题夸张度档位X={initial} 校准档次={title_exaggeration_calibrated} 标题={title_short!r}"
    )
    return JsonResponse({'ok': True})


@require_http_methods(['POST'])
@_serialize_sqlite_writes
@retry_on_db_locked(max_retries=3, delay=0.5)
def writer_select_body(request):
    """写手选择正文后：存正文文本，并将该正文对应的实际相关度存为 内容相关度_校准值。"""
    if request.session.get('role') != 'writer':
        return JsonResponse({'error': '未登录或非写手'}, status=403)
    article = _get_writer_article(request)
    if not article:
        return JsonResponse({'error': '请先点击发布文章'}, status=400)
    body_text = (request.POST.get('body_text') or '').strip()
    try:
        position = int(request.POST.get('position', 1))
    except (TypeError, ValueError):
        position = 1
    position = max(0, min(2, position))
    try:
        initial = int(request.POST.get('content_relevance_level', 3))
    except (TypeError, ValueError):
        initial = 3
    initial = max(1, min(5, initial))
    # 五档模式：left/center/right 分别对应 Y-1 / Y / Y+1
    content_relevance_calibrated = initial + (position - 1)
    if content_relevance_calibrated < 1 or content_relevance_calibrated > 5:
        return JsonResponse({'error': '所选正文档次越界（该位置应为空）'}, status=400)
    article.正文 = body_text
    article.内容相关度_校准值 = content_relevance_calibrated
    article.轮次 = _get_current_round()
    article.save(update_fields=['正文', '内容相关度_校准值', '轮次'])
    account = request.session.get('account', '')
    body_short = (body_text[:80] + '...') if len(body_text) > 80 else body_text
    body_short = body_short.replace('\n', ' ').replace('\r', ' ')
    action_log(
        f"写手 {account} 选择正文 位置={position} 内容相关度档位Y={initial} 校准档次={content_relevance_calibrated} 正文摘要={body_short!r}"
    )

    # 标题党检测 + 账号健康分规则
    writer = WriterAccount.objects.filter(账号=account).first()
    writer_platform = getattr(writer, '所属平台', 0) if writer else 0
    round_num = article.轮次

    # 标题党检测：仅当功能包生效时才执行并落库结果（符合测试说明书要求）
    X = article.标题夸张度_校准值 or article.标题夸张度_初始值 or 0
    Y = article.内容相关度_校准值 or article.内容相关度_初始值 or 0
    detection_executed = bool(_get_effective_governance_measure(writer_platform, 'clickbait_detection', round_num))
    clickbait = False
    if detection_executed:
        clickbait = is_clickbait(article, writer_platform, round_num)
        # 记录检测结果
        ClickbaitDetectionResult.objects.create(
            文章=article,
            轮次=round_num,
            平台=writer_platform,
            标题夸张度X=X,
            内容相关度Y=Y,
            自动检测是否执行=True,
            检测结果=clickbait,
        )
        # 更新文章标题党标记
        article.is_clickbait = clickbait
        article.clickbait_detected_at = round_num
        if clickbait:
            article.method_auto_rule = True
        article.save(update_fields=['is_clickbait', 'clickbait_detected_at', 'method_auto_rule'])
        action_log(
            f"{PLATFORM_NAMES.get(writer_platform, f'平台{writer_platform}')} 写手{account} 文章{article.pk} 进入标题党检测功能，"
            f"检测结果为{'标题党' if clickbait else '非标题党'}，已更新文章表与标题党检测结果表。"
        )

    # 账号健康分规则：扣分
    health_rule = _get_effective_health_rule(writer_platform, round_num)
    health_cfg = _get_latest_account_health_config(writer_platform)
    health_config_id = health_cfg.pk if health_cfg else None
    configs = _get_effective_health_level_configs(round_num, platform_id=writer_platform, config_id=health_config_id)
    before_score = int(getattr(writer, '健康分', 100) if writer else 100)
    after_score = before_score
    delta = 0
    if health_rule and clickbait and writer:
        punish_value = int(getattr(health_cfg, '每次违规扣减分值', 10) or 10)
        delta = -punish_value
        after_score = max(0, before_score + delta)
        new_tier, new_ratio = _resolve_health_tier_and_ratio(after_score, configs)
        writer.健康分 = after_score
        writer.health_tier = new_tier
        writer.推流系数 = new_ratio
        writer.健康分最近更新轮次 = round_num
        writer.save(update_fields=['健康分', 'health_tier', '推流系数', '健康分最近更新轮次'])
        WriterHealthScoreLog.objects.create(
            写手账号=account,
            轮次=round_num,
            event_type='violation',
            文章编号=article.pk,
            变更值=delta,
            原因='标题党命中',
        )
        action_log(
            f"健康分扣减 writer={account} article_id={article.pk} round={round_num} "
            f"delta={delta} before={before_score} after={after_score} tier={new_tier} gamma={str(new_ratio)}"
        )

    ratio = _match_push_ratio(after_score, configs)
    if not health_rule:
        ratio = _match_push_ratio(before_score, configs)

    _do_article_push(article, discover_ratio=ratio)
    return JsonResponse({'ok': True, 'article_id': article.pk})


# 写手生成标题：按五档自然语言风格生成 3 个备选标题
TITLE_EXAGGERATION_LEVELS = {
    1: {
        'name': '朴实客观',
        'desc': '像正规新闻通讯社的标题。纯粹陈述事实，用词中性克制，不带任何情感色彩或修辞手法。标题本身就是对事件的精确概括。',
        'examples': [
            '某市2024年住宅均价同比下降5%',
            '统计局：某市商品房成交量较去年减少12%',
        ],
    },
    2: {
        'name': '略加修饰',
        'desc': '像优质媒体的特稿标题。在事实基础上进行了表达优化，可能用了比喻、设问等温和修辞，让标题更具可读性，但措辞上仍然节制、有分寸。',
        'examples': [
            '房价拐点来了？某市住宅均价悄然下滑',
            '某市楼市降温，刚需族的机会来了吗',
        ],
    },
    3: {
        'name': '适度渲染',
        'desc': '像社交媒体上有传播力的内容标题。措辞上做了放大和取舍，可能使用了轻度情绪化表达或悬念句式，对事实的某些侧面有选择性强调。标题读起来有吸引力和冲击感，但还不至于让人觉得离谱。',
        'examples': [
            '这座城市的房价终于扛不住了',
            '房价跌了，但真正的信号藏在数据背后',
        ],
    },
    4: {
        'name': '明显夸大',
        'desc': '标题大量使用情绪化词汇、悬念句式和夸大表述，对事实进行了显著的放大、简化甚至局部扭曲。措辞上追求最大化的情绪冲击力，可能使用“震惊”“暴跌”“紧急”等强烈词汇。',
        'examples': [
            '房价暴跌！炒房客一夜之间血本无归',
            '震惊！这座城市房价崩了，千万家庭瑟瑟发抖',
        ],
    },
    5: {
        'name': '极度夸张',
        'desc': '标题的措辞已经完全脱离事实的合理边界。可能无中生有、捏造因果、使用极端词汇和大量感叹号，把普通事件描述成惊天动地的大事件。',
        'examples': [
            '崩盘！房价一夜归零，千万家庭哭晕在厕所！！',
            '刚刚传来！某市房价原地蒸发，政府紧急封锁消息！',
        ],
    },
}

CONTENT_RELEVANCE_LEVELS = {
    1: {
        'name': '几乎无关',
        'desc': '正文与标题之间不存在有意义的内容关联。标题主题在正文中既没有被讨论，也没有被回应，两者之间找不到实质性的信息连接。',
    },
    2: {
        'name': '勉强沾边',
        'desc': '正文与标题只存在表面上的关键词关联，实质内容几乎没有回应标题的核心主题。读者读完后会明确感到“这篇文章不是在讲标题说的那件事”。',
    },
    3: {
        'name': '部分相关',
        'desc': '正文和标题存在一定的主题关联，但出现了明显的偏离或避重就轻。标题核心主题可能只被简单提及就转向了其他话题。',
    },
    4: {
        'name': '基本相关',
        'desc': '正文的主体内容与标题主题一致，但在完整度或聚焦度上有所不足。可能存在适度延伸发散，或对标题核心信息回应不够深入。',
    },
    5: {
        'name': '高度相关',
        'desc': '正文内容完整、准确地回应标题提出的主题。文章围绕核心信息展开，论述集中，论据充分，没有明显跑题或注水。',
    },
}


SYSTEM_CONTENT_TITLES = """你是一个平台写手。你将从用户消息中获得【核心主题】与【用户指定标题夸张度档次（1-5）】。请据此生成 3 个不同标题，构成一个「低–中–高」三档对比序列。

【生成规则】
1. 你必须生成 3 个标题，分别对应：
   - "left"：比用户指定档次低一档的标题（即档次 X-1），若该档次不存在（如 X=1），则输出空字符串 ""
   - "center"：用户指定档次（即档次 X）的标题，必须严格符合其风格描述
   - "right"：比用户指定档次高一档的标题（即档次 X+1），若该档次不存在（如 X=5），则输出空字符串 ""

2. 标题风格须严格匹配对应档次的描述（见下方档次定义），尤其注意：

3. 标题需与核心主题相关，不要编造明显不合理的事实细节。

4. **绝对不要**输出任何解释、前后缀文字、注释或 Markdown 代码块，只输出一个合法 JSON 对象。

5. 输出的 JSON 格式必须严格为：
{
  "left": "标题文本（若无则为空字符串）",
  "center": "标题文本",
  "right": "标题文本（若无则为空字符串）"
}

【标题夸张度档次定义】
档次1 · 朴实客观  
风格：像正规新闻通讯社的标题。纯粹陈述事实，用词中性克制，不带任何情感色彩或修辞手法。标题本身就是对事件的精确概括。  
示例：  
- 某市2024年住宅均价同比下降5%  
- 统计局：某市商品房成交量较去年减少12%

档次2 · 略加修饰  
风格：像优质媒体的特稿标题。在事实基础上进行了表达优化，可能用了比喻、设问等温和修辞，让标题更具可读性，但措辞上仍然节制、有分寸。  
示例：  
- 房价拐点来了？某市住宅均价悄然下滑  
- 某市楼市降温，刚需族的机会来了吗

档次3 · 适度渲染  
风格：像社交媒体上有传播力的内容标题。措辞上做了放大和取舍，可能使用了轻度情绪化表达或悬念句式，对事实的某些侧面有选择性强调。标题读起来有吸引力和冲击感，但还不至于让人觉得离谱。  
示例：  
- 这座城市的房价终于扛不住了  
- 房价跌了，但真正的信号藏在数据背后

档次4 · 明显夸大  
风格：标题大量使用情绪化词汇、悬念句式和夸大表述，对事实进行了显著的放大、简化甚至局部扭曲。措辞上追求最大化的情绪冲击力，可能使用“震惊”“暴跌”“紧急”等强烈词汇。  
示例：  
- 房价暴跌！炒房客一夜之间血本无归  
- 震惊！这座城市房价崩了，千万家庭瑟瑟发抖

档次5 · 极度夸张  
风格：标题的措辞已经完全脱离事实的合理边界。可能无中生有、捏造因果、使用极端词汇和大量感叹号，把一件普通的事描述成惊天动地的大事件。  
示例：  
- 崩盘！房价一夜归零，千万家庭哭晕在厕所！！  
- 刚刚传来！某市房价原地蒸发，政府紧急封锁消息！
"""



def _parse_json_from_llm(raw):
    """从大模型返回中解析 JSON，兼容被 ```json ... ``` 包裹的情况。"""
    import json
    import re
    text = (raw or "").strip()
    # 去掉可能的 markdown 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _safe_brace_replace(template: str, mapping: dict) -> str:
    """兼容旧逻辑保留（已不再用于标题/正文 system prompt）。"""
    text = template or ""
    for k, v in (mapping or {}).items():
        text = text.replace("{" + str(k) + "}", str(v))
    return text


@require_http_methods(['POST'])
@retry_on_db_locked(max_retries=3, delay=0.5)
def writer_generate_titles(request):
    """根据写手输入的主题与两项档位调用大模型，要求返回 JSON，解析为 { left, center, right } 返回前端；并写入文章表初始档位值。"""
    #region agent log
    try:
        with open('debug-3cc876.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "sessionId": "3cc876",
                "runId": "pre-fix",
                "hypothesisId": "H1_csrf_cookie_missing_or_token_mismatch",
                "location": "accounts/views.py:writer_generate_titles",
                "message": "writer_generate_titles request csrf evidence",
                "data": {
                    "role": request.session.get('role'),
                    "has_csrftoken_cookie": "csrftoken" in (request.COOKIES or {}),
                    "x_csrf_token_present": bool(request.META.get("HTTP_X_CSRFTOKEN")),
                    "post_csrf_present": bool((request.POST.get("csrfmiddlewaretoken") or "").strip()),
                    "content_type": request.META.get("CONTENT_TYPE"),
                },
                "timestamp": int(time.time() * 1000)
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    #endregion
    print("[generate_titles] 1. 请求到达 POST keys:", list(request.POST.keys()))
    if request.session.get('role') != 'writer':
        print("[generate_titles] 2. 未登录或非写手，已拒绝")
        return JsonResponse({'error': '未登录或非写手', 'left': '', 'center': '', 'right': ''}, status=403)
    topic = (request.POST.get('topic') or '').strip() or '关于喝水与健康的科普'
    try:
        title_level = int(request.POST.get('title_exaggeration_level', 3))
    except (TypeError, ValueError):
        title_level = 3
    try:
        relevance_level = int(request.POST.get('content_relevance_level', 3))
    except (TypeError, ValueError):
        relevance_level = 3
    title_level = max(1, min(5, title_level))
    relevance_level = max(1, min(5, relevance_level))
    account = request.session.get('account', '')
    action_log(f"写手 {account} 输入主题={topic!r} 标题夸张度档位={title_level} 内容相关度档位={relevance_level}")
    print("[generate_titles] 2. 主题:", topic, "| 标题夸张度(档位):", title_level, "| 内容相关度(档位):", relevance_level)
    # 写手选择档位点「提交」时，将两档位值写入文章表初始值（字段仍沿用原名）
    article = _get_writer_article(request)
    if article:
        article.标题夸张度_初始值 = title_level
        article.内容相关度_初始值 = relevance_level
        article.save(update_fields=['标题夸张度_初始值', '内容相关度_初始值'])
    lvl = TITLE_EXAGGERATION_LEVELS.get(title_level) or TITLE_EXAGGERATION_LEVELS[3]
    system_content = SYSTEM_CONTENT_TITLES
    user_content = (
        f"核心主题：{topic}\n"
        f"用户指定标题夸张度档次X：{title_level}（{lvl.get('name','')}）\n"
        "请严格按系统提示词输出 JSON，且只输出 JSON。"
    )
    try:
        from sandbox_site.callLLM import call_deepseek_api
        raw = call_deepseek_api(system_content, user_content)
        print("[generate_titles] 3. 大模型原始返回 长度:", len(raw) if raw else 0)
        print("[generate_titles] 3. 大模型原始内容(前500字):", repr((raw or "")[:500]))
    except Exception as e:
        print("[generate_titles] 3. 调用大模型异常:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e), 'left': '', 'center': '', 'right': ''}, status=500)
    try:
        obj = _parse_json_from_llm(raw)
        left = (obj.get('left') or '').strip()
        center = (obj.get('center') or '').strip()
        right = (obj.get('right') or '').strip()
        print("[generate_titles] 4. 解析 JSON 成功 | left/center/right 长度:", len(left), len(center), len(right))
        return JsonResponse({'left': left, 'center': center, 'right': right})
    except Exception as e:
        print("[generate_titles] 4. 解析 JSON 失败:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': '大模型返回不是合法 JSON: ' + str(e), 'left': '', 'center': '', 'right': ''}, status=500)


# 写手生成正文：对齐 SYSTEM_CONTENT_TITLES 的三档输出结构（left=Y-1, center=Y, right=Y+1）
SYSTEM_CONTENT_BODIES = """你是一个平台写手。你将从用户消息中获得【文章标题】与【用户指定内容相关度档次（1-5）】。请据此生成 3 篇文章正文，构成一个「低–中–高」三档对比序列。

【生成规则】
1. 你必须生成 3 篇正文，分别对应：
   - \"left\"：比用户指定档次低一档的正文（即档次 Y-1），若该档次不存在（如 Y=1），则输出空字符串 \"\"
   - \"center\"：用户指定档次（即档次 Y）的正文，必须严格符合其相关度描述
   - \"right\"：比用户指定档次高一档的正文（即档次 Y+1），若该档次不存在（如 Y=5），则输出空字符串 \"\"

2. 内容相关度衡量标题与正文的一致度。请严格匹配对应档次的描述（见下方档次定义），尤其注意：
   - 档次1（几乎无关）：正文与标题几乎没有实质关联
   - 档次5（高度相关）：正文完整、准确回应标题核心信息

3. 每篇正文字数 100-200 字。

4. **绝对不要**输出任何解释、前后缀文字、注释或 Markdown 代码块，只输出一个合法 JSON 对象。

5. 输出 JSON 格式必须严格为：
{
  \"left\": \"正文文本（若无则为空字符串）\",
  \"center\": \"正文文本\",
  \"right\": \"正文文本（若无则为空字符串）\"
}

【内容相关度档次定义】
档次1 · 几乎无关  
风格：正文与标题之间不存在有意义的内容关联。标题主题在正文中既没有被讨论，也没有被回应，两者之间找不到实质性的信息连接。  

档次2 · 勉强沾边  
风格：正文与标题只存在表面上的关键词关联，实质内容几乎没有回应标题的核心主题。读者读完后会明确感到“这篇文章不是在讲标题说的那件事”。  

档次3 · 部分相关  
风格：正文和标题存在一定的主题关联，但出现了明显的偏离或避重就轻。标题核心主题可能只被简单提及就转向了其他话题。  

档次4 · 基本相关  
风格：正文的主体内容与标题主题一致，但在完整度或聚焦度上有所不足。可能存在适度延伸发散，或对标题核心信息回应不够深入。  

档次5 · 高度相关  
风格：正文内容完整、准确地回应标题所提出的主题。文章围绕标题的核心信息展开，论述集中，论据充分，没有明显跑题或注水。  
"""


@require_http_methods(['POST'])
def writer_generate_bodies(request):
    """根据选中的标题与内容相关度档次调用大模型，要求返回 JSON，解析为 { left, center, right } 返回前端。"""
    if request.session.get('role') != 'writer':
        return JsonResponse({'error': '未登录或非写手', 'left': '', 'center': '', 'right': ''}, status=403)
    article_title = (request.POST.get('article_title') or '').strip()
    try:
        relevance_level = int(request.POST.get('content_relevance_level', 3))
    except (TypeError, ValueError):
        relevance_level = 3
    relevance_level = max(1, min(5, relevance_level))
    account = request.session.get('account', '')
    title_short = (article_title[:50] + '...') if len(article_title or '') > 50 else (article_title or '（无）')
    action_log(f"写手 {account} 请求生成正文 已选标题={title_short!r} 内容相关度档位={relevance_level}")
    lvl = CONTENT_RELEVANCE_LEVELS.get(relevance_level) or CONTENT_RELEVANCE_LEVELS[3]
    system_content = SYSTEM_CONTENT_BODIES
    user_content = (
        f"文章标题：{article_title}\n"
        f"用户指定内容相关度档次Y：{relevance_level}（{lvl.get('name','')}）\n"
        "请严格按系统提示词输出 JSON，且只输出 JSON。"
    )
    try:
        from sandbox_site.callLLM import call_deepseek_api
        raw = call_deepseek_api(system_content, user_content)
    except Exception as e:
        return JsonResponse({'error': str(e), 'left': '', 'center': '', 'right': ''}, status=500)
    try:
        obj = _parse_json_from_llm(raw)
        left = (obj.get('left') or '').strip()
        center = (obj.get('center') or '').strip()
        right = (obj.get('right') or '').strip()
        return JsonResponse({'left': left, 'center': center, 'right': right})
    except Exception as e:
        return JsonResponse({'error': '大模型返回不是合法 JSON: ' + str(e), 'left': '', 'center': '', 'right': ''}, status=500)


def article_detail(request, article_id):
    """写手本人文章页：标题、正文、侧面数据、评论。"""
    account = request.session.get('account', '')
    role = request.session.get('role', '')
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return redirect('accounts:writer_home')
    if role != 'writer' or article.写手账号 != account:
        return redirect('accounts:login')
    comments = list(article.评论列表.all().order_by('创建时间'))
    return render(request, 'accounts/article_detail.html', {
        'article': article,
        'comments': comments,
        'comment_count': len(comments),
        'is_user_view': False,
        'is_following': False,
        'has_liked': False,
        'has_collected': False,
        'has_read_complete': False,
    })
