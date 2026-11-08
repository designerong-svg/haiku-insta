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


def _wait_container(base: str, container: str, token: str, tries: int = 60, pause: int = 5) -> None:
    for _ in range(tries):  # 영상은 처리 시간이 더 걸린다 (기본 최대 ~5분)
        s = _check(requests.get(f"{base}/{container}", timeout=30, params={
            "fields": "status_code", "access_token": token}))
        code = s.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"릴스 처리 실패: {s}")
        time.sleep(pause)
    raise RuntimeError("릴스 처리 시간 초과")


def post_reel(video_path: str, video_url: str | None, caption: str, cfg: dict) -> str:
    """릴스 게시. 1순위: 파일을 Meta에 직접 올리는 방식(resumable), 안 되면 2순위: 공개 URL 방식."""
    base = cfg["graph_base"].rstrip("/")
    uid = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    container = None
    try:
        r = requests.post(f"{base}/{uid}/media", timeout=60, data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption,
            "share_to_feed": "true", "access_token": token})
        j = _check(r)
        data = open(video_path, "rb").read()
        up = requests.post(j["uri"], timeout=300, data=data, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))})
        if not up.ok:
            raise RuntimeError(f"직접 업로드 실패 {up.status_code}: {up.text[:200]}")
        container = j["id"]
    except Exception as e:  # noqa: BLE001
        if not video_url:
            raise
        print(f"[reel] 직접 업로드 불가({e}). 공개 URL 방식으로 다시 시도합니다.")
        r = requests.post(f"{base}/{uid}/media", timeout=60, data={
            "media_type": "REELS", "video_url": video_url, "caption": caption,
            "share_to_feed": "true", "access_token": token})
        container = _check(r)["id"]
    _wait_container(base, container, token)
    r = requests.post(f"{base}/{uid}/media_publish", timeout=60, data={
        "creation_id": container, "access_token": token})
    return _check(r)["id"]
