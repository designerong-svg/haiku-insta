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
import sys
from zoneinfo import ZoneInfo

from . import publish, render, store

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


def cmd_prepare(args) -> int:
    cfg = store.load_config()
    queue = store.load_queue()
    if args.id:
        item = next((p for p in queue if p["id"] == args.id), None)
    else:
        import datetime as dt
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo(cfg["timezone"])).date().isoformat()
        item = store.pick_next(queue, store.current_season(cfg), today)
    if not item:
        print("게시 가능한(status=approved) 항목이 큐에 없습니다. data/queue.json을 채워주세요.", file=sys.stderr)
        return 1

    out = ROOT / "out" / item["id"]
    shutil.rmtree(out, ignore_errors=True)
    files = render.render_post(item, out, cfg)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"id": item["id"], "files": [str(f.relative_to(ROOT)) for f in files]}), "utf-8")

    print(f"선택: {item['id']} · {item['poet_ko']} · {' / '.join(item['translation_ko'])}")
    print(f"렌더링: {out}")
    print("--- 캡션 ---")
    print(store.build_caption(item, cfg))
    return 0


def cmd_publish(_args) -> int:
    cfg = store.load_config()
    state = json.loads(STATE.read_text("utf-8"))
    queue = store.load_queue()
    item = next(p for p in queue if p["id"] == state["id"])
    if item.get("status") != "approved":
        print(f"{item['id']} 는 이미 게시됐거나 승인 상태가 아닙니다.", file=sys.stderr)
        return 1

    urls = [public_url(rel, cfg) for rel in state["files"]]
    publish.wait_for_urls(urls)
    media_id = publish.post_carousel(urls, store.build_caption(item, cfg), cfg)

    item["status"] = "posted"
    item["posted_at"] = dt.datetime.now(ZoneInfo(cfg["timezone"])).isoformat(timespec="seconds")
    item["media_id"] = media_id
    store.save_queue(queue)
    shutil.rmtree(ROOT / "out" / item["id"], ignore_errors=True)
    STATE.unlink(missing_ok=True)
    print(f"게시 완료: {item['id']} (media_id={media_id})")
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
