from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from accounts.models import (
    Article,
    ArticleReport,
    PlatformGovernanceMeasure,
    SimulationRound,
)
from accounts.views import _get_current_round


def _create_article(*, writer_account: str, round_num: int = 1, clicks: int = 10) -> Article:
    return Article.objects.create(
        写手账号=writer_account,
        轮次=round_num,
        标题="pytest_title",
        正文="pytest_body",
        点击量=clicks,
    )


def _login_as_user(account: str, password: str):
    from django.test import Client

    c = Client()
    r = c.post("/", {"account": account, "password": password})
    assert r.status_code in (200, 302)
    return c


@pytest.mark.django_db
def test_report_button_shown_and_becomes_reported_state(client_user_logged_in, writer_accounts):
    client, _user = client_user_logged_in
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=_get_current_round())

    # 前端页面有举报按钮
    r = client.get(f"/user/article/{article.pk}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert 'id="btn_report"' in html
    assert "举报" in html
    assert "取消举报" not in html

    # 点击举报后成功
    r = client.post(f"/user/article/{article.pk}/report/")
    assert r.status_code == 200

    # 再次打开页面应显示“已举报”并禁用
    r = client.get(f"/user/article/{article.pk}/")
    html = r.content.decode("utf-8", errors="replace")
    assert "已举报" in html
    assert 'id="btn_report"' in html
    assert "disabled" in html


@pytest.mark.django_db
def test_report_records_even_when_measure_disabled(client_user_logged_in, writer_accounts, action_log_path):
    client, user = client_user_logged_in
    round_num = _get_current_round()
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=round_num)

    r = client.post(f"/user/article/{article.pk}/report/")
    assert r.status_code == 200

    rec = ArticleReport.objects.filter(
        platform_id=user.所属平台,
        文章=article,
        举报人=user.账号,
        举报轮次=round_num,
    ).first()
    assert rec is not None
    assert rec.审核状态 == "pending"

    article.refresh_from_db()
    assert article.report_count_current_round == 1

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert f"用户{user.账号}" in log_text
    assert f"举报了{article.写手账号}写手的{article.pk}文章" in log_text


@pytest.mark.django_db
def test_report_duplicate_blocked_same_user_same_round(client_user_logged_in, writer_accounts):
    client, user = client_user_logged_in
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=_get_current_round())

    r1 = client.post(f"/user/article/{article.pk}/report/")
    assert r1.status_code == 200

    r2 = client.post(f"/user/article/{article.pk}/report/")
    assert r2.status_code == 400
    assert "本轮已举报过该文章" in (r2.json().get("error") or "")

    assert ArticleReport.objects.filter(
        platform_id=user.所属平台, 文章=article, 举报人=user.账号, 举报轮次=_get_current_round()
    ).count() == 1


@pytest.mark.django_db
def test_publish_user_report_requires_config(client_platform_logged_in, platform_account):
    from accounts.models import UserReportConfig

    UserReportConfig.objects.filter(platform_id=platform_account.所属平台).delete()

    client, _p = client_platform_logged_in
    r = client.post("/platform/governance/publish/", {"measure_type": "user_report"})
    assert r.status_code == 400
    assert "请先提交用户举报配置" in (r.json().get("error") or "")


@pytest.mark.django_db
def test_user_report_governance_toggle_flow(
    client_platform_logged_in,
    platform_account,
    user_report_config_factory,
    action_log_path,
):
    SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})
    cfg = user_report_config_factory(status="active", review_method="auto")

    client, p = client_platform_logged_in

    # 发布
    r = client.post("/platform/governance/publish/", {"measure_type": "user_report"})
    assert r.status_code == 200
    rec = (
        PlatformGovernanceMeasure.objects.filter(平台=p.所属平台, 措施类型="user_report")
        .order_by("-轮次", "-id")
        .first()
    )
    assert rec is not None
    assert rec.status == "pending"
    assert rec.config_id == cfg.pk

    # 模拟管理员通过
    rec.status = "active"
    rec.save(update_fields=["status"])

    # 取消
    r = client.post("/platform/governance/cancel/", {"measure_type": "user_report"})
    assert r.status_code == 200
    rec.refresh_from_db()
    assert rec.取消轮次 == 2

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert "提交治理措施待审 type=user_report" in log_text
    assert "取消治理措施 type=user_report" in log_text


@pytest.mark.django_db
def test_end_round_without_measure_does_not_trigger_threshold_review(client_user_logged_in, writer_accounts):
    client, user = client_user_logged_in
    round_num = _get_current_round()
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=round_num, clicks=1)

    # 未启用治理措施也允许举报记录
    r = client.post(f"/user/article/{article.pk}/report/")
    assert r.status_code == 200

    # 结束本轮：不应触发阈值审核
    r = client.post("/end-round/")
    assert r.status_code == 200

    article.refresh_from_db()
    assert article.is_clickbait is None
    assert article.method_user is None

    rec = ArticleReport.objects.filter(文章=article, 举报人=user.账号, 举报轮次=round_num).first()
    assert rec is not None
    assert rec.审核状态 == "pending"


