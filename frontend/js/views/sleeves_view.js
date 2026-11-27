window.SleevesView = {
  props: ["rows"],
  emits: ["refresh"],
  data() {
    return { open: {}, detail: {}, err: "" };
  },
  methods: {
    async toggle(id) {
      this.err = "";
      if (this.open[id]) {
        const next = { ...this.open };
        delete next[id];
        this.open = next;
        return;
      }
      try {
        const d = await BasisAPI.sleeve(id);
        this.detail = { ...this.detail, [id]: d };
        this.open = { ...this.open, [id]: true };
      } catch (e) { this.err = e.message; }
    },
  },
  template: `
  <div>
    <div class="panel">
      <h3>策略纸面簿</h3>
      <p class="meta">点开簿可见仓位边与保证金占用；强平后占用随仓位边即时重算，不留旧名义。</p>
      <table>
        <thead><tr><th>编码</th><th>名称</th><th>负责人</th><th>权益</th><th>敞口上限</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <template v-for="r in rows" :key="r.id">
            <tr>
              <td>{{ r.code }}</td><td>{{ r.title }}</td><td>{{ r.owner }}</td>
              <td>{{ r.base_equity }}</td><td>{{ r.max_gross_exposure }}</td>
              <td><span class="tag" :class="r.status==='active'?'ok':(r.status==='frozen'?'warn':'')">{{ r.status }}</span></td>
              <td><button class="btn secondary" @click="toggle(r.id)">{{ open[r.id] ? '收起' : '展开' }}</button></td>
            </tr>
            <tr v-if="open[r.id] && detail[r.id]">
              <td colspan="7">
                <div class="meta">
                  保证金：占用 {{ detail[r.id].margin ? detail[r.id].margin.used_margin : '-' }}
                  · 可用 {{ detail[r.id].margin ? detail[r.id].margin.available : '-' }}
                  · 状态 {{ detail[r.id].margin ? detail[r.id].margin.status : '-' }}
                </div>
                <table>
                  <thead><tr><th>标的</th><th>仓位边</th><th>均价</th><th>已实现</th></tr></thead>
                  <tbody>
                    <tr v-for="p in detail[r.id].positions" :key="p.id">
                      <td>{{ p.instrument_id }}</td><td>{{ p.qty }}</td>
                      <td>{{ p.avg_entry }}</td><td>{{ p.realized_pnl }}</td>
                    </tr>
                    <tr v-if="!detail[r.id].positions.length"><td colspan="4" class="meta">无仓位</td></tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
  </div>`
};
