import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from itertools import islice

# -----------------------
# Config
# -----------------------
st.set_page_config(page_title="Crypto Dashboard", page_icon="💹", layout="wide")
st.markdown("<style>body {background-color:#0E1117; color:#E6EEF8;}</style>", unsafe_allow_html=True)

COIN_IDS = ["bitcoin", "ethereum", "solana", "sui", "pyth-network", "cardano", "polkadot"]

# -----------------------
# Utilities
# -----------------------
def batched(iterable, n_cols):
    it = iter(iterable)
    while True:
        batch = tuple(islice(it, n_cols))
        if not batch:
            break
        yield batch

# -----------------------
# Data fetching
# -----------------------
@st.cache_data(ttl=60)
def fetch_live_prices(coin_ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        live = r.json()
        data = []
        for ticker, metrics in live.items():
            last_price = metrics.get("usd", 0)
            change_pct = metrics.get("usd_24h_change", 0) or 0
            change_pct = metrics.get("usd_24h_change", 0) or 0
            last_price = metrics.get("usd", 0)
# Generate a ##################
            sparkline = [last_price / (1 + change_pct/100 * (i/6)) for i in range(6, -1, -1)]
            data.append({
                "id": ticker,
                "ticker": ticker.upper(),
                "last_price": float(last_price),
                "change_pct": float(change_pct),
                "volume": float(metrics.get("usd_24h_vol", 0) or 0),
                "market_cap": float(metrics.get("usd_market_cap", 0) or 0),
                "open": sparkline
            })
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_historical_market_chart(coin_id, days="90"):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        prices = pd.DataFrame(data.get("prices", []), columns=["ts", "close"])
        vols = pd.DataFrame(data.get("total_volumes", []), columns=["ts", "volume"])
        if prices.empty or vols.empty:
            return pd.DataFrame()
        prices["date"] = pd.to_datetime(prices["ts"], unit="ms")
        vols["date"] = pd.to_datetime(vols["ts"], unit="ms")
        df = prices.merge(vols, on="date")
        df["open"] = df["close"].shift(1).fillna(df["close"])
        df["high"] = df[["open", "close"]].max(axis=1)
        df["low"] = df[["open", "close"]].min(axis=1)
        df = df[["open","high","low","close","volume"]].dropna()
        df.index = df.index if df.index is not None else df["date"]
        return df
    except:
        return pd.DataFrame()

# -----------------------
# Plot helpers
# -----------------------
def build_sparkline(series):
    y = list(series) if hasattr(series, "iter") else [0,0]
    if len(y) < 2: y=[0,0]
    fig = go.Figure(go.Scatter(y=y, mode="lines", fill="tozeroy"))
    fig.update_traces(line_color="lime")
    fig.update_layout(height=60, margin=dict(t=6,b=6,l=6,r=6), paper_bgcolor="#111419", plot_bgcolor="#111419")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig

def build_candlestick_figure(df):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75,0.25], vertical_spacing=0.06)
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                                    increasing_line_color='lime', decreasing_line_color='red', name="Price"), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume"), row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False, height=520, template="plotly_dark",
                      paper_bgcolor="#111419", plot_bgcolor="#111419")
    return fig

# -----------------------
# UI Components
# -----------------------
def display_watchlist(ticker_df):
    st.subheader("Watchlist")
    if ticker_df.empty:
        st.info("No live data")
        return
    n_cols = 4
    for row in batched(ticker_df.to_dict("records"), n_cols):
        cols = st.columns(n_cols)
        for col, rec in zip(cols, row):
            with col:
                st.markdown(f"### {rec['ticker']}")
                arrow = "▲" if rec["change_pct"] >= 0 else "▼"
                color = "green" if rec["change_pct"] >= 0 else "red"
                st.markdown(f"<span style='color:{color}'>{arrow} {rec['change_pct']:.2f}%</span>", unsafe_allow_html=True)
                st.write(f"${rec['last_price']:,.2f}")
                st.plotly_chart(build_sparkline(rec["open"]), use_container_width=True, key=f"spark_{rec['ticker']}")
def display_overview(df):
    st.subheader("Overview Table")
    if df.empty:
        st.info("No data")
        return
    st.dataframe(df.drop(columns=["open"], errors="ignore"), use_container_width=True)

def display_symbol_history(ticker_df, history_days=90):
    st.subheader("Symbol History")
    if ticker_df.empty:
        st.info("No symbols")
        return
    ticker_to_id = {row["ticker"]: row["id"] for _, row in ticker_df.iterrows()}
    selected_ticker = st.selectbox("Select Symbol:", options=list(ticker_to_id.keys()))
    if not selected_ticker:
        st.info("Select a symbol")
        return
    coin_id = ticker_to_id[selected_ticker]
    df = fetch_historical_market_chart(coin_id, days=str(history_days))
    if df.empty:
        st.warning(f"No historical data for {selected_ticker}")
        return
    fig = build_candlestick_figure(df)
    st.plotly_chart(fig, use_container_width=True, key=f"candlestick_{selected_ticker}")

# -----------------------
# Main App Flow
# -----------------------
st.title("Crypto Dashboard, Live Prices")
ticker_df = fetch_live_prices(COIN_IDS)

left_col, right_col = st.columns([2.5,1])

with left_col:
    display_watchlist(ticker_df)
    st.divider()
    display_symbol_history(ticker_df, history_days=90)

with right_col:
    st.subheader("Quick Metrics")
    if not ticker_df.empty:
        top = ticker_df.iloc[0]
        st.metric("Top Token", top["ticker"])
        st.metric("Top Price", f"${top['last_price']:,.2f}")
        st.metric("Top 24h Change", f"{top['change_pct']:.2f}%")
    st.divider()
    display_overview(ticker_df)

st.markdown("Data provided by [CoinGecko](https://www.coingecko.com/)")

