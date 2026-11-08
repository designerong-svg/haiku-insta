"""X(트위터) API v2로 이미지 + 글 게시.

필요한 환경변수 (GitHub Secrets에 직접 등록 — 코드/채팅에 붙여넣지 마세요):
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
  (앱 권한을 'Read and write'로 바꾼 '뒤에' Access Token/Secret을 발급해야 쓰기가 됩니다)

OAuth 1.0a 사용자 컨텍스트. 크레딧(사용량 과금)이 충전되어 있어야 합니다.
이미지 업로드 주소는 X가 최근 바꾸고 있어 config.json 의 "x_media_upload_url" 로 바꿀 수 있습니다.
"""
from __future__ import annotations

import os
import sys

import requests

TWEET_URL = "https://api.x.com/2/tweets"
DEFAULT_MEDIA_URL = "https://api.x.com/2/media/upload"


def configured() -> bool:
    return all(os.environ.get(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"))


def _auth():
    from requests_oauthlib import OAuth1   # X를 쓸 때만 필요
    return OAuth1(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                  os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"])


def _check(r: requests.Response) -> dict:
    if not r.ok:
        hint = {401: "키/토큰 확인", 402: "크레딧 잔액 확인", 403: "앱 권한(Read and write)·토큰 재발급 확인",
                429: "호출 한도 초과"}.get(r.status_code, "")
        raise RuntimeError(f"X API 오류 {r.status_code} ({hint}): {r.text}")
    return r.json() if r.text else {}


def upload_image(path: str, cfg: dict | None = None) -> str:
    url = (cfg or {}).get("x_media_upload_url") or DEFAULT_MEDIA_URL
    with open(path, "rb") as f:
        r = requests.post(url, auth=_auth(), timeout=120,
                          files={"media": f}, data={"media_category": "tweet_image"})
    d = _check(r)
    mid = (d.get("data") or {}).get("id") or d.get("media_id_string") or d.get("id")
    if not mid:
        raise RuntimeError(f"X 이미지 업로드 응답에서 media id를 찾지 못했습니다: {d}")
    return str(mid)


def post(text: str, image_paths: list[str] | None = None, cfg: dict | None = None) -> str:
    body: dict = {"text": text}
    if image_paths:
        ids = [upload_image(p, cfg) for p in image_paths[:4]]   # 한 글에 이미지 최대 4장
        body["media"] = {"media_ids": ids}
    d = _check(requests.post(TWEET_URL, auth=_auth(), json=body, timeout=60))
    return d["data"]["id"]


if __name__ == "__main__":
    print("글만 올리는 테스트:  python -m src.channels test x \"테스트 글\"", file=sys.stderr)
