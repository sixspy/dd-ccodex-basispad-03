window.InstrumentsView = {
  props: ["rows"],
  template: `
  <div class="panel">
    <h3>永续标的</h3>
    <table>
      <thead><tr><th>代码</th><th>名称</th><th>类型</th><th>报价</th><th>费率周期(h)</th><th>杠杆上限</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.symbol }}</td><td>{{ r.title }}</td><td>{{ r.kind }}</td>
          <td>{{ r.quote_ccy }}</td><td>{{ r.funding_interval_h }}</td><td>{{ r.max_leverage }}</td>
          <td><span class="tag" :class="r.status==='active'?'ok':''">{{ r.status }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>`
};
