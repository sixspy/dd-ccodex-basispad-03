window.FundingView = {
  props: ["snapshots", "ledgers", "instruments"],
  emits: ["refresh"],
  data() {
    return { form: { code: "", instrument_id: "", rate: "0.0001", mark_price: "", period_start: "", period_end: "" }, err: "" };
  },
  methods: {
    async create() {
      this.err = "";
      try {
        const now = Date.now() / 1000;
        await BasisAPI.createFunding({
          code: this.form.code,
          instrument_id: Number(this.form.instrument_id),
          rate: Number(this.form.rate),
          mark_price: this.form.mark_price === "" ? null : Number(this.form.mark_price),
          period_start: Number(this.form.period_start || now - 28800),
          period_end: Number(this.form.period_end || now),
        });
        this.$emit("refresh");
      } catch (e) { this.err = e.message; }
    },
    async accrue(id) {
      try { await BasisAPI.accrueFunding(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>新建资金费率快照</h3>
      <div class="form-grid">
        <div><label>编码</label><input v-model="form.code" /></div>
        <div><label>标的</label>
          <select v-model="form.instrument_id"><option value="">选择</option>
            <option v-for="i in instruments" :value="i.id">{{ i.symbol }}</option></select></div>
        <div><label>费率</label><input v-model="form.rate" /></div>
        <div><label>标记价(可空)</label><input v-model="form.mark_price" /></div>
      </div>
      <div class="row"><button class="btn" @click="create">创建草稿快照</button></div>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel">
      <h3>费率快照</h3>
      <table>
        <thead><tr><th>编码</th><th>标的</th><th>费率</th><th>标记价</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in snapshots" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.instrument_id }}</td><td>{{ r.rate }}</td><td>{{ r.mark_price }}</td>
            <td>{{ r.status }}</td>
            <td><button class="btn secondary" v-if="r.status==='draft'" @click="accrue(r.id)">正式计提</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>费率台账</h3>
      <table>
        <thead><tr><th>编码</th><th>快照</th><th>簿</th><th>仓位</th><th>支付</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="r in ledgers" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.snapshot_id }}</td><td>{{ r.sleeve_id }}</td>
            <td>{{ r.position_qty }}</td><td>{{ r.payment }}</td><td>{{ r.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
