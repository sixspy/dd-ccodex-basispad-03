window.BasisAPI = (function () {
  const KEY = "basispad_token";
  function token() { return localStorage.getItem(KEY) || ""; }
  function setToken(t) { localStorage.setItem(KEY, t || ""); }
  async function req(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const t = token();
    if (t) headers.Authorization = "Bearer " + t;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { raw: text }; }
    if (!res.ok) {
      const err = new Error((data && (data.detail || data.message)) || res.statusText);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }
  return {
    token, setToken,
    login: (username, password) => req("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
    me: () => req("/api/auth/me"),
    logout: () => req("/api/auth/logout", { method: "POST" }),
    health: () => req("/api/health"),
    summary: () => req("/api/dashboard/summary"),
    instruments: () => req("/api/instruments"),
    sleeves: () => req("/api/sleeves"),
    sleeve: (id) => req("/api/sleeves/" + id),
    tickets: (q) => req("/api/tickets" + (q || "")),
    createTicket: (body) => req("/api/tickets", { method: "POST", body: JSON.stringify(body) }),
    cancelTicket: (id) => req("/api/tickets/" + id + "/cancel", { method: "POST" }),
    match: (body) => req("/api/matcher/match", { method: "POST", body: JSON.stringify(body) }),
    fills: () => req("/api/matcher/fills"),
    fundingSnapshots: () => req("/api/funding/snapshots"),
    fundingLedgers: () => req("/api/funding/ledgers"),
    createFunding: (body) => req("/api/funding/snapshots", { method: "POST", body: JSON.stringify(body) }),
    accrueFunding: (id) => req("/api/funding/snapshots/" + id + "/accrue", { method: "POST" }),
    marks: () => req("/api/marks"),
    mtm: () => req("/api/marks/mtm"),
    upsertMark: (body) => req("/api/marks/upsert", { method: "POST", body: JSON.stringify(body) }),
    marginStates: () => req("/api/margin/states"),
    recomputeMargin: (id) => req("/api/margin/recompute/" + id, { method: "POST" }),
    liquidations: () => req("/api/margin/liquidations"),
    enqueueLiq: (body) => req("/api/margin/liquidations/enqueue", { method: "POST", body: JSON.stringify(body) }),
    executeLiq: (id) => req("/api/margin/liquidations/" + id + "/execute", { method: "POST" }),
    batches: () => req("/api/settle/batches"),
    createBatch: (body) => req("/api/settle/batches", { method: "POST", body: JSON.stringify(body) }),
    lockBatch: (id) => req("/api/settle/batches/" + id + "/lock", { method: "POST" }),
    promoteBatch: (id) => req("/api/settle/batches/" + id + "/promote", { method: "POST" }),
    riskLimits: () => req("/api/risk/limits"),
    riskRequests: () => req("/api/risk/requests"),
    createRiskReq: (body) => req("/api/risk/requests", { method: "POST", body: JSON.stringify(body) }),
    approveRisk: (id) => req("/api/risk/requests/" + id + "/approve", { method: "POST" }),
    wallets: () => req("/api/wallets"),
    walletTxs: () => req("/api/wallets/txs"),
    createWalletTx: (body) => req("/api/wallets/txs", { method: "POST", body: JSON.stringify(body) }),
    timeline: () => req("/api/history/timeline"),
    stubs: () => req("/api/stubs"),
    callStub: (key) => req("/api/stubs/" + key),
  };
})();
