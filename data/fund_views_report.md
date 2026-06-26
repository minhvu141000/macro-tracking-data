# Đồng thuận phân bổ ngành — các quỹ lớn Mỹ

_Tổng hợp: 2026-06-25 · 4 nguồn · tầng đối chiếu (KHÔNG trộn vào rotation engine)_

> **Neo đối chiếu:** DỰ BÁO rotation tháng tới `2026-07` (forward, từ build_monthly_rotation.py) — khớp câu hỏi 'nhóm nào nhận tiền quý tới'.

> **Regime engine:** Tăng trưởng vượt kỳ vọng, lạm phát nguội hơn kỳ vọng, lãi suất đi ngang, risk-on. Chu kỳ: đường cong normal.

> ⚠️ **Báo cáo cũ (>100d):** Goldman Sachs (2025-11-18, 219d) — cần làm mới.

## Nguồn

| Quỹ | Báo cáo | Ngày | Tuổi | Verify | Phủ |
|---|---|---|---|---|---|
| J.P. Morgan | Mid-Year Outlook 2026 — Promise and Pressure | 2026-06-15 | 10d | ✓ | partial |
| Goldman Sachs | 2026 Equity Outlook — Tech Tonic: a Broadening Bull Market (+ 2026 themes) | 2025-11-18 | 219d | ✓ | partial |
| State Street SPDR | Sector Market Perspectives — Q2 2026 | 2026-04-08 | 78d | ✓ | full |
| Morningstar | US Stock Market Outlook — Where to Find Value (mid-June 2026) | 2026-06-15 | 10d | ✓ | partial |

## Bảng đồng thuận (xếp theo net score)

| Ngành | Đồng thuận | Net | #OW | #UW | Dự báo engine | Đối chiếu |
|---|---|---:|---:|---:|---|---|
| XLK Technology | Mạnh OW | +1.00 | 4 | 0 | INFLOW_LIKELY | ✅ KHỚP |
| XLE Energy | Mạnh OW | +1.00 | 2 | 0 | AVOID | ⚠️ LỆCH |
| XLU Utilities | Mạnh OW | +1.00 | 2 | 0 | OUTFLOW_LIKELY | ⚠️ LỆCH |
| XLC Communication Services | Mạnh OW | +1.00 | 1 | 0 | FORMING | ✅ KHỚP |
| XLF Financials | Mạnh OW | +0.75 | 3 | 0 | INFLOW_LIKELY | ✅ KHỚP |
| XLV Healthcare | Mạnh OW | +0.67 | 2 | 0 | AVOID | ⚠️ LỆCH |
| XLI Industrials | OW | +0.33 | 2 | 1 | INFLOW_LIKELY | ✅ KHỚP |
| XLB Materials | Trái chiều | +0.00 | 1 | 1 | NEUTRAL | ◐ một phần |
| XLRE Real Estate | Trái chiều | +0.00 | 1 | 1 | NEUTRAL | ◐ một phần |
| XLP Consumer Staples | Mạnh UW | -1.00 | 0 | 2 | NEUTRAL | ◐ một phần |
| XLY Consumer Discretionary | Mạnh UW | -1.00 | 0 | 1 | INFLOW_LIKELY | ⚠️ LỆCH |

## ⚠️ Điểm LỆCH (quỹ ≠ dự báo engine) — soi kỹ

- **XLE Energy**: quỹ Mạnh OW (net +1.00) nhưng dự báo engine `AVOID`.
- **XLU Utilities**: quỹ Mạnh OW (net +1.00) nhưng dự báo engine `OUTFLOW_LIKELY`.
- **XLV Healthcare**: quỹ Mạnh OW (net +0.67) nhưng dự báo engine `AVOID`. _(gồm lăng kính định giá Morningstar — lệch momentum là tension bình thường)_
- **XLY Consumer Discretionary**: quỹ Mạnh UW (net -1.00) nhưng dự báo engine `INFLOW_LIKELY`.

## Chi tiết view từng quỹ

