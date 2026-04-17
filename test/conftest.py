from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).resolve().parent.parent
PYTEST_SQLITE_PATH = TEST_ROOT / ".pytest" / "sandbox_pytest.sqlite3"
ACTION_LOG_INDEX = TEST_ROOT / "test" / "reports" / "action_log_paths.txt"


def pytest_sessionstart(session: pytest.Session) -> None:  # noqa: ARG001
    ACTION_LOG_INDEX.parent.mkdir(parents=True, exist_ok=True)
    try:
        ACTION_LOG_INDEX.write_text("", encoding="utf-8")
    except OSError:
        pass


def pytest_configure() -> None:
    """
    sqlite 并发写入优化：WAL + busy_timeout（测试环境用）。
    """
    from django.db.backends.signals import connection_created

    def _pragma(sender, connection, **kwargs):
        if connection.vendor != "sqlite":
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA busy_timeout=60000;")
        except Exception:
            # 测试不应因 pragma 失败而直接中断收集阶段
            return

    connection_created.connect(_pragma)


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix: None) -> None:  # noqa: ARG001
    """
    强制 pytest 使用独立的 sqlite 文件，避免与开发库 `db.sqlite3` 并发占用导致 database is locked。
    必须在 pytest-django 创建测试库之前生效（django_db_modify_db_settings hook）。
    """
    from django.conf import settings

    PYTEST_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.DATABASES["default"]["ENGINE"] = "django.db.backends.sqlite3"
    settings.DATABASES["default"]["NAME"] = str(PYTEST_SQLITE_PATH)
    settings.DATABASES["default"].setdefault("OPTIONS", {})
    settings.DATABASES["default"]["OPTIONS"]["timeout"] = 60


@pytest.fixture(scope="session", autouse=True)
def _sandbox_seed_base_world(
    django_db_setup: None,
    django_db_blocker,
):
    """
    pytest 测试库默认是“空库迁移”，这里预置最小可登录账号/轮次，保证视图级集成测试可跑。
    """
    from accounts.models import PlatformAccount, SimulationRound, UserAccount, WriterAccount

    with django_db_blocker.unblock():
        SimulationRound.objects.update_or_create(pk=1, defaults={"当前轮次": 1})

        PlatformAccount.objects.update_or_create(
            账号="pytest_platform_0",
            defaults={"密码": "pytest", "所属平台": 0},
        )

        for i in range(1, 11):
            WriterAccount.objects.update_or_create(
                账号=f"pytest_writer_{i}",
                defaults={"密码": "pytest", "所属平台": 0},
            )
        for i in range(1, 21):
            UserAccount.objects.update_or_create(
                账号=f"pytest_user_{i}",
                defaults={"密码": "pytest", "所属平台": 0},
            )


@pytest.fixture(autouse=True)
def _sandbox_per_test_paths(settings, tmp_path):
    """
    每个测试函数独立 BASE_DIR：保证 logs/simulation_actions.log 可复现、互不污染。
    """
    settings.BASE_DIR = tmp_path
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "simulation_actions.log").write_text("", encoding="utf-8")
    try:
        with ACTION_LOG_INDEX.open("a", encoding="utf-8") as f:
            f.write(str((log_dir / "simulation_actions.log").resolve()) + "\n")
    except OSError:
        pass

    # 并发测试下 sqlite 写入 django_session 容易锁表；课程沙箱场景可用 signed_cookies（不落库）
    settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
    # 让 sqlite 关键写路径在测试里串行化，避免多线程 TestClient 触发 database is locked
    setattr(settings, "SANDBOX_SQLITE_SERIALIZE_WRITES", True)
    yield


@pytest.fixture
def action_log_path(settings) -> Path:
    return Path(settings.BASE_DIR) / "logs" / "simulation_actions.log"


@pytest.fixture
def platform_account(db):
    from accounts.models import PlatformAccount

    acc = PlatformAccount.objects.get(账号="pytest_platform_0")
    return acc


@pytest.fixture
def writer_accounts(db):
    from accounts.models import WriterAccount

    return list(WriterAccount.objects.filter(账号__startswith="pytest_writer_").order_by("账号"))


