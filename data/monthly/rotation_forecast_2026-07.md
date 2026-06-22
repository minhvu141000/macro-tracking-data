# Dự báo luân chuyển dòng tiền — Tháng 2026-07

> **File cho AI agent (fundamental stock-picker) — KHÔNG hiển thị trên dashboard.**
> Horizon: tháng tới · Cửa sổ: 17 phiên (2026-05-26 → 2026-06-18).
> Regime: Tăng trưởng vượt kỳ vọng, lạm phát nguội hơn kỳ vọng, lãi suất đi ngang, risk-on. Chu kỳ: đường cong normal.

⚠️ **Độ tin:** engine dự báo dựa trên persistence 3 trục (vĩ mô · dòng tiền · giá). Edge dự báo hiện CHƯA kiểm chứng (mẫu nhỏ/backfill — xem `rotation_engine_scorecard.md`). Dùng như xếp hạng ưu tiên + giả thuyết, KHÔNG phải tín hiệu chắc chắn.

## Xếp hạng dự báo (cao → thấp)

| # | Sector | ETF | Phase | Conf | Score | Vĩ mô | Dòng tiền (MFI vs SPY) | Giá (RS 1M) |
|---|--------|-----|-------|------|-------|-------|------------------------|-------------|
| 1 | Industrials | XLI | **INFLOW_LIKELY** | HIGH | +0.88 | 16/17 | +43.6 STRONG_INFLOW | 5.43% |
| 2 | Financials | XLF | **INFLOW_LIKELY** | HIGH | +0.74 | 14/17 | +25.9 STRONG_INFLOW | 2.89% |
| 3 | Consumer Discretionary | XLY | **INFLOW_LIKELY** | MED | +0.71 | 17/17 | +3.9 INFLOW | 0.01% |
| 4 | Technology | XLK | **INFLOW_LIKELY** | HIGH | +0.39 | 12/17 | +5.9 INFLOW | 8.55% |
| 5 | Communication Services | XLC | **FORMING** | MED | +0.03 | 14/17 | -23.6 STRONG_OUTFLOW | -7.19% |
| 6 | Materials | XLB | **NEUTRAL** | MED | +0.13 | 8/17 | +1.5 INFLOW | 3.76% |
| 7 | Real Estate | XLRE | **NEUTRAL** | MED | -0.32 | 2/17 | -29.8 STRONG_OUTFLOW | -1.99% |
| 8 | Consumer Staples | XLP | **NEUTRAL** | MED | -0.39 | 2/17 | -23.9 STRONG_OUTFLOW | -4.96% |
| 9 | Utilities | XLU | **OUTFLOW_LIKELY** | MED | -0.26 | 0/17 | +23.8 STRONG_INFLOW | -0.99% |
| 10 | Healthcare | XLV | **AVOID** | HIGH | -0.58 | 0/17 | -37.6 STRONG_OUTFLOW | -0.41% |
| 11 | Energy | XLE | **AVOID** | HIGH | -1.76 | 0/17 | -56.4 STRONG_OUTFLOW | -14.01% |

## Sector để fundamental agent SĂN cổ phiếu

### Industrials (XLI) — INFLOW_LIKELY · conf HIGH
Vĩ mô hậu thuẫn bền 16/17 phiên + dòng tiền/giá xác nhận (mom 14/17, MFI vs SPY +43.6, trend -0.1) → KHẢ NĂNG NHẬN dòng tiền tháng tới. Sector để fundamental agent săn cổ phiếu.

**Universe (đã lọc rs_1m>0 + above_ma50, sort RS giảm dần):**
| Ticker | RS 1M | Ret 1M | >MA200 |
|--------|-------|--------|--------|
| GE | 23.32% | 25.36% | ✓ |
| CAT | 12.57% | 14.61% | ✓ |
| ETN | 11.38% | 13.42% | ✓ |
| RTX | 4.77% | 6.81% | ✓ |
| DE | 3.55% | 5.59% | ✓ |
| HON | 3.42% | 5.46% | ✓ |

