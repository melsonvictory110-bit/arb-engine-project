import streamlit as st
import pandas as pd
import numpy as np
import time
import plotly.express as px
from dataclasses import dataclass

# --- Page Configuration ---
st.set_page_config(
    page_title="HFT Arbitrage Feasibility Engine",
    page_icon="⚡",
    layout="wide"
)

# --- Core Order Book & Arbitrage Engine Classes ---
@dataclass
class OrderBook:
    venue: str
    best_bid: float
    best_ask: float

class ArbitrageEngine:
    def __init__(self, min_profit_bps: float = 5.0, taker_fee_bps: float = 1.5):
        self.min_profit_margin = min_profit_bps / 10000.0
        self.total_fee_margin = (2 * taker_fee_bps) / 10000.0

    def evaluate_spread(self, book_a: OrderBook, book_b: OrderBook):
        # Direction 1: Buy Exchange A -> Sell Exchange B
        spread_1 = (book_b.best_bid - book_a.best_ask) / book_a.best_ask
        net_yield_1 = spread_1 - self.total_fee_margin

        # Direction 2: Buy Exchange B -> Sell Exchange A
        spread_2 = (book_a.best_bid - book_b.best_ask) / book_b.best_ask
        net_yield_2 = spread_2 - self.total_fee_margin

        if net_yield_1 > self.min_profit_margin:
            return "BUY_A_SELL_B", net_yield_1 * 10000.0
        elif net_yield_2 > self.min_profit_margin:
            return "BUY_B_SELL_A", net_yield_2 * 10000.0
        
        return "NO_TRADE", max(net_yield_1, net_yield_2) * 10000.0


# --- Dashboard UI Header ---
st.title("⚡ Algorithmic High-Frequency Arbitrage Feasibility Engine")
st.markdown("Real-time simulation monitoring order book spreads, execution latency, and net profit.")

# --- Sidebar Controls ---
st.sidebar.header("Strategy Configuration")
min_spread_bps = st.sidebar.slider("Min Profit Threshold (bps)", 1.0, 20.0, 5.0, 0.5)
taker_fee_bps = st.sidebar.slider("Taker Fee per Leg (bps)", 0.0, 10.0, 1.5, 0.5)
trade_size_usd = st.sidebar.number_input("Trade Size ($)", value=100000, step=10000)
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 0.2, 2.0, 0.5, 0.1)
run_simulation = st.sidebar.checkbox("Run Live Feed Simulation", value=True)

# --- Session State Data Caching ---
if "log_data" not in st.session_state:
    st.session_state.log_data = pd.DataFrame(
        columns=["Timestamp", "Direction", "Spread_bps", "Latency_ms", "Profit_USD"]
    )

# --- Initialize Engine Instance ---
engine = ArbitrageEngine(min_profit_bps=min_spread_bps, taker_fee_bps=taker_fee_bps)

# --- Top Level Metric Containers ---
col1, col2, col3, col4 = st.columns(4)
m_price_a = col1.empty()
m_price_b = col2.empty()
m_spread = col3.empty()
m_pnl = col4.empty()

st.divider()

# --- Visualization Placeholders ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Live Net Spread Monitor (bps)")
    chart_spot = st.empty()

with col_right:
    st.subheader("Execution Latency Distribution (ms)")
    latency_spot = st.empty()

st.subheader("Order Execution Logs")
table_spot = st.empty()

# --- Live Execution / Simulation Loop ---
base_price = 50000.0

if run_simulation:
    for _ in range(30):  # Runs continuous loop cycles per execution
        # 1. Simulate market order book price noise
        bid_a = round(base_price + np.random.normal(0, 4), 2)
        ask_a = round(bid_a + 0.5, 2)
        bid_b = round(base_price + np.random.normal(0, 4), 2)
        ask_b = round(bid_b + 0.5, 2)

        book_a = OrderBook("Exchange_A", bid_a, ask_a)
        book_b = OrderBook("Exchange_B", bid_b, ask_b)

        # 2. Evaluate Arbitrage Signal
        signal, net_spread_bps = engine.evaluate_spread(book_a, book_b)
        latency_ms = round(np.random.uniform(0.5, 3.5), 2)

        # 3. Log Trade if Opportunity Exceeds Threshold
        if signal != "NO_TRADE":
            profit = round(trade_size_usd * (net_spread_bps / 10000.0), 2)
            new_row = pd.DataFrame([{
                "Timestamp": time.strftime("%H:%M:%S"),
                "Direction": signal,
                "Spread_bps": round(net_spread_bps, 2),
                "Latency_ms": latency_ms,
                "Profit_USD": profit
            }])
            st.session_state.log_data = pd.concat([new_row, st.session_state.log_data]).head(25)

        # 4. Refresh Dashboard Top Metrics
        m_price_a.metric("Exchange A (Bid / Ask)", f"${bid_a} / ${ask_a}")
        m_price_b.metric("Exchange B (Bid / Ask)", f"${bid_b} / ${ask_b}")
        m_spread.metric("Net Spread Margin", f"{net_spread_bps:.2f} bps")
        
        total_pnl = st.session_state.log_data["Profit_USD"].sum() if not st.session_state.log_data.empty else 0.0
        m_pnl.metric("Total Net Profit", f"${total_pnl:,.2f}")

        # 5. Refresh Visualizations & Log Tables
        if not st.session_state.log_data.empty:
            fig_spread = px.line(
                st.session_state.log_data, 
                x="Timestamp", 
                y="Spread_bps", 
                title="Spread History", 
                markers=True
            )
            chart_spot.plotly_chart(fig_spread, use_container_width=True)

            fig_lat = px.histogram(
                st.session_state.log_data, 
                x="Latency_ms", 
                nbins=8, 
                title="Latency Distribution", 
                color_discrete_sequence=['#00CC96']
            )
            latency_spot.plotly_chart(fig_lat, use_container_width=True)

            table_spot.dataframe(st.session_state.log_data, use_container_width=True)

        time.sleep(refresh_interval)