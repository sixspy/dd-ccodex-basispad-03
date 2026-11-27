window.FillsView = {
  props: ["rows"],
  computed: {
    liqRows() { return (this.rows || []).filter((r) => r.source === "liquidation"); },
  },
  template: `
  <div class="panel">
    <h3>成交回报</h3>
    <p class="meta">来源列区分撮合 / 强平 / 结算调整；强平行以备注回指强平编码，与仓位边同事务落账。</p>
    <table>
      <thead><tr><th>编码</th><th>委托</th><th>簿</th><th>标的</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>来源</th><th>备注(强平号)</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id" :class="{liq: r.source==='liquidation'}">
          <td>{{ r.code }}</td><td>{{ r.ticket_id ?? '-' }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
          <td>{{ r.side }}</td><td>{{ r.price }}</td><td>{{ r.qty }}</td><td>{{ r.fee }}</td>
          <td><span class="tag" :class="r.source==='liquidation'?'bad':(r.source==='matcher'?'ok':'warn')">{{ r.source }}</span></td>
          <td>{{ r.note || '-' }}</td>
        </tr>
      </tbody>
    </table>
    <div class="meta">强平成交 {{ liqRows.length }} 笔</div>
  </div>`
};
