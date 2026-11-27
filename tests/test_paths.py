"""结构闸：模块数、多页、seed、领域字样。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_domain():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "其它垂类行业" in text
    assert "web3 区块链 量化交易" in text
    assert "docker compose up" in text


def test_backend_modules():
    svcs = list((ROOT / "backend").glob("*_svc.py"))
    assert len(svcs) >= 5


def test_frontend_views():
    views = list((ROOT / "frontend" / "js" / "views").glob("*_view.js"))
    assert len(views) >= 3


def test_fixtures_exist():
    assert (ROOT / "fixtures" / "instruments.json").exists()
    assert (ROOT / "fixtures" / "sleeves.json").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / "Dockerfile").exists()
