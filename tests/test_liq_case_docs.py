"""结构闸（强平执行案补充）：专文与复现链落盘、红测三文件不合并。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_liq_case_docs_exist():
    spec = ROOT / "docs/费率丙轨专文.md"
    repro = ROOT / "docs/费率复现链起笔.md"
    assert spec.exists() and repro.exists()
    spec_text = spec.read_text(encoding="utf-8")
    repro_text = repro.read_text(encoding="utf-8")
    assert "强平成交" in spec_text and "仓位边" in spec_text
    assert "queued 强平单点执行" in repro_text
    # 甲乙互斥：专文必须写明只走甲、不实现乙
    assert "甲" in spec_text and "乙" in spec_text and "不实现乙" in spec_text


def test_red_tests_are_separate_files():
    names = (
        "tests/feat_liq_fill_write.py",
        "tests/feat_liq_margin_fake.py",
        "tests/feat_liq_race.py",
    )
    for n in names:
        assert (ROOT / n).exists(), n
    contents = [(ROOT / n).read_text(encoding="utf-8") for n in names]
    assert len({c[:200] for c in contents}) == 3


def test_case_label_present():
    repro = (ROOT / "docs/费率复现链起笔.md").read_text(encoding="utf-8")
    assert "强平执行案" in repro
    assert "basispad-03" in repro
