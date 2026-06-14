# RUNBOOK — Thu thập dữ liệu & viết báo cáo vĩ mô Mỹ trong ngày

> File tự chứa cho **bất kỳ AI agent nào** (Claude, ChatGPT, agent khác). Làm đúng 3 bước
> dưới đây là ra báo cáo đạt chuẩn — không cần cơ chế subagent của Claude Code.
> Mọi lệnh chạy từ thư mục gốc dự án. Date format: `YYYY-MM-DD`.

---

## Bước 1 — Thu thập dữ liệu

```bash
source .venv/bin/activate
python scripts/collect.py --date <YYYY-MM-DD>      # thêm --force nếu cần ghi đè
```

Script tự động ghi `data/raw/<date>.json` và **enrich sẵn** (không cần tự tính):
- Mỗi release có: `parsed` (số đã parse), `surprise` (`z_score` + `label`), `vs_previous`, `group`, `is_noise`.
- Block `release_summary`: `surprise_count` (đã dedupe theo nhóm), `groups_present`, `signal_release_count`.
- Block `inflation_context`: CPI/PCE hard-data mới nhất + cờ `hard_data_hot` + `note`.

Xác minh: file tồn tại, có `releases`, `fred_snapshot`, `release_summary`. Nếu `releases` rỗng → ngày không có lịch kinh tế US (vẫn viết báo cáo wrap-up ngắn).

---

## Bước 2 — Viết báo cáo `data/daily/<date>.md`

**Đọc template đầy đủ tại `.claude/agents/macro-analyst.md`** (format breakdown cho từng nhóm: GDP, CPI, NFP, ISM, PPI…). Các quy tắc CỐT LÕI (bắt buộc):

1. **Frontmatter** YAML phải có: `schema_version`, `date`, `surprise_count`, `regime_signal`, `key_takeaway`.
   - `surprise_count` = **copy nguyên** `release_summary.surprise_count` (KHÔNG tự đếm).
   - `regime_signal` ∈ {`neutral`, `dovish`, `hawkish`, `risk-on`, `risk-off`, `rotation-confirmed`, `bounce-relief`, `rotation-broadening`}.

2. **Gộp nhóm**: tất cả release cùng `group` → **1 section duy nhất** có bảng sub-component (vd 5 dòng Michigan = 1 section, KHÔNG tách 5).

3. **Surprise**: đọc `surprise.z_score` + `surprise.label` đã chấm sẵn (đừng tự đánh giá). Tự dịch label (above/below-forecast) sang tốt/xấu theo loại chỉ số (CPI above = xấu; NFP above = tốt; Claims above = dovish).

4. **Nhiễu** (`is_noise=true`: CFTC, rig count, EIA, auctions): chỉ ghi 2-3 dòng, không bảng.

5. **Đối chiếu soft vs hard** — khi `inflation_context.hard_data_hot = true` và ngày chỉ có soft-data (Michigan/confidence/inflation *expectations*): KHÔNG tuyên bố "disinflation xác nhận / dovish hẳn / risk-on bền vững" một chiều. PHẢI có đoạn đối chiếu trích số hard-data (vd Core PCE YoY, CPI YoY) → kết luận "dovish nhẹ/cần xác nhận". Lưu ý mức tuyệt đối (vd Michigan <50 vẫn yếu dù beat).

6. **Section bắt buộc**: `## Tóm tắt`, `## Chi tiết từng chỉ số`, `## Bối cảnh xu hướng`, `## Cảnh báo & catalyst sắp tới`.

7. Tiếng Việt, định lượng, không khuyến nghị mua/bán cổ phiếu cụ thể (chỉ sector). Ghi nguồn (investing.com vs FRED).

---

## Bước 3 — Validate (BẮT BUỘC, lặp đến khi PASS)

```bash
python scripts/validate_report.py <YYYY-MM-DD>
```

- **PASS** (exit 0) → xong.
- **FAIL / có ERROR** → đọc lỗi, sửa báo cáo, chạy lại. KHÔNG nộp khi còn ERROR.
- **WARNING** → nên xử lý (vd cảnh báo soft/hard-data lạc quan một chiều), nhưng không chặn.

Validator kiểm: đủ frontmatter, `surprise_count` khớp raw, `regime_signal` đúng enum, **mọi nhóm signal đều được phân tích**, và giọng điệu dovish có đối chiếu hard-data khi cần.

---

## Tóm tắt 1 dòng cho agent

> `collect.py --date X` → đọc `data/raw/X.json` (đã enrich) → viết `data/daily/X.md` theo `.claude/agents/macro-analyst.md` → `validate_report.py X` đến khi PASS.
