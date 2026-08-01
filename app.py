import streamlit as st
import pandas as pd
import numpy as np
import time
import plotly.express as px
from main import ArbitrageEngine, OrderBook

# --- Page Setup ---
st.set_page_config(
    page_title="HFT Arbitrage Feasibility Engine",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Algorithmic High-Frequency Arbitrage Feasibility Engine")
st.markdown("Real-time monitoring for order book spreads, execution latency, and net yield.")

# --- Sidebar Controls ---
st.sidebar.header("Strategy Configuration")
min_spread_bps = st.sidebar.slider("Min Profit Threshold (bps)", 1.0, 20.0, 5.0, 0.5)
taker_fee_bps = st.sidebar.slider("Taker Fee per Leg (bps)", 0.0, 10.0, 1.5, 0.5)
trade_size_usd = st.sidebar.number_input("Trade Size ($)", value=100000, step=10000)
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 0.2, 2.0, 0.5, 0.1)
run_simulation = st.sidebar.checkbox("Run Live Feed Simulation", value=True)

# --- State Initialization ---
if "log_data" not in st.session_state:
    st.session_state.log_data = pd.DataFrame(
        columns=["Timestamp", "Direction", "Spread_bps", "Latency_ms", "Profit_USD"]
    )

engine = ArbitrageEngine(min_profit_bps=min_spread_bps, taker_fee_bps=taker_fee_bps)

# --- Top Level Metrics Containers ---
col1, col2, col3, col4 = st.columns(4)
m_price_a = col1.empty()
m_price_b = col2.empty()
m_spread = col3.empty()
m_pnl = col4.empty()

st.divider()

# --- Visualizations & Table Placeholders ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Live Net Spread Monitor (bps)")
    chart_spot = st.empty()

with col_right:
    st.subheader("Execution Latency Distribution (ms)")
    latency_spot = st.empty()

st.subheader("Order Execution Logs")
table_spot = st.empty()

# --- Live Execution Loop ---
base_price = 50000.0

if run_simulation:
    for _ in range(30):
        # Generate market order book price noise
        bid_a = round(base_price + np.random.normal(0, 4), 2)
        ask_a = round(bid_a + 0.5, 2)
        bid_b = round(base_price + np.random.normal(0, 4), 2)
        ask_b = round(bid_b + 0.5, 2)

        book_a = OrderBook("Exchange_A", bid_a, ask_a)
        book_b = OrderBook("Exchange_B", bid_b, ask_b)

        signal, net_spread_bps = engine.evaluate_spread(book_a, book_b)
        latency_ms = round(np.random.uniform(0.5, 3.5), 2)

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

        # UI Refreshes
        m_price_a.metric("Exchange A (Bid / Ask)", f"${bid_a} / ${ask_a}")
        m_price_b.metric("Exchange B (Bid / Ask)", f"${bid_b} / ${ask_b}")
        m_spread.metric("Net Spread Margin", f"{net_spread_bps:.2f} bps")
        
        total_pnl = st.session_state.log_data["Profit_USD"].sum() if not st.session_state.log_data.empty else 0.0
        m_pnl.metric("Total Net Profit", f"${total_pnl:,.2f}")

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
