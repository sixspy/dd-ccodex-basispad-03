"""SQLite 初始化与种子。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from models import DOMAIN, PRODUCT_NAME, SKELETON, SUB_DIRECTION, USERS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "app.db"
FIXTURES = ROOT / "fixtures"
FRONTEND = ROOT / "frontend"

PRODUCT_META = {
    "name": PRODUCT_NAME,
    "skeleton": SKELETON,
    "domain": DOMAIN,
    "sub": SUB_DIRECTION,
}


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments(
  id INTEGER PRIMARY KEY,
  symbol TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  quote_ccy TEXT NOT NULL,
  base_ccy TEXT NOT NULL,
  tick_size REAL NOT NULL,
  lot_size REAL NOT NULL,
  funding_interval_h INTEGER NOT NULL,
  max_leverage REAL NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sleeves(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,
  base_equity REAL NOT NULL,
  max_gross_exposure REAL NOT NULL,
  created_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tickets(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  price REAL,
  qty REAL NOT NULL,
  filled_qty REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  leverage REAL NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL,
  created_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS fills(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  ticket_id INTEGER REFERENCES tickets(id),
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  side TEXT NOT NULL,
  price REAL NOT NULL,
  qty REAL NOT NULL,
  fee REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  created_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS positions(
  id INTEGER PRIMARY KEY,
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  qty REAL NOT NULL,
  avg_entry REAL NOT NULL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  UNIQUE(sleeve_id, instrument_id)
);
CREATE TABLE IF NOT EXISTS funding_snapshots(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  rate REAL NOT NULL,
  mark_price REAL NOT NULL,
  status TEXT NOT NULL,
  period_start REAL NOT NULL,
  period_end REAL NOT NULL,
  created_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS funding_ledgers(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  snapshot_id INTEGER NOT NULL REFERENCES funding_snapshots(id),
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  position_qty REAL NOT NULL,
  payment REAL NOT NULL,
  status TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mark_prices(
  id INTEGER PRIMARY KEY,
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  mark REAL NOT NULL,
  index_price REAL NOT NULL,
  basis_bps REAL NOT NULL,
  status TEXT NOT NULL,
  as_of REAL NOT NULL,
  UNIQUE(instrument_id)
);
CREATE TABLE IF NOT EXISTS margin_states(
  id INTEGER PRIMARY KEY,
  sleeve_id INTEGER NOT NULL UNIQUE REFERENCES sleeves(id),
  equity REAL NOT NULL,
  used_margin REAL NOT NULL,
  available REAL NOT NULL,
  status TEXT NOT NULL,
  liq_price_hint REAL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS liquidation_queue(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  qty REAL NOT NULL,
  trigger_mark REAL NOT NULL,
  status TEXT NOT NULL,
  created_at REAL NOT NULL,
  executed_at REAL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settle_batches(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  official INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  funding_count INTEGER NOT NULL DEFAULT 0,
  mtm_total REAL NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL,
  created_at REAL NOT NULL,
  locked_at REAL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settle_items(
  id INTEGER PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES settle_batches(id),
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER NOT NULL REFERENCES instruments(id),
  funding_payment REAL NOT NULL DEFAULT 0,
  mtm_pnl REAL NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS risk_limits(
  id INTEGER PRIMARY KEY,
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  instrument_id INTEGER REFERENCES instruments(id),
  max_position REAL NOT NULL,
  max_order_notional REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  UNIQUE(sleeve_id, instrument_id)
);
CREATE TABLE IF NOT EXISTS risk_requests(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  sleeve_id INTEGER NOT NULL REFERENCES sleeves(id),
  action TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  approved_by TEXT,
  created_at REAL NOT NULL,
  decided_at REAL
);
CREATE TABLE IF NOT EXISTS wallets(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  chain TEXT NOT NULL,
  address TEXT NOT NULL,
  balance REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS wallet_txs(
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  wallet_id INTEGER NOT NULL REFERENCES wallets(id),
  kind TEXT NOT NULL,
  amount REAL NOT NULL,
  tx_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  sleeve_id INTEGER REFERENCES sleeves(id),
  created_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_logs(
  id INTEGER PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS write_locks(
  id INTEGER PRIMARY KEY,
  resource TEXT UNIQUE NOT NULL,
  holder TEXT NOT NULL,
  reason TEXT NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  role TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


def _load_json(name: str):
    path = FIXTURES / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _seed(conn: sqlite3.Connection) -> None:
    now = time.time()
    if conn.execute("SELECT COUNT(*) c FROM instruments").fetchone()["c"]:
        return

    for row in _load_json("instruments.json"):
        conn.execute(
            "INSERT INTO instruments(symbol,title,kind,quote_ccy,base_ccy,tick_size,lot_size,"
            "funding_interval_h,max_leverage,status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["symbol"],
                row["title"],
                row["kind"],
                row["quote_ccy"],
                row["base_ccy"],
                row["tick_size"],
                row["lot_size"],
                row["funding_interval_h"],
                row["max_leverage"],
                row["status"],
                row.get("note", ""),
            ),
        )
    for row in _load_json("sleeves.json"):
        conn.execute(
            "INSERT INTO sleeves(code,title,owner,status,base_equity,max_gross_exposure,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["title"],
                row["owner"],
                row["status"],
                row["base_equity"],
                row["max_gross_exposure"],
                row.get("created_at", now),
                row.get("note", ""),
            ),
        )
    for row in _load_json("mark_prices.json"):
        conn.execute(
            "INSERT INTO mark_prices(instrument_id,mark,index_price,basis_bps,status,as_of)"
            " VALUES(?,?,?,?,?,?)",
            (
                row["instrument_id"],
                row["mark"],
                row["index_price"],
                row["basis_bps"],
                row["status"],
                row.get("as_of", now),
            ),
        )
    for row in _load_json("tickets.json"):
        conn.execute(
            "INSERT INTO tickets(code,sleeve_id,instrument_id,side,order_type,price,qty,"
            "filled_qty,status,leverage,created_by,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["sleeve_id"],
                row["instrument_id"],
                row["side"],
                row["order_type"],
                row.get("price"),
                row["qty"],
                row.get("filled_qty", 0),
                row["status"],
                row.get("leverage", 1),
                row["created_by"],
                row.get("created_at", now),
                row.get("note", ""),
            ),
        )
    for row in _load_json("fills.json"):
        conn.execute(
            "INSERT INTO fills(code,ticket_id,sleeve_id,instrument_id,side,price,qty,fee,source,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row.get("ticket_id"),
                row["sleeve_id"],
                row["instrument_id"],
                row["side"],
                row["price"],
                row["qty"],
                row.get("fee", 0),
                row["source"],
                row.get("created_at", now),
                row.get("note", ""),
            ),
        )
    for row in _load_json("positions.json"):
        conn.execute(
            "INSERT INTO positions(sleeve_id,instrument_id,qty,avg_entry,realized_pnl,updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (
                row["sleeve_id"],
                row["instrument_id"],
                row["qty"],
                row["avg_entry"],
                row.get("realized_pnl", 0),
                row.get("updated_at", now),
            ),
        )
    for row in _load_json("funding_snapshots.json"):
        conn.execute(
            "INSERT INTO funding_snapshots(code,instrument_id,rate,mark_price,status,"
            "period_start,period_end,created_at,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["instrument_id"],
                row["rate"],
                row["mark_price"],
                row["status"],
                row["period_start"],
                row["period_end"],
                row.get("created_at", now),
                row.get("note", ""),
            ),
        )
    for row in _load_json("funding_ledgers.json"):
        conn.execute(
            "INSERT INTO funding_ledgers(code,snapshot_id,sleeve_id,instrument_id,position_qty,payment,status,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["snapshot_id"],
                row["sleeve_id"],
                row["instrument_id"],
                row["position_qty"],
                row["payment"],
                row["status"],
                row.get("created_at", now),
            ),
        )
    for row in _load_json("margin_states.json"):
        conn.execute(
            "INSERT INTO margin_states(sleeve_id,equity,used_margin,available,status,liq_price_hint,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                row["sleeve_id"],
                row["equity"],
                row["used_margin"],
                row["available"],
                row["status"],
                row.get("liq_price_hint"),
                row.get("updated_at", now),
            ),
        )
    for row in _load_json("liquidation_queue.json"):
        conn.execute(
            "INSERT INTO liquidation_queue(code,sleeve_id,instrument_id,qty,trigger_mark,status,created_at,executed_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["sleeve_id"],
                row["instrument_id"],
                row["qty"],
                row["trigger_mark"],
                row["status"],
                row.get("created_at", now),
                row.get("executed_at"),
                row.get("note", ""),
            ),
        )
    for row in _load_json("settle_batches.json"):
        conn.execute(
            "INSERT INTO settle_batches(code,title,status,official,version,funding_count,mtm_total,created_by,created_at,locked_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["title"],
                row["status"],
                row.get("official", 0),
                row.get("version", 1),
                row.get("funding_count", 0),
                row.get("mtm_total", 0),
                row["created_by"],
                row.get("created_at", now),
                row.get("locked_at"),
                row.get("note", ""),
            ),
        )
    for row in _load_json("settle_items.json"):
        conn.execute(
            "INSERT INTO settle_items(batch_id,sleeve_id,instrument_id,funding_payment,mtm_pnl,note)"
            " VALUES(?,?,?,?,?,?)",
            (
                row["batch_id"],
                row["sleeve_id"],
                row["instrument_id"],
                row.get("funding_payment", 0),
                row.get("mtm_pnl", 0),
                row.get("note", ""),
            ),
        )
    for row in _load_json("risk_limits.json"):
        conn.execute(
            "INSERT INTO risk_limits(sleeve_id,instrument_id,max_position,max_order_notional,status)"
            " VALUES(?,?,?,?,?)",
            (
                row["sleeve_id"],
                row.get("instrument_id"),
                row["max_position"],
                row["max_order_notional"],
                row.get("status", "active"),
            ),
        )
    for row in _load_json("risk_requests.json"):
        conn.execute(
            "INSERT INTO risk_requests(code,sleeve_id,action,payload_json,status,requested_by,approved_by,created_at,decided_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["sleeve_id"],
                row["action"],
                json.dumps(row.get("payload", {}), ensure_ascii=False),
                row["status"],
                row["requested_by"],
                row.get("approved_by"),
                row.get("created_at", now),
                row.get("decided_at"),
            ),
        )
    for row in _load_json("wallets.json"):
        conn.execute(
            "INSERT INTO wallets(code,title,kind,chain,address,balance,status,note)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["title"],
                row["kind"],
                row["chain"],
                row["address"],
                row.get("balance", 0),
                row["status"],
                row.get("note", ""),
            ),
        )
    for row in _load_json("wallet_txs.json"):
        conn.execute(
            "INSERT INTO wallet_txs(code,wallet_id,kind,amount,tx_hash,status,sleeve_id,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row["code"],
                row["wallet_id"],
                row["kind"],
                row["amount"],
                row.get("tx_hash", ""),
                row["status"],
                row.get("sleeve_id"),
                row.get("created_at", now),
                row.get("note", ""),
            ),
        )
    for row in _load_json("audit_logs.json"):
        conn.execute(
            "INSERT INTO audit_logs(actor,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)",
            (
                row["actor"],
                row["action"],
                row["entity"],
                str(row["entity_id"]),
                row["detail"],
                row.get("created_at", now),
            ),
        )
    conn.commit()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _seed(conn)


def audit(conn: sqlite3.Connection, actor: str, action: str, entity: str, entity_id, detail: str) -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)",
        (actor, action, entity, str(entity_id), detail, time.time()),
    )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
