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
from accounts.action_logger import action_log
from accounts.db_retry import retry_on_db_locked
from accounts.models import (
    WriterAccount, UserAccount, PlatformAccount, ProfitWeightConfig, PlatformRoundProfit, PlatformGovernanceMeasure, PlatformPerformanceScheme, Article, Comment, PlatformSwitchSurvey,
    UserFollowWriter, UnfollowSurvey, ArticlePush, ArticlePushDetail,
    UserArticleLike, UserArticleCollect, UserArticleReadComplete,
    SimulationRound,
    AccountHealthLevelConfig, WriterNoticeRead, WriterHealthScoreLog,
)

PLATFORM_NAMES = {0: '平台1', 1: '平台2'}

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

    cfg = _get_effective_profit_config(current_round) or ProfitWeightConfig.objects.order_by('-id').first()
    period = int(getattr(cfg, '利润展示窗口轮数', 4) or 4)
    period = max(1, min(50, period))

    # 利润看板：只展示“完整周期”内的利润
    # 例如 period=4：第4轮展示1-4；第8轮展示5-8；第6轮展示1-4（上一个完整周期）
    cycle_end = (current_round // period) * period
    cycle_start = max(1, cycle_end - period + 1) if cycle_end > 0 else 1
    profits = []
    if cycle_end >= 1:
        profits = list(
            PlatformRoundProfit.objects
            .filter(平台=platform_id, 轮次__gte=cycle_start, 轮次__lte=cycle_end)
            .order_by('轮次')
        )
    cycle_profit_total = sum([_decimal(p.利润) for p in profits], Decimal('0'))

    prev_cycle_total = None
    prev_cycle_end = cycle_end - period
    if prev_cycle_end >= 1:
        prev_cycle_start = max(1, prev_cycle_end - period + 1)
        prev_profits = list(
            PlatformRoundProfit.objects
            .filter(平台=platform_id, 轮次__gte=prev_cycle_start, 轮次__lte=prev_cycle_end)
            .order_by('轮次')
        )
        prev_cycle_total = sum([_decimal(p.利润) for p in prev_profits], Decimal('0'))
    cycle_profit_delta = (cycle_profit_total - prev_cycle_total) if prev_cycle_total is not None else None
    return render(request, 'accounts/platform_home.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'profits': profits,
        'profit_period': period,
        'cycle_start': cycle_start,
        'cycle_end': cycle_end,
        'cycle_profit_total': cycle_profit_total,
        'cycle_profit_delta': cycle_profit_delta,
        'governance_notices': list(
            PlatformGovernanceMeasure.objects
            .filter(平台=platform_id)
            .order_by('-轮次', '-创建时间')[:20]
        ),
        'current_performance_scheme': (
            PlatformPerformanceScheme.objects.filter(平台=platform_id, 生效轮次__lte=current_round)
            .order_by('-生效轮次', '-id')
            .first()
        ),
    })


def platform_governance(request):
    """平台治理：展示可选措施。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    latest_health_rule = (
        PlatformGovernanceMeasure.objects
        .filter(平台=platform_id, 措施类型='account_health_rule')
        .order_by('-轮次', '-id')
        .first()
    )
    # 按 UI 语义：只要存在一条“未取消”的规则记录，就显示“取消该措施”
    # 一旦点击取消会写入取消轮次，此时按钮回到“发布该措施”
    health_rule_published = bool(latest_health_rule and latest_health_rule.取消轮次 is None)
    measures = [
        {
            'type': 'account_health_rule',
            'name': '账号健康分规则',
            'desc': '对平台所有写手账号设置健康分（初始100分），按梯度惩罚（细则待补）。发布后进入通知栏。',
        },
    ]
    return render(request, 'accounts/platform_governance.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'measures': measures,
        'health_rule_published': health_rule_published,
    })


@require_http_methods(['POST'])
def platform_governance_publish(request):
    """发布平台治理措施：写入记录表，平台首页通知栏可见。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    measure_type = (request.POST.get('measure_type') or '').strip()
    if measure_type not in ('account_health_rule',):
        return JsonResponse({'error': '未知措施类型'}, status=400)
    round_num = _get_current_round()
    effective_round = round_num + 1
    content = {}
    if measure_type == 'account_health_rule':
        content = {
            'initial_score': 100,
            'note': '细则占位，后续补充惩罚梯度与触发条件。',
        }
    rec = PlatformGovernanceMeasure.objects.create(
        平台=platform_id,
        轮次=round_num,
        生效轮次=effective_round,
        措施类型=measure_type,
        措施内容=content,
        发布人账号=account,
    )
    action_log(f"平台 {platform_id} 发布治理措施 type={measure_type} round={round_num} effective_round={effective_round} rec_id={rec.pk}")
    return JsonResponse({'ok': True, 'id': rec.pk})


