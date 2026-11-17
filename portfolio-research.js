const byId = id => document.getElementById(id);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const stances = { BUY: "Buy", HOLD: "Hold", SELL: "Sell", Unavailable: "Unavailable" };
const snapshotAgeLimit = 7 * 24 * 60 * 60 * 1000;
const dateFormat = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata"
});
let watchlist = [];
let models = [];

function listing(ticker) {
  if (ticker.endsWith(".NS")) return "NSE";
  if (ticker.endsWith(".BO")) return "BSE";
  return "Other listings";
}

function signal(quote) {
  if (!(quote?.current > 0) || !Number.isFinite(quote.ai_score)) return "Unavailable";
  if (quote.ai_score >= 1) return "BUY";
  if (quote.ai_score <= -1) return "SELL";
  return "HOLD";
}

function recent(date) {
  const age = Date.now() - Date.parse(date);
  return age >= 0 && age <= snapshotAgeLimit;
}

function pill(stance) {
  return '<span class="pill ' + stance.toLowerCase() + '">' + stances[stance] + '</span>';
}

function showBreadth(freshSnapshot) {
  const groups = ["NSE", "BSE", "Other listings"];
  byId("breadth").innerHTML = groups.map(group => {
    const eligible = watchlist.filter(({ ticker, quote }) =>
      listing(ticker) === group && quote?.current > 0 && quote.avg30 > 0 &&
      (!freshSnapshot || recent(quote.price_date)));
    const above = eligible.filter(({ quote }) => quote.current > quote.avg30).length;
    const ratio = eligible.length ? above + " / " + eligible.length : "—";
    return "<div><span>" + group + "</span><strong>" + ratio +
      "</strong><small>Above 30-day average</small></div>";
  }).join("");
  byId("breadth").hidden = false;
}

function renderReviews(ticker, archived) {
  const opinions = models.flatMap(({ model, reviews }) => {
    const review = reviews?.[ticker];
    return review && ["BUY", "HOLD", "SELL"].includes(review.stance) ? [{ model, ...review }] : [];
  });
  if (!opinions.length || archived) return "—";
  const stancesSeen = new Set(opinions.map(({ stance }) => stance));
  const label = stancesSeen.size > 1 ? "Models disagree" :
    opinions.length > 1 ? "Both models · " + stances[opinions[0].stance] : stances[opinions[0].stance] + " · 1 model";
  const content = opinions.map(({ model, stance, rationale, risk }) =>
    '<div class="review"><strong>' + escapeHtml(model) + '</strong> ' + pill(stance) +
    '<p>' + escapeHtml(rationale) + '</p><p><strong>Risk</strong> ' + escapeHtml(risk) + '</p></div>'
  ).join("");
  return "<details><summary>" + label + "</summary>" + content + "</details>";
}

function render() {
  const query = byId("search").value.trim().toUpperCase();
  const filter = byId("filter").value;
  const openTickers = new Set(Array.from(document.querySelectorAll("#rows details[open]"),
    details => details.closest("tr").dataset.ticker));
  const shown = watchlist.filter(({ ticker, quote }) =>
    ticker.toUpperCase().includes(query) && (!filter || signal(quote) === filter));
  byId("count").textContent = shown.length + " of " + watchlist.length + " symbols";
  byId("rows").innerHTML = shown.map(({ ticker, quote }) => {
    const stance = signal(quote);
    const date = quote?.price_date;
    const archived = !recent(date);
    const price = quote?.current > 0 ? quote.current.toFixed(2) : "—";
    const priceLabel = listing(ticker) === "Other listings" ? price : "₹" + price;
    const rsi = Number.isFinite(quote?.rsi) ? quote.rsi.toFixed(1) : "—";
    const distance = quote?.avg30 > 0 && quote.current > 0 ? (quote.current / quote.avg30 - 1) * 100 : null;
    const deviation = distance === null ? "—" : (distance > 0 ? "+" : "") + distance.toFixed(1) + "%";
    const reasons = quote?.reasons?.join(" · ") || "Quote data unavailable";
    return '<tr data-ticker="' + escapeHtml(ticker) + '"><th scope="row">' + escapeHtml(ticker) +
      '<small>' + listing(ticker) + '</small></th><td class="number">' + (price === "—" ? price : priceLabel) +
      (quote ? "<small>" + escapeHtml(date || "Date unavailable") + "</small>" : "") +
      '</td><td class="number">' + rsi + '</td><td class="number">' + deviation + '</td><td>' +
      pill(stance) + (archived && stance !== "Unavailable" ? "<small>Historical</small>" : "") +
      "</td><td>" + escapeHtml(reasons) + "</td><td>" + renderReviews(ticker, archived) + "</td></tr>";
  }).join("") || '<tr><td colspan="7">No matching symbols.</td></tr>';
  document.querySelectorAll("#rows details").forEach(details => {
    details.open = openTickers.has(details.closest("tr").dataset.ticker);
  });
}

async function readFile(path, type) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(path + " returned " + response.status);
  return response[type]();
}

async function load() {
  const [quoteResult, portfolioResult, modelResult] = await Promise.allSettled([
    readFile("data.json", "json"), readFile("stocks.csv", "text"),
    readFile("portfolio_research.json", "json")
  ]);
  const quotes = Array.isArray(quoteResult.value) ? quoteResult.value : [];
  const byTicker = new Map(quotes.map(quote => [quote.ticker, quote]));
  const portfolio = portfolioResult.value?.trim().split(/\r?\n/).slice(1)
    .map(line => line.split(",", 1)[0].trim()).filter(Boolean);
  watchlist = [...new Set(portfolio?.length ? portfolio : byTicker.keys())]
    .map(ticker => ({ ticker, quote: byTicker.get(ticker) }))
    .sort((a, b) => a.ticker.localeCompare(b.ticker));

  const snapshot = quotes[0]?.snapshot;
  const research = modelResult.value;
  models = recent(snapshot) && research?.snapshot === snapshot && Array.isArray(research.models)
    ? research.models : [];
  byId("snapshot").textContent = !quotes.length ? "Quote snapshot unavailable" :
    !Number.isFinite(Date.parse(snapshot)) ? "Historical snapshot · quote dates unavailable" :
    (recent(snapshot) ? "Snapshot refreshed " : "Historical snapshot · ") +
      dateFormat.format(new Date(snapshot)) + " IST";
  byId("model-status").textContent = models.length
    ? "Model coverage · " + models.map(({ provider }) => provider).join(" + ")
    : "AI opinions unavailable for this snapshot. Technical signals shown where available.";
  if (portfolioResult.status === "rejected") {
    byId("model-status").textContent += " Portfolio list unavailable. Showing symbols from the quote snapshot.";
  }
  showBreadth(recent(snapshot));
  render();
}

byId("search").addEventListener("input", render);
byId("filter").addEventListener("change", render);
load();
