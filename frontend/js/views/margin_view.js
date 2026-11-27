window.MarginView = {
  props: ["states", "liqs", "sleeves", "recon"],
  emits: ["refresh"],
  data() {
    return { form: { sleeve_id: "", instrument_id: "1", qty: "" }, err: "", last: null };
  },
  computed: {
    violations() { return (this.recon && this.recon.violations) || []; },
    liqFillCount() { return (this.recon && this.recon.executed) || 0; },
    statusClass() {
      return (s) => (s === "ok" ? "ok" : s === "warn" ? "warn" : "bad");
    },
  },
  methods: {
    async recompute(id) {
      this.err = "";
      try { await BasisAPI.recomputeMargin(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    },
    async enqueue() {
      this.err = "";
      try {
        await BasisAPI.enqueueLiq({
          sleeve_id: Number(this.form.sleeve_id),
          instrument_id: Number(this.form.instrument_id),
          qty: this.form.qty === "" ? null : Number(this.form.qty),
        });
        this.$emit("refresh");
      } catch (e) { this.err = e.message; }
    },
    async execute(id) {
      this.err = "";
      try {
        const r = await BasisAPI.executeLiq(id);
        this.last = r;
        this.$emit("refresh");
      } catch (e) { this.err = e.message; this.$emit("refresh"); }
    },
  },
  template: `
  <div>
    <div class="panel">
      <h3>保证金状态</h3>
      <p class="meta">状态按正式强平凭据推导：成交 + 仓位边 + 队列三边齐套才显示 liquidated。</p>
      <table>
        <thead><tr><th>簿</th><th>权益</th><th>占用</th><th>可用</th><th>状态</th><th>库内值</th><th>凭据</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in states" :key="r.sleeve_id">
            <td>{{ r.sleeve_id }}</td><td>{{ r.equity }}</td><td>{{ r.used_margin }}</td>
            <td>{{ r.available }}</td>
            <td><span class="tag" :class="statusClass(r.status)">{{ r.status }}</span></td>
            <td>{{ r.status_stored || r.status }}</td>
            <td><span class="tag" :class="r.status_source==='official'?'ok':'bad'">{{ r.status_source || '-' }}</span></td>
            <td><button class="btn secondary" @click="recompute(r.sleeve_id)">重算</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel" v-if="violations.length">
      <h3>强平账实联查 · 违规</h3>
      <table>
        <thead><tr><th>类型</th><th>簿</th><th>强平单</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="(v,i) in violations" :key="i">
            <td><span class="tag bad">{{ v.kind }}</span></td>
            <td>{{ v.sleeve_id }}</td><td>{{ v.liq_id ?? '-' }}</td>
            <td>{{ v.detail || (v.status || '') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>入队强平</h3>
      <div class="form-grid">
        <div><label>策略簿</label>
          <select v-model="form.sleeve_id"><option value="">选择</option>
            <option v-for="s in sleeves" :value="s.id">{{ s.code }}</option></select></div>
        <div><label>标的ID</label><input v-model="form.instrument_id" /></div>
        <div><label>数量(可空=全平)</label><input v-model="form.qty" /></div>
      </div>
      <div class="row"><button class="btn danger" @click="enqueue">入队</button></div>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel">
      <h3>强平队列</h3>
      <p class="meta">执行强平 = 同事务写强平成交 + 回写仓位 + 升状态 + 重算保证金；缺成交整笔回滚，队列保持 queued。</p>
      <table>
        <thead><tr><th>编码</th><th>簿</th><th>标的</th><th>数量</th><th>触发标记</th><th>状态</th><th>成交号</th><th>仓位边余额</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in liqs" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
            <td>{{ r.qty }}</td><td>{{ r.trigger_mark }}</td>
            <td><span class="tag" :class="r.status==='executed'?'ok':'warn'">{{ r.status }}</span></td>
            <td>{{ r.fill_code || '-' }}</td>
            <td>{{ r.remaining_qty === null || r.remaining_qty === undefined ? '-' : r.remaining_qty }}</td>
            <td><button class="btn" v-if="r.status==='queued'" @click="execute(r.id)">执行强平</button></td>
          </tr>
        </tbody>
      </table>
      <div class="meta" v-if="last">
        交班：成交号 {{ last.fill_code }} · 仓位边差额 {{ last.position_delta }} · 剩余 {{ last.remaining_qty }}
      </div>
    </div>
  </div>`
};
