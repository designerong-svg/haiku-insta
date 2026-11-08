"""일일 실행 진입점.

  python -m src.run_daily prepare [--dry-run] [--id h001]   다음 게시물 선택 + 이미지 렌더링
  python -m src.run_daily publish                            렌더된 이미지를 인스타에 게시하고 큐 갱신
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

from . import channels, publish, publish_threads, publish_x, render, store

ROOT = store.ROOT
STATE = ROOT / "out" / "current.json"


def public_url(rel_path: str, cfg: dict) -> str:
    base = cfg.get("public_base_url", "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY")
        branch = os.environ.get("GITHUB_REF_NAME", "main")
        if not repo:
            raise RuntimeError("public_base_url 설정이 없고 GitHub Actions 환경도 아닙니다.")
        base = f"https://raw.githubusercontent.com/{repo}/{branch}"
    return f"{base}/{rel_path}"


def _reel_url(rel: str, cfg: dict) -> str | None:
    """공개 URL 방식(2순위)용. raw.githubusercontent 는 mp4 형식을 octet-stream 으로 내려 jsDelivr(커밋 고정)를 쓴다."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        sha = ""
    return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{rel}" if sha else None


def cmd_prepare(args) -> int:
    cfg = store.load_config()
    queue = store.load_queue()
    today = dt.datetime.now(ZoneInfo(cfg["timezone"])).date().isoformat()
    if args.id:
        item = next((p for p in queue if p["id"] == args.id), None)
    else:
        # 예약 실행이 하루에 여러 번 돌아도(건너뜀 대비 이중 예약) 같은 날 두 번 올리지 않는다.
        # 단, 오늘 올라간 글에 아직 못 올린 채널(스레드/X 실패 등)이 있으면 그 채널만 다시 시도한다.
        item = None
        if os.environ.get("GITHUB_EVENT_NAME") == "schedule" or os.environ.get("HAIKU_SKIP_IF_POSTED") == "true":
            todays = [p for p in queue if str(p.get("posted_at") or "").startswith(today)]
            if todays:
                left = [p for p in todays if channels.pending(p, cfg)]
                if not left:
                    print(f"{today}: 오늘은 이미 모든 채널에 게시되었습니다. 건너뜁니다.")
                    STATE.unlink(missing_ok=True)
                    return 0
                item = left[0]
                print(f"{today}: 남은 채널만 다시 시도합니다: {', '.join(channels.pending(item, cfg))}")
        if item is None:
            item = store.pick_next(queue, store.current_season(cfg), today)
    if not item:
        print("게시 가능한(status=approved) 항목이 큐에 없습니다. data/queue.json을 채워주세요.", file=sys.stderr)
        return 1

    out = ROOT / "out" / item["id"]
    shutil.rmtree(out, ignore_errors=True)
    today = dt.datetime.now(ZoneInfo(cfg["timezone"])).date().isoformat()
    files = render.render_post({**item, "_color": render.poster_color(today, cfg)}, out, cfg)
    state = {"id": item["id"], "files": [str(f.relative_to(ROOT)) for f in files]}
    if "reel" in channels.pending(item, cfg):
        try:
            from . import reel
            state["reel"] = str(reel.make_reel(files, out / "reel.mp4").relative_to(ROOT))
            print(f"릴스 영상: {state['reel']}")
        except Exception as e:  # noqa: BLE001 - 릴스 제작 실패가 캐러셀 게시를 막지 않게
            print(f"[reel] 영상 제작 실패, 릴스는 건너뜁니다: {e}", file=sys.stderr)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state), "utf-8")

    print(f"선택: {item['id']} · {item['poet_ko']} · {' / '.join(item['translation_ko'])}")
    print(f"렌더링: {out}")
    print("--- 캡션 ---")
    print(store.build_caption(item, cfg))
    return 0


def cmd_publish(_args) -> int:
    cfg = store.load_config()
    if not STATE.exists():
        print("게시할 항목이 없습니다(오늘 이미 게시됨). 건너뜁니다.")
        return 0
    state = json.loads(STATE.read_text("utf-8"))
    queue = store.load_queue()
    item = next(p for p in queue if p["id"] == state["id"])
    todo = channels.pending(item, cfg)
    if item.get("status") not in ("approved", "posted") or not todo:
        print(f"{item['id']} 는 게시할 채널이 남아 있지 않거나 승인 상태가 아닙니다.", file=sys.stderr)
        return 1 if item.get("status") not in ("approved", "posted") else 0

    urls = [public_url(rel, cfg) for rel in state["files"]]
    local = [str(ROOT / rel) for rel in state["files"]]
    texts = channels.texts(item, cfg)
    now = lambda: dt.datetime.now(ZoneInfo(cfg["timezone"])).isoformat(timespec="seconds")
    failed: list[str] = []

    if "instagram" in todo or "threads" in todo:
        publish.wait_for_urls(urls)

    # 채널마다 따로 시도한다. 한 곳이 실패해도 나머지는 계속 올린다.
    for ch in todo:
        try:
            if ch == "instagram":
                pid = publish.post_carousel(urls, texts["instagram"], cfg)
            elif ch == "reel":
                if not state.get("reel"):
                    raise RuntimeError("릴스 영상이 만들어지지 않았습니다")
                pid = publish.post_reel(str(ROOT / state["reel"]), _reel_url(state["reel"], cfg),
                                        texts["reel"], cfg)
            elif ch == "threads":
                pid = publish_threads.post_carousel(urls, texts["threads"], cfg)
            else:
                pid = publish_x.post(texts["x"], local[:4], cfg)
        except Exception as e:  # noqa: BLE001 - 채널 하나의 실패가 전체를 멈추지 않게
            failed.append(ch)
            print(f"[{ch}] 게시 실패: {e}", file=sys.stderr)
            continue
        item.setdefault("channels_posted", {})[ch] = {"id": pid, "at": now()}
        if ch == "instagram":                      # 기존 필드 유지 (중복 방지 · 달력과 호환)
            item["status"] = "posted"
            item["posted_at"] = now()
            item["media_id"] = pid
        store.save_queue(queue)                    # 성공할 때마다 바로 기록
        print(f"[{ch}] 게시 완료: {item['id']} ({pid})")

    if not channels.pending(item, cfg):
        shutil.rmtree(ROOT / "out" / item["id"], ignore_errors=True)
        STATE.unlink(missing_ok=True)
    if failed:
        print(f"실패한 채널: {', '.join(failed)} (다음 예약 실행에서 해당 채널만 다시 시도합니다)", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dry-run", action="store_true", help="렌더링만 (큐/게시 변경 없음; prepare는 원래 큐를 바꾸지 않음)")
    p.add_argument("--id")
    sub.add_parser("publish")
    args = ap.parse_args()
    return cmd_prepare(args) if args.cmd == "prepare" else cmd_publish(args)


if __name__ == "__main__":
    sys.exit(main())
