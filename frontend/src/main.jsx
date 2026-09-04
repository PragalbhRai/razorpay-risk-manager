import React from "react";
import { createRoot } from "react-dom/client";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./styles.css";

const MERCHANT_ID = "123e4567-e89b-12d3-a456-426614174000";
const REFRESH_INTERVAL_MS = 7000;

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function apiRequest(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status if the backend does not return JSON.
    }
    throw new Error(detail);
  }

  return response.json();
}

const dashboardApi = {
  getSummary: () => apiRequest(`/api/v1/dashboard/summary?merchant_id=${MERCHANT_ID}`),
  getTimeline: () => apiRequest(`/api/v1/dashboard/timeline?merchant_id=${MERCHANT_ID}&limit=50`),
  getMerchant: () => apiRequest(`/api/v1/dashboard/merchants/${MERCHANT_ID}`),
  getAlerts: () => apiRequest(`/api/v1/alerts?merchant_id=${MERCHANT_ID}&limit=20`),
  acknowledgeAlert: (alertId) => apiRequest(`/api/v1/alerts/${alertId}/acknowledge`, { method: "PATCH" }),
  resolveAlert: (alertId) => apiRequest(`/api/v1/alerts/${alertId}/resolve`, { method: "PATCH" }),
};

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (value === null || value === undefined) return "--";
  return `${formatNumber(Number(value) * 100, 1)}%`;
}