@require_http_methods(['POST'])
def platform_governance_cancel(request):
    """取消平台治理措施（账号健康分规则）：写入取消轮次，下一轮起不再执行。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    measure_type = (request.POST.get('measure_type') or '').strip() or 'account_health_rule'
    if measure_type not in ('account_health_rule',):
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
    rec.取消轮次 = cancel_round
    rec.save(update_fields=['取消轮次'])
    action_log(f"平台 {platform_id} 取消治理措施 type={measure_type} round={round_num} cancel_round={cancel_round} rec_id={rec.pk}")
    return JsonResponse({'ok': True, 'id': rec.pk, 'cancel_round': cancel_round})


def platform_performance(request):
    """平台绩效：选择并应用绩效方案（接口占位，后续联动写手报酬）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return redirect('accounts:login')
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    current_round = _get_current_round()
    current_scheme = (
        PlatformPerformanceScheme.objects.filter(平台=platform_id, 生效轮次__lte=current_round)
        .order_by('-生效轮次', '-id')
        .first()
    )
    schemes = [
        {
            'code': 'S1_balanced',
            'name': '方案1：均衡',
            'desc': '保持点击/收藏/读完等指标权重相对均衡（占位）。',
        },
        {
            'code': 'S2_click_first',
            'name': '方案2：点击优先',
            'desc': '更强调点击带来的短期传播（占位）。',
        },
        {
            'code': 'S3_quality_first',
            'name': '方案3：质量优先',
            'desc': '更强调收藏与读完等质量指标（占位）。',
        },
    ]
    return render(request, 'accounts/platform_performance.html', {
        'name': account,
        'platform_id': platform_id,
        'platform_name': PLATFORM_NAMES.get(platform_id, '平台1'),
        'current_round': current_round,
        'schemes': schemes,
        'current_scheme': current_scheme,
    })


@require_http_methods(['POST'])
def platform_performance_apply(request):
    """应用绩效方案：写入方案记录（从当前轮次生效）。"""
    account = request.session.get('account', '')
    if not account or request.session.get('role') != 'platform':
        return JsonResponse({'error': '未登录或非平台角色'}, status=403)
    platform_user = PlatformAccount.objects.filter(账号=account).first()
    platform_id = getattr(platform_user, '所属平台', 0) if platform_user else 0
    code = (request.POST.get('scheme_code') or '').strip()
    allowed = {'S1_balanced', 'S2_click_first', 'S3_quality_first'}
    if code not in allowed:
        return JsonResponse({'error': '未知方案编号'}, status=400)
    round_num = _get_current_round()
    content = {'note': '占位：后续联动写手报酬权重计算。'}
    rec = PlatformPerformanceScheme.objects.create(
        平台=platform_id,
        生效轮次=round_num,
        方案编号=code,
        方案内容=content,
        发布人账号=account,
    )
    action_log(f"平台 {platform_id} 应用绩效方案 code={code} round={round_num} rec_id={rec.pk}")
    return JsonResponse({'ok': True, 'id': rec.pk})


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


def _get_effective_profit_config(round_num: int):
    """获取指定轮次生效的利润权重配置（若无则返回 None）。"""
    return (
        ProfitWeightConfig.objects
        .filter(生效轮次起__lte=round_num)
        .filter(Q(生效轮次止__isnull=True) | Q(生效轮次止__gte=round_num))
        .order_by('-生效轮次起', '-id')
        .first()
    )


def _decimal(v) -> Decimal:
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except Exception:
        return Decimal('0')


def is_clickbait(title: str, body: str) -> bool:
    """标题党检测接口（占位）。

    输入标题与正文，输出 True/False 表示是否为标题党。当前默认返回 False，后续替换为真实检测逻辑。
    """
    _ = (title or '').strip()
    __ = (body or '').strip()
    return False


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
    if rec.生效轮次 and rec.生效轮次 > round_num:
        return None
    if rec.取消轮次 is not None and round_num >= rec.取消轮次:
        return None
    return rec


def _get_effective_health_level_configs(round_num: int):
    """获取指定轮次生效的健康分档位配置列表（按排序优先）。"""
    return list(
        AccountHealthLevelConfig.objects
        .filter(生效轮次起__lte=round_num)
        .filter(Q(生效轮次止__isnull=True) | Q(生效轮次止__gte=round_num))
        .order_by('排序', '下界开', '上界闭', 'id')
    )


