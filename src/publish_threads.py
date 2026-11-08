"""Threads API로 캐러셀(이미지 2~20장) 게시.

필요한 환경변수 (GitHub Secrets에 직접 등록 — 코드/채팅에 붙여넣지 마세요):
  THREADS_USER_ID       Threads 사용자 ID (토큰 교환 응답의 user_id 또는 GET /me 의 id)
  THREADS_ACCESS_TOKEN  threads_basic + threads_content_publish 권한의 장기 토큰 (60일 유효)

주의: 호스트는 graph.facebook.com 이 아니라 graph.threads.net 입니다.
토큰 연장(로컬 터미널에서):  python -m src.publish_threads refresh
"""
from __future__ import annotations

import os
import sys
import time

import requests

BASE = "https://graph.threads.net/v1.0"


def _check(r: requests.Response) -> dict:
    if not r.ok:
        raise RuntimeError(f"Threads API 오류 {r.status_code}: {r.text}")
    return r.json()


def configured() -> bool:
    return bool(os.environ.get("THREADS_USER_ID") and os.environ.get("THREADS_ACCESS_TOKEN"))


def _wait_ready(container: str, token: str, tries: int = 30, delay: int = 4) -> None:
    """컨테이너 처리가 끝날 때까지 대기 (상태 조회가 안 되는 경우를 대비해 최소 대기 포함)."""
    time.sleep(10)
    for _ in range(tries):
        try:
            s = _check(requests.get(f"{BASE}/{container}", timeout=30, params={
                "fields": "status,error_message", "access_token": token}))
        except RuntimeError:
            s = {}
        status = s.get("status")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Threads 컨테이너 처리 실패: {s}")
        if status is None:   # 상태 필드를 못 받으면 문서 권장 대기(약 30초)로 대체
            time.sleep(25)
            return
        time.sleep(delay)
    raise RuntimeError("Threads 컨테이너 처리 시간 초과")


def post_carousel(image_urls: list[str], text: str, cfg: dict | None = None) -> str:
    uid = os.environ["THREADS_USER_ID"]
    token = os.environ["THREADS_ACCESS_TOKEN"]
    if not 2 <= len(image_urls) <= 20:
        raise ValueError("Threads 캐러셀은 2~20장이어야 합니다.")

    children = []
    for u in image_urls:
        r = requests.post(f"{BASE}/{uid}/threads", timeout=60, data={
            "media_type": "IMAGE", "image_url": u, "is_carousel_item": "true",
            "access_token": token})
        children.append(_check(r)["id"])

    r = requests.post(f"{BASE}/{uid}/threads", timeout=60, data={
        "media_type": "CAROUSEL", "children": ",".join(children),
        "text": text, "access_token": token})
    container = _check(r)["id"]

    _wait_ready(container, token)

    r = requests.post(f"{BASE}/{uid}/threads_publish", timeout=60, data={
        "creation_id": container, "access_token": token})
    return _check(r)["id"]


def post_text(text: str) -> str:
    """연습용: 글만 게시 (키·권한 확인)."""
    uid = os.environ["THREADS_USER_ID"]
    token = os.environ["THREADS_ACCESS_TOKEN"]
    r = requests.post(f"{BASE}/{uid}/threads", timeout=60, data={
        "media_type": "TEXT", "text": text, "access_token": token})
    container = _check(r)["id"]
    _wait_ready(container, token)
    r = requests.post(f"{BASE}/{uid}/threads_publish", timeout=60, data={
        "creation_id": container, "access_token": token})
    return _check(r)["id"]


def whoami() -> dict:
    return _check(requests.get(f"{BASE}/me", timeout=30, params={
        "fields": "id,username", "access_token": os.environ["THREADS_ACCESS_TOKEN"]}))


def refresh(show: bool = False) -> None:
    """장기 토큰 연장. 새 토큰은 GitHub Secrets에 직접 다시 저장해야 합니다."""
    r = requests.get("https://graph.threads.net/refresh_access_token", timeout=30, params={
        "grant_type": "th_refresh_token", "access_token": os.environ["THREADS_ACCESS_TOKEN"]})
    d = _check(r)
    days = int(d.get("expires_in", 0)) // 86400
    print(f"연장 성공: 약 {days}일 유효")
    if show:
        print("새 토큰(GitHub Secrets의 THREADS_ACCESS_TOKEN에 덮어쓰기, 다른 곳에 붙이지 마세요):")
        print(d["access_token"])
    else:
        print("새 토큰을 보려면 --show 를 붙여 로컬 터미널에서만 실행하세요.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh("--show" in sys.argv)
    else:
        print(whoami())
