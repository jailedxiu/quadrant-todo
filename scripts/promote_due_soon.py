#!/usr/bin/env python3
"""Move Microsoft To Do tasks due in fewer than 5 days from non-urgent to urgent lists.

Does not use Grok tokens. Intended for GitHub Actions (and can be run locally).
Graph cannot truly move a task: this creates a copy in the target list (checklist
and linked resources included when possible), then deletes the original.
Attachments and the original task ID are not preserved.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPES = "Tasks.ReadWrite offline_access User.Read"
TZ = ZoneInfo("Asia/Shanghai")
DUE_SOON_DAYS = 5
DEFAULT_CLIENT_ID = "c0a7409f-7493-4aa4-be0f-096818d12a6b"
LISTS = {
    "q1": "重要紧急",
    "q2": "重要不紧急",
    "q3": "紧急不重要",
    "q4": "不重要不紧急",
}
PROMOTE = {"q2": "q1", "q4": "q3"}
COPY_FIELDS = (
    "body",
    "dueDateTime",
    "reminderDateTime",
    "isReminderOn",
    "recurrence",
    "startDateTime",
    "categories",
    "importance",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def request_json(method: str, url: str, *, token: str | None = None, data=None, form=None):
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw or resp.status == 204:
                return None
            return json.loads(raw.decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        # Never echo tokens if they somehow appear.
        lowered = err_body.lower()
        if "refresh_token" in lowered or "access_token" in lowered:
            err_body = "(token redacted from error body)"
        raise RuntimeError(f"{method} {url.split('?')[0]} -> {e.code}: {err_body}") from e


def get_access_token(client_id: str, refresh_token: str) -> tuple[str, str | None]:
    data = request_json(
        "POST",
        TOKEN_URL,
        form={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": SCOPES,
        },
    )
    if not data or not data.get("access_token"):
        raise RuntimeError("token endpoint did not return an access_token")
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        log(
            "warning: Microsoft issued a new refresh token. "
            "If later runs fail with invalid_grant, re-run scripts/login_refresh_token.py"
        )
    return data["access_token"], new_refresh


def graph(token: str, method: str, path: str, data=None):
    url = path if path.startswith("http") else GRAPH + path
    return request_json(method, url, token=token, data=data)


def graph_all(token: str, path: str) -> list:
    url = path if path.startswith("http") else GRAPH + path
    out = []
    while url:
        data = graph(token, "GET", url)
        out.extend(data.get("value") or [])
        url = data.get("@odata.nextLink")
    return out


def due_day(task: dict) -> date | None:
    due = task.get("dueDateTime") or {}
    dt = due.get("dateTime")
    if not dt:
        return None
    try:
        return date.fromisoformat(dt[:10])
    except ValueError:
        return None


def is_due_soon(task: dict, today: date) -> bool:
    day = due_day(task)
    if day is None:
        return False
    return (day - today).days < DUE_SOON_DAYS


def payload_from(task: dict) -> dict:
    copy = {"title": task.get("title") or ""}
    for field in COPY_FIELDS:
        if task.get(field) is not None:
            copy[field] = task[field]
    body = copy.get("body")
    if isinstance(body, dict) and not body.get("content"):
        copy.pop("body", None)
    return copy


def copy_subitems(token: str, from_list: str, from_id: str, to_list: str, to_id: str) -> None:
    items = graph_all(token, f"/me/todo/lists/{from_list}/tasks/{from_id}/checklistItems")
    for item in items:
        graph(
            token,
            "POST",
            f"/me/todo/lists/{to_list}/tasks/{to_id}/checklistItems",
            {"displayName": item.get("displayName") or "", "isChecked": bool(item.get("isChecked"))},
        )
    try:
        links = graph_all(token, f"/me/todo/lists/{from_list}/tasks/{from_id}/linkedResources")
    except RuntimeError:
        links = []
    for lr in links:
        body = {k: lr[k] for k in ("webUrl", "applicationName", "displayName", "externalId") if lr.get(k)}
        if body:
            try:
                graph(token, "POST", f"/me/todo/lists/{to_list}/tasks/{to_id}/linkedResources", body)
            except RuntimeError as e:
                log(f"  linked resource copy skipped: {e}")


def transfer(token: str, from_list: str, to_list: str, task: dict, dry_run: bool) -> None:
    title = task.get("title") or "(untitled)"
    day = due_day(task)
    log(f"  {title}  due={day.isoformat() if day else '?'}  -> transfer")
    if dry_run:
        return
    created = graph(token, "POST", f"/me/todo/lists/{to_list}/tasks", payload_from(task))
    if not created or not created.get("id"):
        raise RuntimeError(f"create failed for {title!r}")
    try:
        copy_subitems(token, from_list, task["id"], to_list, created["id"])
    except RuntimeError as e:
        log(f"  checklist copy incomplete for {title!r}: {e}")
    graph(token, "DELETE", f"/me/todo/lists/{from_list}/tasks/{task['id']}")


def resolve_lists(token: str) -> dict[str, str]:
    existing = graph_all(token, "/me/todo/lists")
    by_name = {x.get("displayName"): x["id"] for x in existing if x.get("id")}
    ids = {}
    for key, name in LISTS.items():
        if name not in by_name:
            raise RuntimeError(f"To Do list not found: {name}")
        ids[key] = by_name[name]
    return ids


def main() -> int:
    client_id = os.environ.get("AZURE_CLIENT_ID") or DEFAULT_CLIENT_ID
    refresh = os.environ.get("MS_REFRESH_TOKEN", "").strip()
    if not refresh:
        log("error: set MS_REFRESH_TOKEN (repo Actions secret)")
        return 2
    dry_run = os.environ.get("DRY_RUN", "").strip() in {"1", "true", "True", "yes"}
    today = datetime.now(TZ).date()
    log(f"today={today.isoformat()} (Asia/Shanghai)  due_soon_days={DUE_SOON_DAYS}  dry_run={dry_run}")
    token, _ = get_access_token(client_id, refresh)
    lists = resolve_lists(token)
    moved = 0
    failed = 0
    for src_key, dst_key in PROMOTE.items():
        src_id, dst_id = lists[src_key], lists[dst_key]
        filter_q = urllib.parse.quote("status ne 'completed'", safe="")
        tasks = graph_all(token, f"/me/todo/lists/{src_id}/tasks?$filter={filter_q}")
        due_soon = [t for t in tasks if is_due_soon(t, today)]
        log(f"{LISTS[src_key]}: {len(tasks)} open, {len(due_soon)} due soon -> {LISTS[dst_key]}")
        for task in due_soon:
            try:
                transfer(token, src_id, dst_id, task, dry_run)
                moved += 1
            except Exception as e:
                failed += 1
                log(f"  FAILED {task.get('title')!r}: {e}")
    log(f"done: moved={moved} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