@pytest.mark.django_db
def test_end_round_with_auto_review_approves(
    client_user_logged_in,
    writer_accounts,
    platform_account,
    user_report_config_factory,
    action_log_path,
):
    round_num = _get_current_round()
    cfg = user_report_config_factory(status="active", review_method="auto", threshold="0.30")
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="user_report",
        措施内容={"举报触发阈值": str(cfg.举报触发阈值), "审核方式": cfg.审核方式},
        config_id=cfg.pk,
        发布人账号=platform_account.账号,
        status="active",
        管理员确认账号="admin",
    )

    client, user = client_user_logged_in
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=round_num, clicks=1)

    r = client.post(f"/user/article/{article.pk}/report/")
    assert r.status_code == 200

    r = client.post("/end-round/")
    assert r.status_code == 200

    article.refresh_from_db()
    assert article.report_count_current_round == 1
    assert article.is_clickbait is True
    assert article.method_user is True

    rec = ArticleReport.objects.filter(文章=article, 举报人=user.账号, 举报轮次=round_num).first()
    assert rec is not None
    assert rec.审核状态 == "approved"

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert "举报达阈值自动审核通过" in log_text


@pytest.mark.django_db
def test_end_round_with_manual_review_keeps_pending(
    client_user_logged_in,
    writer_accounts,
    platform_account,
    user_report_config_factory,
    action_log_path,
):
    round_num = _get_current_round()
    cfg = user_report_config_factory(status="active", review_method="manual", threshold="0.30")
    PlatformGovernanceMeasure.objects.create(
        平台=platform_account.所属平台,
        轮次=max(1, round_num - 1),
        生效轮次=round_num,
        措施类型="user_report",
        措施内容={"举报触发阈值": str(cfg.举报触发阈值), "审核方式": cfg.审核方式},
        config_id=cfg.pk,
        发布人账号=platform_account.账号,
        status="active",
        管理员确认账号="admin",
    )

    client, user = client_user_logged_in
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=round_num, clicks=1)

    r = client.post(f"/user/article/{article.pk}/report/")
    assert r.status_code == 200

    r = client.post("/end-round/")
    assert r.status_code == 200

    article.refresh_from_db()
    assert article.report_count_current_round == 1
    assert article.is_clickbait is None
    assert article.method_user is None

    rec = ArticleReport.objects.filter(文章=article, 举报人=user.账号, 举报轮次=round_num).first()
    assert rec is not None
    assert rec.审核状态 == "pending"

    log_text = action_log_path.read_text(encoding="utf-8", errors="replace")
    assert "举报达阈值待人工审核" in log_text


@pytest.mark.django_db(transaction=True)
def test_user_report_concurrency_multi_users(writer_accounts, user_accounts):
    from accounts.models import UserAccount, WriterAccount

    if not writer_accounts:
        WriterAccount.objects.update_or_create(
            账号="pytest_writer_fallback",
            defaults={"密码": "pytest", "所属平台": 0},
        )
        writer_accounts = list(WriterAccount.objects.filter(账号__startswith="pytest_writer_").order_by("账号"))
        if not writer_accounts:
            writer_accounts = list(WriterAccount.objects.filter(账号="pytest_writer_fallback"))

    if not user_accounts:
        for i in range(1, 6):
            UserAccount.objects.update_or_create(
                账号=f"pytest_user_fallback_{i}",
                defaults={"密码": "pytest", "所属平台": 0},
            )
        user_accounts = list(UserAccount.objects.filter(账号__startswith="pytest_user_").order_by("账号"))
        if not user_accounts:
            user_accounts = list(UserAccount.objects.filter(账号__startswith="pytest_user_fallback_").order_by("账号"))

    round_num = _get_current_round()
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=round_num, clicks=50)

    users = user_accounts[:5]

    def _report_one(u):
        c = _login_as_user(u.账号, u.密码)
        r = c.post(f"/user/article/{article.pk}/report/")
        assert r.status_code == 200
        return u.账号

    with ThreadPoolExecutor(max_workers=len(users)) as ex:
        futs = [ex.submit(_report_one, u) for u in users]
        done = [f.result(timeout=60) for f in as_completed(futs)]

    assert len(done) == len(users)
    assert ArticleReport.objects.filter(文章=article, 举报轮次=round_num).count() == len(users)


@pytest.mark.django_db
def test_no_cancel_report_entry_in_ui(client_user_logged_in, writer_accounts):
    client, _user = client_user_logged_in
    article = _create_article(writer_account=writer_accounts[0].账号, round_num=_get_current_round())

    r = client.get(f"/user/article/{article.pk}/")
    assert r.status_code == 200
    html = r.content.decode("utf-8", errors="replace")
    assert "取消举报" not in html
    assert "/report/cancel/" not in html
