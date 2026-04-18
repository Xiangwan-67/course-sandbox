# -*- coding: utf-8 -*-
"""
写手/用户操作动作日志：同时打印到终端并追加写入日志 txt 文件，便于后续查验。
不记录写手查看历史文章列表行为。
"""
import os
import sys
from datetime import datetime


def _log_path():
    """日志文件路径：项目根目录下的 logs/simulation_actions.log。"""
    try:
        from django.conf import settings
        base = settings.BASE_DIR
    except Exception:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, 'simulation_actions.log')


def _regulator_log_path():
    """监管专项日志文件路径：项目根目录下的 logs/regulator_actions.log。"""
    try:
        from django.conf import settings
        base = settings.BASE_DIR
    except Exception:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, 'regulator_actions.log')


def action_log(message):
    """
    记录一条操作日志：打印到终端，并追加写入 logs/simulation_actions.log。
    message: 纯文本，建议格式「角色 账号 动作 关键参数」。
    """
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {message}"
    print(line, flush=True)
    try:
        path = _log_path()
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception as e:
        print(f"[action_log] 写入文件失败: {e}", file=sys.stderr, flush=True)


def regulator_action_log(message):
    """
    记录一条监管专项日志：打印到终端，并追加写入 logs/regulator_actions.log。
    """
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {message}"
    print(line, flush=True)
    try:
        path = _regulator_log_path()
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception as e:
        print(f"[regulator_action_log] 写入文件失败: {e}", file=sys.stderr, flush=True)
