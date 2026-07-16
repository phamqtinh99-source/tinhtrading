import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time

# Set Page Config
st.set_page_config(
    page_title="Underground Trading Terminal v2",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply CSS Styling
st.markdown("""
<style>
    .reportview-container {
        background: #0f111a;
    }
    .main .block-container {
        padding-top: 2rem;
    }
    h1, h2, h3 {
        color: #00ffcc !important;
    }
    .stButton>button {
        background-color: #00ffcc;
        color: black;
        font-weight: bold;
        border-radius: 5px;
    }
    .stButton>button:hover {
        background-color: #00cc99;
        color: black;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to send Telegram messages
def send_telegram_message(token, chat_id, text):
    if not token or not chat_id:
        return False, "Thiếu Token hoặc Chat ID!"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True, "Gửi tin nhắn Telegram thành công!"
        else:
            return False, f"Lỗi từ Telegram API: {response.text}"
    except Exception as e:
        return False, f"Lỗi kết nối: {str(e)}"

# Mock Data Generator (Fallback when offline)
def get_mock_klines(symbol):
    np.random.seed(42 + hash(symbol) % 100)
    num_candles = 100
    dates = [datetime.now() - timedelta(hours=4*i) for i in range(num_candles)][::-1]
    
    # Generate prices
    prices = [100.0]
    for _ in range(num_candles - 1):
        change = np.random.normal(0.001, 0.015)
        prices.append(prices[-1] * (1 + change))
        
    df = pd.DataFrame(index=range(num_candles))
    df['open_time'] = dates
    df['close_time'] = dates
    df['open'] = prices
    df['high'] = [p * (1 + np.random.uniform(0, 0.02)) for p in prices]
    df['low'] = [p * (1 - np.random.uniform(0, 0.02)) for p in prices]
    df['close'] = [np.random.uniform(l, h) for l, h in zip(df['low'], df['high'])]
    df['volume'] = np.random.uniform(100, 1000, num_candles)
    return df

# Fetch Binance Futures Candles
def fetch_binance_futures_klines(symbol, interval="4h", limit=100):
    symbol_upper = f"{symbol.upper()}USDT"
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol_upper,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df, False
        else:
            return get_mock_klines(symbol), True
    except Exception:
        return get_mock_klines(symbol), True

# Fetch Funding Rate
def fetch_funding_rate(symbol):
    symbol_upper = f"{symbol.upper()}USDT"
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    params = {"symbol": symbol_upper}
    try:
        response = requests.get(url, params=params, timeout=3)
        if response.status_code == 200:
            data = response.json()
            funding_rate = float(data.get('lastFundingRate', 0.0)) * 100
            next_funding_time = int(data.get('nextFundingTime', 0)) / 1000
            next_funding_dt = datetime.fromtimestamp(next_funding_time)
            return funding_rate, next_funding_dt, False
        return 0.01, datetime.now() + timedelta(hours=4), True
    except Exception:
        return 0.01, datetime.now() + timedelta(hours=4), True

# Indicators Calculations
def calculate_indicators(df):
    # EMAs
    df['ema_34'] = df['close'].ewm(span=34, adjust=False).mean()
    df['ema_89'] = df['close'].ewm(span=89, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd'] - df['signal']
    
    return df

# Find Peaks and Troughs for DOW Structure
def find_peaks_troughs(df, order=5):
    highs = df['high'].values
    lows = df['low'].values
    peaks = []
    troughs = []
    
    for i in range(order, len(df) - order):
        if all(highs[i] >= highs[i-j] for j in range(1, order+1)) and all(highs[i] >= highs[i+j] for j in range(1, order+1)):
            peaks.append((i, highs[i]))
        if all(lows[i] <= lows[i-j] for j in range(1, order+1)) and all(lows[i] <= lows[i+j] for j in range(1, order+1)):
            troughs.append((i, lows[i]))
            
    return peaks, troughs

# Detect RSI/MACD Divergence
def detect_divergence(df, peaks, troughs):
    divergences = []
    
    # 1. Bearish Divergence (Phân kỳ giảm) - Price higher highs, Indicator lower highs
    if len(peaks) >= 2:
        for i in range(len(peaks) - 1):
            idx1, val1 = peaks[i]
            idx2, val2 = peaks[i+1]
            if val2 > val1: # Higher High in Price
                # Check RSI
                rsi1 = df['rsi'].iloc[idx1]
                rsi2 = df['rsi'].iloc[idx2]
                if rsi2 < rsi1 and df['macd'].iloc[idx2] > 0: # Lower High in RSI
                    divergences.append({
                        'type': 'Bearish Divergence (Phân kỳ giảm)',
                        'indicator': 'RSI',
                        'p1': (df['open_time'].iloc[idx1], val1),
                        'p2': (df['open_time'].iloc[idx2], val2),
                        'details': f"Giá tạo Đỉnh Cao Hơn (${val2:.2f} > ${val1:.2f}) nhưng RSI tạo Đỉnh Thấp Hơn ({rsi2:.1f} < {rsi1:.1f}) trên mốc 0."
                    })
                # Check MACD Hist
                hist1 = df['histogram'].iloc[idx1]
                hist2 = df['histogram'].iloc[idx2]
                if hist2 < hist1 and df['macd'].iloc[idx2] > 0:
                    divergences.append({
                        'type': 'Bearish Divergence (Phân kỳ giảm)',
                        'indicator': 'MACD Histogram',
                        'p1': (df['open_time'].iloc[idx1], val1),
                        'p2': (df['open_time'].iloc[idx2], val2),
                        'details': f"Giá tạo Đỉnh Cao Hơn (${val2:.2f} > ${val1:.2f}) nhưng MACD Histogram tạo Đỉnh Thấp Hơn ({hist2:.4f} < {hist1:.4f})."
                    })

    # 2. Bullish Convergence (Hội tụ tăng) - Price lower lows, Indicator higher lows
    if len(troughs) >= 2:
        for i in range(len(troughs) - 1):
            idx1, val1 = troughs[i]
            idx2, val2 = troughs[i+1]
            if val2 < val1: # Lower Low in Price
                # Check RSI
                rsi1 = df['rsi'].iloc[idx1]
                rsi2 = df['rsi'].iloc[idx2]
                if rsi2 > rsi1 and df['macd'].iloc[idx2] < 0: # Higher Low in RSI
                    divergences.append({
                        'type': 'Bullish Convergence (Hội tụ tăng)',
                        'indicator': 'RSI',
                        'p1': (df['open_time'].iloc[idx1], val1),
                        'p2': (df['open_time'].iloc[idx2], val2),
                        'details': f"Giá tạo Đáy Thấp Hơn (${val2:.2f} < ${val1:.2f}) nhưng RSI tạo Đáy Cao Hơn ({rsi2:.1f} > {rsi1:.1f}) dưới mốc 0."
                    })
                # Check MACD Hist
                hist1 = df['histogram'].iloc[idx1]
                hist2 = df['histogram'].iloc[idx2]
                if hist2 > hist1 and df['macd'].iloc[idx2] < 0:
                    divergences.append({
                        'type': 'Bullish Convergence (Hội tụ tăng)',
                        'indicator': 'MACD Histogram',
                        'p1': (df['open_time'].iloc[idx1], val1),
                        'p2': (df['open_time'].iloc[idx2], val2),
                        'details': f"Giá tạo Đáy Thấp Hơn (${val2:.2f} < ${val1:.2f}) nhưng MACD Histogram tạo Đáy Cao Hơn ({hist2:.4f} > {hist1:.4f})."
                    })
                    
    return divergences

# Initialize Journal in Session State
if 'journal' not in st.session_state:
    st.session_state.journal = pd.DataFrame(columns=[
        'Thời gian', 'Coin', 'Vị thế', 'Entry', 'Stop Loss', 'Take Profit', 'Phí', 'Kết quả PnL (USDT)', 'Bài học xương máu'
    ])

# ================= PAGE HEADER =================
st.title("📉 Underground Trading Terminal v2")
st.caption("Thiết kế theo triết lý của sếp Jesse J.L & Downcome - Trường Đại Học Underground. Bản nâng cấp Telegram Bot Alerts.")

# ================= SIDEBAR CẤU HÌNH BOT TELEGRAM =================
st.sidebar.header("🔌 Cấu Hình Telegram Bot Alerts")
st.sidebar.markdown("""
Bạn có thể nhận thông báo phân kỳ H4 trực tiếp về điện thoại bằng cách tạo một Bot qua `@BotFather` trên Telegram.
""")

bot_token = st.sidebar.text_input("Telegram Bot Token", type="password", help="Ví dụ: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
chat_id = st.sidebar.text_input("Telegram Chat ID", help="ID của nhóm hoặc tài khoản cá nhân của bạn (Dùng @userinfobot để lấy)")

# Test Button
if st.sidebar.button("🔔 Gửi Tin Nhắn Thử Nghiệm"):
    if bot_token and chat_id:
        test_msg = "<b>[TEST]</b> Cảnh báo kết nối Telegram Bot thành công từ Trading Terminal v2! 🚀"
        success, msg = send_telegram_message(bot_token, chat_id, test_msg)
        if success:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)
    else:
        st.sidebar.warning("Vui lòng điền đủ Token và Chat ID để kiểm thử!")

# Watchlist configuration
watchlist = ["BTC", "ETH", "BNB", "SOL", "LINK", "ADA"]

# Create Tabs
tab1, tab2, tab3 = st.tabs([
    "📈 Xu Hướng & Cảnh Báo Phân Kỳ (H4)",
    "🧮 Bảng Tính Vol & Phí Thực Chiến",
    "📝 Nhật Ký Giao Dịch & Sửa Sai"
])

# ================= TAB 1: XU HƯỚNG & CẢNH BÁO PHÂN KỲ =================
with tab1:
    st.subheader("🔥 Quét Xu Hướng & Cản Động/Tĩnh Khung H4")
    
    # Active symbol selector
    selected_coin = st.selectbox("Chọn đồng Coin để phân tích sâu:", watchlist)
    
    # Fetch Data
    df, is_mock = fetch_binance_futures_klines(selected_coin, interval="4h", limit=100)
    df = calculate_indicators(df)
    
    # Fetch Funding info
    funding_rate, next_funding_dt, _ = fetch_funding_rate(selected_coin)
    
    if is_mock:
        st.warning("⚠️ Đang hoạt động ở chế độ Offline (Dữ liệu giả lập mượt mà). Khi chạy online, app sẽ tự động kết nối API Binance Futures thực tế.")
    else:
        st.success("🔌 Kết nối API Binance Futures Thành công!")

    # Grid Info
    col1, col2, col3, col4 = st.columns(4)
    current_price = df['close'].iloc[-1]
    ema_34 = df['ema_34'].iloc[-1]
    ema_89 = df['ema_89'].iloc[-1]
    
    # Determine Trend based on EMA 34/89
    if current_price > ema_34 and current_price > ema_89:
        trend_status = "UPTREND (Canh Mua)"
        trend_color = "green"
    elif current_price < ema_34 and current_price < ema_89:
        trend_status = "DOWNTREND (Canh Bán)"
        trend_color = "red"
    else:
        trend_status = "SIDEWAY (Đứng Ngoài Quan Sát)"
        trend_color = "orange"

    col1.metric("Giá Hiện Tại", f"${current_price:,.2f}")
    col2.metric("Xu Hướng Chủ Đạo", trend_status, delta=None)
    col3.metric("Funding Rate", f"{funding_rate:.4f}%")
    
    # Funding Rate Countdown warning
    seconds_to_funding = (next_funding_dt - datetime.now()).total_seconds()
    if seconds_to_funding > 0:
        hours = int(seconds_to_funding // 3600)
        minutes = int((seconds_to_funding % 3600) // 60)
        col4.metric("Kỳ Thanh Toán Phí", f"{hours}h {minutes}m nữa", help="Cẩn thận giữ vị thế sát khung giờ thanh toán để tránh trả phí ngoài ý muốn!")
    else:
        col4.metric("Kỳ Thanh Toán Phí", "Đang cập nhật...")

    # Peaks & Troughs
    peaks, troughs = find_peaks_troughs(df)
    
    # Divergence Analysis
    divergences = detect_divergence(df, peaks, troughs)
    
    st.markdown("### 🔔 Cảnh Báo Phân Kỳ & Hội Tụ Trên Khung H4")
    if len(divergences) > 0:
        for div in divergences:
            st.warning(f"⚠️ **{div['type']}** detected via **{div['indicator']}** on {selected_coin}\n\n*Chi tiết:* {div['details']}")
            
            # Send Notification Button
            if bot_token and chat_id:
                if st.button(f"📲 Gửi cảnh báo {selected_coin} qua Telegram", key=f"tg_{selected_coin}_{div['indicator']}"):
                    tg_text = (
                        f"⚠️ <b>[CẢNH BÁO PHÂN KỲ H4]</b>\n"
                        f"• <b>Đồng Coin:</b> #{selected_coin}USDT\n"
                        f"• <b>Tín hiệu:</b> {div['type']}\n"
                        f"• <b>Chỉ báo:</b> {div['indicator']}\n"
                        f"• <b>Giá hiện tại:</b> ${current_price:,.4f}\n"
                        f"• <b>Chi tiết:</b> {div['details']}\n\n"
                        f"📢 <i>Kỷ luật là chén thánh! QLV rủi ro 1% - 2% trước khi kích hoạt lệnh!</i>"
                    )
                    success, msg = send_telegram_message(bot_token, chat_id, tg_text)
                    if success:
                        st.success("Cảnh báo đã được gửi lên nhóm Telegram thành công!")
                    else:
                        st.error(msg)
    else:
        st.info("Hiện tại chưa phát hiện tín hiệu phân kỳ/hội tụ rõ ràng trên khung H4 của đồng coin này. Hãy an tâm đứng ngoài hoặc giữ lệnh theo xu hướng.")

    # Plot chart
    fig = go.Figure()
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df['open_time'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="Đường Giá"
    ))
    # EMAs
    fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_34'], name="EMA 34 (Cản động ngắn)", line=dict(color='#00ffcc', width=1.5)))
    fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_89'], name="EMA 89 (Xu thế chính)", line=dict(color='#ff3366', width=2)))
    
    # Peaks/Troughs annotation on chart
    for idx, val in peaks:
        fig.add_annotation(x=df['open_time'].iloc[idx], y=val, text="Đỉnh DOW", showarrow=True, arrowhead=1, color='yellow')
    for idx, val in troughs:
        fig.add_annotation(x=df['open_time'].iloc[idx], y=val, text="Đáy DOW", showarrow=True, arrowhead=1, color='#00ffcc')

    fig.update_layout(
        title=f"Biểu đồ phân tích {selected_coin}USDT H4 - Lý thuyết Dow và EMA",
        yaxis_title="Giá (USDT)",
        xaxis_title="Thời gian",
        template="plotly_dark",
        height=500,
        xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig, use_container_width=True)

# ================= TAB 2: BẢNG TÍNH VOLUME & PHÍ THỰC CHIẾN =================
with tab2:
    st.subheader("🧮 Bảng Tính Volume Vào Lệnh & Phí Thực Tế")
    st.caption("Quản lý rủi ro 1%-2% chặt chẽ theo Elder & sếp Jess. Tuyệt đối gồng lời chứ không bao giờ gồng lỗ!")

    col_inp1, col_inp2 = st.columns(2)
    with col_inp1:
        total_balance = st.number_input("Tổng vốn tài khoản của bạn (USDT):", value=1000.0, step=100.0)
        risk_pct = st.slider("Mức rủi ro chấp nhận cho mỗi lệnh (%):", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
        entry_price = st.number_input("Điểm vào lệnh mong muốn (Entry):", value=current_price, step=0.1)
        stop_loss = st.number_input("Điểm dừng lỗ tuyệt đối (Stop Loss):", value=current_price*0.97, step=0.1)
        leverage = st.number_input("Đòn bẩy mong muốn (X):", min_value=1, max_value=125, value=10, step=1)
    
    with col_inp2:
        take_profit = st.number_input("Điểm chốt lời kỳ vọng (Take Profit):", value=current_price*1.06, step=0.1)
        st.markdown("##### 🧾 Thiết lập phí giao dịch của Binance")
        vip_level = st.selectbox("Cấp độ VIP của bạn trên Binance:", [f"VIP {i}" for i in range(10)])
        order_type = st.radio("Phương thức khớp lệnh (Phí Maker/Taker):", ["Maker (Lệnh Limit)", "Taker (Lệnh Market)"])
        pay_with_bnb = st.checkbox("Sử dụng BNB để thanh toán phí (Giảm 10% phí Futures)", value=True)
        zero_maker_promo = st.checkbox("Áp dụng ưu đãi Maker 0% cho cặp U-Margined", value=False)

    # Risk and Volume Calculations
    risk_amount = total_balance * (risk_pct / 100.0)
    sl_distance = abs(entry_price - stop_loss)
    sl_pct = (sl_distance / entry_price) * 100.0
    
    # Avoid Division by Zero
    if sl_distance > 0:
        # Vol = Risk / SL %
        position_vol = risk_amount / (sl_pct / 100.0)
        required_margin = position_vol / leverage
        coin_amount = position_vol / entry_price
        
        # Risk Reward Ratio
        tp_distance = abs(take_profit - entry_price)
        rr_ratio = tp_distance / sl_distance
    else:
        position_vol = 0
        required_margin = 0
        coin_amount = 0
        rr_ratio = 0

    # Fee Calculations
    # Standard VIP 0 Futures Fees: Maker = 0.02%, Taker = 0.04%
    vip_fees = {
        "VIP 0": (0.02, 0.04), "VIP 1": (0.016, 0.04), "VIP 2": (0.014, 0.035),
        "VIP 3": (0.012, 0.032), "VIP 4": (0.01, 0.03), "VIP 5": (0.008, 0.028),
        "VIP 6": (0.006, 0.026), "VIP 7": (0.004, 0.024), "VIP 8": (0.002, 0.022),
        "VIP 9": (0.0, 0.02)
    }
    
    maker_rate, taker_rate = vip_fees[vip_level]
    fee_rate = (0.0 if zero_maker_promo else maker_rate) if "Maker" in order_type else taker_rate
    fee_rate_pct = fee_rate / 100.0
    
    if pay_with_bnb:
        fee_rate_pct *= 0.9 # 10% discount
        
    entry_fee = position_vol * fee_rate_pct
    exit_fee = (position_vol * (take_profit / entry_price)) * fee_rate_pct
    total_estimated_fee = entry_fee + exit_fee
    
    # PnL Calculations
    raw_profit = (abs(take_profit - entry_price) / entry_price) * position_vol
    net_profit = raw_profit - total_estimated_fee

    # Display Calculations Grid
    st.markdown("### 📊 Thông Số Khuyến Nghị Lên Lệnh")
    col_out1, col_out2, col_out3 = st.columns(3)
    
    with col_out1:
        st.metric("Số tiền rủi ro tối đa (1% - 2%)", f"${risk_amount:.2f}")
        st.metric("Khoảng cách cắt lỗ (%)", f"{sl_pct:.2f}%")
        st.metric("Số vốn ký quỹ thực tế (Margin)", f"${required_margin:.2f}")

    with col_out2:
        st.metric("TỔNG VOLUME VÀO LỆNH (VỊ THẾ)", f"${position_vol:,.2f}")
        st.metric("Số lượng coin cần mua/bán", f"{coin_amount:.4f} {selected_coin}")
        st.metric("Tổng phí giao dịch ước tính", f"${total_estimated_fee:.4f}", delta=f"-{fee_rate_pct*100:.4f}%")

    with col_out3:
        st.metric("Tỷ lệ Risk / Reward (R:R)", f"1 : {rr_ratio:.2f}")
        if rr_ratio < 1.0:
            st.error("🚨 Tỷ lệ R:R dưới 1:1! Đây là vị thế rủi ro quá cao, sếp Jess khuyên nên hủy lệnh và đứng ngoài!")
        else:
            st.success("✅ Tỷ lệ R:R hợp lệ để vào lệnh.")
        st.metric("LỢI NHUẬN RÒNG SAU PHÍ (Net PnL)", f"${net_profit:.2f}", delta=f"{raw_profit:.2f} (Trước phí)")

# ================= TAB 3: NHẬT KÝ GIAO DỊCH =================
with tab3:
    st.subheader("📝 Nhật Ký Giao Dịch - Sửa Sai Bản Thân")
    st.caption("Hãy viết nhật ký đều đặn để rèn luyện kỷ luật thép và loại bỏ cảm xúc thù hận thị trường!")

    with st.form("journal_entry_form"):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            form_coin = st.text_input("Đồng Coin:", value=selected_coin)
            form_side = st.selectbox("Vị thế (Long/Short):", ["Long", "Short"])
        with col_f2:
            form_entry = st.number_input("Giá Entry:", value=entry_price)
            form_sl = st.number_input("Giá Stop Loss:", value=stop_loss)
        with col_f3:
            form_tp = st.number_input("Giá Take Profit:", value=take_profit)
            form_pnl = st.number_input("Kết quả PnL thực tế sau phí (USDT):", value=0.0)
            
        form_lesson = st.text_area("Bài học xương máu rút ra (Tại sao đúng? Sai lầm cảm xúc nào đã mắc phải?):")
        submitted = st.form_submit_state = st.form_submit_button("💾 Lưu Lệnh Vào Nhật Ký")
        
        if submitted:
            new_row = {
                'Thời gian': datetime.now().strftime("%Y-%m-%d %H:%M"),
                'Coin': form_coin.upper(),
                'Vị thế': form_side,
                'Entry': form_entry,
                'Stop Loss': form_sl,
                'Take Profit': form_tp,
                'Phí': total_estimated_fee,
                'Kết quả PnL (USDT)': form_pnl,
                'Bài học xương máu': form_lesson
            }
            st.session_state.journal = pd.concat([st.session_state.journal, pd.DataFrame([new_row])], ignore_index=True)
            st.success("Đã ghi nhận nhật ký giao dịch thành công!")

    # Display Journal Table
    st.markdown("### 🗂️ Lịch Sử Nhật Ký Giao Dịch Đã Lưu")
    if len(st.session_state.journal) > 0:
        st.dataframe(st.session_state.journal, use_container_width=True)
        
        # Calculate stats
        total_pnl = st.session_state.journal['Kết quả PnL (USDT)'].sum()
        win_count = len(st.session_state.journal[st.session_state.journal['Kết quả PnL (USDT)'] > 0])
        total_trades = len(st.session_state.journal)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        st.markdown("### 📊 Thống Kê Hiệu Suất")
        col_st1, col_st2, col_st3 = st.columns(3)
        col_st1.metric("Tổng Số Lệnh", total_trades)
        col_st2.metric("Tổng PnL thực tế", f"${total_pnl:.2f}", delta=f"{total_pnl:.2f}")
        col_st3.metric("Tỷ Lệ Thắng (Win Rate)", f"{win_rate:.1f}%")
    else:
        st.info("Nhật ký hiện tại đang trống. Hãy bắt đầu lưu các lệnh thực chiến của bạn!")
