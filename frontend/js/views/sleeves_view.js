window.SleevesView = {
  props: ["rows"],
  emits: ["refresh"],
  template: `
  <div class="panel">
    <h3>策略纸面簿</h3>
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>负责人</th><th>权益</th><th>敞口上限</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.code }}</td><td>{{ r.title }}</td><td>{{ r.owner }}</td>
          <td>{{ r.base_equity }}</td><td>{{ r.max_gross_exposure }}</td>
          <td><span class="tag" :class="r.status==='active'?'ok':(r.status==='frozen'?'warn':'')">{{ r.status }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>`
};
