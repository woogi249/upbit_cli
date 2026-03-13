# Quotation API 나머지 구현 계획 (최종)

시세 조회(Quotation) 미구현 4가지(마켓 목록, 최근 체결, 캔들 확장, 호가 정책) 구현 계획.  
**AI-Agent-First** 4가지 필수 개선 사항을 반영함.

---

## 준수 사항 (기존 지침)

- **출력**: 성공 시 `{"success": true, "data": ...}` 만 stdout, 에러 시 표준 JSON envelope을 stderr.
- **토큰 효율**: `--compact` 기본 True, `--limit` 기본값 작게. 배열 응답은 limit으로 자르기.
- **정밀도**: 금액/수량은 `Decimal`, JSON 직렬화 시 `field_serializer`로 **문자열**.
- **Self-documenting**: 모든 옵션/커맨드 영문 Docstring.
- **Rich 모드**: `--output rich` 시 `_is_rich(ctx)` 분기, Rich Table 출력.
- **에러**: `request_json` → `UpbitAPIError` 처리, `_print_error_stderr` 후 `typer.Exit`.
- **거래/자산(Exchange)**: 본 계획에 포함하지 않음.

---

## AI-Agent-First 4가지 필수 개선

### 1. Smart Filtering for `list-markets` (--quote)

- **목적**: 300+ 마켓 전체 대신, 특정 견적 통화만 조회해 토큰 절약.
- **동작**:  
  - 옵션 `--quote` (선택, 문자열, 예: `KRW`, `USDT`, `BTC`).  
  - API로 전체 마켓 조회 후, **먼저** `market.startswith(f"{quote}-")` 로 필터.  
  - 그 다음 `--limit` 적용하여 상위 N개만 반환.  
- **순서**: fetch → filter by quote (if given) → slice by limit → output.

### 2. Abstract Time Formatting (--to, ISO 8601)

- **목적**: LLM이 업비트 전용 시간 형식 대신 표준 ISO 8601만 쓰도록.
- **적용 커맨드**: `get-trades`, `get-candles`.
- **동작**:  
  - `--to` 인자를 **ISO 8601** 문자열로 받음 (예: `2026-03-13T21:58:37`, `2026-03-13T21:58:37Z`).  
  - Python에서 `datetime.fromisoformat(...)` 또는 `dateutil.parser`로 파싱 후, 업비트가 요구하는 형식으로 변환:  
    - **get-trades**: 업비트는 `to` 로 `HHmmss` 또는 `HH:mm:ss` 등 사용 시, 해당 일자의 시간 부분만 추출해 전달. (문서 확인: `to` 파라미터 형식)  
    - **get-candles**: `to` 는 보통 `yyyy-MM-dd'T'HH:mm:ss` 또는 `yyyy-MM-dd HH:mm:ss` 등. 파싱한 datetime을 해당 형식 문자열로 변환.  
  - 변환 유틸을 한 곳에 두고 (예: `upbit_cli/commands/market.py` 내 `_to_upbit_time(iso_str: str, for_trades: bool) -> str`), get-trades와 get-candles에서 공통 사용.

### 3. Mandatory Pagination Keys (TradeCompact.sequential_id)

- **목적**: 에이전트가 다음 페이지 요청 시 `--cursor` 로 사용할 수 있도록.
- **동작**:  
  - **TradeCompact** 에 반드시 **`sequential_id`** 필드를 포함.  
  - 업비트 `GET /v1/trades/ticks` 응답의 `sequential_id` 를 그대로 전달.  
  - `get-trades` 에 `--cursor` 옵션 추가: API의 `cursor` 파라미터에 전달 (이전 응답의 `sequential_id` 값).  
  - Docstring에 "Use the last `sequential_id` from the response as `--cursor` for the next call" 명시.

### 4. Hard Limits (캔들 200, 체결 500)

- **목적**: AI가 `--limit 1000` 등을 요청해도 HTTP 400이 나지 않도록.
- **동작**:  
  - **get-candles**: `--limit` 값을 **최대 200**으로 clamp. 예: `limit = min(limit, 200)` 또는 Typer 콜백/validator에서 `min(limit, 200)` 사용.  
  - **get-trades**: `--limit` 값을 **최대 500**으로 clamp.  
  - 기본값은 그대로 작게 유지 (캔들 5, 체결 10 등). 사용자가 200/500을 넘기면 **자동으로 200/500으로 제한**하고, 에러 없이 요청.  
  - (선택) stderr에 "limit was capped to 200" 같은 한 줄 안내 가능. 기본은 무음 cap.

---

## 1. 마켓 목록 (list-markets)

**API**: `GET /v1/market/all`, 선택 `is_details`.

- **Pydantic**: `MarketInfoRaw`, `MarketInfoCompact` (market, korean_name, english_name; 상세는 Raw만).
- **커맨드**: `upbit market list-markets`
  - `--details` / `--no-details` (기본 False).
  - **`--quote`** (선택, str): 예: `KRW`, `USDT`. 적용 순서: **fetch → filter `market.startswith(f"{quote}-")` → then `--limit`**.
  - `--limit` (기본 50): 필터 후 상위 N개.
  - `--compact` (기본 True).
