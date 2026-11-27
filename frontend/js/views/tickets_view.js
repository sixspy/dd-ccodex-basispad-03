window.TicketsView = {
  props: ["rows", "instruments", "sleeves"],
  emits: ["refresh"],
  data() {
    return { form: { code: "", sleeve_id: "", instrument_id: "", side: "buy", order_type: "limit", price: "", qty: "", leverage: 5 }, err: "" };
  },
  methods: {
    async submit() {
      this.err = "";
      try {
        const body = {
          code: this.form.code,
          sleeve_id: Number(this.form.sleeve_id),
          instrument_id: Number(this.form.instrument_id),
          side: this.form.side,
          order_type: this.form.order_type,
          price: this.form.price === "" ? null : Number(this.form.price),
          qty: Number(this.form.qty),
          leverage: Number(this.form.leverage),
        };
        await BasisAPI.createTicket(body);
        this.$emit("refresh");
      } catch (e) { this.err = e.message; }
    },
    async cancel(id) {
      try { await BasisAPI.cancelTicket(id); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    },
    async match(id) {
      try { await BasisAPI.match({ ticket_id: id }); this.$emit("refresh"); }
      catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>新建委托</h3>
      <div class="form-grid">
        <div><label>编码</label><input v-model="form.code" /></div>
        <div><label>策略簿</label>
          <select v-model="form.sleeve_id"><option value="">选择</option>
            <option v-for="s in sleeves" :value="s.id">{{ s.code }}</option></select></div>
        <div><label>标的</label>
          <select v-model="form.instrument_id"><option value="">选择</option>
            <option v-for="i in instruments" :value="i.id">{{ i.symbol }}</option></select></div>
        <div><label>方向</label><select v-model="form.side"><option>buy</option><option>sell</option></select></div>
        <div><label>类型</label><select v-model="form.order_type"><option>limit</option><option>market</option></select></div>
        <div><label>价格</label><input v-model="form.price" /></div>
        <div><label>数量</label><input v-model="form.qty" /></div>
        <div><label>杠杆</label><input v-model="form.leverage" /></div>
      </div>
      <div class="row"><button class="btn" @click="submit">提交委托</button></div>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel">
      <h3>委托列表</h3>
      <table>
        <thead><tr><th>编码</th><th>簿</th><th>标的</th><th>方向</th><th>价格</th><th>数量</th><th>已成</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.sleeve_id }}</td><td>{{ r.instrument_id }}</td>
            <td>{{ r.side }}</td><td>{{ r.price }}</td><td>{{ r.qty }}</td><td>{{ r.filled_qty }}</td>
            <td>{{ r.status }}</td>
            <td>
              <button class="btn secondary" v-if="r.status==='open'||r.status==='partial'" @click="match(r.id)">撮合</button>
              <button class="btn danger" v-if="r.status==='open'||r.status==='partial'" @click="cancel(r.id)">撤单</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
