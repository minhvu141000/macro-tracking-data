# Rotation Engine Scorecard — 2026-06-27

Backtest tự kiểm của engine: điểm `rotation_score` tại ngày D có dự báo đúng forward RS (vs SPY) 5–10 phiên sau không? Cửa sổ history: **21 phiên** (trong đó **8 phiên dữ liệu THẬT**, còn lại backfill — độ tin tăng dần khi chạy `/daily-macro` mỗi ngày).

| Horizon | Hit rate hướng | Edge (top3−bot3 fwd RS) | Bull avg fwd | Bear avg fwd | n chấm |
|---|---|---|---|---|---|
| 5 phiên | 42.5% | -1.20% | -0.13% | +1.10% | 106 |
| 10 phiên | 43.8% | -0.50% | +1.08% | +1.68% | 89 |

> **Edge** = trung bình mỗi ngày: (forward RS của 3 sector điểm cao nhất) − (3 sector thấp nhất). Dương = thứ hạng engine có giá trị. **Hit rate** = trong các call có hướng rõ (|score|>0.3), tỷ lệ forward RS đúng hướng (ngưỡng ±0.5%).
> ⚠️ Mẫu còn nhỏ + phần lớn backfill → đọc như tín hiệu sơ bộ, không phải kết luận. Chạy daily đều để mẫu lớn dần.

---
