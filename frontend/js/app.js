const { createApp, ref, computed, onMounted } = Vue;

createApp({
  components: {
    DashboardView, InstrumentsView, SleevesView, TicketsView, FillsView,
    FundingView, MarksView, MarginView, SettleView, RiskView, WalletsView,
    HistoryView, StubsView,
  },
  setup() {
    const user = ref(null);
    const page = ref("dashboard");
    const loginForm = ref({ username: "trader", password: "trader123" });
    const loginErr = ref("");
    const summary = ref({});
    const instruments = ref([]);
    const sleeves = ref([]);
    const tickets = ref([]);
    const fills = ref([]);
    const fundingSnapshots = ref([]);
    const fundingLedgers = ref([]);
    const marks = ref([]);
    const mtm = ref([]);
    const marginStates = ref([]);
    const liqs = ref([]);
    const batches = ref([]);
    const riskLimits = ref([]);
    const riskRequests = ref([]);
    const wallets = ref([]);
    const walletTxs = ref([]);
    const events = ref([]);
    const stubs = ref([]);
    const health = ref({});

    const title = computed(() => ({
      dashboard: "总览",
      instruments: "永续标的",
      sleeves: "策略纸面簿",
      tickets: "委托撮合",
      fills: "成交回报",
      funding: "资金费率",
      marks: "标记价盯市",
      margin: "保证金强平",
      settle: "结算封批",
      risk: "风控限额",
      wallets: "链上出入金",
      history: "时间线",
      stubs: "空桩",
    })[page.value] || "");

    async function refresh() {
      if (!BasisAPI.token()) return;
      const tasks = [
        BasisAPI.summary().then((d) => (summary.value = d)),
        BasisAPI.instruments().then((d) => (instruments.value = d)),
        BasisAPI.sleeves().then((d) => (sleeves.value = d)),
        BasisAPI.tickets().then((d) => (tickets.value = d)),
        BasisAPI.fills().then((d) => (fills.value = d)),
        BasisAPI.fundingSnapshots().then((d) => (fundingSnapshots.value = d)),
        BasisAPI.fundingLedgers().then((d) => (fundingLedgers.value = d)),
        BasisAPI.marks().then((d) => (marks.value = d)),
        BasisAPI.mtm().then((d) => (mtm.value = d)),
        BasisAPI.marginStates().then((d) => (marginStates.value = d)),
        BasisAPI.liquidations().then((d) => (liqs.value = d)),
        BasisAPI.batches().then((d) => (batches.value = d)),
        BasisAPI.riskLimits().then((d) => (riskLimits.value = d)),
        BasisAPI.riskRequests().then((d) => (riskRequests.value = d)),
        BasisAPI.wallets().then((d) => (wallets.value = d)),
        BasisAPI.walletTxs().then((d) => (walletTxs.value = d)),
        BasisAPI.timeline().then((d) => (events.value = d)),
        BasisAPI.stubs().then((d) => (stubs.value = d)),
        BasisAPI.health().then((d) => (health.value = d)),
      ];
      await Promise.all(tasks);
    }

    async function doLogin() {
      loginErr.value = "";
      try {
        const d = await BasisAPI.login(loginForm.value.username, loginForm.value.password);
        BasisAPI.setToken(d.token);
        user.value = d;
        await refresh();
      } catch (e) {
        loginErr.value = e.message || "登录失败";
      }
    }

    async function doLogout() {
      try { await BasisAPI.logout(); } catch (e) {}
      BasisAPI.setToken("");
      user.value = null;
    }

    onMounted(async () => {
      if (BasisAPI.token()) {
        try {
          user.value = await BasisAPI.me();
          await refresh();
        } catch (e) {
          BasisAPI.setToken("");
        }
      }
    });

    return {
      user, page, loginForm, loginErr, title, summary, instruments, sleeves, tickets, fills,
      fundingSnapshots, fundingLedgers, marks, mtm, marginStates, liqs, batches,
      riskLimits, riskRequests, wallets, walletTxs, events, stubs, health,
      refresh, doLogin, doLogout,
    };
  },
  template: `
  <div v-if="!user" class="login-wrap">
    <div class="login-card">
      <h2>永续纸面基差台</h2>
      <p>其它垂类行业 · web3 区块链 量化交易</p>
      <label>用户名</label>
      <input v-model="loginForm.username" />
      <label>密码</label>
      <input type="password" v-model="loginForm.password" @keyup.enter="doLogin" />
      <div class="row"><button class="btn" @click="doLogin">登录</button></div>
      <div class="err" v-if="loginErr">{{ loginErr }}</div>
    </div>
  </div>
  <div v-else class="layout">
    <aside class="side">
      <div class="brand">BASISPAD<small>{{ health.domain }} · {{ health.sub_direction }}</small></div>
      <nav class="nav">
        <button :class="{active: page==='dashboard'}" @click="page='dashboard'">总览</button>
        <button :class="{active: page==='instruments'}" @click="page='instruments'">永续标的</button>
        <button :class="{active: page==='sleeves'}" @click="page='sleeves'">策略纸面簿</button>
        <button :class="{active: page==='tickets'}" @click="page='tickets'">委托撮合</button>
        <button :class="{active: page==='fills'}" @click="page='fills'">成交回报</button>
        <button :class="{active: page==='funding'}" @click="page='funding'">资金费率</button>
        <button :class="{active: page==='marks'}" @click="page='marks'">标记价盯市</button>
        <button :class="{active: page==='margin'}" @click="page='margin'">保证金强平</button>
        <button :class="{active: page==='settle'}" @click="page='settle'">结算封批</button>
        <button :class="{active: page==='risk'}" @click="page='risk'">风控限额</button>
        <button :class="{active: page==='wallets'}" @click="page='wallets'">链上出入金</button>
        <button :class="{active: page==='history'}" @click="page='history'">时间线</button>
        <button :class="{active: page==='stubs'}" @click="page='stubs'">空桩</button>
      </nav>
    </aside>
    <main class="main">
      <div class="topbar">
        <div>
          <h1>{{ title }}</h1>
          <div class="meta">{{ user.display || user.username }} · {{ user.role }}</div>
        </div>
        <div class="row">
          <button class="btn secondary" @click="refresh">刷新</button>
          <button class="btn secondary" @click="doLogout">退出</button>
        </div>
      </div>
      <DashboardView v-if="page==='dashboard'" :summary="summary" />
      <InstrumentsView v-else-if="page==='instruments'" :rows="instruments" />
      <SleevesView v-else-if="page==='sleeves'" :rows="sleeves" @refresh="refresh" />
      <TicketsView v-else-if="page==='tickets'" :rows="tickets" :instruments="instruments" :sleeves="sleeves" @refresh="refresh" />
      <FillsView v-else-if="page==='fills'" :rows="fills" />
      <FundingView v-else-if="page==='funding'" :snapshots="fundingSnapshots" :ledgers="fundingLedgers" :instruments="instruments" @refresh="refresh" />
      <MarksView v-else-if="page==='marks'" :rows="marks" :mtm="mtm" :instruments="instruments" @refresh="refresh" />
      <MarginView v-else-if="page==='margin'" :states="marginStates" :liqs="liqs" :sleeves="sleeves" @refresh="refresh" />
      <SettleView v-else-if="page==='settle'" :batches="batches" @refresh="refresh" />
      <RiskView v-else-if="page==='risk'" :limits="riskLimits" :requests="riskRequests" :sleeves="sleeves" @refresh="refresh" />
      <WalletsView v-else-if="page==='wallets'" :wallets="wallets" :txs="walletTxs" @refresh="refresh" />
      <HistoryView v-else-if="page==='history'" :events="events" />
      <StubsView v-else-if="page==='stubs'" :stubs="stubs" />
    </main>
  </div>`
}).mount("#app");
