window.FillsView = {
  props: ["rows"],
  template: `
  <div class="panel">
    <h3>成交回报</h3>
    <table>
      <thead><tr><th>编码</th><th>委托</th><th>簿</th><th>标的</th><th>方向</th><th>价格</th><th>数量</th><th>手续费</th><th>来源</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td><td>{{ r.ticket_id }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
          <td>{{ r.side }}</td><td>{{ r.price }}</td><td>{{ r.qty }}</td><td>{{ r.fee }}</td><td>{{ r.source }}</td>
        </tr>
      </tbody>
    </table>
  </div>`
};