def _match_push_ratio(score: int, configs):
    """按(下界开,上界闭]匹配可推流比例；未匹配则返回默认 0.7000。"""
    s = int(score or 0)
    for c in configs or []:
        if s > int(c.下界开) and s <= int(c.上界闭):
            return _decimal(c.可推流比例)
    return Decimal('0.7000')


def _settle_platform_profit(platform_id: int, round_num: int):
    """结算并落库平台某轮利润（监管成本默认 0）。返回 PlatformRoundProfit 对象。"""
    writer_accounts = list(
        WriterAccount.objects.filter(所属平台=platform_id).values_list('账号', flat=True)
    )
    agg = (
        Article.objects
        .filter(轮次=round_num, 写手账号__in=writer_accounts)
        .aggregate(
            sum_click=Sum('点击量'),
            sum_collect=Sum('收藏量'),
            sum_read_complete=Sum('阅读完成量'),
            sum_pushed=Sum('已推送'),
        )
    )
    sum_click = int(agg.get('sum_click') or 0)
    sum_collect = int(agg.get('sum_collect') or 0)
    sum_read_complete = int(agg.get('sum_read_complete') or 0)
    sum_pushed = int(agg.get('sum_pushed') or 0)

    click_rate = Decimal(sum_click) / Decimal(max(1, sum_pushed))
    collect_rate = Decimal(sum_collect) / Decimal(max(1, sum_click))
    read_complete_rate = Decimal(sum_read_complete) / Decimal(max(1, sum_click))

    platform_fans = int(
        WriterAccount.objects.filter(所属平台=platform_id).aggregate(s=Sum('粉丝数')).get('s') or 0
    )

    cfg = _get_effective_profit_config(round_num)
    w_click = _decimal(getattr(cfg, '点击率权重', 0))
    w_collect = _decimal(getattr(cfg, '收藏率权重', 0))
    w_read = _decimal(getattr(cfg, '阅读完成率权重', 0))
    w_fans = _decimal(getattr(cfg, '平台粉丝数权重', 0))

    regulator_cost = 0
    profit = (click_rate * w_click) + (collect_rate * w_collect) + (read_complete_rate * w_read) + (Decimal(platform_fans) * w_fans) - Decimal(regulator_cost)

    prev = PlatformRoundProfit.objects.filter(平台=platform_id, 轮次=round_num - 1).first()
    yoy = (profit - _decimal(prev.利润)) if prev else None

    factor_snapshot = {
        'round': round_num,
        'platform_id': platform_id,
        'sum_click': sum_click,
        'sum_collect': sum_collect,
        'sum_read_complete': sum_read_complete,
        'sum_pushed': sum_pushed,
        'click_rate': str(click_rate),
        'collect_rate': str(collect_rate),
        'read_complete_rate': str(read_complete_rate),
        'platform_fans': platform_fans,
        'weights': {
            '点击率权重': str(w_click),
            '收藏率权重': str(w_collect),
            '阅读完成率权重': str(w_read),
            '平台粉丝数权重': str(w_fans),
        },
        'regulator_cost': regulator_cost,
    }

    obj, created = PlatformRoundProfit.objects.get_or_create(
        平台=platform_id,
        轮次=round_num,
        defaults={
            '利润': profit,
            '同比增减': yoy,
            '因子快照': factor_snapshot,
            '权重配置': cfg,
            '监管成本': regulator_cost,
        }
    )
    if not created:
        obj.利润 = profit
        obj.同比增减 = yoy
        obj.因子快照 = factor_snapshot
        obj.权重配置 = cfg
        obj.监管成本 = regulator_cost
        obj.save(update_fields=['利润', '同比增减', '因子快照', '权重配置', '监管成本'])
    return obj


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
    has_liked = has_collected = has_read_complete = False
    try:
        user = UserAccount.objects.get(账号=account)
        is_following = user.关注列表.filter(写手账号=article.写手账号).exists()
        has_liked = UserArticleLike.objects.filter(用户=user, 文章=article).exists()
        has_collected = UserArticleCollect.objects.filter(用户=user, 文章=article).exists()
        has_read_complete = UserArticleReadComplete.objects.filter(用户=user, 文章=article).exists()
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
    1) 先结算“本轮”平台利润并落库（平台+轮次唯一，监管成本默认 0）。
    2) 再将当前模拟轮次 +1，不删任何文章/推送数据。

    用户端列表只查当前轮次，故等效于清空列表进入下一轮。可由管理员或脚本在用户们退出后调用。
    """
    round_to_settle = _get_current_round()
    # 目前平台编码沿用 0/1；后续扩展更多平台时，可改为从平台表/配置表读取
    settled = []
    for pid in (0, 1):
        rec = _settle_platform_profit(pid, round_to_settle)
        settled.append({'platform_id': pid, 'profit_id': rec.pk})

    SimulationRound.objects.filter(pk=1).update(当前轮次=F('当前轮次') + 1)
    new_round = _get_current_round()
    action_log(f"结束本轮 round={round_to_settle} -> {new_round} | 已结算平台利润={settled}")
    return JsonResponse({'ok': True, 'current_round': new_round, 'settled_profit': settled})


@require_http_methods(['POST'])
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

    - 关注列表：粉丝 100% 推送
    - 发现列表：非粉丝按 discover_ratio 随机抽样推送
    """
    import random
    writer = WriterAccount.objects.filter(账号=article.写手账号).first()
    if not writer:
        return
    writer_platform = getattr(writer, '所属平台', 0)
    users_same_platform = list(UserAccount.objects.filter(所属平台=writer_platform))
    if not users_same_platform:
        return
    fan_ids = set(
        UserFollowWriter.objects.filter(写手账号=article.写手账号, 用户__in=users_same_platform)
        .values_list('用户_id', flat=True)
    )
    fans = [u for u in users_same_platform if u.pk in fan_ids]
    non_fans = [u for u in users_same_platform if u.pk not in fan_ids]
    for u in fans:
        ArticlePush.objects.get_or_create(文章=article, 用户=u, defaults={'列表类型': 0})
        ArticlePushDetail.objects.get_or_create(文章=article, 用户=u, defaults={'是否粉丝': True})
    ratio = max(Decimal('0'), min(Decimal('1'), _decimal(discover_ratio)))
    # 非粉丝按比例：必须随机抽取，不能按表顺序取前 n 个（否则会总是 id 最小的几个）
    n_non = int(Decimal(len(non_fans)) * ratio)
    rng = random.SystemRandom()
    chosen_non_fans = rng.sample(non_fans, min(n_non, len(non_fans)))
    for u in chosen_non_fans:
        ArticlePush.objects.get_or_create(文章=article, 用户=u, defaults={'列表类型': 1})
        ArticlePushDetail.objects.get_or_create(文章=article, 用户=u, defaults={'是否粉丝': False})
    article.已推送 = ArticlePush.objects.filter(文章=article).count()
    article.save(update_fields=['已推送'])
    action_log(
        f"文章推送完成 article_id={article.pk} 平台={writer_platform} fans={len(fans)} non_fans_total={len(non_fans)} "
        f"discover_ratio={str(ratio)} discover_chosen={len(chosen_non_fans)}"
    )