@pytest.fixture
def client_platform_logged_in(client, db, platform_account):
    r = client.post("/", {"account": platform_account.账号, "password": platform_account.密码})
    assert r.status_code in (200, 302)
    return client, platform_account


@pytest.fixture
def active_clickbait_config(db, platform_account):
    from accounts.models import ClickbaitDetectionConfig

    cfg, _created = ClickbaitDetectionConfig.objects.get_or_create(
        platform_id=platform_account.所属平台,
        status="active",
        defaults={
            "标题夸张度阈值X": 4,
            "内容相关度阈值Y": 3,
            "提交人账号": "admin",
            "管理员确认账号": "admin",
        },
    )
    # 防御：确保阈值是期望值（避免重复对象带来的漂移）
    cfg.标题夸张度阈值X = 4
    cfg.内容相关度阈值Y = 3
    cfg.save(update_fields=["标题夸张度阈值X", "内容相关度阈值Y"])
    return cfg


@pytest.fixture
def enable_clickbait_measure(db, platform_account, active_clickbait_config):
    """
    使标题党检测功能对当前轮次生效（直接模拟管理员已审核通过的 active 记录）。
    """
    from accounts.models import PlatformGovernanceMeasure
    from accounts.views import _get_current_round

    current_round = _get_current_round()
    rec, _ = PlatformGovernanceMeasure.objects.get_or_create(
        平台=platform_account.所属平台,
        措施类型="clickbait_detection",
        生效轮次=current_round,
        defaults={
            "轮次": max(1, current_round - 1),
            "措施内容": {},
            "config_id": active_clickbait_config.pk,
            "发布人账号": platform_account.账号,
            "status": "active",
            "管理员确认账号": "admin",
        },
    )
    # 同步字段（避免并发创建时的占位 defaults 不一致）
    rec.轮次 = max(1, current_round - 1)
    rec.config_id = active_clickbait_config.pk
    rec.status = "active"
    rec.取消轮次 = None
    rec.save(update_fields=["轮次", "config_id", "status", "取消轮次"])
    return rec


@pytest.fixture
def client_writer_logged_in(client, db, writer_accounts):
    """
    使用第一个预置写手登录 session，并返回 client。
    """
    w = writer_accounts[0]
    r = client.post("/", {"account": w.账号, "password": w.密码})
    assert r.status_code in (200, 302)
    return client, w


@pytest.fixture
def user_accounts(db):
    from accounts.models import UserAccount

    return list(UserAccount.objects.filter(账号__startswith="pytest_user_").order_by("账号"))


@pytest.fixture
def client_user_logged_in(client, db, user_accounts):
    u = user_accounts[0]
    r = client.post("/", {"account": u.账号, "password": u.密码})
    assert r.status_code in (200, 302)
    return client, u


@pytest.fixture
def user_report_config_factory(db, platform_account):
    from accounts.models import UserReportConfig

    def _factory(
        *,
        review_method: str = "auto",
        threshold: str = "0.30",
        status: str = "active",
        submitter: str = "admin",
    ):
        cfg = UserReportConfig.objects.create(
            platform_id=platform_account.所属平台,
            举报触发阈值=threshold,
            审核方式=review_method,
            status=status,
            提交人账号=submitter,
            管理员确认账号="admin" if status == "active" else "",
        )
        return cfg

    return _factory


@pytest.fixture
def enable_user_report_measure(db, platform_account, user_report_config_factory):
    from accounts.models import PlatformGovernanceMeasure
    from accounts.views import _get_current_round

    current_round = _get_current_round()
    cfg = user_report_config_factory(status="active", review_method="auto")
    rec, _ = PlatformGovernanceMeasure.objects.get_or_create(
        平台=platform_account.所属平台,
        措施类型="user_report",
        生效轮次=current_round,
        defaults={
            "轮次": max(1, current_round - 1),
            "措施内容": {"举报触发阈值": str(cfg.举报触发阈值), "审核方式": cfg.审核方式},
            "config_id": cfg.pk,
            "发布人账号": platform_account.账号,
            "status": "active",
            "管理员确认账号": "admin",
        },
    )
    rec.轮次 = max(1, current_round - 1)
    rec.config_id = cfg.pk
    rec.status = "active"
    rec.取消轮次 = None
    rec.save(update_fields=["轮次", "config_id", "status", "取消轮次"])
    return rec