function formatCurrency(value) {
  if (value === null || value === undefined) return "--";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatDateTime(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(value) {
  return (value || "unknown").toUpperCase();
}

function statusClass(value) {
  return `status status-${(value || "unknown").toLowerCase()}`;
}

function useDashboardData() {
  const [data, setData] = React.useState({
    summary: null,
    timeline: [],
    merchant: null,
    alerts: [],
  });
  const [isLoading, setIsLoading] = React.useState(true);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [lastUpdated, setLastUpdated] = React.useState(null);

  const load = React.useCallback(async ({ silent = false } = {}) => {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setError(null);

    try {
      const [summary, timelineResult, merchantResult, alertsResult] = await Promise.all([
        dashboardApi.getSummary(),
        dashboardApi.getTimeline(),
        dashboardApi.getMerchant(),
        dashboardApi.getAlerts(),
      ]);

      setData({
        summary,
        timeline: timelineResult.timeline || [],
        merchant: merchantResult.merchant,
        alerts: alertsResult.alerts || [],
      });
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message || "Unable to load dashboard data");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  React.useEffect(() => {
    load();
    const timer = window.setInterval(() => load({ silent: true }), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  return {
    data,
    isLoading,
    isRefreshing,
    error,
    lastUpdated,
    refresh: () => load({ silent: true }),
  };
}

function SummaryCard({ label, value, tone, suffix }) {
  return (
    <article className={`summary-card ${tone ? `summary-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>
        {value}
        {suffix ? <small>{suffix}</small> : null}
      </strong>
    </article>
  );
}

function ClassificationCounts({ summary }) {
  const total =
    (summary?.normal_count || 0) +
    (summary?.watch_count || 0) +
    (summary?.alert_count || 0);

  return (
    <section className="classification-strip" aria-label="Classification counts">
      <ClassificationPill label="Normal" value={summary?.normal_count || 0} total={total} tone="normal" />
      <ClassificationPill label="Watch" value={summary?.watch_count || 0} total={total} tone="watch" />
      <ClassificationPill label="Alert" value={summary?.alert_count || 0} total={total} tone="alert" />
    </section>
  );
}

function ClassificationPill({ label, value, total, tone }) {
  const width = total > 0 ? `${Math.max((value / total) * 100, value > 0 ? 8 : 0)}%` : "0%";

  return (
    <div className={`classification-pill ${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="classification-meter">
        <i style={{ width }} />
      </div>
    </div>
  );
}

function RiskTimeline({ timeline, selectedWindow, onSelectWindow }) {
  const chartData = React.useMemo(
    () =>
      timeline.map((item) => ({
        ...item,
        label: formatDateTime(item.window_start),
        risk_score: item.risk_score ?? 0,
      })),
    [timeline],
  );

  if (!timeline.length) {
    return <EmptyState title="No risk windows yet" message="Processed windows will appear here as the worker evaluates transactions." />;
  }

  return (
    <div className="timeline-layout">
      <div className="chart-shell">
        <ResponsiveContainer width="100%" height={285}>
          <LineChart data={chartData} margin={{ top: 18, right: 24, bottom: 8, left: 0 }} onClick={(state) => {
            if (state?.activePayload?.[0]?.payload) onSelectWindow(state.activePayload[0].payload);
          }}>
            <CartesianGrid stroke="#253244" strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fill: "#93a4ba", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "#2c3a4d" }} />
            <YAxis domain={[0, 100]} tick={{ fill: "#93a4ba", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "#2c3a4d" }} />
            <Tooltip content={<RiskTooltip />} />
            <Line type="monotone" dataKey="risk_score" stroke="#62a8ff" strokeWidth={2.5} dot={<RiskDot />} activeDot={{ r: 7, strokeWidth: 2, stroke: "#f8fafc" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <WindowDetails windowItem={selectedWindow || timeline[timeline.length - 1]} />
    </div>
  );
}

function RiskDot(props) {
  const { cx, cy, payload } = props;
  const classification = payload?.classification;
  const fill = classification === "alert" ? "#ff5c74" : classification === "watch" ? "#f7c85b" : "#44d19d";
  const radius = classification === "alert" ? 6 : 4;

  return <circle cx={cx} cy={cy} r={radius} fill={fill} stroke="#101722" strokeWidth="2" />;
}

function RiskTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;

  return (
    <div className="chart-tooltip">
      <strong>{formatDateTime(item.window_start)}</strong>
      <span>Risk score: {formatNumber(item.risk_score, 1)}</span>
      <span>Transactions: {item.tx_count}</span>
      <span>Failure rate: {formatPercent(item.failure_rate)}</span>
      <span className={statusClass(item.classification)}>{statusLabel(item.classification)}</span>
    </div>
  );
}

function WindowDetails({ windowItem }) {
  if (!windowItem) return null;

  return (
    <aside className="window-detail">
      <div className="section-kicker">Selected Window</div>
      <div className="risk-readout">
        <strong>{formatNumber(windowItem.risk_score, 1)}</strong>
        <span className={statusClass(windowItem.classification)}>{statusLabel(windowItem.classification)}</span>
      </div>
      <dl>
        <div>
          <dt>Window</dt>
          <dd>{formatDateTime(windowItem.window_start)} - {formatDateTime(windowItem.window_end)}</dd>
        </div>
        <div>
          <dt>Transactions</dt>
          <dd>{windowItem.tx_count}</dd>
        </div>
        <div>
          <dt>Failure Rate</dt>
          <dd>{formatPercent(windowItem.failure_rate)}</dd>
        </div>
        <div>
          <dt>Average Amount</dt>
          <dd>{formatCurrency(windowItem.amount_mean)}</dd>
        </div>
        <div>
          <dt>Baseline Deviation</dt>
          <dd>{formatNumber(windowItem.baseline_deviation_score, 2)}</dd>
        </div>
      </dl>
    </aside>
  );
}

function AlertPanel({ alerts, onAcknowledge, onResolve, busyAlertId }) {
  const activeAlerts = alerts.filter((alert) => alert.status !== "resolved");
  const displayAlerts = activeAlerts.length ? activeAlerts : alerts.slice(0, 5);

  return (
    <section className="panel alert-panel">
      <PanelHeader title="Fraud Alerts" eyebrow={`${alerts.length} total`} />
      {!displayAlerts.length ? (
        <EmptyState title="No alerts" message="Fraud spikes and lifecycle updates will appear here." compact />
      ) : (
        <div className="alert-list">
          {displayAlerts.map((alert) => (
            <AlertItem
              key={alert.id}
              alert={alert}
              onAcknowledge={onAcknowledge}
              onResolve={onResolve}
              isBusy={busyAlertId === alert.id}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function AlertItem({ alert, onAcknowledge, onResolve, isBusy }) {
  const riskScore = alert.decision?.risk_score;
  const canAcknowledge = alert.status === "open";
  const canResolve = alert.status === "acknowledged";

  return (
    <article className={`alert-item ${alert.status === "open" ? "alert-hot" : ""}`}>
      <div className="alert-topline">
        <span className={`severity severity-${alert.severity}`}>{alert.severity}</span>
        <span className={statusClass(alert.status)}>{statusLabel(alert.status)}</span>
      </div>
      <div className="alert-body">
        <div>
          <h3>{alert.title}</h3>
          <p>{alert.message || alert.decision?.explanation || "No explanation supplied."}</p>
        </div>
        <div className="alert-score">
          <span>Risk</span>
          <strong>{formatNumber(riskScore, 1)}</strong>
        </div>
      </div>
      {alert.decision?.explanation && alert.decision.explanation !== alert.message ? (
        <p className="alert-explanation">{alert.decision.explanation}</p>
      ) : null}
      <div className="alert-footer">
        <time>{formatDateTime(alert.created_at)}</time>
        <div className="alert-actions">
          <button type="button" onClick={() => onAcknowledge(alert.id)} disabled={!canAcknowledge || isBusy}>
            {isBusy && canAcknowledge ? "Working" : "Acknowledge"}
          </button>
          <button type="button" className="resolve-button" onClick={() => onResolve(alert.id)} disabled={!canResolve || isBusy}>
            {isBusy && canResolve ? "Working" : "Resolve"}
          </button>
        </div>
      </div>
    </article>
  );
}

function MerchantPanel({ merchant }) {
  return (
    <section className="panel merchant-panel">
      <PanelHeader title="Merchant" eyebrow="Monitored account" />
      {!merchant ? (
        <EmptyState title="Merchant unavailable" message="The merchant endpoint did not return details." compact />
      ) : (
        <dl className="merchant-list">
          <div>
            <dt>Name</dt>
            <dd>{merchant.name}</dd>
          </div>
          <div>
            <dt>Razorpay Account</dt>
            <dd>{merchant.razorpay_account_id}</dd>
          </div>
          <div>
            <dt>Merchant UUID</dt>
            <dd className="mono">{merchant.id}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function RecentActivity({ timeline }) {
  const rows = [...timeline].reverse().slice(0, 12);

  return (
    <section className="panel full-width">
      <PanelHeader title="Recent Window Activity" eyebrow={`${timeline.length} windows loaded`} />
      {!rows.length ? (
        <EmptyState title="No recent windows" message="The table will populate after the worker processes transaction windows." compact />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Transactions</th>
                <th>Failure Rate</th>
                <th>Avg Amount</th>
                <th>Risk Score</th>
                <th>Classification</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.window_id}>
                  <td>{formatDateTime(row.window_start)}</td>
                  <td>{row.tx_count}</td>
                  <td>{formatPercent(row.failure_rate)}</td>
                  <td>{formatCurrency(row.amount_mean)}</td>
                  <td>{formatNumber(row.risk_score, 1)}</td>
                  <td><span className={statusClass(row.classification)}>{statusLabel(row.classification)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RiskDistribution({ summary }) {
  const data = [
    { name: "Normal", value: summary?.normal_count || 0 },
    { name: "Watch", value: summary?.watch_count || 0 },
    { name: "Alert", value: summary?.alert_count || 0 },
  ];

  return (
    <section className="panel compact-chart">
      <PanelHeader title="Classification Mix" eyebrow="Processed windows" />
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="classificationFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#62a8ff" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#62a8ff" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#253244" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fill: "#93a4ba", fontSize: 12 }} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: "#93a4ba", fontSize: 12 }} tickLine={false} axisLine={false} width={28} />
          <Area type="monotone" dataKey="value" stroke="#62a8ff" fill="url(#classificationFill)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  );
}

function PanelHeader({ title, eyebrow }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <span>{eyebrow}</span>
    </div>
  );
}

function EmptyState({ title, message, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-compact" : ""}`}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <main className="app-shell">
      <div className="loading-page">
        <div className="loader" />
        <strong>Loading risk dashboard</strong>
      </div>
    </main>
  );
}

function App() {
  const { data, isLoading, isRefreshing, error, lastUpdated, refresh } = useDashboardData();
  const [selectedWindow, setSelectedWindow] = React.useState(null);
  const [busyAlertId, setBusyAlertId] = React.useState(null);
  const [actionError, setActionError] = React.useState(null);

  React.useEffect(() => {
    if (!selectedWindow && data.timeline.length) {
      setSelectedWindow(data.timeline[data.timeline.length - 1]);
    }
  }, [data.timeline, selectedWindow]);

  const handleAlertAction = async (alertId, action) => {
    setBusyAlertId(alertId);
    setActionError(null);
    try {
      if (action === "acknowledge") {
        await dashboardApi.acknowledgeAlert(alertId);
      } else {
        await dashboardApi.resolveAlert(alertId);
      }
      await refresh();
    } catch (err) {
      setActionError(err.message || "Alert action failed");
    } finally {
      setBusyAlertId(null);
    }
  };

  if (isLoading) return <LoadingState />;

  const summary = data.summary || {};
  const openAlertCount = summary.open_alerts || data.alerts.filter((alert) => alert.status === "open").length;
  const hasAlert = (summary.alert_count || 0) > 0 || openAlertCount > 0;

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p>Razorpay Risk Manager</p>
          <h1>Fraud Spike Monitoring</h1>
        </div>
        <div className="refresh-meta">
          <span className={hasAlert ? "live-indicator alerting" : "live-indicator"} />
          <div>
            <strong>{isRefreshing ? "Refreshing" : "Live dashboard"}</strong>
            <span>Updated {lastUpdated ? formatDateTime(lastUpdated.toISOString()) : "--"}</span>
          </div>
        </div>
      </header>

      {error ? <div className="notice error">API error: {error}</div> : null}
      {actionError ? <div className="notice warning">Alert action failed: {actionError}</div> : null}

      <section className="summary-grid">
        <SummaryCard label="Total Transactions" value={formatNumber(summary.total_transactions)} />
        <SummaryCard label="Windows Processed" value={formatNumber(summary.total_windows)} />
        <SummaryCard label="Open Alerts" value={formatNumber(openAlertCount)} tone={openAlertCount > 0 ? "alert" : "normal"} />
        <SummaryCard label="Average Risk Score" value={formatNumber(summary.average_risk_score, 2)} suffix="/100" tone={hasAlert ? "watch" : ""} />
      </section>

      <ClassificationCounts summary={summary} />

      <section className="dashboard-grid">
        <section className="panel timeline-panel">
          <PanelHeader title="Risk Timeline" eyebrow="Risk score over time" />
          <RiskTimeline timeline={data.timeline} selectedWindow={selectedWindow} onSelectWindow={setSelectedWindow} />
        </section>
        <AlertPanel
          alerts={data.alerts}
          onAcknowledge={(alertId) => handleAlertAction(alertId, "acknowledge")}
          onResolve={(alertId) => handleAlertAction(alertId, "resolve")}
          busyAlertId={busyAlertId}
        />
        <MerchantPanel merchant={data.merchant} />
        <RiskDistribution summary={summary} />
        <RecentActivity timeline={data.timeline} />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
