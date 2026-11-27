window.WalletsView = {
  props: ["wallets", "txs"],
  emits: ["refresh"],
  data() {
    return { form: { code: "", wallet_id: "", kind: "deposit", amount: "", sleeve_id: "" }, err: "" };
  },
  methods: {
    async submit() {
      this.err = "";
      try {
        await BasisAPI.createWalletTx({
          code: this.form.code,
          wallet_id: Number(this.form.wallet_id),
          kind: this.form.kind,
          amount: Number(this.form.amount),
          sleeve_id: this.form.sleeve_id === "" ? null : Number(this.form.sleeve_id),
          tx_hash: "paper-" + Date.now(),
        });
        this.$emit("refresh");
      } catch (e) { this.err = e.message; }
    }
  },
  template: `
  <div>
    <div class="panel">
      <h3>钱包台账</h3>
      <table>
        <thead><tr><th>编码</th><th>名称</th><th>类型</th><th>链</th><th>地址</th><th>余额</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="r in wallets" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.title }}</td><td>{{ r.kind }}</td>
            <td>{{ r.chain }}</td><td>{{ r.address }}</td><td>{{ r.balance }}</td><td>{{ r.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>记一笔出入金</h3>
      <div class="form-grid">
        <div><label>编码</label><input v-model="form.code" /></div>
        <div><label>钱包</label>
          <select v-model="form.wallet_id"><option value="">选择</option>
            <option v-for="w in wallets" :value="w.id">{{ w.code }}</option></select></div>
        <div><label>类型</label>
          <select v-model="form.kind"><option>deposit</option><option>withdraw</option><option>internal_transfer</option></select></div>
        <div><label>金额</label><input v-model="form.amount" /></div>
        <div><label>关联策略簿ID</label><input v-model="form.sleeve_id" /></div>
      </div>
      <div class="row"><button class="btn" @click="submit">过账</button></div>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel">
      <h3>出入金流水</h3>
      <table>
        <thead><tr><th>编码</th><th>钱包</th><th>类型</th><th>金额</th><th>哈希</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="r in txs" :key="r.id">
            <td>{{ r.code }}</td><td>{{ r.wallet_id }}</td><td>{{ r.kind }}</td>
            <td>{{ r.amount }}</td><td>{{ r.tx_hash }}</td><td>{{ r.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
