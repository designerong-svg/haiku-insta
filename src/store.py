"""큐(data/queue.json) 읽기/쓰기, 시즌 판별, 캡션 생성."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "data" / "queue.json"
CONFIG = ROOT / "config.json"

SEASON_KO = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울", "any": ""}
SEASON_EMOJI = {"spring": "🌸", "summer": "🌿", "autumn": "🍁", "winter": "❄️", "any": "📜"}


def load_config() -> dict:
    return json.loads(CONFIG.read_text("utf-8"))


def load_queue() -> list[dict]:
    return json.loads(QUEUE.read_text("utf-8"))


def save_queue(queue: list[dict]) -> None:
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", "utf-8")


def current_season(cfg: dict, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(ZoneInfo(cfg["timezone"]))
    m = now.month
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    if m in (9, 10, 11):
        return "autumn"
    return "winter"


CALENDAR = ROOT / "data" / "calendar.json"


def calendar_poem_id(date_iso: str) -> str | None:
    """365일 캘린더에서 해당 날짜에 배정된 시 ID (없으면 None)."""
    try:
        for row in json.loads(CALENDAR.read_text("utf-8")):
            if row["date"] == date_iso:
                return row.get("poem_id")
    except (OSError, ValueError, KeyError):
        pass
    return None


def pick_next(queue: list[dict], season: str, date_iso: str | None = None) -> dict | None:
    """오늘 캘린더에 배정된 시(approved)를 먼저, 없으면 현재 계절(또는 any), 그다음 큐 순서."""
    ready = [p for p in queue if p.get("status") == "approved"]
    if date_iso:
        pid = calendar_poem_id(date_iso)
        for p in ready:
            if pid and p["id"] == pid:
                return p
    for p in ready:
        if p.get("season") in (season, "any"):
            return p
    return ready[0] if ready else None


def build_caption(post: dict, cfg: dict) -> str:
    season = post.get("season", "any")
    tags: list[str] = []
    for t in cfg.get("base_hashtags", []) + cfg.get("season_hashtags", {}).get(season, []):
        if t not in tags:
            tags.append(t)
    lines = [
        f"{SEASON_EMOJI.get(season, '📜')} 오늘의 하이쿠 | {post['theme']}",
        "",
        " / ".join(post["translation_ko"]),
        f"— {post['poet_ko']}",
        "",
        post["commentary_ko"][0],
        "",
        "🔖 저장해두고 마음이 헛헛할 때 꺼내 보세요.",
        "💌 함께 읽고 싶은 사람에게 공유해 보세요.",
        "",
        " ".join(tags[:30]),
    ]
    return "\n".join(lines)
