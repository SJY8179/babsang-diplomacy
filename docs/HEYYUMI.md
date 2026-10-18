# Hey Yumi 연동

모든 외부 호출은 `app/yumi/client.py` 한 파일에서만 일어납니다. 에이전트는 `YumiClient` 인터페이스만 알고, 구현은 설정으로 바뀝니다.

| 구현 | 언제 | 검색·상세 | 문의·예약 |
|---|---|---|---|
| `FakeYumi` | `YUMI_MODE=mock` | 데모 데이터 | 가짜 응답 |
| `HybridYumi` | `rest` + `simulate` | **실제** | 가짜 응답 |
| `RoutedYumi` | `rest` + `live` + `YUMI_LIVE_PLACES` | **실제** | 허용한 가게만 **실제**, 나머지 가짜 |
| `RestYumi` | `rest` + `sandbox`/`live` | **실제** | **실제** (sandbox는 샌드박스 헤더) |

## 쓰는 도구

| 단계 | MCP 도구 | API | 메서드 |
|---|---|---|---|
| 지역 → 좌표 | `resolve_regions` | `GET /regions` | `region()` |
| 조건 검색 | `search_places` | `GET /places?region_name=` | `search()` |
| 주변 검색 | `nearby_places` | `GET /places/nearby` | `nearby()` |
| 이름 검색 | `search_places(keyword)` | `GET /places?keyword=` | `lookup()` |
| 상세 · 사진 · 메뉴 | `get_place` | `GET /places/{id}?fields=core,contact_hours,edge,media` | `place()` |
| 지금 자리 문의 | `request_live_status` · `wait_for_live_status` | `POST /live-status` · `GET /live-status/{id}?wait=25` | `ask()` · `ask_result()` |
| 예약 | `request_reservation` · `wait_for_reservation` | `POST /reservations` · `GET /reservations/{id}?wait=25` | `reserve()` · `reservation_result()` |

## 참석자 조건 → 검색 조건

| 참석자가 쓴 것 | 검색에 들어가는 값 | 처리 |
|---|---|---|
| 1인 예산 | — | 가장 큰 예산을 상한으로, 메뉴 평균이 20% 넘게 비싸면 제외. 충돌 시 중앙값으로 완화 제안 |
| 채식 · 비건 | `dietary=vegetarian_mixed_group_suitable` / `mixed_group_suitable` | 같이 먹는 일반 메뉴도 있어야 하므로 혼합 식단 값 사용 |
| 알레르기 | `exclude=갑각류` | 해당 음식이 대표 메뉴인 전문점만 제외. 안전 보장은 아니므로 "매장 확인" 표시 |
| 분위기 | `atmosphere=quiet,cozy…` | 정렬용(후보를 줄이지 않음) |
| 회식 시간 | `open_at=2026-10-23 19:00` | 그 시간에 영업하는 곳만 |
| 출발역 | — | 참석자별 이동 시간 → 이동 균형 점수(30%) |

처음 검색에서 남는 후보가 5곳보다 적으면, 식당만 남기고 필터를 풀어 다시 찾습니다. 대신 카드에 조건별 "충족 / 확인 필요"를 표시합니다.

## 응답에서 쓰는 값

- `possiblyClosed` · `closureSignal` · `freshnessScore` → 폐업 의심이나 오래된 정보는 후보에서 제외
- `serviceAttributes` (group_friendly · private_room · parking · reservable …) → 조건 충족 여부와 근거 배지
- `price.avg` → **메뉴 평균**. 1인 금액이 아니므로 화면에도 그렇게 표기
- `yumiReservable` → 앱 안에서 문의·예약 가능한 파트너인지
- `nearestStation` · `distanceM` · `menu` · `aiSummary` · `photos`

## 지킨 규칙

- 실시간 문의는 '지금' 질문입니다. 회식이 90분 안일 때만 쓰고, 그보다 먼 날은 예약 요청으로 확인합니다.
- 동시 문의는 최대 3곳, 예약은 한 번에 한 곳이고 사람이 승인한 뒤에만 보냅니다.
- 422는 재시도하지 않고 "문의 미지원"으로 처리하고, 429는 `Retry-After`를 따릅니다.
- MCP 도구로는 문의·예약을 호출하지 않습니다(샌드박스가 없어 실제 사장님께 갑니다).
