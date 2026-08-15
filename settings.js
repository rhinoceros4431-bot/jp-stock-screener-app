const formEl = document.getElementById("settings-form");

function toggleField(id, label, checked) {
  return `
    <div class="field-row">
      <label for="${id}">${label}</label>
      <label class="toggle">
        <input type="checkbox" id="${id}" ${checked ? "checked" : ""} />
        <span class="slider"></span>
      </label>
    </div>`;
}

function numberField(id, label, value, step = "1") {
  return `
    <div class="field-row">
      <label for="${id}">${label}</label>
      <input type="number" id="${id}" value="${value}" step="${step}" />
    </div>`;
}

function selectField(id, label, value, options) {
  const opts = options
    .map((o) => `<option value="${o.value}" ${o.value === value ? "selected" : ""}>${o.label}</option>`)
    .join("");
  return `
    <div class="field-row">
      <label for="${id}">${label}</label>
      <select id="${id}">${opts}</select>
    </div>`;
}

// シグナル別の通知ON/OFF設定に使うカテゴリ一覧(バックエンドのCATEGORY_PRIORITYと対応)
const NOTIFY_CATEGORY_OPTIONS = [
  { key: "oversold", label: "売られすぎ" },
  { key: "overbought", label: "買われすぎ" },
  { key: "golden_cross", label: "ゴールデンクロス" },
  { key: "dead_cross", label: "デッドクロス" },
  { key: "breakout", label: "値幅ブレイク" },
  { key: "volume_surge", label: "出来高急増" },
];

function render(cfg) {
  formEl.innerHTML = `
    <div class="settings-section">
      <h2>ゴールデンクロス / デッドクロス</h2>
      <p class="desc">短期移動平均線が長期移動平均線を上抜け(ゴールデン)・下抜け(デッド)したら通知</p>
      ${toggleField("gdc_enabled", "この条件を有効にする", cfg.golden_dead_cross.enabled)}
      ${numberField("gdc_short", "短期移動平均(日)", cfg.golden_dead_cross.short_window)}
      ${numberField("gdc_long", "長期移動平均(日)", cfg.golden_dead_cross.long_window)}
      ${toggleField("gdc_golden", "ゴールデンクロスを通知", cfg.golden_dead_cross.notify_golden)}
      ${toggleField("gdc_dead", "デッドクロスを通知", cfg.golden_dead_cross.notify_dead)}
    </div>

    <div class="settings-section">
      <h2>RSI・ストキャスティクス(過熱感)</h2>
      <p class="desc">売られすぎ・買われすぎのタイミングを通知</p>
      ${toggleField("ov_enabled", "この条件を有効にする", cfg.overheat_indicators.enabled)}
      ${toggleField("rsi_enabled", "RSIを使う", cfg.overheat_indicators.rsi.enabled)}
      ${numberField("rsi_period", "RSI期間(日)", cfg.overheat_indicators.rsi.period)}
      ${numberField("rsi_oversold", "売られすぎ閾値(以下)", cfg.overheat_indicators.rsi.oversold)}
      ${numberField("rsi_overbought", "買われすぎ閾値(以上)", cfg.overheat_indicators.rsi.overbought)}
      ${toggleField("stoch_enabled", "ストキャスティクスを使う", cfg.overheat_indicators.stochastic.enabled)}
      ${numberField("stoch_k", "%K期間(日)", cfg.overheat_indicators.stochastic.k_period)}
      ${numberField("stoch_d", "%D期間(日)", cfg.overheat_indicators.stochastic.d_period)}
      ${numberField("stoch_oversold", "売られすぎ閾値(以下)", cfg.overheat_indicators.stochastic.oversold)}
      ${numberField("stoch_overbought", "買われすぎ閾値(以上)", cfg.overheat_indicators.stochastic.overbought)}
    </div>

    <div class="settings-section">
      <h2>出来高急増・ブレイクアウト</h2>
      <p class="desc">出来高が急に増えた銘柄や、直近の高値・安値を更新した銘柄を通知</p>
      ${toggleField("vb_enabled", "この条件を有効にする", cfg.volume_breakout.enabled)}
      ${toggleField("vs_enabled", "出来高急増を使う", cfg.volume_breakout.volume_surge.enabled)}
      ${numberField("vs_lookback", "平均算出期間(日)", cfg.volume_breakout.volume_surge.lookback_days)}
      ${numberField("vs_multiple", "急増と判定する倍率", cfg.volume_breakout.volume_surge.surge_multiple, "0.1")}
      ${toggleField("pb_enabled", "ブレイクアウトを使う", cfg.volume_breakout.price_breakout.enabled)}
      ${numberField("pb_lookback", "判定期間(日)", cfg.volume_breakout.price_breakout.lookback_days)}
      ${selectField("pb_type", "対象", cfg.volume_breakout.price_breakout.breakout_type, [
        { value: "both", label: "高値・安値どちらも" },
        { value: "high", label: "高値更新のみ" },
        { value: "low", label: "安値更新のみ" },
      ])}
    </div>

    <div class="settings-section">
      <h2>ボリンジャーバンド</h2>
      <p class="desc">株価が指定したσ(シグマ)を超えて逸脱したら通知</p>
      ${toggleField("bb_enabled", "この条件を有効にする", cfg.bollinger_band.enabled)}
      ${numberField("bb_window", "算出期間(日)", cfg.bollinger_band.window)}
      ${numberField("bb_sigma", "シグマ(σ)", cfg.bollinger_band.sigma, "0.1")}
    </div>

    <div class="settings-section">
      <h2>後場での急落</h2>
      <p class="desc">※要 J-Quantsプレミアムプラン(ザラ場データが必要)。未契約の場合はオフのままにしてください</p>
      ${toggleField("ad_enabled", "この条件を有効にする", cfg.afternoon_drop.enabled)}
      ${numberField("ad_threshold", "下落率の閾値(%、マイナス値)", cfg.afternoon_drop.drop_threshold_pct, "0.1")}
    </div>

    <div class="settings-section">
      <h2>通知するシグナル</h2>
      <p class="desc">オフにしたカテゴリは一覧画面には表示されますが、プッシュ通知は送られません</p>
      ${NOTIFY_CATEGORY_OPTIONS.map((o) =>
        toggleField(
          `notify_${o.key}`,
          o.label,
          (cfg.notification.notify_categories || []).includes(o.key)
        )
      ).join("")}
    </div>

    <div class="settings-section">
      <h2>その他</h2>
      ${numberField("min_vol", "最低平均出来高(これ未満は除外)", cfg.min_avg_volume)}
      ${numberField("max_items", "1通あたりの最大通知件数", cfg.notification.max_items_per_message)}
      ${toggleField("quiet", "該当銘柄が無いときは通知しない", cfg.notification.quiet_if_no_match)}
    </div>

    <div class="save-bar">
      <button id="save-btn">保存する</button>
      <span id="save-status"></span>
    </div>
  `;

  document.getElementById("save-btn").addEventListener("click", () => save(cfg));
}

