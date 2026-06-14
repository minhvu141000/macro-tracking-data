#!/usr/bin/env python3
"""Validate a daily macro report against the raw data + structural rules.

Deterministic guardrail: any agent (or the user) runs this AFTER writing a
report to catch the failure modes a weak/external LLM tends to produce —
missing sections, wrong surprise_count, un-analyzed release groups, made-up
numbers, invalid regime enum.

    python scripts/validate_report.py 2026-06-12
    python scripts/validate_report.py            # validates the latest report

Exit code 0 = pass, 1 = fail (errors printed). Warnings never fail the build.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DAILY_DIR = ROOT / "data" / "daily"

REQUIRED_FRONTMATTER = ["date", "surprise_count", "regime_signal", "key_takeaway"]
VALID_REGIMES = {
    "neutral", "dovish", "hawkish", "risk-on", "risk-off",
    "rotation-confirmed", "bounce-relief", "rotation-broadening",
}
REQUIRED_SECTIONS = ["Tóm tắt", "Chi tiết", "Bối cảnh", "Cảnh báo"]

# Human-readable label per group → what the analyst section title likely contains.
GROUP_KEYWORDS: dict[str, list[str]] = {
    "jobs_report": ["nfp", "payroll", "jobs", "việc làm", "lao động"],
    "jobless_claims": ["claims", "thất nghiệp", "trợ cấp"],
    "cpi": ["cpi"],
    "ppi": ["ppi"],
    "pce_inflation": ["pce"],
    "michigan_sentiment": ["michigan"],
    "gdp": ["gdp"],
    "ism_manufacturing": ["ism manufacturing", "ism mfg", "ism sản xuất"],
    "ism_services": ["ism services", "ism svc", "ism dịch vụ", "non-manufacturing"],
    "spglobal_pmi": ["s&p global", "pmi"],
    "retail_sales": ["retail", "bán lẻ"],
    "durable_goods": ["durable", "factory orders", "hàng bền", "đơn hàng"],
    "industrial_production": ["industrial production", "sản xuất công nghiệp"],
    "income_spending": ["personal income", "personal spending", "thu nhập", "chi tiêu"],
    "confidence": ["confidence", "sentiment", "niềm tin", "nfib", "optimism"],
    "housing_starts": ["housing starts", "building permits", "khởi công"],
    "home_sales": ["home sales", "doanh số nhà"],
    "home_prices": ["home price", "case-shiller", "giá nhà"],
    "trade": ["trade", "exports", "imports", "thương mại", "xuất khẩu", "nhập khẩu"],
    "jolts": ["jolts", "job openings"],
    "adp": ["adp"],
    "challenger": ["challenger"],
    "vehicle_sales": ["vehicle", "car sales", "doanh số xe"],
    "construction": ["construction", "xây dựng"],
    "regional_fed": ["richmond", "dallas", "chicago", "philadelphia", "empire", "kansas"],
}


def parse_report(path: Path) -> tuple[dict[str, Any], str]:
    """Split YAML-ish frontmatter from body. Lightweight (no yaml dep)."""
    text = path.read_text()
    fm: dict[str, Any] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        block, body = m.group(1), m.group(2)
        for line in block.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


def validate(date_str: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    raw_path = RAW_DIR / f"{date_str}.json"
    report_path = DAILY_DIR / f"{date_str}.md"

    if not report_path.exists():
        return [f"Report not found: {report_path}"], []
    if not raw_path.exists():
        warnings.append(f"Raw data not found ({raw_path}) — skipping cross-checks")
        raw = {}
    else:
        raw = json.loads(raw_path.read_text())

    fm, body = parse_report(report_path)
    body_low = body.lower()

    # 1. Frontmatter completeness
    for field in REQUIRED_FRONTMATTER:
        if field not in fm or not str(fm[field]).strip():
            errors.append(f"Frontmatter thiếu field bắt buộc: '{field}'")

    # 2. regime_signal enum
    regime = fm.get("regime_signal", "")
    if regime and regime not in VALID_REGIMES:
        errors.append(
            f"regime_signal '{regime}' không hợp lệ. Phải thuộc: {sorted(VALID_REGIMES)}"
        )

    # 3. Required sections
    for sec in REQUIRED_SECTIONS:
        if sec.lower() not in body_low:
            warnings.append(f"Thiếu section gợi ý: '{sec}'")

    summary = raw.get("release_summary", {})

    # 4. surprise_count matches deterministic count
    if summary and "surprise_count" in fm:
        try:
            report_sc = int(str(fm["surprise_count"]).strip())
            true_sc = int(summary.get("surprise_count", 0))
            if report_sc != true_sc:
                errors.append(
                    f"surprise_count={report_sc} sai — raw data tính được {true_sc} "
                    f"(nhóm surprise: {summary.get('surprised_groups')})"
                )
        except ValueError:
            errors.append(f"surprise_count '{fm.get('surprise_count')}' không phải số")

    # 5. Every SIGNAL group must be analyzed (noise groups exempt)
    if raw:
        signal_groups = [g for g in summary.get("groups_present", [])]
        for group in signal_groups:
            kws = GROUP_KEYWORDS.get(group, [group.replace("_", " ")])
            if not any(kw in body_low for kw in kws):
                errors.append(
                    f"Nhóm chỉ số '{group}' có trong raw data nhưng KHÔNG được "
                    f"phân tích trong báo cáo (tìm keyword: {kws[:3]})"
                )

    # 6. Soft-data optimism vs hot hard-data (analytical guardrail → WARNING)
    infl = raw.get("inflation_context") or {}
    if infl.get("hard_data_hot"):
        optimistic = [
            "disinflation", "dovish", "risk-on bền", "risk-on bền vững",
            "hạ cánh mềm", "soft landing", "soft-landing", "goldilocks",
            "lạm phát đang thực sự hạ nhiệt", "lạm phát thực sự hạ nhiệt",
        ]
        reconcile = [
            "hard-data", "hard data", "soft-data", "soft data", "mâu thuẫn",
            "chưa xác nhận", "vẫn nóng", "vẫn cao", "core pce", "đối chiếu",
        ]
        hit_opt = [w for w in optimistic if w in body_low]
        if hit_opt and not any(w in body_low for w in reconcile):
            warnings.append(
                "Báo cáo dùng giọng lạc quan/dovish ("
                f"'{hit_opt[0]}') NHƯNG hard-data lạm phát còn nóng "
                f"(Core PCE YoY {infl.get('core_pce_yoy')}%, CPI YoY {infl.get('cpi_yoy')}%) "
                "và KHÔNG đối chiếu soft-data vs hard-data. Cân nhắc thêm caveat."
            )

    # 7. No-data day sanity
    if raw and summary.get("signal_release_count", 0) == 0:
        if "không có" not in body_low and "no " not in body_low:
            warnings.append(
                "Ngày không có release signal nào — báo cáo nên ghi rõ '(không có chỉ số US)'"
            )

    # 8. Length sanity
    if len(body.strip()) < 300:
        warnings.append("Báo cáo rất ngắn (<300 ký tự) — có thể thiếu nội dung")

    return errors, warnings


def main() -> int:
    args = sys.argv[1:]
    if args:
        date_str = args[0]
    else:
        reports = sorted(DAILY_DIR.glob("*.md"))
        if not reports:
            print("Không tìm thấy report nào trong data/daily/")
            return 1
        date_str = reports[-1].stem

    print(f"Validating report: {date_str}\n")
    errors, warnings = validate(date_str)

    for w in warnings:
        print(f"  ⚠️  WARNING: {w}")
    for e in errors:
        print(f"  ❌ ERROR:   {e}")

    print()
    if errors:
        print(f"FAIL — {len(errors)} lỗi, {len(warnings)} cảnh báo")
        return 1
    print(f"PASS — 0 lỗi, {len(warnings)} cảnh báo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