### Financials (XLF) — INFLOW_LIKELY · conf HIGH
Vĩ mô hậu thuẫn bền 14/17 phiên + dòng tiền/giá xác nhận (mom 10/17, MFI vs SPY +25.9, trend +0.05) → KHẢ NĂNG NHẬN dòng tiền tháng tới. Sector để fundamental agent săn cổ phiếu.

**Universe (đã lọc rs_1m>0 + above_ma50, sort RS giảm dần):**
| Ticker | RS 1M | Ret 1M | >MA200 |
|--------|-------|--------|--------|
| C | 17.21% | 19.25% | ✓ |
| GS | 16.55% | 18.59% | ✓ |
| MS | 15.68% | 17.72% | ✓ |
| BAC | 9.38% | 11.42% | ✓ |
| WFC | 8.22% | 10.26% | ✗ |
| JPM | 7.94% | 9.98% | ✓ |
| AXP | 7.24% | 9.28% | ✓ |

### Consumer Discretionary (XLY) — INFLOW_LIKELY · conf MED
Vĩ mô hậu thuẫn bền 17/17 phiên + dòng tiền/giá xác nhận (mom 8/17, MFI vs SPY +3.9, trend +0.3) → KHẢ NĂNG NHẬN dòng tiền tháng tới. Sector để fundamental agent săn cổ phiếu.

**Universe (đã lọc rs_1m>0 + above_ma50, sort RS giảm dần):**
| Ticker | RS 1M | Ret 1M | >MA200 |
|--------|-------|--------|--------|
| BKNG | 9.4% | 11.44% | ✗ |
| HD | 9.32% | 11.36% | ✗ |
| MAR | 8.64% | 10.68% | ✓ |
| GM | 7.37% | 9.41% | ✓ |
| TJX | 6.67% | 8.71% | ✓ |
| ABNB | 6.54% | 8.58% | ✓ |
| NKE | 5.47% | 7.51% | ✗ |

### Technology (XLK) — INFLOW_LIKELY · conf HIGH
Vĩ mô hậu thuẫn bền 12/17 phiên + dòng tiền/giá xác nhận (mom 10/17, MFI vs SPY +5.9, trend -0.1) → KHẢ NĂNG NHẬN dòng tiền tháng tới. Sector để fundamental agent săn cổ phiếu.

**Universe (đã lọc rs_1m>0 + above_ma50, sort RS giảm dần):**
| Ticker | RS 1M | Ret 1M | >MA200 |
|--------|-------|--------|--------|
| AMD | 27.74% | 29.78% | ✓ |
| TXN | 4.76% | 6.8% | ✓ |
| CSCO | 1.57% | 3.61% | ✓ |

### Communication Services (XLC) — FORMING · conf MED
Vĩ mô bền (14/17) nhưng dòng tiền/giá chưa theo (mom 2/17, MFI vs SPY -23.6) → ĐANG HÌNH THÀNH, canh vào sớm khi giá vượt MA / dòng tiền chuyển dương.

_Không có cổ phiếu nào trong universe đạt rs_1m>0 + above_ma50._

## Sector NÉ (outflow/avoid)

- **Utilities (XLU)** — OUTFLOW_LIKELY: Vĩ mô yếu (0/17) + dòng tiền/giá yếu (mom 7/17, MFI vs SPY +23.8) → có khả năng RA tiền.
- **Healthcare (XLV)** — AVOID: Vĩ mô yếu bền + dòng tiền ra + RS âm (-0.4%) → tránh.
- **Energy (XLE)** — AVOID: Vĩ mô yếu bền + dòng tiền ra + RS âm (-14.0%) → tránh.

## Hướng dẫn cho agent
1. Ưu tiên INFLOW_LIKELY → FORMING (theo `ranked`).
2. Lấy `stock_universe` mỗi sector → chấm fundamental (tăng trưởng EPS/doanh thu, định giá P/E-P/S, biên LN, FCF, nợ).
3. Tôn trọng `confidence`: HIGH=vào mạnh · MED=thăm dò · LOW=watchlist.
4. BỎ QUA outflow_likely/avoid.
5. Dữ liệu máy đọc đầy đủ: `rotation_forecast_2026-07.json`.
