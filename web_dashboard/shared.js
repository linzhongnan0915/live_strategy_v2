const PATHS = {
  liveStatus: ["../output/live_polling_status.json", "snapshots/live_polling_status.json"],
  market: ["../output/openbb_market_monitor_snapshot.json", "snapshots/openbb_market_monitor_snapshot.json"],
  watchlist: ["../output/openbb_overnight_watchlist.json", "snapshots/openbb_overnight_watchlist.json"],
  news: ["../output/news_risk_snapshot.json", "snapshots/news_risk_snapshot.json"],
  macro: ["../output/macro_context_snapshot.json", "snapshots/macro_context_snapshot.json"],
  metrics: ["../output/openbb_metrics_snapshot.json", "snapshots/openbb_metrics_snapshot.json"],
  ranking: ["../output/strategy_ranking_snapshot.json", "snapshots/strategy_ranking_snapshot.json"],
  backtest: ["../output/strategy_backtest_snapshot.json", "snapshots/strategy_backtest_snapshot.json"],
  wfo: ["../output/strategy_walk_forward_snapshot.json", "snapshots/strategy_walk_forward_snapshot.json"],
  dailyReview: ["../output/daily_strategy_review_snapshot.json", "snapshots/daily_strategy_review_snapshot.json"],
  simulation: ["../output/portfolio_strategy_simulation_snapshot.json", "snapshots/portfolio_strategy_simulation_snapshot.json"],
  factorRisk: ["../output/factor_risk_snapshot.json", "snapshots/factor_risk_snapshot.json"],
  strategyLibrary: ["../data/config/strategy_library.csv", "snapshots/strategy_library.csv"]
};

async function loadJson(path, fallback = {}) {
  const paths = Array.isArray(path) ? path : [path];
  let lastError = "";
  for (const candidate of paths) {
    try {
      const response = await fetch(`${candidate}?t=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) {
        lastError = response.statusText;
        continue;
      }
      const payload = await response.json();
      if (candidate.includes("/snapshots/")) {
        payload.snapshot_fallback_used = true;
      }
      return payload;
    } catch (error) {
      lastError = String(error);
    }
  }
  return { ...fallback, status: "missing", error: lastError || "all paths failed" };
}

async function loadCsv(path) {
  const paths = Array.isArray(path) ? path : [path];
  for (const candidate of paths) {
    try {
      const response = await fetch(`${candidate}?t=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) continue;
      return parseCsv(await response.text());
    } catch {
      // Try the next source.
    }
  }
  return [];
}

function parseCsv(text) {
  const lines = String(text ?? "").trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const parseLine = line => {
    const out = [];
    let current = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = !quoted;
      } else if (ch === "," && !quoted) {
        out.push(current);
        current = "";
      } else {
        current += ch;
      }
    }
    out.push(current);
    return out;
  };
  const headers = parseLine(lines[0]);
  return lines.slice(1).map(line => {
    const values = parseLine(line);
    const row = {};
    headers.forEach((header, i) => {
      row[header] = values[i] ?? "";
    });
    return row;
  });
}

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const node = byId(id);
  if (node) node.textContent = value ?? "N/A";
}

function fmtNum(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  return n.toFixed(digits);
}

function fmtPct(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  return `${n.toFixed(digits)}%`;
}

function fmtTime(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 19);
  return date.toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }) + " ET";
}

function fmtDateTimeET(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `${String(value).slice(0, 19)} UTC`;
  return date.toLocaleString("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short"
  });
}

function fmtUnit(value, unit) {
  if (value === undefined || value === null || value === "N/A") return "N/A";
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  return `${n}${unit}`;
}

function signedClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "pos" : "neg";
}

function signalClass(level) {
  const v = String(level ?? "").toLowerCase();
  if (v === "red" || v === "urgent" || v === "failed") return "neg";
  if (v === "yellow" || v === "watch" || v === "warning" || v === "starting") return "warn";
  if (v === "green" || v === "success" || v === "info") return "pos";
  return "";
}

function timingLabel(value) {
  const v = String(value ?? "").toLowerCase();
  if (v === "newer_than_official_eod") return "Live";
  if (v === "official_eod_aligned") return "EOD";
  if (v === "stale_vs_official_eod") return "Stale";
  if (!v || v === "undefined" || v === "null") return "N/A";
  return value;
}

function timingTooltip(value) {
  const v = String(value ?? "").toLowerCase();
  if (v === "newer_than_official_eod") return "Latest observation is newer than the official EOD anchor; live monitor context only.";
  if (v === "official_eod_aligned") return "Latest observation matches the official EOD anchor.";
  if (v === "stale_vs_official_eod") return "Latest observation is older than the official EOD anchor; verify data freshness.";
  return "Timing status from market monitor.";
}

function scoreBadge(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return `<span class="score-badge low">N/A</span>`;
  const cls = n >= 0.65 ? "high" : n >= 0.45 ? "mid" : "low";
  return `<span class="score-badge ${cls}">${fmtNum(n, 3)}</span>`;
}

function rankBadge(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return `<span class="rank-badge low">N/A</span>`;
  const cls = n <= 3 ? "top" : n <= 8 ? "watch" : "low";
  return `<span class="rank-badge ${cls}">#${n}</span>`;
}

function evidenceBadge(value, kind = "positive") {
  const n = Number(value);
  if (!Number.isFinite(n)) return `<span class="evidence-badge watch">N/A</span>`;
  let cls = "watch";
  if (kind === "drawdown") {
    cls = n <= -0.18 ? "risk" : n <= -0.1 ? "watch" : "good";
  } else if (n >= 0.65) {
    cls = "good";
  } else if (n < 0.4) {
    cls = "risk";
  }
  return `<span class="evidence-badge ${cls}">${kind === "drawdown" ? fmtPct(n * 100) : fmtPct(n * 100)}</span>`;
}

