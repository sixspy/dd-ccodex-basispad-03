# 永续纸面基差台（basispad）

**所属领域：其它垂类行业 · 子方向：web3 区块链 量化交易**

全栈产品：永续标的台账 → 策略纸面簿 → 委托与撮合 → 成交回写 → 资金费率计提 → 标记价盯市 → 保证金与强平队列 → 结算封批 → 链上出入金纸面台账 → 风控限额。

## 骨架一句话

量化纸面台按永续标的与策略簿下单撮合，资金费率与标记价同源入账，结算封批与强平队列互锁，链上出入金只记账不直连主网。

## H3 切口候选（写路径互斥 · 须择一）

1. **结算封批**：同事务写入正式结算批次并锁住费率/盯市快照，或只写影子结算草案、升正时原子落正式区（正式区升正前零改）。
2. **强平执行**：同事务立即写正式强平成交并扣减保证金，或影子强平草案确认后原子落正式强平。
3. **资金费率计提**：同事务写正式费率台账行，或影子计提草案升正。

正确性口径只能走甲乙中的一种且两边不得混用。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器：http://localhost:11740

- `admin` / `admin123`（管理员）
- `trader` / `trader123`（交易员）
- `viewer` / `viewer123`（只读）

## 本地开发

```powershell
cd projects/19-basispad
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8040
python -m pytest
python scripts/count_loc.py
```

## 空桩

- 链上预言机桥（`chain_oracle`）
- 中心化所行情桥（`cex_bridge`）

接口固定返回 501，题面可点名。