- **출력**: 기존 패턴 + Rich 테이블.

---

## 2. 최근 체결 내역 (get-trades)

**API**: `GET /v1/trades/ticks`, params: `market`, `count`, `days_ago`, `to`, `cursor`.

- **Pydantic**: `TradeRaw`, **TradeCompact** — 반드시 **`sequential_id`** 포함 (그 외: market, timestamp, trade_price, trade_volume, ask_bid). Decimal → 문자열.
- **커맨드**: `upbit market get-trades`
  - `--market` (필수), **`--limit`** (기본 10, **max 500으로 clamp**), `--days-ago`, **`--to`** (ISO 8601 문자열, 내부에서 업비트 형식으로 변환), **`--cursor`** (이전 응답의 sequential_id).
  - `--compact` (기본 True).
- **로직**: `to` 가 있으면 `_to_upbit_time(to, for_trades=True)` 로 변환 후 API에 전달. `limit = min(limit, 500)`.

---

## 3. 캔들 단위 확장 (초/주/월)

- **get-candles** 확장: `--unit` = `seconds | minutes | days | weeks | months`.
- **경로**: seconds → `/candles/seconds/{interval}`, minutes → `/candles/minutes/{interval}`, days → `/candles/days`, weeks → `/candles/weeks`, months → `/candles/months`.
- **`--to`**: ISO 8601 입력 → `_to_upbit_time(to, for_trades=False)` 로 캔들용 형식 변환 후 API에 전달.
- **`--limit`**: **min(limit, 200)** 으로 clamp (캔들 최대 200).

---

## 4. 호가 정책 (get-orderbook-instruments)

**API**: `GET /v1/orderbook/instruments`, params: `markets`.

- **Pydantic**: `OrderbookInstrumentRaw`, `OrderbookInstrumentCompact` (market, tick_size 등, 문자열 직렬화).
- **커맨드**: `upbit market get-orderbook-instruments` — `--markets` (필수, 쉼표 구분), `--compact` (기본 True).

---

## 5. 공통 유틸 및 검증

- **시간 변환**: `_parse_iso8601_to_upbit(iso_str: str, for_trades: bool) -> str` (또는 두 함수로 분리). get-trades는 해당 API의 `to` 스펙에 맞게, get-candles는 `to` 스펙에 맞게 변환.
- **Limit clamp**:  
  - 캔들: `effective_limit = min(limit, 200)`.  
  - 체결: `effective_limit = min(limit, 500)`.

---

## 6. 테스트

- list-markets: 200 + 목록, `--quote KRW` 시 필터 결과만 포함, exit 0 및 JSON 파싱.
- get-trades: 200 + 배열, **TradeCompact에 sequential_id 존재**, `--to` ISO 8601 전달 시 변환된 값이 API mock에 전달되는지, `--limit 1000` 시 500으로 cap되어 400 미발생.
- get-candles: `--unit weeks`, `--limit 300` 시 200으로 cap, `--to` ISO 8601 변환.
- get-orderbook-instruments: 200 + 배열, exit 0.
- (선택) conftest에 sample_markets_response, sample_trades_response, sample_orderbook_instruments_response.

---

## 7. 파일 변경 요약

| 파일 | 변경 내용 |
|------|------------|
| `upbit_cli/commands/market.py` | Market/Trade/OrderbookInstrument 모델; list-markets(**--quote**, --limit), get-trades(**--cursor**, **--to** ISO 8601, **limit clamp 500**), get-candles(**--to** ISO 8601, **unit 확장**, **limit clamp 200**), get-orderbook-instruments; **TradeCompact.sequential_id** 필수; **_parse_iso8601_to_upbit** (또는 _to_upbit_time) 유틸; Rich 헬퍼. |
| `tests/test_cli.py` | list-markets(quote 필터), get-trades(cursor, to, limit cap), get-candles(weeks, to, limit cap), get-orderbook-instruments. |
| `tests/test_models.py` | TradeCompact에 sequential_id 포함 및 직렬화 검증. |
| `docs/API_COVERAGE.md` | 구현 완료 후 미구현 목록 갱신. |

---

## 8. 구현 순서 제안

1. **공통**: `_parse_iso8601_to_upbit` (또는 _to_upbit_time) 구현, limit clamp 상수 (CANDLES_MAX=200, TRADES_MAX=500).
2. **list-markets**: 모델 + 커맨드 + **--quote** 필터(quote 적용 후 limit).
3. **get-candles 확장**: unit 확장 + **--to** ISO 8601 + **limit clamp 200**.
4. **get-trades**: 모델(TradeCompact에 **sequential_id** 포함) + 커맨드 + **--cursor**, **--to** ISO 8601, **limit clamp 500**.
5. **get-orderbook-instruments**: 모델 + 커맨드.
6. **테스트** 및 API_COVERAGE.md 갱신.
