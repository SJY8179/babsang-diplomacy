# API

서버는 `app/main.py` 하나에 있습니다. 모든 응답은 JSON이고, 진행 상황은 SSE로 흘러갑니다.

## 부서 · 회식 · 참석자

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/config` | 실행 모드(데모/실제), 실제 요청 허용 가게, 지역 목록 |
| GET · POST | `/api/groups` | 부서 목록 / 부서 추가 |
| GET | `/api/groups/{group_id}/meeting` | 부서의 최근 회식 + 참석자 + 입력 현황 |
| POST | `/api/meetings` | 회식 만들기 (이름 · 일시 · 지역) |
| GET · PATCH | `/api/meetings/{mid}` | 회식 조회 / 수정 |
| POST | `/api/meetings/{mid}/participants` | 참석자 추가 → 개인 링크 발급 |
| GET · PUT · DELETE | `/api/p/{token}` | 참석자 본인 조건 조회 / 저장 / 삭제 (로그인 없음) |
| GET | `/p/{token}` | 참석자 입력 페이지 |

## 후보 찾기 · 확인 · 예약

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/meetings/{mid}/plan` | 조건 정리 → 검색 → 점수. 본문은 완화 옵션(`{"budget": "median"}` 등) |
| GET | `/api/sessions/{sid}` | 세션 상태 (후보 · 문의 상태 · 예약) |
| GET | `/api/sessions/{sid}/events` | **SSE** — 에이전트 작업 로그와 최신 세션 상태 |
| POST | `/api/sessions/{sid}/ask` | 90분 안이면 상위 3곳에 자리 문의, 아니면 예약 요청 준비 |
| POST | `/api/sessions/{sid}/approve` | 예약 요청 `{place_id, phone, auto_fallback}` |
| GET | `/api/sessions/{sid}/notice` | 단톡방 공지문 |
| POST | `/api/sessions/{sid}/headcount` | 인원 변경 → 같은 가게부터 재확인 |
| POST | `/api/sessions/{sid}/afterparty` | 1차 근처 2차 찾기 |
| GET | `/api/places/{place_id}` | 가게 상세 (사진 · 메뉴 · 주소, 캐시) |

## 기억

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/feedback` | 만족도 · 1인 지출 · 재방문 의사 저장 |
| GET | `/api/groups/{group_id}/memory` | 팀 프로필(만족 가격대 · 제외할 곳) + 방문 기록 |
| POST | `/api/groups/{group_id}/blog` | 방문 기록 기반 후기 초안 |

## 실매장 테스트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/lab/lookup?q=` | 이름으로 가게 찾기 (읽기 전용) |
| POST | `/api/lab/session` | 가게 하나로 테스트 세션 (자동 넘김 없음). 실제 요청 모드에서는 서버를 켠 컴퓨터에서만 |

실제 요청이 나갈 수 있는 동작(`ask` · `approve` · `headcount` · `lab/session`)은 프록시·터널을 거친 요청이면 403을 돌려줍니다.
