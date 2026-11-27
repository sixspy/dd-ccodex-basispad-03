window.HistoryView = {
  props: ["events"],
  template: `
  <div class="panel">
    <h3>业务时间线</h3>
    <table>
      <thead><tr><th>类型</th><th>编码</th><th>状态</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="(r,i) in events" :key="i">
          <td>{{ r.kind }}</td><td>{{ r.code }}</td><td>{{ r.status }}</td>
          <td>{{ r.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>`
};
