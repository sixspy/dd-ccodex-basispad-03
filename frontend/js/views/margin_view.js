window.MarginView = {
  props: ["states", "liqs", "sleeves"],
  emits: ["refresh"],
  data() {
    return { form: { sleeve_id: "", instrument_id: "1", qty: "" }, err: "" };
  },
  methods: {
    async recompute(id) {
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
      try { await BasisAPI.executeLiq(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>保证金状态</h3>
      <table>
        <thead><tr><th>簿</th><th>权益</th><th>占用</th><th>可用</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in states" :key="r.sleeve_id">
            <td>{{ r.sleeve_id }}</td><td>{{ r.equity }}</td><td>{{ r.used_margin }}</td>
            <td>{{ r.available }}</td>
            <td><span class="tag" :class="r.status==='ok'?'ok':(r.status==='warn'?'warn':'bad')">{{ r.status }}</span></td>
            <td><button class="btn secondary" @click="recompute(r.sleeve_id)">重算</button></td>
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
      <table>
        <thead><tr><th>编码</th><th>簿</th><th>标的</th><th>数量</th><th>触发标记</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in liqs" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
            <td>{{ r.qty }}</td><td>{{ r.trigger_mark }}</td><td>{{ r.status }}</td>
            <td><button class="btn" v-if="r.status==='queued'" @click="execute(r.id)">执行强平</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
