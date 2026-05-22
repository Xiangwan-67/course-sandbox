# -*- coding: utf-8 -*-
"""Admin 模拟看板页面与 API。"""
from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from accounts.admin_monitor_data import (
    build_governance_payload,
    build_page_context,
    build_writers_payload,
    parse_round_param,
    platform_names_dict,
)


@require_http_methods(['GET'])
def sandbox_monitor_dashboard(request: HttpRequest) -> HttpResponse:
    ctx = build_page_context()
    ctx['title'] = '模拟看板'
    dr = ctx['display_round']
    ctx['writers_json'] = json.dumps(build_writers_payload(dr), ensure_ascii=False)
    ctx['governance_json'] = json.dumps(build_governance_payload(dr), ensure_ascii=False)
    ctx['platform_names_json'] = json.dumps(platform_names_dict(), ensure_ascii=False)
    return render(request, 'admin/sandbox_monitor.html', ctx)


@require_http_methods(['GET'])
def sandbox_monitor_api_writers(request: HttpRequest) -> HttpResponse:
    round_num = parse_round_param(request.GET.get('round'))
    return JsonResponse(build_writers_payload(round_num))


@require_http_methods(['GET'])
def sandbox_monitor_api_governance(request: HttpRequest) -> HttpResponse:
    round_num = parse_round_param(request.GET.get('round'))
    return JsonResponse(build_governance_payload(round_num))