function statusPill(value) {
  const v = String(value ?? "unknown").toLowerCase();
  let cls = "yellow";
  if (["success", "green", "normal", "ok", "info"].includes(v)) cls = "green";
  if (["failed", "red", "urgent", "error", "invalid"].includes(v)) cls = "red";
  if (v.includes("maintain")) cls = "green";
  if (v.includes("candidate")) cls = "yellow";
  if (v.includes("risk review")) cls = "red";
  return `<span class="pill ${cls}">${escapeHtml(value ?? "unknown")}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderTable(id, rows, columns, limit = 100) {
  const target = byId(id);
  if (!target) return;
  if (!rows || rows.length === 0) {
    target.innerHTML = `<div class="small">No rows available.</div>`;
    return;
  }
  const body = rows.slice(0, limit).map((row, index) => {
    const cells = columns.map(col => {
      const raw = typeof col.value === "function" ? col.value(row, index) : row[col.key];
      const html = col.html ? raw : escapeHtml(raw);
      return `<td>${html}</td>`;
    }).join("");
    const rowTitle = row.tooltip ?? row._tooltip ?? "";
    return `<tr title="${escapeHtml(rowTitle)}">${cells}</tr>`;
  }).join("");
  const head = columns.map(col => `<th>${escapeHtml(col.label)}</th>`).join("");
  target.innerHTML = `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function newsTimeLabel(row, news) {
  const original = row.timestamp ?? row.published_at;
  if (original) return fmtTime(original);
  const fallback = row.generated_at_utc ?? news?.generated_at_utc;
  return fallback ? `${fmtTime(fallback)} feed` : "time N/A";
}

function renderNewsCards(id, rows, news, limit = 8) {
  const target = byId(id);
  if (!target) return;
  const data = (rows ?? []).slice(0, limit);
  if (data.length === 0) {
    target.innerHTML = `<div class="small">No news in this bucket.</div>`;
    return;
  }
  target.innerHTML = `<div class="news-card-list">` + data.map(row => {
    const level = row.warning_level ?? row.watch_level ?? "info";
    const affected = [
      (row.affected_tickers ?? []).slice(0, 4).join(", "),
      (row.affected_strategies ?? []).slice(0, 2).join(", ")
    ].filter(Boolean).join(" | ") || row.exposure || "context only";
    const keywords = (row.keywords ?? row.topics ?? []).slice(0, 4).join(", ") || "no keywords";
    const managerRead = row.explanation ?? row.reasoning ?? "No direct portfolio or strategy linkage.";
    return `
      <article class="news-card ${escapeHtml(level)}">
        <div class="news-card-head">
          ${statusPill(level)}
          <span>${escapeHtml(newsTimeLabel(row, news))}</span>
          <span>${escapeHtml(row.source ?? "source N/A")}</span>
          <strong>${fmtNum(row.severity, 1)}</strong>
        </div>
        <div class="news-headline">${escapeHtml(row.title ?? "Untitled headline")}</div>
        <div class="news-meta"><strong>Keywords:</strong> ${escapeHtml(keywords)}</div>
        <div class="news-meta"><strong>Impact:</strong> ${escapeHtml(affected)}</div>
        <div class="news-read">${escapeHtml(managerRead)}</div>
      </article>
    `;
  }).join("") + `</div>`;
}

function renderList(id, items) {
  const target = byId(id);
  if (!target) return;
  const rows = (items ?? []).filter(Boolean);
  if (rows.length === 0) {
    target.innerHTML = "<li>No decision details available.</li>";
    return;
  }
  target.innerHTML = rows.map(item => `<li>${escapeHtml(item)}</li>`).join("");
}

function groupAverage(rows, groupKey, valueKey) {
  const map = new Map();
  for (const row of rows) {
    if (row.asset_class === "monitor_only") continue;
    const key = row[groupKey] ?? "unknown";
    const value = Number(row[valueKey]);
    if (!Number.isFinite(value)) continue;
    const current = map.get(key) ?? { name: key, sum: 0, count: 0 };
    current.sum += value;
    current.count += 1;
    map.set(key, current);
  }
  return Array.from(map.values())
    .map(item => ({ name: item.name, value: item.sum / item.count }))
    .sort((a, b) => b.value - a.value);
}

function monitorRows(rows) {
  return rows.filter(row => row.asset_class === "monitor_only" || Number(row.target_weight ?? 0) === 0);
}

function investableRows(rows) {
  return rows.filter(row => row.asset_class !== "monitor_only" && Number(row.target_weight ?? 0) > 0);
}

function marketConfirmationCount(market) {
  const items = market.items ?? [];
  const find = ticker => items.find(x => x.ticker === ticker) ?? {};
  let count = 0;
  if (Number(find("SPY").latest_return_pct) <= -0.75) count += 1;
  if (Number(find("HYG").latest_return_pct) - Number(find("LQD").latest_return_pct) <= -0.3) count += 1;
  if (Number(find("VIX").latest_close) >= 20) count += 1;
  if (Number(find("GLD").latest_return_pct) >= 1 || Number(find("USO").latest_return_pct) >= 1.5) count += 1;
  return count;
}

function deriveNewsImpact(news, market) {
  const items = news.items ?? [];
  const severity = Math.max(Number(news.max_severity ?? 0), ...items.map(item => Number(item.severity ?? 0)), 0);
  const affected = Array.from(new Set([
    ...(news.affected_strategies ?? []),
    ...items.flatMap(item => item.affected_strategies ?? [])
  ]));
  const rows = items.map(item => classifyNewsItem(item, market));
  const reviewCount = rows.filter(item => item.requires_human_review || item.warning_level === "warning" || item.warning_level === "urgent").length;
  const confirmations = marketConfirmationCount(market);
  const itemConfirmations = rows.reduce((sum, item) => sum + (item.market_confirmations ?? []).length, 0);
  const linkedCount = rows.filter(item => (item.affected_strategies ?? []).length > 0 || (item.affected_tickers ?? []).length > 0).length;
  const urgentCount = rows.filter(item => item.warning_level === "urgent").length;
  const warningCount = rows.filter(item => item.warning_level === "warning").length;
  let level = "green";
  let reason = "No material market-relevant news impact.";
  if (urgentCount > 0) {
    level = "red";
    reason = "At least one severe headline is mapped to portfolio/strategy exposure and confirmed by market moves.";
  } else if (warningCount > 0) {
    level = "yellow";
    reason = "Portfolio-relevant news has market confirmation; prepare human review.";
  } else if (severity >= 8 && linkedCount === 0) {
    level = "yellow";
    reason = "High raw severity, but no strategy linkage or market confirmation; cap at watch.";
  } else if (severity >= 5 || linkedCount > 0) {
    level = "yellow";
    reason = "Relevant news is on watch, but not independently decisive without stronger market confirmation.";
  }
  return { severity, affected, reviewCount, confirmations: Math.max(confirmations, itemConfirmations), level, reason };
}

function uniqueNewsItems(items) {
  const seen = new Set();
  const out = [];
  for (const item of items ?? []) {
    const key = `${String(item.title ?? "").toLowerCase()}|${String(item.source ?? "").toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function topicCounts(items) {
  const counts = new Map();
  for (const item of items ?? []) {
    for (const topic of item.topics ?? []) {
      const key = String(topic || "unknown").toLowerCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

function classifyNewsItem(item, market) {
  const topics = (item.topics ?? []).map(x => String(x).toLowerCase());
  const affected = item.affected_strategies ?? [];
  const affectedTickers = item.affected_tickers ?? [];
  const affectedAssetClass = item.affected_asset_class ?? [];
  const severity = Number(item.severity ?? 0);
  const itemConfirmations = Array.isArray(item.market_confirmations) ? item.market_confirmations : [];
  const confirmations = Math.max(marketConfirmationCount(market), itemConfirmations.length);
  const portfolioTopics = [
    "oil", "inflation", "rates", "credit", "liquidity", "usd", "geopolitical",
    "war", "tariffs", "bank-crisis", "fed-rates", "technology", "macro"
  ];
  const isPortfolioTopic = topics.some(topic => portfolioTopics.includes(topic));
  const isCrypto = topics.includes("crypto") || /bitcoin|btc|crypto/i.test(`${item.title ?? ""} ${item.summary ?? ""}`);
  const isPoliticsOnly = topics.includes("politics") || topics.includes("election");

  let exposure = item.portfolio_impact ?? "context only";
  let decision = "monitor only";
  let explanation = item.reasoning ?? "No direct ETF sleeve or strategy mapping.";
  if (affected.length > 0) {
    exposure = "strategy-linked";
    decision = item.warning_level === "urgent" || item.warning_level === "warning" ? "human review" : "watch";
    explanation = item.reasoning ?? `Mapped to ${affected.length} strategy sleeve(s).`;
  } else if (affectedTickers.length > 0 || affectedAssetClass.length > 0) {
    exposure = "portfolio-relevant";
    decision = item.warning_level === "urgent" || item.warning_level === "warning" ? "human review" : "watch";
    explanation = item.reasoning ?? "Mapped to ETF or asset-class exposure.";
  } else if (isPortfolioTopic) {
    exposure = "portfolio-theme";
    decision = confirmations >= 2 ? "human review" : "watch";
    explanation = "Relevant macro/factor topic, but no strategy link in the current mapping.";
  } else if (isCrypto) {
    exposure = "crypto spillover";
    decision = confirmations >= 2 ? "watch for spillover" : "context only";
    explanation = "Crypto-specific headline; portfolio has no direct crypto ETF sleeve, so require cross-market confirmation.";
  } else if (isPoliticsOnly) {
    exposure = "political context";
    decision = confirmations >= 2 ? "watch for spillover" : "context only";
    explanation = "Political headline without direct macro/sector/ETF linkage.";
  }
  const warningLevel = item.warning_level ?? (decision === "human review" ? "warning" : decision === "context only" ? "info" : "watch");
  return {
    exposure,
    decision,
    explanation,
    confirmations,
    warning_level: warningLevel,
    keywords: item.keywords ?? topics.slice(0, 6),
    affected_tickers: affectedTickers,
    affected_asset_class: affectedAssetClass,
    confidence: item.confidence ?? Math.min(0.88, 0.35 + severity / 14),
    requires_human_review: Boolean(item.requires_human_review || warningLevel === "warning" || warningLevel === "urgent"),
    market_confirmations: itemConfirmations
  };
}

function buildNewsTriage(news, market) {
  const items = uniqueNewsItems(news.items ?? []);
  const impact = deriveNewsImpact({ ...news, items }, market);
  const topics = topicCounts(items);
  const topTopics = topics.slice(0, 4).map(row => `${row.name} (${row.count})`).join(", ") || "none";
  const linked = items.filter(item => (item.affected_strategies ?? []).length > 0);
  const urgent = items.filter(item => item.requires_human_review || item.watch_level === "urgent_review");
  const crypto = items.filter(item => classifyNewsItem(item, market).exposure === "crypto spillover").length;
  const contextOnly = items.filter(item => classifyNewsItem(item, market).decision === "context only").length;
  let conclusion = "News is monitoring context only.";
  if (linked.length > 0 && impact.confirmations >= 1) {
    conclusion = "News has strategy linkage and market confirmation; prepare human review.";
  } else if (linked.length > 0) {
    conclusion = "News maps to strategy sleeves but lacks market confirmation; keep on watch.";
  } else if (impact.confirmations >= 2) {
    conclusion = "No direct strategy link, but cross-market confirmation is rising; watch for spillover.";
  } else if (crypto > 0 || contextOnly > 0) {
    conclusion = "Feed is mostly context-only relative to current ETF portfolio; do not escalate without cross-market confirmation.";
  }
  return {
    ...impact,
    unique_count: items.length,
    top_topics: topTopics,
    linked_count: linked.length,
    urgent_count: urgent.length,
    context_only_count: contextOnly,
    conclusion,
    manager_action: impact.level === "red"
      ? "Escalate only if strategy link or multi-market confirmation is present."
      : "Monitor headlines; require ETF/factor linkage before changing strategy posture.",
    rows: items.map(item => ({ ...item, ...classifyNewsItem(item, market) }))
  };
}

function renderBars(id, rows, maxRows = 12) {
  const target = byId(id);
  if (!target) return;
  if (!rows || rows.length === 0) {
    target.innerHTML = `<div class="small">No data.</div>`;
    return;
  }
  const max = Math.max(...rows.map(r => Math.abs(Number(r.value) || 0)), 0.01);
  target.innerHTML = rows.slice(0, maxRows).map(row => {
    const value = Number(row.value) || 0;
    const width = Math.min(100, Math.abs(value) / max * 100);
    const sign = value < 0 ? "negative" : "positive";
    const title = row.tooltip ?? `${row.name}: ${fmtPct(value)}`;
    return `
      <div class="bar-row" title="${escapeHtml(title)}">
        <div>${escapeHtml(row.name)}</div>
        <div class="bar-track"><div class="bar ${sign}" style="width:${width}%"></div></div>
        <div class="${signedClass(value)}">${fmtPct(value)}</div>
      </div>
    `;
  }).join("");
}

const MARKET_PULSE_TICKERS = [
  ["SPX", "S&P 500"],
  ["NASDAQ", "Nasdaq"],
  ["DOW", "Dow"],
  ["IWM", "Small Cap"],
  ["VIX", "VIX"],
  ["GOLD", "Gold futures"],
  ["OIL", "WTI crude"],
  ["DXY", "US Dollar Index"],
  ["EURUSD", "EUR/USD"],
  ["US10Y", "US 10Y yield"]
];

function buildMarketPulseRows(market) {
  const rows = market.items ?? [];
  const byTicker = new Map(rows.map(row => [row.ticker, row]));
  return MARKET_PULSE_TICKERS.map(([ticker, label]) => {
    const row = byTicker.get(ticker) ?? {};
    const hasData = Number.isFinite(Number(row.latest_close));
    return {
      ticker,
      label,
      close: row.latest_close,
      ret: row.latest_return_pct,
      date: row.latest_date,
      timing: row.timing_status,
      hasData,
      source: row.source ?? market.data_mode,
      _tooltip: hasData
        ? `${ticker}: ${label}. ${timingLabel(row.timing_status)} ${row.latest_date ?? ""}. Used as market confirmation for news, factor risk, and strategy review.`
        : `${ticker}: ${label}. Waiting for hosted yfinance/OpenBB polling data.`
    };
  });
}

function renderMarketPulseCards(id, market) {
  const target = byId(id);
  if (!target) return;
  const rows = buildMarketPulseRows(market);
  target.innerHTML = rows.map(row => `
    <div class="pulse-card" title="${escapeHtml(row._tooltip)}">
      <div class="pulse-label">${escapeHtml(row.label)}</div>
      <div class="pulse-ticker">${escapeHtml(row.ticker)}</div>
      <div class="pulse-close">${row.hasData ? fmtNum(row.close, row.ticker === "VIX" ? 2 : 2) : "Waiting"}</div>
      <div class="pulse-move ${row.hasData ? signedClass(row.ret) : "muted"}">${row.hasData ? fmtPct(row.ret) : "live poll"}</div>
      <div class="pulse-source">${row.hasData ? `${timingLabel(row.timing)} ${row.date ?? ""}` : "no hard-coded price"}</div>
    </div>
  `).join("");
}

function newsDisplayTime(row, news) {
  return row.timestamp ?? row.published_at ?? row.generated_at_utc ?? news?.generated_at_utc;
}

function renderScatter(id, rows, options) {
  const target = byId(id);
  if (!target) return;
  const data = rows
    .map(row => ({
      label: String(row[options.labelKey] ?? ""),
      x: Number(typeof options.x === "function" ? options.x(row) : row[options.xKey]),
      y: Number(typeof options.y === "function" ? options.y(row) : row[options.yKey]),
      color: typeof options.color === "function" ? options.color(row) : (options.color ?? "#4ea1ff")
    }))
    .filter(row => Number.isFinite(row.x) && Number.isFinite(row.y));
  if (data.length === 0) {
    target.innerHTML = `<div class="small">No chart data.</div>`;
    return;
  }
  const width = 760;
  const height = 300;
  const pad = 38;
  const xs = data.map(row => row.x);
  const ys = data.map(row => row.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const scale = (v, min, max, a, b) => {
    if (max === min) return (a + b) / 2;
    return a + (v - min) / (max - min) * (b - a);
  };
  let labeled = new Set();
  if (typeof options.labelPredicate === "function") {
    data.forEach((row, index) => {
      if (options.labelPredicate(row, index, data)) labeled.add(index);
    });
  } else if (options.labelTopAbsY) {
    [...data]
      .map((row, index) => ({ ...row, index }))
      .sort((a, b) => Math.abs(b.y) - Math.abs(a.y))
      .slice(0, options.labelTopAbsY)
      .forEach(row => labeled.add(row.index));
  }
  const points = data.map((row, index) => {
    const cx = scale(row.x, minX, maxX, pad, width - pad);
    const cy = scale(row.y, minY, maxY, height - pad, pad);
    const showLabel = options.showLabels || labeled.has(index);
    const label = showLabel ? `<text class="chart-label" x="${cx + 7}" y="${cy + 4}">${escapeHtml(row.label).slice(0, 16)}</text>` : "";
    return `<g><circle class="chart-point" cx="${cx}" cy="${cy}" r="5" fill="${row.color}"><title>${escapeHtml(row.label)} | x=${fmtNum(row.x, 3)} y=${fmtNum(row.y, 3)}</title></circle>${label}</g>`;
  }).join("");
  target.innerHTML = `
    <svg class="svg-chart" viewBox="0 0 ${width} ${height}" role="img">
      <line class="chart-axis" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}"></line>
      <line class="chart-axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}"></line>
      <text class="chart-label" x="${pad}" y="${height - 10}">${escapeHtml(options.xLabel ?? "x")}</text>
      <text class="chart-label" x="${pad}" y="18">${escapeHtml(options.yLabel ?? "y")}</text>
      ${points}
    </svg>
  `;
}

function renderDonut(id, rows, options) {
  const target = byId(id);
  if (!target) return;
  const data = rows
    .map(row => ({
      label: String(row[options.labelKey] ?? ""),
      value: Number(row[options.valueKey])
    }))
    .filter(row => row.label && Number.isFinite(row.value) && row.value > 0);
  if (data.length === 0) {
    target.innerHTML = `<div class="small">No allocation data.</div>`;
    return;
  }
  const total = data.reduce((sum, row) => sum + row.value, 0);
  const colors = ["#4ea1ff", "#29b36a", "#d6a21f", "#e04f5f", "#9b8cff", "#43c6ac", "#f28e2b", "#8c9aaa"];
  let offset = 25;
  const circles = data.map((row, index) => {
    const pct = row.value / total * 100;
    const circle = `<circle r="15.9155" cx="18" cy="18" fill="transparent" stroke="${colors[index % colors.length]}" stroke-width="7" stroke-dasharray="${pct} ${100 - pct}" stroke-dashoffset="${offset}"><title>${escapeHtml(row.label)} ${fmtPct(pct)}</title></circle>`;
    offset -= pct;
    return circle;
  }).join("");
  const legend = data.map((row, index) => {
    const pct = row.value / total * 100;
    return `<div class="legend-row"><span class="legend-dot" style="background:${colors[index % colors.length]}"></span><span>${escapeHtml(row.label)}</span><span>${fmtPct(pct)}</span></div>`;
  }).join("");
  target.innerHTML = `
    <div class="donut-wrap">
      <svg class="donut" viewBox="0 0 36 36">${circles}<circle r="9" cx="18" cy="18" fill="#121923"></circle></svg>
      <div class="donut-legend">${legend}</div>
    </div>
  `;
}

function groupAllocation(rows, groupKey, valueKey) {
  const map = new Map();
  for (const row of rows) {
    if (row.asset_class === "monitor_only") continue;
    const key = row[groupKey] ?? "unknown";
    const value = Number(row[valueKey]);
    if (!Number.isFinite(value) || value <= 0) continue;
    const current = map.get(key) ?? { name: key, value: 0, members: [] };
    current.value += value;
    current.members.push({
      ticker: row.ticker,
      value,
      latest_return_pct: row.latest_return_pct,
      asset_class: row.asset_class,
      risk_bucket: row.risk_bucket
    });
    map.set(key, current);
  }
  return Array.from(map.values())
    .map(item => ({
      ...item,
      members: item.members.sort((a, b) => Number(b.value) - Number(a.value))
    }))
    .sort((a, b) => b.value - a.value);
}

function polarToCartesian(cx, cy, r, angle) {
  const rad = (angle - 90) * Math.PI / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function piePath(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? "0" : "1";
  return [
    "M", cx, cy,
    "L", start.x, start.y,
    "A", r, r, 0, largeArc, 0, end.x, end.y,
    "Z"
  ].join(" ");
}

function allocationTooltip(row, total) {
  const pct = row.value / total * 100;
  const members = (row.members ?? [])
    .slice(0, 12)
    .map(item => `${item.ticker} ${fmtPct(Number(item.value) * 100)} (${fmtPct(item.latest_return_pct)})`)
    .join(" | ");
  return `${row.name} ${fmtPct(pct)} | ${members}`;
}

function renderAllocationPie(id, rows, options = {}) {
  const target = byId(id);
  if (!target) return;
  const data = (rows ?? []).filter(row => Number(row.value) > 0);
  if (data.length === 0) {
    target.innerHTML = `<div class="small">No allocation data.</div>`;
    return;
  }
  const total = data.reduce((sum, row) => sum + Number(row.value), 0);
  const colors = ["#4ea1ff", "#29b36a", "#d6a21f", "#e04f5f", "#9b8cff", "#43c6ac", "#f28e2b", "#8c9aaa", "#d372f2", "#6fb6c8"];
  let angle = 0;
  const slices = data.map((row, index) => {
    const pct = Number(row.value) / total;
    const start = angle;
    const end = angle + pct * 360;
    angle = end;
    return `<path d="${piePath(90, 90, 78, start, end)}" fill="${colors[index % colors.length]}" stroke="#0b0f14" stroke-width="1.5"><title>${escapeHtml(allocationTooltip(row, total))}</title></path>`;
  }).join("");
  const legend = data.map((row, index) => {
    const pct = Number(row.value) / total * 100;
    const topMembers = (row.members ?? []).slice(0, 4).map(item => item.ticker).join(", ");
    return `
      <div class="allocation-row" title="${escapeHtml(allocationTooltip(row, total))}">
        <span class="legend-dot" style="background:${colors[index % colors.length]}"></span>
        <span class="allocation-name">${escapeHtml(row.name)}</span>
        <span class="allocation-pct">${fmtPct(pct)}</span>
        <span class="allocation-members">${escapeHtml(topMembers)}</span>
      </div>
    `;
  }).join("");
  target.innerHTML = `
    <div class="allocation-chart">
      <svg class="pie-chart" viewBox="0 0 180 180" role="img" aria-label="${escapeHtml(options.label ?? "portfolio allocation")}">${slices}</svg>
      <div class="allocation-legend">${legend}</div>
    </div>
  `;
}

function groupSum(rows, groupKey, valueKey) {
  const map = new Map();
  for (const row of rows) {
    if (row.asset_class === "monitor_only") continue;
    const key = row[groupKey] ?? "unknown";
    const value = Number(row[valueKey]);
    if (!Number.isFinite(value)) continue;
    map.set(key, (map.get(key) ?? 0) + value);
  }
  return Array.from(map.entries())
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

function topGroupsWithOther(groups, limit = 10) {
  if (!groups || groups.length <= limit) return groups ?? [];
  const head = groups.slice(0, limit - 1);
  const tail = groups.slice(limit - 1);
  const other = {
    name: "Other",
    value: tail.reduce((sum, row) => sum + Number(row.value || 0), 0),
    members: tail.flatMap(row => row.members ?? []).sort((a, b) => Number(b.value) - Number(a.value))
  };
  return [...head, other].filter(row => Number(row.value) > 0);
}

function selectedStrategyHoldings(strategy, market) {
  const tickers = String(strategy.target_etfs ?? "")
    .split(";")
    .map(x => x.trim())
    .filter(Boolean);
  const items = market.items ?? [];
  const sleeveWeight = tickers.length ? 1 / tickers.length : 0;
  return tickers.map(ticker => {
    const row = items.find(item => item.ticker === ticker) ?? {};
    return {
      ticker,
      sleeve_weight: sleeveWeight,
      latest_close: row.latest_close,
      latest_return_pct: row.latest_return_pct,
      asset_class: row.asset_class,
      risk_bucket: row.risk_bucket
    };
  });
}

function clamp(value, min = 0, max = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

function buildStrategyDecisionRows({ reviewRows, strategyLibrary, market, news }) {
  const configById = new Map(strategyLibrary.map(row => [row.strategy_id, row]));
  const newsImpact = deriveNewsImpact(news, market);
  return (reviewRows ?? []).map(row => {
    const config = configById.get(row.strategy_id) ?? row;
    const holdings = selectedStrategyHoldings(config.target_etfs ? config : row, market);
    const sleeveMove = holdings.length
      ? holdings.reduce((sum, item) => sum + (Number(item.latest_return_pct) || 0) * item.sleeve_weight, 0)
      : 0;
    const affected = newsImpact.affected.includes(row.strategy_id) ? 1 : 0;
    const wfo = clamp(Number(row.wfo_score), 0, 1);
    const currentFit = clamp((Number(sleeveMove) + 2) / 4, 0, 1);
    const stability = clamp(Number(row.train_top5_hit_rate), 0, 1);
    const coverage = clamp(Number(row.price_coverage_ratio), 0, 1);
    const drawdownPenalty = Number(row.oos_avg_max_drawdown) < -0.18 ? 0.10 : 0;
    const newsPenalty = newsImpact.level === "red" && affected === 0 ? 0.10 : 0;
    const decisionScore = clamp(
      0.35 * wfo + 0.25 * currentFit + 0.20 * stability + 0.10 * affected + 0.10 * coverage - drawdownPenalty - newsPenalty,
      0,
      1
    );
    return {
      ...row,
      current_sleeve_move_pct: sleeveMove,
      current_fit_score: currentFit,
      news_linked: affected === 1,
      decision_score: decisionScore,
      decision_basis: "Current market fit + WFO evidence + stability + coverage; not total return alone."
    };
  }).sort((a, b) => Number(b.decision_score) - Number(a.decision_score));
}

function buildMarketStrategyContext({ market, news, metrics }) {
  const rows = investableRows(market.items ?? []);
  const assetPerf = groupAverage(rows, "asset_class", "latest_return_pct");
  const bucketPerf = groupAverage(rows, "risk_bucket", "latest_return_pct");
  const topAsset = assetPerf[0] ?? {};
  const weakAsset = [...assetPerf].reverse()[0] ?? {};
  const topBucket = bucketPerf[0] ?? {};
  const weakBucket = [...bucketPerf].reverse()[0] ?? {};
  const risk = calculateRiskSignals(market, news, metrics ?? {});
  const posture = risk.overall === "red"
    ? "Defensive review"
    : risk.overall === "yellow"
      ? "Selective risk review"
      : "Normal monitoring";
  const implication = risk.overall === "red"
    ? "Do not add risk automatically. Prioritize drawdown control, liquidity, and confirmation before any sleeve change."
    : risk.overall === "yellow"
      ? "Look for strategies that match confirmed market moves, but keep human review and risk limits first."
      : "Use strategy board for opportunity scan; no escalation without stronger confirmation.";
  return {
    posture,
    implication,
    action: risk.overall === "red"
      ? "Escalate risk review; strategy changes require manager approval."
      : risk.overall === "yellow"
        ? "Prepare candidate strategy review; no automatic switch."
        : "Maintain watch; review only if live signals strengthen.",
    story: `Broad lens: ${topAsset.name ?? "N/A"} leads at ${fmtPct(topAsset.value)}, while ${weakAsset.name ?? "N/A"} lags at ${fmtPct(weakAsset.value)}. Portfolio risk-driver lens: ${topBucket.name ?? "N/A"} leads at ${fmtPct(topBucket.value)}, while ${weakBucket.name ?? "N/A"} lags at ${fmtPct(weakBucket.value)}. News impact is ${risk.newsImpact.level.toUpperCase()} with severity ${fmtNum(risk.newsImpact.severity, 1)}.`
  };
}

function buildSelectedStrategySummary({ selected, strategyLibrary, backtestRows, wfoWindows, market, news }) {
  const config = strategyLibrary.find(row => row.strategy_id === selected.strategy_id) ?? {};
  const backtest = backtestRows.find(row => row.strategy_id === selected.strategy_id) ?? {};
  const windows = (wfoWindows ?? []).filter(row => row.strategy_id === selected.strategy_id);
  const holdings = selectedStrategyHoldings(config, market);
  const avgToday = holdings.length
    ? holdings.reduce((sum, row) => sum + (Number(row.latest_return_pct) || 0) * row.sleeve_weight, 0)
    : null;
  const newsImpact = deriveNewsImpact(news, market);
  const triageRows = buildNewsTriage(news, market).rows ?? [];
  const strategyNewsRows = triageRows
    .filter(row => (row.affected_strategies ?? []).includes(selected.strategy_id))
    .slice(0, 6);
  const contextNewsRows = strategyNewsRows.length
    ? strategyNewsRows
    : triageRows
        .filter(row => row.warning_level !== "info" || Number(row.severity) >= 5)
        .slice(0, 4)
        .map(row => ({
          ...row,
          strategy_link_note: "No direct selected-strategy link; context only."
        }));
  const selectedWindows = windows.filter(row => row.selected_top_n).length;
  const top5Hit = Number(selected.train_top5_hit_rate);
  const stabilityText = Number.isFinite(top5Hit)
    ? `${fmtPct(top5Hit * 100)} train-window top-5 stability`
    : "train-window stability not available";
  return {
    config,
    backtest,
    windows,
    holdings,
    avgToday,
    newsImpact,
    strategyNewsRows: contextNewsRows,
    selectedWindows,
    thesis: config.objective ?? "",
    decisionBullets: [
      `Review ${selected.strategy_id} as a candidate sleeve, not an automatic trade.`,
      `Decision score ${fmtNum(selected.decision_score, 3)} combines current market fit, WFO evidence, stability, coverage, and news linkage.`,
      `Sleeve ETFs: ${config.target_etfs ?? selected.target_etfs}.`,
      `Action: keep human review gate before any escalation or allocation change.`
    ],
    evidenceBullets: [
      `WFO rank #${selected.wfo_rank}; WFO score ${fmtNum(selected.wfo_score, 3)}.`,
      `${fmtPct(Number(selected.oos_positive_window_rate) * 100)} positive OOS windows; average OOS return ${fmtPct(Number(selected.oos_avg_total_return) * 100)}.`,
      `Average OOS Sharpe ${fmtNum(selected.oos_avg_sharpe, 2)}; average OOS max drawdown ${fmtPct(Number(selected.oos_avg_max_drawdown) * 100)}.`,
      `${stabilityText}; low stability means review only.`
    ],
    previewBullets: [
      `Watch whether ${config.target_etfs ?? selected.target_etfs} continues to confirm the factor story.`,
      `Upgrade only if market confirmation improves and risk signals stay below red limits.`,
      `Downgrade to risk review if credit, volatility, or selected-strategy news linkage worsens.`,
      `Use WFO evidence as scenario support, not as tomorrow's return forecast.`
    ],
    why: `Current review direction score is ${fmtNum(selected.decision_score, 3)}. It uses current sleeve move (${fmtPct(selected.current_sleeve_move_pct)}), WFO rank #${selected.wfo_rank}, WFO score ${fmtNum(selected.wfo_score, 3)}, ${fmtPct(Number(selected.oos_positive_window_rate) * 100)} positive OOS windows, ${fmtNum(selected.oos_avg_sharpe, 2)} average OOS Sharpe, ${fmtPct(Number(selected.oos_avg_max_drawdown) * 100)} average OOS max drawdown, and ${stabilityText}. This is a strategy review direction, not a daily automatic switch.`,
    expected: `Historical WFO evidence suggests an average test-window return of ${fmtPct(Number(selected.oos_avg_total_return) * 100)} with average test-window max drawdown of ${fmtPct(Number(selected.oos_avg_max_drawdown) * 100)}. Use this as scenario evidence, not as tomorrow's expected return.`,
    benefits: `Potential benefit: aligns portfolio discussion with ${config.primary_factor ?? "the selected factor"} exposure through ${config.target_etfs ?? selected.target_etfs}. It can help express the current market view with explicit ETF proxies and documented risk controls.`,
    tradeoffs: `Main tradeoff: ${config.failure_mode ?? "the sleeve can fail when the regime reverses or signals are noisy"}. Stability and drawdown evidence must be reviewed before any escalation.`,
    riskImpact: `Risk-control impact: ${config.risk_controls ?? "human review required before allocation changes"}. Escalate only if market signals, news linkage, and portfolio risk limits confirm the thesis.`,
    factorRationale: `Factor-to-assets rationale: current signals are mapped into ${config.primary_factor ?? "factor"} / ${config.secondary_factor ?? "secondary factor"} exposure, then expressed through ETF proxies ${config.target_etfs ?? selected.target_etfs}. This follows the BlackRock-style idea of translating macro/factor views into investable asset sleeves instead of picking a ticker only because past return was high.`,
    nextPreview: `Next business day preview: watch whether the sleeve ETFs (${config.target_etfs ?? selected.target_etfs}) continue to confirm the market story. If confirmation improves and risk signals stay below red limits, keep this as a manager review candidate. If credit, volatility, or news risk worsens, downgrade to risk review and avoid increasing exposure.`,
    tomorrow: newsImpact.level === "red"
      ? "Tomorrow plan: risk review first; do not increase exposure without human approval."
      : "Tomorrow plan: monitor target ETF moves, inflation/commodity/rates proxies, news linkage, and risk limits. Keep as review candidate; do not treat as a forecast or automatic trade."
  };
}

