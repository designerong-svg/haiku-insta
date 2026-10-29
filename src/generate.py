"""큐 자동 보충: 현재 계절에 맞는 하이쿠 게시물을 Claude API로 생성해 data/queue.json 에 추가.

환경변수: ANTHROPIC_API_KEY (필수), HAIKU_AUTO_APPROVE=true (선택), HAIKU_MODEL (선택)

기본값은 status="draft" 로 저장 → 사람이 원문/번역을 확인하고 "approved" 로 바꿔야 게시됩니다.
(LLM이 하이쿠 원문·작가를 틀리게 인용하는 일이 실제로 있어 기본은 검수 후 게시입니다.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import store

MODEL = os.getenv("HAIKU_MODEL", "claude-sonnet-5-5")
SEASON_NAME = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
REQUIRED = ["season", "theme", "poet_ja", "poet_ko", "original", "romaji", "translation_ko",
            "kigo_ja", "kigo_ko", "cover_ko", "commentary_ko", "question_ko"]

PROMPT = """한국 인스타그램 하이쿠 큐레이션 채널용 게시물 {count}개를 만들어 주세요. 계절: {season_ko}.

규칙:
- 작가는 퍼블릭 도메인 고전 작가만: 마츠오 바쇼, 요사 부손, 코바야시 잇사, 마사오카 시키, 료칸.
- 원문(일본어)과 작가 귀속에 '확신이 있는' 작품만 고르세요. 조금이라도 불확실하면 빼세요. 개수가 모자라도 괜찮습니다.
- 현대인이 공감할 감정(위로, 고독, 그리움, 일상의 발견 등)과 계절감이 있는 작품.
- original/romaji는 5-7-5에 맞춰 정확히 3개 요소 배열. 로마자는 매크론 없이 표기.
- translation_ko는 자연스러운 한국어 3줄. commentary_ko는 2개 문단(각 1~2문장). 사실이 불확실한 일화는 쓰지 마세요.
- cover_ko는 공감을 부르는 한 문장, question_ko는 댓글 참여를 유도하는 질문 한 문장.
- 아래 이미 사용한 원문은 제외: {existing}

JSON 배열만 출력하세요(설명·코드펜스 금지). 각 원소 키:
season("{season}"), theme, poet_ja, poet_ko, original[3], romaji[3], translation_ko[3],
kigo_ja, kigo_ko, cover_ko, commentary_ko[2], question_ko
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=7)
    ap.add_argument("--if-below", type=int, default=0, help="승인된 대기 항목이 이 수 이상이면 생성하지 않음")
    args = ap.parse_args()

    cfg = store.load_config()
    queue = store.load_queue()
    waiting = [p for p in queue if p.get("status") == "approved"]
    if args.if_below and len(waiting) >= args.if_below:
        print(f"대기 {len(waiting)}개 — 보충 불필요")
        return 0

    season = store.current_season(cfg)
    existing = " | ".join("".join(p["original"]) for p in queue)

    import anthropic  # 지연 임포트: 키 없는 환경에서도 다른 모듈은 동작

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "user", "content": PROMPT.format(
            count=args.count, season=season, season_ko=SEASON_NAME[season], existing=existing or "없음")}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        print("응답에서 JSON 배열을 찾지 못했습니다.", file=sys.stderr)
        return 1
    items = json.loads(m.group(0))

    used = {"".join(p["original"]) for p in queue}
    nums = [int(p["id"][1:]) for p in queue if re.fullmatch(r"h\d+", p["id"])]
    next_id = max(nums, default=0) + 1
    status = "approved" if os.getenv("HAIKU_AUTO_APPROVE", "").lower() == "true" else "draft"

    added = 0
    for it in items:
        if any(k not in it for k in REQUIRED):
            continue
        if len(it["original"]) != 3 or len(it["romaji"]) != 3 or not it["translation_ko"]:
            continue
        if "".join(it["original"]) in used:
            continue
        it.update({"id": f"h{next_id:03d}", "status": status, "posted_at": None})
        queue.append(it)
        used.add("".join(it["original"]))
        next_id += 1
        added += 1

    store.save_queue(queue)
    print(f"{added}개 추가 (status={status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
