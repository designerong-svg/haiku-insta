"""채널별 글 만들기 · 길이 제한 · 켜짐 여부 · 연습용 CLI.

  python -m src.channels preview [--id h001]     인스타/스레드/X 글을 미리 보기 (게시 안 함)
  python -m src.channels test threads "글"       글만 올려 보기(키·권한 확인용)
  python -m src.channels test x "글"
"""
from __future__ import annotations

import os
import re
import sys

from . import publish_threads, publish_x, store

ALL = ("instagram", "reel", "threads", "x")
THREADS_LIMIT = 500
X_LIMIT = 280  # 가중치 기준 (한글/한자/일본어 = 2, 그 외 = 1, 링크 = 23)

_WIDE = re.compile(r"[ᄀ-ᇿ　-鿿가-힯＀-￯]")
_URL = re.compile(r"https?://\S+")


def x_weight(text: str) -> int:
    n = 0
    for part in re.split(r"(https?://\S+)", text):
        if _URL.fullmatch(part):
            n += 23
        else:
            n += sum(2 if _WIDE.match(c) else 1 for c in part)
    return n


def _trim(text: str, limit: int, weigh) -> str:
    while weigh(text) > limit:
        text = text[:-1]
    return text.rstrip()


def enabled(cfg: dict) -> list[str]:
    """켜진 채널. 우선순위: 환경변수 HAIKU_CHANNELS > config.json "channels" > 자동(키가 있으면 켬)."""
    env = os.environ.get("HAIKU_CHANNELS", "").strip()
    if env:
        names = [c.strip() for c in env.split(",") if c.strip() in ALL]
    elif isinstance(cfg.get("channels"), dict):
        names = [c for c in ALL if cfg["channels"].get(c)]
    else:
        names = ["instagram"]
        if publish_threads.configured():
            names.append("threads")
        if publish_x.configured():
            names.append("x")
    if cfg.get("reel") and not os.environ.get("HAIKU_CHANNELS", "").strip() and "reel" not in names \
            and not isinstance(cfg.get("channels"), dict):
        names.insert(1, "reel")            # config.json 의 "reel": true 이면 자동으로 켬
    return names


def pending(item: dict, cfg: dict) -> list[str]:
    done = set((item.get("channels_posted") or {}).keys())
    if item.get("status") == "posted" and not item.get("channels_posted"):
        done.add("instagram")          # 예전 방식으로 올라간 글은 인스타그램 완료로 본다
    return [c for c in enabled(cfg) if c not in done]


def threads_text(item: dict, cfg: dict) -> str:
    tags = [cfg.get("threads_tag") or (cfg.get("base_hashtags") or ["#하이쿠"])[0]]   # 스레드는 주제 태그 1개
    head = f"{store.SEASON_EMOJI.get(item.get('season', 'any'), '📜')} 오늘의 하이쿠 | {item['theme']}"
    body = "\n".join([head, "", " / ".join(item["translation_ko"]), f"— {item['poet_ko']}", "",
                      item["commentary_ko"][0], "", item.get("question_ko", ""), "", " ".join(tags)])
    return _trim(body, THREADS_LIMIT - 10, len)


def x_text(item: dict, cfg: dict) -> str:
    tag = cfg.get("threads_tag") or (cfg.get("base_hashtags") or ["#하이쿠"])[0]
    full = f"{' / '.join(item['translation_ko'])}\n— {item['poet_ko']}\n\n{item.get('question_ko', '')}\n{tag}"
    if x_weight(full) <= X_LIMIT:
        return full
    short = f"{' / '.join(item['translation_ko'])}\n— {item['poet_ko']}\n{tag}"
    return _trim(short, X_LIMIT, x_weight)


def texts(item: dict, cfg: dict) -> dict[str, str]:
    return {"instagram": store.build_caption(item, cfg), "reel": store.build_caption(item, cfg),
            "threads": threads_text(item, cfg),
            "x": x_text(item, cfg)}


def _main(argv: list[str]) -> int:
    cfg = store.load_config()
    if argv and argv[0] == "preview":
        queue = store.load_queue()
        want = argv[argv.index("--id") + 1] if "--id" in argv else None
        item = next((p for p in queue if (p["id"] == want if want else p.get("status") == "approved")), None)
        if not item:
            print("항목이 없습니다.")
            return 1
        t = texts(item, cfg)
        print(f"켜진 채널: {', '.join(enabled(cfg))}\n")
        print(f"[스레드] {len(t['threads'])}/{THREADS_LIMIT}자\n{t['threads']}\n")
        print(f"[X] 가중치 {x_weight(t['x'])}/{X_LIMIT} (이미지는 앞 4장만)\n{t['x']}")
        return 0
    if len(argv) >= 3 and argv[0] == "test":
        if argv[1] == "threads":
            print("스레드 게시 id:", publish_threads.post_text(argv[2]))
        elif argv[1] == "x":
            print("X 게시 id:", publish_x.post(argv[2]))
        else:
            return 2
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