function renderLiveStatus(status) {
  setText("poll-status", status.status ?? "unknown");
  setText("poll-cycle", status.cycle ?? "N/A");
  setText("poll-mode", status.market_data_mode ?? "N/A");
  setText("poll-latest", status.latest_observed_date ?? "N/A");
  setText("poll-rows", status.row_count ?? "N/A");
  setText("poll-time", fmtDateTimeET(status.generated_at_utc));
}

function calculateRiskSignals(market, news, metrics) {
  const items = market.items ?? [];
  const find = ticker => items.find(x => x.ticker === ticker) ?? {};
  const vix = Number(find("VIX").latest_close);
  const spyRet = Number(find("SPY").latest_return_pct);
  const hygRet = Number(find("HYG").latest_return_pct);
  const lqdRet = Number(find("LQD").latest_return_pct);
  const usoRet = Number(find("USO").latest_return_pct);
  const gldRet = Number(find("GLD").latest_return_pct);
  const newsImpact = deriveNewsImpact(news, market);
  const portfolioVar = Number(metrics?.metrics?.["portfolio VaR"]);
  const drawdown = Number(metrics?.metrics?.["portfolio drawdown"]);

  const signals = [
    {
      name: "Volatility pressure",
      value: Number.isFinite(vix) ? vix : null,
      unit: "VIX",
      level: vix >= 30 ? "red" : vix >= 20 ? "yellow" : "green",
      reason: "VIX level from market monitor"
    },
    {
      name: "Equity selloff",
      value: Number.isFinite(spyRet) ? spyRet : null,
      unit: "%",
      level: spyRet <= -2 ? "red" : spyRet <= -0.75 ? "yellow" : "green",
      reason: "SPY latest return"
    },
    {
      name: "Credit stress proxy",
      value: Number.isFinite(hygRet - lqdRet) ? hygRet - lqdRet : null,
      unit: "%",
      level: (hygRet - lqdRet) <= -0.75 ? "red" : (hygRet - lqdRet) <= -0.3 ? "yellow" : "green",
      reason: "HYG relative to LQD"
    },
    {
      name: "Energy shock",
      value: Number.isFinite(usoRet) ? usoRet : null,
      unit: "%",
      level: usoRet >= 3 ? "red" : usoRet >= 1.5 ? "yellow" : "green",
      reason: "USO latest return"
    },
    {
      name: "Safe-haven bid",
      value: Number.isFinite(gldRet) ? gldRet : null,
      unit: "%",
      level: gldRet >= 2 ? "red" : gldRet >= 1 ? "yellow" : "green",
      reason: "GLD latest return"
    },
    {
      name: "News/event risk",
      value: newsImpact.severity,
      unit: "severity",
      level: newsImpact.level,
      reason: newsImpact.reason
    },
    {
      name: "Portfolio VaR",
      value: Number.isFinite(portfolioVar) ? portfolioVar : null,
      unit: "ratio",
      level: portfolioVar >= 1 ? "red" : portfolioVar >= 0.75 ? "yellow" : "green",
      reason: "Official EOD metrics snapshot"
    },
    {
      name: "Portfolio drawdown",
      value: Number.isFinite(drawdown) ? drawdown : null,
      unit: "ratio",
      level: drawdown <= -0.08 ? "red" : drawdown <= -0.04 ? "yellow" : "green",
      reason: "Official EOD metrics snapshot"
    }
  ];
  const decisiveSignals = signals.filter(x => x.name !== "News/event risk" || newsImpact.confirmations >= 1 || newsImpact.affected.length > 0);
  const red = decisiveSignals.filter(x => x.level === "red").length;
  const yellow = signals.filter(x => x.level === "yellow").length;
  const overall = red > 0 ? "red" : yellow > 0 ? "yellow" : "green";
  return { signals, overall, red, yellow, newsImpact };
}

