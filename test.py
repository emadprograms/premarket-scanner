import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, time
import yfinance as yf

# --- Page Config ---
st.set_page_config(page_title="Pre-Market Time Matrix", layout="wide")

# --- Helper Functions ---

def get_real_market_data(ticker="SPY"):
    """
    Fetches real 1-minute data using yfinance.
    Extracts the most recent day that has valid pre-market data (04:00 - 09:30 ET).
    """
    try:
        # Fetch 5 days of data to ensure we catch the last trading session
        # interval='1m' gives us the granularity we need
        # prepost=True is CRITICAL to get pre-market data
        stock = yf.Ticker(ticker)
        df = stock.history(period="5d", interval="1m", prepost=True)
        
        if df.empty:
            return None, "No data received from API."

        # Ensure index is datetime and handle timezones
        df.reset_index(inplace=True)
        
        # Convert to US/Eastern time if timezone aware, or localize if naive
        # yfinance usually returns UTC or America/New_York. 
        # We normalize to ensure our hour checks (4am-9:30am) are correct.
        if df['Datetime'].dt.tz is None:
             df['Datetime'] = df['Datetime'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
        else:
             df['Datetime'] = df['Datetime'].dt.tz_convert('America/New_York')

        df['Date'] = df['Datetime'].dt.date
        
        # Iterate backwards through dates to find one with good pre-market data
        unique_dates = sorted(df['Date'].unique(), reverse=True)
        
        for date in unique_dates:
            day_data = df[df['Date'] == date].copy()
            
            # Filter for Pre-Market: 04:00 <= Time < 09:30
            # 9:30 AM is hour 9, minute 30
            mask = (
                (day_data['Datetime'].dt.hour >= 4) & 
                (
                    (day_data['Datetime'].dt.hour < 9) | 
                    ((day_data['Datetime'].dt.hour == 9) & (day_data['Datetime'].dt.minute < 30))
                )
            )
            pre_market_df = day_data[mask].copy()
            
            # If we have a decent amount of data points (e.g. > 10 mins of pre-market), use it
            if len(pre_market_df) > 10:
                # Rename cols to match our app structure
                pre_market_df = pre_market_df[['Datetime', 'Open', 'High', 'Low', 'Close']]
                pre_market_df.rename(columns={'Datetime': 'Timestamp'}, inplace=True)
                return pre_market_df, None
                
        return None, "No pre-market data (04:00-09:30) found in the last 5 days."
        
    except Exception as e:
        return None, str(e)

def generate_synthetic_data(start_price=150.0, volatility=0.2, num_points=330):
    """
    Fallback: Generates synthetic data if real data fails.
    """
    start_time = datetime.strptime("04:00", "%H:%M")
    timestamps = [start_time + timedelta(minutes=i) for i in range(num_points)]
    
    close_prices = [start_price]
    for _ in range(num_points - 1):
        change = np.random.normal(0, volatility)
        close_prices.append(close_prices[-1] + change)
    
    opens = [start_price] + close_prices[:-1]
    highs = []
    lows = []
    
    for o, c in zip(opens, close_prices):
        noise_h = abs(np.random.normal(0, volatility * 0.5))
        noise_l = abs(np.random.normal(0, volatility * 0.5))
        highs.append(max(o, c) + noise_h)
        lows.append(min(o, c) - noise_l)

    return pd.DataFrame({
        'Timestamp': timestamps, 
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': close_prices
    })

def create_market_matrix(df, price_bucket_size=0.10, time_block_minutes=30):
    """
    Converts linear price history into a 2D Matrix (Grid).
    """
    # 1. Bucket the Time
    df['TimeBlock'] = df['Timestamp'].apply(
        lambda x: x.replace(minute=(x.minute // time_block_minutes) * time_block_minutes, second=0)
    )
    df['TimeBlockStr'] = df['TimeBlock'].apply(lambda x: x.strftime('%H:%M'))
    
    # 2. Bucket the Price
    df['PriceBucket'] = (df['Close'] / price_bucket_size).round() * price_bucket_size
    
    # 3. Create the Matrix
    matrix = df.groupby(['PriceBucket', 'TimeBlockStr']).size().unstack(fill_value=0)
    matrix = matrix.sort_index(ascending=False)
    
    return matrix

def generate_market_narrative(matrix, bucket_size, total_tpo, global_poc, recent_poc):
    """
    Analyzes the TPO Matrix to generate a human-readable interpretation of the session,
    focusing on the chronological story of value migration.
    """
    narrative = []
    
    # --- Contextual Stats ---
    prices = total_tpo.index.astype(float)
    session_high = prices.max()
    session_low = prices.min()
    session_range = session_high - session_low
    midpoint = session_low + (session_range / 2)
    
    # --- 1. The Stage (Floor & Ceiling) ---
    narrative.append("#### 1. The Arena (Context)")
    narrative.append(f"Before analyzing the movement, we must define the battlefield. The pre-market participant established a hard ceiling at **${session_high:.2f}** and a hard floor at **${session_low:.2f}**.")
    narrative.append(f"Everything analyzed below happened within this **${session_range:.2f}** range.")
    
    # --- 2. The Story of Migration (Phases) ---
    narrative.append("\n#### 2. The Narrative of Value (Chronological)")
    narrative.append(f"Scanning the session from start to finish, here is how value migrated between the floor (${session_low:.2f}) and ceiling (${session_high:.2f}):")
    
    # Algorithm: Group consecutive time blocks with similar POCs into "Phases"
    block_pocs = matrix.idxmax()
    phases = []
    
    if not block_pocs.empty:
        # Initialize first phase
        current_phase = {
            'start_time': block_pocs.index[0],
            'end_time': block_pocs.index[0],
            'prices': [block_pocs.iloc[0]]
        }
        
        for time_str, price in block_pocs.iloc[1:].items():
            avg_phase_price = sum(current_phase['prices']) / len(current_phase['prices'])
            # If the new price is within a small threshold of the current phase average, keep it in the same phase
            if abs(price - avg_phase_price) <= (bucket_size * 2):
                current_phase['end_time'] = time_str
                current_phase['prices'].append(price)
            else:
                # Close old phase
                current_phase['avg_price'] = sum(current_phase['prices']) / len(current_phase['prices'])
                phases.append(current_phase)
                # Start new phase
                current_phase = {
                    'start_time': time_str,
                    'end_time': time_str,
                    'prices': [price]
                }
        # Append final phase
        current_phase['avg_price'] = sum(current_phase['prices']) / len(current_phase['prices'])
        phases.append(current_phase)

    # Narrative Generation for Phases
    for i, phase in enumerate(phases):
        avg_price = phase['avg_price']
        
        # Determine location relative to range
        loc_desc = "Mid-Range"
        if avg_price > midpoint + (session_range * 0.2): loc_desc = "High (Near Ceiling)"
        elif avg_price < midpoint - (session_range * 0.2): loc_desc = "Low (Near Floor)"
        
        price_tag = f"**${avg_price:.2f}**"
        time_tag = f"_{phase['start_time']} to {phase['end_time']}_"
        
        if i == 0:
            narrative.append(f"- **Phase 1 (Opening Bid):** The session began with the market accepting value at {price_tag}. This established the initial {loc_desc} baseline between {time_tag}.")
        else:
            prev_price = phases[i-1]['avg_price']
            diff = avg_price - prev_price
            direction = "HIGHER" if diff > 0 else "LOWER"
            narrative.append(f"- **Phase {i+1} (Migration):** Value then migrated **{direction}** to {price_tag}. The market shifted its acceptance to the {loc_desc} area during {time_tag}.")

    # --- 3. Accepted Areas (Key Levels) ---
    narrative.append("\n#### 3. Key Levels for the Open")
    narrative.append("Based on the migration story above, here are the critical levels where 'Time' was spent:")
    narrative.append(f"- **The Anchor (Global POC):** **${global_poc:.2f}**. This is the price the market agreed on most. It acts as the center of gravity.")
    narrative.append(f"- **The Current Edge (Recent POC):** **${recent_poc:.2f}**. This is where the market is finishing.")
    
    return "\n".join(narrative)

# --- Main App Interface ---

st.title("🧩 Pre-Market Time-Price Matrix")
st.markdown("""
This tool visualizes the **intersection of Time and Price** (TPO) using **Real Market Data**.
It helps identify where value is being accepted before the market opens.
""")

# --- Sidebar Controls ---
st.sidebar.header("Data Source")
data_source = st.sidebar.radio("Source", ["Real Data (yfinance)", "Synthetic (Random)"])

if data_source == "Real Data (yfinance)":
    ticker_symbol = st.sidebar.text_input("Ticker Symbol", value="SPY").upper()
    if st.sidebar.button("Fetch Real Data"):
        with st.spinner(f"Fetching pre-market data for {ticker_symbol}..."):
            df_real, error = get_real_market_data(ticker_symbol)
            if df_real is not None:
                st.session_state['data'] = df_real
                st.sidebar.success(f"Loaded {len(df_real)} mins of data for {ticker_symbol}")
            else:
                st.sidebar.error(f"Error: {error}")
                
elif data_source == "Synthetic (Random)":
    volatility = st.sidebar.slider("Market Volatility", 0.05, 0.50, 0.15)
    if st.sidebar.button("Generate Random"):
        st.session_state['data'] = generate_synthetic_data(volatility=volatility)

st.sidebar.divider()
st.sidebar.header("Matrix Settings")
bucket_size = st.sidebar.select_slider("Price Bucket Size ($)", options=[0.01, 0.05, 0.10, 0.25, 0.50, 1.00], value=0.10)
time_block = st.sidebar.selectbox("Time Block Split (Mins)", options=[15, 30, 60], index=1)


# Initialize data if not present (Default to Synthetic for safety if API fails on first load)
if 'data' not in st.session_state:
    st.session_state['data'] = generate_synthetic_data()

df = st.session_state['data']

# --- Processing ---
matrix = create_market_matrix(df, bucket_size, time_block)

# --- Visualization ---

tab1, tab2 = st.tabs(["Visualization", "Raw Data"])

with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # 1. HEATMAP (The Matrix)
        st.subheader("1. Time Density (TPO) Matrix")
        
        # Dynamic height based on number of price levels to prevent squashing
        heatmap_height = max(400, len(matrix) * 15) 
        
        fig_matrix = go.Figure(data=go.Heatmap(
            z=matrix.values,
            x=matrix.columns,
            y=matrix.index,
            colorscale='Viridis',
            colorbar=dict(title='Mins'),
            hovertemplate='Time: %{x}<br>Price: $%{y}<br>Duration: %{z} mins<extra></extra>'
        ))

        fig_matrix.update_layout(
            height=heatmap_height,
            margin=dict(b=0),
            xaxis_title=None,
            yaxis_title='Price Zones',
            template='plotly_dark'
        )
        st.plotly_chart(fig_matrix, use_container_width=True)

        # 2. CANDLESTICK CHART
        st.subheader("2. Price Action (Candlesticks)")
        fig_candle = go.Figure(data=[go.Candlestick(
            x=df['Timestamp'],
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name='Price'
        )])
        
        fig_candle.update_layout(
            height=400,
            xaxis_rangeslider_visible=False,
            xaxis_title='Time',
            yaxis_title='Price',
            template='plotly_dark',
            margin=dict(t=0)
        )
        st.plotly_chart(fig_candle, use_container_width=True)

    with col2:
        st.subheader("Detailed Interpretation")
        
        # Calculate Total TPO (Summing horizontally)
        total_tpo = matrix.sum(axis=1)
        if not total_tpo.empty:
            max_tpo_price = total_tpo.idxmax()
            
            # Recent TPO (Last column analysis)
            last_col = matrix.columns[-1]
            recent_tpo = matrix[last_col]
            recent_poc = recent_tpo.idxmax()
            
            # Metrics
            st.metric(label="Global POC (Avg Value)", value=f"${max_tpo_price:.2f}")
            st.metric(label=f"Recent POC ({last_col})", value=f"${recent_poc:.2f}")
            
            st.markdown("---")
            
            # --- GENERATE NARRATIVE ---
            narrative_text = generate_market_narrative(matrix, bucket_size, total_tpo, max_tpo_price, recent_poc)
            st.markdown(narrative_text)
            
        else:
            st.warning("Not enough data to calculate TPO.")
            
        st.markdown("---")
        st.caption("Compare the Heatmap (Top) with the Candles (Bottom). Notice how 'wicks' in the candles often correspond to dark/empty areas in the Heatmap (Rejection), while solid bodies align with bright spots (Acceptance).")

with tab2:
    st.write("### Matrix Data")
    st.dataframe(matrix)
    st.write("### Price Data")
    st.dataframe(df)