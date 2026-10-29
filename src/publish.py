"""Instagram Graph API로 캐러셀 게시.

필요한 환경변수 (GitHub Secrets에 직접 등록하세요 — 코드/채팅에 붙여넣지 마세요):
  IG_USER_ID       인스타그램 비즈니스/크리에이터 계정의 IG User ID
  IG_ACCESS_TOKEN  instagram_content_publish 권한이 있는 액세스 토큰
"""
from __future__ import annotations

import os
import time

import requests


def _check(r: requests.Response) -> dict:
    if not r.ok:
        raise RuntimeError(f"Graph API 오류 {r.status_code}: {r.text}")
    return r.json()


def wait_for_urls(urls: list[str], timeout: int = 300) -> None:
    """이미지가 공개 URL에서 실제로 내려받아질 때까지 대기 (Instagram이 서버측에서 가져감)."""
    deadline = time.time() + timeout
    for u in urls:
        while True:
            try:
                if requests.head(u, timeout=15, allow_redirects=True).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.time() > deadline:
                raise RuntimeError(f"이미지 URL이 공개되지 않았습니다: {u}")
            time.sleep(10)


def post_carousel(image_urls: list[str], caption: str, cfg: dict) -> str:
    base = cfg["graph_base"].rstrip("/")
    uid = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]

    children = []
    for u in image_urls:
        r = requests.post(f"{base}/{uid}/media", timeout=60, data={
            "image_url": u, "is_carousel_item": "true", "access_token": token})
        children.append(_check(r)["id"])

    r = requests.post(f"{base}/{uid}/media", timeout=60, data={
        "media_type": "CAROUSEL", "children": ",".join(children),
        "caption": caption, "access_token": token})
    container = _check(r)["id"]

    for _ in range(30):  # 최대 ~2분
        s = _check(requests.get(f"{base}/{container}", timeout=30, params={
            "fields": "status_code", "access_token": token}))
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 처리 실패: {s}")
        time.sleep(4)
    else:
        raise RuntimeError("컨테이너 처리 시간 초과")

    r = requests.post(f"{base}/{uid}/media_publish", timeout=60, data={
        "creation_id": container, "access_token": token})
    return _check(r)["id"]
