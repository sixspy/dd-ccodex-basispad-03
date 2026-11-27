window.StubsView = {
  props: ["stubs"],
  data() { return { msg: "" }; },
  methods: {
    async ping(key) {
      try {
        await BasisAPI.callStub(key);
        this.msg = key + " 意外成功";
      } catch (e) {
        this.msg = key + " → " + (e.status || "") + " " + (e.message || "");
      }
    }
  },
  template: `
  <div class="panel">
    <h3>空桩</h3>
    <p class="meta">链上预言机与 CEX 行情桥固定 501，供题面点名实现。</p>
    <div class="row" style="margin-bottom:12px">
      <button class="btn secondary" v-for="s in stubs" :key="s.key" @click="ping(s.key)">探测 {{ s.title }}</button>
    </div>
    <div class="err" v-if="msg">{{ msg }}</div>
    <table>
      <thead><tr><th>键</th><th>标题</th><th>路径</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="s in stubs" :key="s.key">
          <td>{{ s.key }}</td><td>{{ s.title }}</td><td>{{ s.path }}</td><td>{{ s.status }}</td>
        </tr>
      </tbody>
    </table>
  </div>`
};
