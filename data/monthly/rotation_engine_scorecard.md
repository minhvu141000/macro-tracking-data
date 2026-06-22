# Rotation Engine Scorecard — 2026-06-21

Backtest tự kiểm của engine: điểm `rotation_score` tại ngày D có dự báo đúng forward RS (vs SPY) 5–10 phiên sau không? Cửa sổ history: **17 phiên** (trong đó **4 phiên dữ liệu THẬT**, còn lại backfill — độ tin tăng dần khi chạy `/daily-macro` mỗi ngày).

| Horizon | Hit rate hướng | Edge (top3−bot3 fwd RS) | Bull avg fwd | Bear avg fwd | n chấm |
|---|---|---|---|---|---|
| 5 phiên | 42.0% | -1.55% | -0.32% | +1.17% | 88 |
| 10 phiên | 41.9% | -1.56% | +1.16% | +2.47% | 62 |

> **Edge** = trung bình mỗi ngày: (forward RS của 3 sector điểm cao nhất) − (3 sector thấp nhất). Dương = thứ hạng engine có giá trị. **Hit rate** = trong các call có hướng rõ (|score|>0.3), tỷ lệ forward RS đúng hướng (ngưỡng ±0.5%).
> ⚠️ Mẫu còn nhỏ + phần lớn backfill → đọc như tín hiệu sơ bộ, không phải kết luận. Chạy daily đều để mẫu lớn dần.

---
