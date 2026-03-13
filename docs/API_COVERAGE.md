# 업비트 API 대비 CLI 구현 현황

업비트 공식 API 문서([docs.upbit.com/reference](https://docs.upbit.com/reference)) 기준으로, 현재 upbit_cli에 구현된 기능과 **미구현** 기능을 정리한 문서입니다.

---

## 1. 요약

| 구분 | 업비트 제공 | 현재 구현 | 미구현 |
|------|-------------|-----------|--------|
| **시세 조회 (Quotation)** | 5개 영역 | 5개 영역 (전체) | 없음 |
| **거래/자산 (Exchange)** | 5개 영역 | 0개 (인증·JWT만 준비) | 전부 |

- **시세 조회**: 인증 없이 사용 가능 (Public).
- **거래/자산**: API Key(JWT) 인증 필요 (Private). `auth.py`의 `get_credentials`, `generate_jwt`만 구현되어 있고, 실제 계정/주문/입출금 API 호출은 없음.

---

## 2. 시세 조회 (Quotation) API

### 2.1 구현됨

| 기능 | 업비트 API | CLI 명령 | 비고 |
|------|------------|----------|------|
| **현재가 (Ticker)** | `GET /v1/ticker` | `upbit market get-ticker --market KRW-BTC` | `--compact` 지원 |
| **호가 (Orderbook)** | `GET /v1/orderbook` | `upbit market get-orderbook --market KRW-BTC` | `--limit`, `--compact` 지원 |
| **캔들 (OHLCV)** | `GET /v1/candles/seconds\|minutes\|days\|weeks\|months` | `upbit market get-candles --market KRW-BTC --unit seconds\|minutes\|days\|weeks\|months` | `--to` ISO 8601, `--limit` 200 상한 |
| **페어 목록** | `GET /v1/market/all` | `upbit market list-markets` | `--quote` (KRW/USDT 등), `--limit`, `--details` |
| **최근 체결 내역** | `GET /v1/trades/ticks` | `upbit market get-trades --market KRW-BTC` | `--cursor`(sequential_id), `--to` ISO 8601, `--limit` 500 상한 |
| **호가 정책** | `GET /v1/orderbook/instruments` | `upbit market get-orderbook-instruments --markets KRW-BTC,KRW-ETH` | tick_size, quote_currency 등 |

### 2.2 미구현 (시세 조회)

시세 조회(Quotation) 관련 API는 위 표 기준으로 **전부 구현**됨. (캔들 연봉 등 문서상 추가 엔드포인트는 필요 시 확장 가능.)

---

## 3. 거래 및 자산 (Exchange) API

전부 **미구현**입니다. JWT 생성·인증 로직(`auth.py`)만 준비된 상태입니다.

| 영역 | 업비트 제공 기능 | CLI 구현 |
|------|------------------|----------|
| **자산 (Asset)** | 계정 잔고 조회 | 없음 → `upbit account balance` 등 필요 |
| **주문 (Order)** | 주문 생성, 주문 생성 테스트, 개별/지정/일괄 취소, 주문 가능 정보, 개별 주문 조회, 주문 목록, 체결 대기/종료 주문 조회 | 없음 → `upbit order place`, `upbit order list`, `upbit order cancel` 등 필요 |
| **출금 (Withdrawal)** | 디지털/원화 출금, 출금 취소, 출금 가능 정보, 출금 허용 주소, 개별/목록 조회 | 없음 |
| **입금 (Deposit)** | 입금 주소 생성/조회/목록, 입금 가능 통화, 개별/목록 입금 조회, 트래블룰, 원화 입금 | 없음 |
| **서비스 정보 (Service)** | 입출금 서비스 상태, API Key 목록 조회 | 없음 |

---

## 4. WebSocket

업비트는 시세/호가/체결/계정/주문 등에 대한 **WebSocket**도 제공합니다.  
현재 upbit_cli는 **REST만** 사용하며, WebSocket 구독·스트림 기능은 없습니다.

---

## 5. 정리 및 권장 작업

- **이미 구현된 것**: 현재가(ticker), 호가(orderbook), 캔들(초/분/일/주/월), 마켓 목록(list-markets, --quote 필터), 최근 체결(get-trades, sequential_id·--cursor), 호가 정책(get-orderbook-instruments), 인증 설정(`upbit configure`), JWT 생성 준비.  
  - AI 에이전트용: `--to` ISO 8601, 캔들/체결 limit 상한(200/500), TradeCompact.sequential_id 필수.
- **거래/자산 쪽**: 계정 잔고 → `upbit account balance`, 주문 생성/조회/취소 → `upbit order ...` 등 새 명령 그룹으로 구현 필요.

이 문서는 업비트 API 문서를 기준으로 작성되었으며, 엔드포인트 경로·옵션은 업비트 개발자 문서 최신 버전을 반드시 확인하는 것을 권장합니다.