### XLK — Technology  ·  Mạnh OW (net +1.00)
- ▲ **J.P. Morgan** (Overweight) — Tỷ trọng lớn nhất; AI broadening, EPS mạnh
- ▲ **Goldman Sachs** (Overweight) — AI infra (memory, connectors, data center)
- ▲ **State Street SPDR** (Positive) — AI-driven earnings rộng + định giá hấp dẫn sau nhịp chỉnh
- ▲ **Morningstar** _[định giá]_ (Undervalued -11%) — Rẻ nhất so với fair value

### XLE — Energy  ·  Mạnh OW (net +1.00)
- ▲ **Goldman Sachs** (Overweight) — Hưởng lợi deregulation
- ▲ **State Street SPDR** (Positive) — Rủi ro gián đoạn nguồn cung kéo dài, premium địa chính trị

### XLU — Utilities  ·  Mạnh OW (net +1.00)
- ▲ **J.P. Morgan** (Overweight) — High-conviction 'power' — nhu cầu điện
- ▲ **State Street SPDR** (Positive) — Nhu cầu điện AI, điện khí hoá, reshoring

### XLC — Communication Services  ·  Mạnh OW (net +1.00)
- ▲ **State Street SPDR** (Positive) — Quảng cáo số tăng tốc + AI monetization

### XLF — Financials  ·  Mạnh OW (net +0.75)
- ▲ **J.P. Morgan** (Overweight) — Tỷ trọng lớn + kỳ vọng lợi nhuận tốt
- ▲ **Goldman Sachs** (Overweight) — Hưởng lợi deregulation
- ■ **State Street SPDR** (Neutral) — Trì hoãn cắt lãi suất bù trừ định giá cải thiện
- ▲ **Morningstar** _[định giá]_ (Undervalued -5%) — Discount so với fair value

### XLV — Healthcare  ·  Mạnh OW (net +0.67)
- ▲ **Goldman Sachs** (Overweight) — GLP-1/obesity, cardiology renaissance
- ■ **State Street SPDR** (Neutral) — Tăng trưởng lợi nhuận chậm, ít catalyst dù định giá rẻ
- ▲ **Morningstar** _[định giá]_ (Undervalued -7%) — Medical devices/diagnostics (DHR, MDT, ABT)

### XLI — Industrials  ·  OW (net +0.33)
- ▲ **J.P. Morgan** (Overweight) — Theme 'power'/AI infra bổ trợ Tech
- ▲ **State Street SPDR** (Positive) — CapEx AI infra, quốc phòng, chính sách tài khoá pro-CapEx
- ▼ **Morningstar** _[định giá]_ (Overvalued +8%) — Tăng ~17% YTD nhờ AI-buildout

### XLB — Materials  ·  Trái chiều (net +0.00)
- ▲ **State Street SPDR** (Positive) — Cân bằng cung-cầu hoá chất, nhu cầu kim loại cấu trúc
- ▼ **Morningstar** _[định giá]_ (Overvalued +12%) — Đã tăng ~14% YTD

### XLRE — Real Estate  ·  Trái chiều (net +0.00)
- ▼ **State Street SPDR** (Negative) — Momentum lợi nhuận yếu + giảm kỳ vọng cắt lãi suất
- ▲ **Morningstar** _[định giá]_ (Undervalued -5%) — Discount so với fair value

### XLP — Consumer Staples  ·  Mạnh UW (net -1.00)
- ▼ **State Street SPDR** (Negative) — Áp lực biên lợi nhuận, tăng trưởng yếu
- ▼ **Morningstar** _[định giá]_ (Overvalued +19%) — Đắt nhất (WMT/COST 1-sao kéo)

### XLY — Consumer Discretionary  ·  Mạnh UW (net -1.00)
- ▼ **State Street SPDR** (Negative) — Thu nhập thực yếu, tiết kiệm thấp ép cầu

---
_Nguồn dữ liệu thô: `data/fund_views_latest.json`. Cập nhật mỗi quý qua nghiên cứu web rồi chạy `python scripts/build_fund_consensus.py`._