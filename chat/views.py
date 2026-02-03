import json
import os

from django.conf import settings
from django.http import JsonResponse, HttpRequest, StreamingHttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .models import RiskEvent, RiskReview
from django.utils import timezone
from .llm import (
    risk_level, crisis_reply, base_system_prompt, medium_mode_prompt,
    lm_chat, lm_chat_stream, force_refusal,
    prune_messages, build_or_update_summary
)
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from .models import Conversation, Message
from django.views.decorators.http import require_GET
from django.shortcuts import render
from django.core.cache import cache

def readme_page(request):
    return render(request, "readme.html")


def rate_limit_or_429(request: HttpRequest, key_prefix: str, limit: int, window_seconds: int):
    uid = request.user.id if request.user.is_authenticated else 0
    key = f"rl:{key_prefix}:u{uid}"
    n = cache.get(key)
    if n is None:
        cache.set(key, 1, timeout=window_seconds)
        return None
    if int(n) >= limit:
        return JsonResponse(
            {"ok": False, "error": "rate_limited", "detail": f"Too many requests, try later."},
            status=429
        )
    try:
        cache.incr(key)
    except Exception:
        cache.set(key, int(n) + 1, timeout=window_seconds)
    return None


@login_required
def home(request):
    return redirect("/conversations/")


@login_required
def conversations(request):
    convs = Conversation.objects.filter(user=request.user).order_by("-updated_at")
    return render(request, "chat/conversations.html", {"convs": convs})


@login_required
def chat_view(request, cid):
    conv = Conversation.objects.get(id=cid, user=request.user)
    msgs = Message.objects.filter(conversation=conv).order_by("created_at")
    return render(request, "chat/index.html", {"conv": conv, "msgs": msgs})


def login_view(request):
    if request.method == "GET":
        return render(request, "chat/login.html")
    username = request.POST.get("username")
    password = request.POST.get("password")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return render(request, "chat/login.html", {"error": "用户名或密码错误"})
    login(request, user)
    return redirect("/conversations/")


def register_view(request):
    if request.method == "GET":
        return render(request, "chat/register.html")
    username = request.POST.get("username")
    password = request.POST.get("password")
    if not username or not password:
        return render(request, "chat/register.html", {"error": "请填写用户名和密码"})
    if User.objects.filter(username=username).exists():
        return render(request, "chat/register.html", {"error": "用户名已存在"})
    user = User.objects.create_user(username=username, password=password, is_staff=False)
    login(request, user)
    return redirect("/conversations/")


@login_required
def logout_view(request):
    logout(request)
    return redirect("/login/")


def _sse(obj):
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _get_state_for_conv(conv: Conversation):
    msgs = Message.objects.filter(conversation=conv).order_by("created_at")
    history = [{"role": "system", "content": base_system_prompt()}]
    summary_text = None
    turn_count = 0

    for m in msgs:
        if m.role == "summary":
            summary_text = m.content
        elif m.role in ("user", "assistant"):
            history.append({"role": m.role, "content": m.content})
            if m.role == "assistant":
                turn_count += 1

    return history, summary_text, turn_count


def _save_summary(conv: Conversation, summary_text: str):
    Message.objects.create(conversation=conv, role="summary", content=summary_text)
    conv.save(update_fields=["updated_at"])


@require_POST
@login_required
def api_new_conversation(request: HttpRequest):
    conv = Conversation.objects.create(user=request.user, title="新对话")
    return JsonResponse({"ok": True, "id": conv.id})


