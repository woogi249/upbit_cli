# 업비트 API / WebSocket 구현 현황

공식 문서 기준으로 CLI 구현 여부를 점검한 결과입니다.

---

## 1. REST API

### 시세 조회 (Quotation) — 전부 구현됨

| 기능 | 메서드/경로 | CLI 커맨드 | 상태 |
|------|-------------|------------|------|
| 페어 목록 | GET /market/all | `market list-markets` | ✅ |
| 현재가 | GET /ticker | `market get-ticker` | ✅ |
| 호가 | GET /orderbook | `market get-orderbook` | ✅ |
| 호가 정책 | GET /orderbook/instruments | `market get-orderbook-instruments` | ✅ |
| 체결 이력 | GET /trades/ticks | `market get-trades` | ✅ |
| 캔들(초/분/일/주/월) | GET /candles/seconds, minutes, days, weeks, months | `market get-candles` | ✅ |

### 거래·자산 (Exchange) — 대부분 구현됨

| 기능 | 메서드/경로 | CLI 커맨드 | 상태 |
|------|-------------|------------|------|
| 자산 조회 | GET /accounts | `account balance` | ✅ |
| 주문 가능 정보 | GET /orders/chance | `order chance` | ✅ |
| 주문 생성 | POST /orders | `order place` | ✅ |
| 주문 목록/단건 | GET /orders, GET /order | `order list`, `order get` | ✅ |
| 주문 취소 | DELETE /order | `order cancel`, `order cancel-all` | ✅ |
| 입금 목록/단건 | GET /deposits, GET /deposit | `deposit list`, `deposit get` | ✅ |
| 입금 주소 생성 | POST /deposits/generate_coin_address | `deposit generate-address` | ✅ |
| 출금 목록/단건 | GET /withdraws, GET /withdraw | `withdraw list`, `withdraw get` | ✅ |
| 원화 출금 | POST /withdraws/krw | `withdraw krw` | ✅ |
| 디지털 자산 출금 | POST /withdraws/coin | `withdraw coin` | ✅ |
| 입출금 상태 / API Key | GET /status/wallet, GET /api_keys | `service wallet-status`, `service api-keys` | ✅ |
| **원화 입금** | **POST /deposits/krw** | — | ❌ 미구현 |
| **디지털 자산 출금 취소** | **DELETE /withdraws/coin** | — | ❌ 미구현 |

---

## 2. WebSocket — 전부 구현됨

| 타입 | CLI 커맨드 | 비고 |
|------|------------|------|
| ticker | `stream ticker` | ✅ |
| orderbook | `stream orderbook` | ✅ |
| trade | `stream trade` | ✅ |
| candle.{unit} | `stream candle --unit 1m` 등 | ✅ 1s,1m,3m,5m,10m,15m,30m,60m,240m,1d,1w,1M |
| myOrder | `stream my-order` | ✅ (Private) |
| myAsset | `stream my-asset` | ✅ (Private) |

---

## 3. 미구현 REST 2종 (추가 시 고려)

1. **POST /deposits/krw** — 원화 입금 요청  
   - 파라미터: `amount`, `two_factor_type` (kakao/naver/hana)  
   - 2채널 인증 필요.

2. **DELETE /withdraws/coin** — 디지털 자산 출금 취소  
   - 파라미터: `uuid` (출금 UUID)  
   - 취소 가능 상태(`is_cancelable`)인 경우만 가능.

---

## 4. 요약

- **REST:** 시세·거래·입출금 조회 및 실행 대부분 구현. 미구현 2건: 원화 입금(POST /deposits/krw), 출금 취소(DELETE /withdraws/coin).
- **WebSocket:** 시세(ticker, orderbook, trade, candle) 및 Private(myOrder, myAsset) 모두 구현됨.
