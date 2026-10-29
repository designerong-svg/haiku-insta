# 하이쿠 인스타 자동 게시 시스템

매일 정해진 시간에 **하이쿠 카드뉴스 5장(커버 → 원문·발음 → 번역 → 계절어 해설 → 참여 질문)** 을 만들어 인스타그램 캐러셀로 자동 게시합니다. (Gemini 대화에서 정리한 기획 그대로)

```
data/queue.json ─▶ 계절에 맞는 항목 선택 ─▶ Pillow로 5장 렌더링 ─▶ 공개 URL 호스팅 ─▶ Instagram Graph API 게시 ─▶ 큐에 posted 기록
                      ▲
        (선택) Claude API로 큐 자동 보충 — 기본은 draft, 검수 후 approved
```

## 1. 로컬에서 먼저 확인 (게시 없이 렌더링만)

```bash
pip install -r requirements.txt
python -m src.run_daily prepare --dry-run            # 오늘 계절에 맞는 항목 렌더링 → out/<id>/slide_1~5.jpg
python -m src.run_daily prepare --dry-run --id h007  # 특정 항목 지정
```

## 2. 디자인 스타일

`config.json` 의 `"style"` 로 고릅니다. 항목별로 `queue.json` 에 `"style"` 을 넣으면 그 항목만 다르게 나옵니다.

- `poster` (기본): 빨강·검정·종이색 원색 대비, 한 줄마다 하이라이트 박스, 묵직한 명조(일본어)+Pretendard Bold(한글), 기하학 블록, 거친 그레인. 슬라이드마다 빨강 → 빨강 → 흰색 블록 → 검정 → 빨강으로 리듬을 줍니다.
- `classic`: 어두운 웜 톤 + 사진 배경 위에 얹는 시집 느낌. 이 스타일일 때만 `backgrounds/` 사진을 사용합니다.

## 3. 꾸밀 것

| 위치 | 내용 |
|---|---|
| `backgrounds/<autumn\|winter\|spring\|summer\|any>/` | (`classic` 전용) **배경 사진**을 넣으면 자동으로 사용(글자 슬라이드는 살짝 블러). 없으면 계절 팔레트로 자동 생성한 임시 배경 |
| `fonts/` | `Pretendard-Bold/Regular/Light.otf` 3종 (없으면 Noto Sans CJK로 대체) |
| `config.json` | `handle`(카드 하단 계정명), 기본 해시태그 |
| `data/queue.json` | 게시 대기열. `status`: `approved`(게시 대상) / `draft`(검수 대기) / `posted`(완료) |

## 4. 인스타그램 연동 (직접 설정이 필요한 부분)

1. 인스타그램 **프로페셔널(비즈니스/크리에이터) 계정**을 페이스북 페이지에 연결
2. [Meta for Developers](https://developers.facebook.com)에서 앱 생성 → `instagram_content_publish` 권한 포함 토큰 발급
   (페이지 액세스 토큰을 쓰면 만료가 없어 관리가 편합니다)
3. IG User ID 확인
4. GitHub 저장소 → Settings → Secrets and variables → Actions 에 등록
   - `IG_USER_ID`, `IG_ACCESS_TOKEN` (필수)
   - `ANTHROPIC_API_KEY` (큐 자동 보충을 쓸 때만)
   - Variables: `HAIKU_AUTO_APPROVE` = `true` 로 두면 생성분이 검수 없이 바로 게시 대상이 됩니다(기본 비권장)

> 토큰은 코드·채팅에 붙여넣지 말고 Secrets에만 넣으세요.

## 5. 배포

- 이 폴더를 **공개(public) GitHub 저장소**로 올립니다. 인스타그램이 이미지를 URL로 가져가므로 `raw.githubusercontent.com` 공개 주소를 씁니다. (비공개 저장소는 불가 — 다른 호스팅을 쓰려면 `config.json`의 `public_base_url` 변경)
- `.github/workflows/daily.yml` 이 **매일 08:00 KST**에 실행됩니다. 시간은 파일 상단 `cron` 에서 변경 (UTC 기준, KST −9시간).
- 처음엔 Actions 탭 → daily-haiku → **Run workflow (dry_run 체크)** 로 돌려 Artifacts에서 이미지를 확인한 뒤, 체크를 풀고 한 번 실제 게시해 보세요.

## 6. 콘텐츠 운영

- 기본 큐에 16편(가을 5·겨울 4·봄 3·여름 4)이 들어 있어 약 2주 반 분량입니다. 현재 계절 항목을 우선 게시하고, 없으면 큐 순서대로 나갑니다.
- 큐가 5편 미만으로 줄면 `ANTHROPIC_API_KEY`가 있을 때 `src/generate.py`가 현재 계절 작품 7편을 `draft`로 추가합니다. **원문·작가는 LLM이 틀리게 인용할 수 있으니** 俳句データベース 등으로 확인한 뒤 `approved` 로 바꿔 주세요.
- 큐에는 퍼블릭 도메인 작가(바쇼·부손·잇사·시키·료칸)의 작품만 쓰세요.

## 7. 365일 테마 캘린더

`data/haiku_calendar_365.xlsx` (2026-10-30 ~ 2027-10-29). 날짜별로 "그날 어떤 하이쿠를 올릴지" 테마를 미리 정해둔 계획표입니다. 계절·절기 / 일상 상황 / 인생 시기 / 14일 데이 / 숫자·MZ 데이 / 명절·가족·사회 기념일의 여섯 겹이고, **2026-10-30 ~ 11-30 (32일)은 시가 배정되어 있고**(`tools/add_nov.py`), 이후는 한 달 분량씩 원문·작가를 확인해 R·S열(노란색)을 채워 가는 방식입니다. 배정된 시 중 `approved`는 원문 대조를 마친 것이고, `draft`는 **원문·작가를 직접 확인한 뒤 `approved`로 바꿔야** 게시됩니다(`draft`인 날은 계절에 맞는 승인 시로 대체).

- `data/calendar.json` / `calendar.csv`: 같은 내용의 데이터 (프로그램용)
- `tools/build_calendar.py`: 캘린더 생성 (데이 추가·수정은 여기서 하고 다시 실행)
- `tools/export_xlsx.py`: 엑셀로 내보내기
- 게시 로직 연결 완료: `store.pick_next` 가 오늘 날짜의 `poem_id`(approved일 때)를 먼저 쓰고, 없으면 계절 → 큐 순서로 대체합니다.

## 파일 구조

```
src/render.py       카드 5장 렌더링 (세로쓰기 원문, 한/일 혼합 폰트)
src/publish.py      Graph API 캐러셀 게시
src/run_daily.py    prepare(선택+렌더) / publish(게시+큐 갱신)
src/generate.py     큐 자동 보충 (Claude API)
src/store.py        큐·시즌·캡션
.github/workflows/daily.yml   일일 스케줄
```