function val(id) {
  return document.getElementById(id).value;
}
function checked(id) {
  return document.getElementById(id).checked;
}

async function save(original) {
  const statusEl = document.getElementById("save-status");
  const cfg = JSON.parse(JSON.stringify(original)); // deep clone, preserves fields not shown in the form (data_source, target_marketsなど)

  cfg.golden_dead_cross.enabled = checked("gdc_enabled");
  cfg.golden_dead_cross.short_window = Number(val("gdc_short"));
  cfg.golden_dead_cross.long_window = Number(val("gdc_long"));
  cfg.golden_dead_cross.notify_golden = checked("gdc_golden");
  cfg.golden_dead_cross.notify_dead = checked("gdc_dead");

  cfg.overheat_indicators.enabled = checked("ov_enabled");
  cfg.overheat_indicators.rsi.enabled = checked("rsi_enabled");
  cfg.overheat_indicators.rsi.period = Number(val("rsi_period"));
  cfg.overheat_indicators.rsi.oversold = Number(val("rsi_oversold"));
  cfg.overheat_indicators.rsi.overbought = Number(val("rsi_overbought"));
  cfg.overheat_indicators.stochastic.enabled = checked("stoch_enabled");
  cfg.overheat_indicators.stochastic.k_period = Number(val("stoch_k"));
  cfg.overheat_indicators.stochastic.d_period = Number(val("stoch_d"));
  cfg.overheat_indicators.stochastic.oversold = Number(val("stoch_oversold"));
  cfg.overheat_indicators.stochastic.overbought = Number(val("stoch_overbought"));

  cfg.volume_breakout.enabled = checked("vb_enabled");
  cfg.volume_breakout.volume_surge.enabled = checked("vs_enabled");
  cfg.volume_breakout.volume_surge.lookback_days = Number(val("vs_lookback"));
  cfg.volume_breakout.volume_surge.surge_multiple = Number(val("vs_multiple"));
  cfg.volume_breakout.price_breakout.enabled = checked("pb_enabled");
  cfg.volume_breakout.price_breakout.lookback_days = Number(val("pb_lookback"));
  cfg.volume_breakout.price_breakout.breakout_type = val("pb_type");

  cfg.bollinger_band.enabled = checked("bb_enabled");
  cfg.bollinger_band.window = Number(val("bb_window"));
  cfg.bollinger_band.sigma = Number(val("bb_sigma"));

  cfg.afternoon_drop.enabled = checked("ad_enabled");
  cfg.afternoon_drop.drop_threshold_pct = Number(val("ad_threshold"));

  cfg.min_avg_volume = Number(val("min_vol"));
  cfg.notification.max_items_per_message = Number(val("max_items"));
  cfg.notification.quiet_if_no_match = checked("quiet");
  cfg.notification.notify_categories = NOTIFY_CATEGORY_OPTIONS
    .filter((o) => checked(`notify_${o.key}`))
    .map((o) => o.key);

  statusEl.textContent = "保存中...";
  try {
    const resp = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (!resp.ok) throw new Error("保存に失敗しました");
    statusEl.textContent = "保存しました(次回のスクリーニングから反映されます)";
  } catch (e) {
    statusEl.textContent = "エラー: " + e.message;
  }
}

async function init() {
  try {
    const cfg = await fetch("/api/config").then((r) => r.json());
    render(cfg);
  } catch (e) {
    formEl.innerHTML = `<div class="empty-state">設定の読み込みに失敗しました: ${e.message}</div>`;
  }
}

init();
