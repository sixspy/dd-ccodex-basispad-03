window.RiskView = {
  props: ["limits", "requests", "sleeves"],
  emits: ["refresh"],
  data() {
    return { form: { code: "", sleeve_id: "", action: "freeze_sleeve" }, err: "" };
  },
  methods: {
    async submit() {
      this.err = "";
      try {
        await BasisAPI.createRiskReq({
          code: this.form.code,
          sleeve_id: Number(this.form.sleeve_id),
          action: this.form.action,
          payload: {},
        });
        this.$emit("refresh");
      } catch (e) { this.err = e.message; }
    },
    async approve(id) {
      try { await BasisAPI.approveRisk(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>限额</h3>
      <table>
        <thead><tr><th>ID</th><th>簿</th><th>标的</th><th>仓位上限</th><th>单笔名义</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="r in limits" :key="r.id">
            <td>{{ r.id }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
            <td>{{ r.max_position }}</td><td>{{ r.max_order_notional }}</td><td>{{ r.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>风控申请</h3>
      <div class="form-grid">
        <div><label>编码</label><input v-model="form.code" /></div>
        <div><label>策略簿</label>
          <select v-model="form.sleeve_id"><option value="">选择</option>
            <option v-for="s in sleeves" :value="s.id">{{ s.code }}</option></select></div>
        <div><label>动作</label>
          <select v-model="form.action">
            <option>freeze_sleeve</option><option>unfreeze_sleeve</option>
            <option>raise_limit</option><option>cut_limit</option>
          </select></div>
      </div>
      <div class="row"><button class="btn" @click="submit">提交申请</button></div>
      <div class="err" v-if="err">{{ err }}</div>
      <table style="margin-top:14px">
        <thead><tr><th>编码</th><th>簿</th><th>动作</th><th>状态</th><th>申请人</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in requests" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.action }}</td>
            <td>{{ r.status }}</td><td>{{ r.requested_by }}</td>
            <td><button class="btn secondary" v-if="r.status==='pending'" @click="approve(r.id)">批准</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
