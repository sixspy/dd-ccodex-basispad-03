window.SettleView = {
  props: ["batches"],
  emits: ["refresh"],
  data() { return { title: "日终结算", err: "" }; },
  methods: {
    async create() {
      this.err = "";
      try { await BasisAPI.createBatch({ title: this.title }); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    },
    async lock(id) {
      try { await BasisAPI.lockBatch(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    },
    async promote(id) {
      try { await BasisAPI.promoteBatch(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>新建结算批次</h3>
      <div class="row">
        <input v-model="title" style="max-width:280px" />
        <button class="btn" @click="create">生成草稿</button>
      </div>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel">
      <h3>结算批次</h3>
      <table>
        <thead><tr><th>编码</th><th>标题</th><th>状态</th><th>官方</th><th>费率条数</th><th>MTM合计</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in batches" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.title }}</td><td>{{ r.status }}</td>
            <td>{{ r.official }}</td><td>{{ r.funding_count }}</td><td>{{ r.mtm_total }}</td>
            <td>
              <button class="btn secondary" v-if="r.status==='draft'" @click="lock(r.id)">锁定</button>
              <button class="btn" v-if="r.status==='locked'" @click="promote(r.id)">升正</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