@require_http_methods(['POST'])
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

    # 账号健康分规则：若规则在本轮已生效且未取消，则进行标题党检测并可能扣分
    writer = WriterAccount.objects.filter(账号=account).first()
    writer_platform = getattr(writer, '所属平台', 0) if writer else 0
    round_num = article.轮次
    health_rule = _get_effective_health_rule(writer_platform, round_num)
    configs = _get_effective_health_level_configs(round_num)
    before_score = int(getattr(writer, '健康分', 100) if writer else 100)
    after_score = before_score
    delta = 0
    clickbait = False
    if health_rule:
        clickbait = bool(is_clickbait(article.标题, article.正文))
        if clickbait and writer:
            delta = -10
            after_score = max(0, before_score + delta)
            writer.健康分 = after_score
            writer.save(update_fields=['健康分'])
            WriterHealthScoreLog.objects.create(
                写手账号=account,
                轮次=round_num,
                文章编号=article.pk,
                变更值=delta,
                原因='标题党命中',
            )
    ratio = _match_push_ratio(after_score, configs)
    # 若平台未发布规则：仍按健康档（score=100）匹配配置，默认 0.7
    if not health_rule:
        ratio = _match_push_ratio(100, configs)
    # 日志：标题党检测与扣分结果
    action_log(
        f"标题党检测 writer={account} article_id={article.pk} round={round_num} platform={writer_platform} "
        f"rule_active={'1' if health_rule else '0'} clickbait={'1' if clickbait else '0'} "
        f"score_before={before_score} delta={delta} score_after={after_score} discover_ratio={str(ratio)}"
    )
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
