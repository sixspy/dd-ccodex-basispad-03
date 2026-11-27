window.DashboardView = {
  props: ["summary"],
  template: `
  <div>
    <div class="panel">
      <div class="grid">
        <div class="kpi" v-for="k in cards" :key="k.label">
          <div class="label">{{ k.label }}</div>
          <div class="value">{{ k.value }}</div>
        </div>
      </div>
    </div>
    <div class="panel">
      <h3>产品骨架</h3>
      <p class="meta">量化纸面台按永续标的与策略簿下单撮合，资金费率与标记价同源入账，结算封批与强平队列互锁。</p>
    </div>
  </div>`,
  computed: {
    cards() {
      const s = this.summary || {};
      return [
        { label: "活跃标的", value: s.instruments ?? "-" },
        { label: "活跃策略簿", value: s.active_sleeves ?? "-" },
        { label: "未完成委托", value: s.open_tickets ?? "-" },
        { label: "成交笔数", value: s.fills ?? "-" },
        { label: "强平排队", value: s.queued_liquidations ?? "-" },
        { label: "草稿费率", value: s.draft_funding ?? "-" },
        { label: "锁定结算", value: s.locked_settle_batches ?? "-" },
        { label: "官方结算", value: s.official_settle_batches ?? "-" },
        { label: "钱包余额合计", value: (s.wallet_balance_sum ?? 0).toFixed?.(2) ?? s.wallet_balance_sum },
        { label: "合计未实现盈亏", value: (s.aggregate_upnl ?? 0).toFixed?.(2) ?? s.aggregate_upnl },
      ];
    }
  }
};
