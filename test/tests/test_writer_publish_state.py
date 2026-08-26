from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import Article, ArticleTraffic, ClickbaitDetectionResult, SimulationRound
from accounts.views import _compute_platform_patrol_metrics


@pytest.mark.django_db
def test_start_article_reuses_unpublished_draft(client_writer_logged_in):
    client, writer = client_writer_logged_in

    r1 = client.post("/writer/start-article/")
    assert r1.status_code == 200
    article_id = r1.json()["article_id"]

    r2 = client.post("/writer/start-article/")
    assert r2.status_code == 200
    assert r2.json()["article_id"] == article_id

    drafts = Article.objects.filter(
        写手账号=writer.账号,
        轮次=1,
        is_published=False,
    )
    assert drafts.count() == 1


@pytest.mark.django_db
def test_start_article_reuses_unpublished_draft_after_session_loss(client_writer_logged_in):
    client, writer = client_writer_logged_in

    r1 = client.post("/writer/start-article/")
    assert r1.status_code == 200
    article_id = r1.json()["article_id"]

    session = client.session
    del session["writer_article_id"]
    session.save()

    r2 = client.post("/writer/start-article/")
    assert r2.status_code == 200
    assert r2.json()["article_id"] == article_id
    assert Article.objects.filter(写手账号=writer.账号, 轮次=1, is_published=False).count() == 1


@pytest.mark.django_db
def test_select_body_marks_published_and_repeat_submit_is_idempotent(client_writer_logged_in):
    client, _writer = client_writer_logged_in

    r = client.post("/writer/start-article/")
    article_id = r.json()["article_id"]
    client.post(
        "/writer/select-title/",
        {"title_text": "t", "position": 1, "title_exaggeration_level": 5},
    )

    body_payload = {"body_text": "b", "position": 1, "content_relevance_level": 1}
    r1 = client.post("/writer/select-body/", body_payload)
    assert r1.status_code == 200
    assert r1.json()["article_id"] == article_id

    art = Article.objects.get(pk=article_id)
    assert art.is_published is True
    traffic_count = ArticleTraffic.objects.filter(文章=art).count()
    judgment_count = ClickbaitDetectionResult.objects.filter(文章=art).count()

    r2 = client.post("/writer/select-body/", body_payload)
    assert r2.status_code == 200
    assert r2.json()["article_id"] == article_id
    assert ArticleTraffic.objects.filter(文章=art).count() == traffic_count
    assert ClickbaitDetectionResult.objects.filter(文章=art).count() == judgment_count


@pytest.mark.django_db
def test_patrol_metrics_ignore_unpublished_articles(active_clickbait_config, writer_accounts):
    SimulationRound.objects.filter(pk=1).update(当前轮次=3)
    writer = writer_accounts[0]

    Article.objects.create(
        写手账号=writer.账号,
        轮次=2,
        标题="published hit",
        正文="body",
        标题夸张度_校准值=5,
        内容相关度_校准值=1,
        is_published=True,
    )
    Article.objects.create(
        写手账号=writer.账号,
        轮次=2,
        标题="draft miss",
        正文="body",
        标题夸张度_校准值=1,
        内容相关度_校准值=5,
        is_published=False,
    )

    metrics, err = _compute_platform_patrol_metrics(
        writer.所属平台,
        Decimal("1"),
        2,
        2,
        exec_round=3,
        rng_seed=1,
    )

    assert err is None
    assert metrics["n"] == 1
    assert metrics["rate"] == Decimal("1")