function buildStrategyDailyReview({ wfoRows, backtestRows, rankingRows, strategyLibrary, news, market }) {
  const configById = new Map(strategyLibrary.map(row => [row.strategy_id, row]));
  const backtestById = new Map(backtestRows.map(row => [row.strategy_id, row]));
  const rankingById = new Map(rankingRows.map(row => [row.strategy_id, row]));
  const newsImpact = deriveNewsImpact(news, market);
  return wfoRows.map(row => {
    const config = configById.get(row.strategy_id) ?? {};
    const bt = backtestById.get(row.strategy_id) ?? {};
    const rk = rankingById.get(row.strategy_id) ?? {};
    let action = "Maintain watch";
    if (Number(row.wfo_rank) <= 5 && Number(row.oos_positive_window_rate) >= 0.6 && newsImpact.level !== "red") {
      action = "Candidate for review";
    }
    if (Number(row.oos_avg_max_drawdown) <= -0.18 || newsImpact.level === "red") {
      action = "Risk review before any use";
    }
    return {
      strategy_id: row.strategy_id,
      action,
      wfo_rank: row.wfo_rank,
      wfo_score: row.wfo_score,
      wfo_status: row.wfo_status,
      category: row.category ?? config.category ?? "",
      window_count: row.window_count,
      selected_top5_window_count: row.selected_top5_window_count,
      train_top5_hit_rate: row.train_top5_hit_rate,
      oos_avg_total_return: row.oos_avg_total_return,
      oos_avg_sharpe: row.oos_avg_sharpe,
      oos_avg_max_drawdown: row.oos_avg_max_drawdown,
      oos_avg_monthly_win_rate: row.oos_avg_monthly_win_rate,
      oos_positive_window_rate: row.oos_positive_window_rate,
      selected_oos_avg_total_return: row.selected_oos_avg_total_return,
      selected_oos_positive_window_rate: row.selected_oos_positive_window_rate,
      first_test_start: row.first_test_start,
      last_test_end: row.last_test_end,
      annualized_return: bt.annualized_return,
      win_rate_monthly: bt.win_rate_monthly,
      max_drawdown: bt.max_drawdown,
      objective: config.objective ?? rk.explanation ?? "",
      core_signal: config.core_signal ?? "",
      target_etfs: config.target_etfs ?? rk.target_etfs ?? "",
      available_price_etfs: row.available_price_etfs ?? bt.available_price_etfs ?? "",
      missing_price_etfs: row.missing_price_etfs ?? bt.missing_price_etfs ?? "",
      price_coverage_ratio: row.price_coverage_ratio ?? bt.price_coverage_ratio,
      price_coverage_status: row.price_coverage_status ?? bt.price_coverage_status,
      risk_controls: config.risk_controls ?? "",
      valid_regime: config.valid_regime ?? "",
      invalid_regime: config.invalid_regime ?? ""
    };
  });
}

function startLoop(fn, seconds = 3) {
  const run = () => {
    try {
      const result = fn();
      if (result && typeof result.catch === "function") {
        result.catch(error => console.error("dashboard update failed", error));
      }
    } catch (error) {
      console.error("dashboard update failed", error);
    }
  };
  run();
  setInterval(run, seconds * 1000);
}