@require_POST
@login_required
def api_rename_conversation(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
    cid = payload.get("id")
    title = (payload.get("title") or "").strip()
    if not cid or not title:
        return JsonResponse({"ok": False, "error": "bad_params"}, status=400)
    c = Conversation.objects.get(id=cid, user=request.user)
    c.title = title
    c.save(update_fields=["title", "updated_at"])
    return JsonResponse({"ok": True})


@require_POST
@login_required
def api_delete_conversation(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
    cid = payload.get("id")
    if not cid:
        return JsonResponse({"ok": False, "error": "bad_params"}, status=400)
    c = Conversation.objects.get(id=cid, user=request.user)
    c.delete()
    return JsonResponse({"ok": True})


@require_POST
@login_required
def api_chat(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    text = (payload.get("text") or "").strip()
    cid = payload.get("cid")
    if not text or not cid:
        return JsonResponse({"ok": False, "error": "bad_params"}, status=400)
    MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "1000"))
    text = text[:MAX_INPUT_CHARS]
    conv = Conversation.objects.get(id=cid, user=request.user)

    Message.objects.create(conversation=conv, role="user", content=text)
    conv.save(update_fields=["updated_at"])

    level = risk_level(text)
    if level == "HIGH":
        reply = crisis_reply()
        Message.objects.create(conversation=conv, role="assistant", content=reply)
        conv.save(update_fields=["updated_at"])
        return JsonResponse({"ok": True, "reply": reply, "risk": "HIGH"})

    history, summary_text, turn_count = _get_state_for_conv(conv)

    if level == "MEDIUM":
        history.append({"role": "system", "content": medium_mode_prompt()})

    try:
        if settings.SUMMARY_ENABLED and (turn_count % settings.SUMMARY_EVERY_TURNS == 0):
            summary_text = build_or_update_summary(
                settings.LM_BASE_URL,
                settings.LM_API_KEY,
                settings.LM_MODEL,
                history,
                summary_text,
                settings.SUMMARY_CONTEXT_TURNS,
                settings.SUMMARY_MAX_TOKENS,
                settings.LM_TIMEOUT,
            )
            _save_summary(conv, summary_text)

        pruned = prune_messages(
            history,
            summary_text,
            max_tokens_budget=settings.MAX_CONTEXT_BUDGET,
            keep_last_turns=settings.KEEP_LAST_TURNS,
            must_keep_last_user=True,
        )

        reply = lm_chat(
            settings.LM_BASE_URL,
            settings.LM_API_KEY,
            settings.LM_MODEL,
            pruned,
            settings.LM_MAX_TOKENS,
            settings.LM_TIMEOUT,
        )

        Message.objects.create(conversation=conv, role="assistant", content=reply)
        conv.save(update_fields=["updated_at"])

        if settings.SUMMARY_ENABLED and (turn_count % settings.SUMMARY_EVERY_TURNS == 0):
            summary_text = build_or_update_summary(
                settings.LM_BASE_URL,
                settings.LM_API_KEY,
                settings.LM_MODEL,
                history + [{"role": "assistant", "content": reply}],
                summary_text,
                settings.SUMMARY_CONTEXT_TURNS,
                settings.SUMMARY_MAX_TOKENS,
                settings.LM_TIMEOUT,
            )
            _save_summary(conv, summary_text)

        return JsonResponse({"ok": True, "reply": reply, "risk": level})

    except Exception:
        fallback = "系统暂时无法回应，但我还在。你可以继续说说发生了什么。"
        Message.objects.create(conversation=conv, role="assistant", content=fallback)
        conv.save(update_fields=["updated_at"])
        return JsonResponse({"ok": True, "reply": fallback, "risk": level})


@require_POST
@login_required
def api_chat_stream(request: HttpRequest):
    rl = rate_limit_or_429(request, "chat_stream", limit=6, window_seconds=60)
    if rl:
        return rl

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    text = (payload.get("text") or "").strip()
    cid = payload.get("cid")
    MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "1000"))
    text = text[:MAX_INPUT_CHARS]
    if not text or not cid:
        return JsonResponse({"ok": False, "error": "bad_params"}, status=400)

    conv = Conversation.objects.get(id=cid, user=request.user)

    m_user = Message.objects.create(conversation=conv, role="user", content=text)
    conv.save(update_fields=["updated_at"])

    level = risk_level(text)
    RiskEvent.objects.create(
        conversation=conv,
        message=m_user,
        level=level
    )

    def gen():
        if level == "HIGH":
            reply = crisis_reply()
            Message.objects.create(conversation=conv, role="assistant", content=reply)
            conv.save(update_fields=["updated_at"])
            yield _sse({"t": "r", "c": reply, "risk": "HIGH"})
            yield _sse({"t": "done", "risk": "HIGH"})
            return

        history, summary_text, turn_count = _get_state_for_conv(conv)

        if level == "MEDIUM":
            history.append({"role": "system", "content": medium_mode_prompt()})

        try:
            if settings.SUMMARY_ENABLED and (turn_count % settings.SUMMARY_EVERY_TURNS == 0):
                summary_text = build_or_update_summary(
                    settings.LM_BASE_URL,
                    settings.LM_API_KEY,
                    settings.LM_MODEL,
                    history,
                    summary_text,
                    settings.SUMMARY_CONTEXT_TURNS,
                    settings.SUMMARY_MAX_TOKENS,
                    settings.LM_TIMEOUT,
                )
                _save_summary(conv, summary_text)

            pruned = prune_messages(
                history,
                summary_text,
                max_tokens_budget=settings.MAX_CONTEXT_BUDGET,
                keep_last_turns=settings.KEEP_LAST_TURNS,
                must_keep_last_user=True,
            )

            acc = []
            for delta in lm_chat_stream(
                    settings.LM_BASE_URL,
                    settings.LM_API_KEY,
                    settings.LM_MODEL,
                    pruned,
                    settings.LM_MAX_TOKENS,
                    settings.LM_TIMEOUT,
            ):
                acc.append(delta)
                yield _sse({"t": "d", "c": delta, "risk": level})

            raw_reply = "".join(acc)
            final_reply = force_refusal(raw_reply)

            if final_reply != raw_reply:
                yield _sse({"t": "r", "c": final_reply, "risk": level})
            else:
                pass

            Message.objects.create(conversation=conv, role="assistant", content=final_reply)
            conv.save(update_fields=["updated_at"])

            if settings.SUMMARY_ENABLED and (turn_count % settings.SUMMARY_EVERY_TURNS == 0):
                summary_text = build_or_update_summary(
                    settings.LM_BASE_URL,
                    settings.LM_API_KEY,
                    settings.LM_MODEL,
                    history + [{"role": "assistant", "content": final_reply}],
                    summary_text,
                    settings.SUMMARY_CONTEXT_TURNS,
                    settings.SUMMARY_MAX_TOKENS,
                    settings.LM_TIMEOUT,
                    )
                _save_summary(conv, summary_text)

            yield _sse({"t": "done", "risk": level})

        except Exception:
            fallback = "系统暂时无法回应，但我还在。你可以继续说说发生了什么。"
            Message.objects.create(conversation=conv, role="assistant", content=fallback)
            conv.save(update_fields=["updated_at"])
            yield _sse({"t": "r", "c": fallback, "risk": level})
            yield _sse({"t": "done", "risk": level})

    return StreamingHttpResponse(
        gen(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

def counselor_required(view_func):
    def _wrap(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return HttpResponseForbidden("Forbidden")
        return view_func(request, *args, **kwargs)
    return _wrap


@login_required
@counselor_required
def counselor_risk_dashboard(request):
    events = (
        RiskEvent.objects
        .select_related("conversation", "conversation__user")
        .order_by("-created_at")
    )

    seen = set()
    rows = []

    for e in events:
        cid = e.conversation_id
        if cid in seen:
            continue
        seen.add(cid)

        summary = (
            Message.objects
            .filter(conversation=e.conversation, role="summary")
            .order_by("-created_at")
            .first()
        )

        review = (
            RiskReview.objects
            .filter(conversation=e.conversation)
            .order_by("-updated_at")
            .first()
        )

        rows.append({
            "cid": cid,
            "title": e.conversation.title,
            "user": e.conversation.user.username,
            "level": e.level,
            "summary": (summary.content[:200] + "…") if summary else "",
        })

    return render(request, "chat/counselor_risk.html", {"rows": rows})

@login_required
@counselor_required
def counselor_conv_detail(request, cid):
    conv = Conversation.objects.select_related("user").get(id=cid)

    summary = (
        Message.objects
        .filter(conversation=conv, role="summary")
        .order_by("-created_at")
        .first()
    )

    msgs = (
        Message.objects
        .filter(conversation=conv)
        .order_by("-created_at")[:12]
    )
    msgs = list(reversed(msgs))

    review, _ = RiskReview.objects.get_or_create(conversation=conv)

    return render(request, "chat/counselor_conv.html", {
        "conv": conv,
        "summary": summary.content if summary else "",
        "msgs": msgs,
        "review": review,
    })


@require_POST
@login_required
@counselor_required
def counselor_review_submit(request):
    cid = int(request.POST.get("cid"))
    note = request.POST.get("note", "")

    conv = Conversation.objects.get(id=cid)
    review, _ = RiskReview.objects.get_or_create(conversation=conv)

    review.note = note
    review.reviewer = request.user
    review.reviewed_at = timezone.now()
    review.save(update_fields=["note", "reviewer", "reviewed_at", "updated_at"])

    return redirect(f"/_counselor/c/{cid}/")


@require_POST
@login_required
@counselor_required
def counselor_send(request):
    cid = int(request.POST.get("cid") or "0")
    text = (request.POST.get("text") or "").strip()
    if not cid or not text:
        return redirect(f"/_counselor/c/{cid}/")

    conv = Conversation.objects.get(id=cid)

    Message.objects.create(
        conversation=conv,
        role="counselor",
        sender=request.user.username,
        content=text
    )

    return redirect(f"/_counselor/c/{cid}/")

@require_GET
@login_required
def counselor_messages_api(request, cid):
    if request.user.is_staff:
        conv = Conversation.objects.get(id=cid)
    else:
        conv = Conversation.objects.get(id=cid, user=request.user)

    msgs = (
        Message.objects
        .filter(conversation=conv, role="counselor")
        .order_by("created_at")
        .values("id", "content", "sender", "created_at")
    )
    return JsonResponse({"msgs": list(msgs)})
