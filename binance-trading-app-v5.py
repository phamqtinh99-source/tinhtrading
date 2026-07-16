import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import datetime
import time

# Cấu hình giao diện Streamlit (phải ở ngay dòng đầu tiên)
st.set_page_config(
    page_title="Underground Trading Terminal v5",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PHẦN STYLE CSS ĐỂ BIẾN APP THÀNH TERMINAL PRO ---
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1f2937;
        border-radius: 4px 4px 0px 0px;
        color: #9ca3af;
        font-weight: bold;
        padding: 10px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
    }
    div[data-testid="metric-container"] {
        background-color: #111827;
        border: 1px solid #1f2937;
        padding: 12px;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: CẤU HÌNH API BINANCE & TELEGRAM ---
st.sidebar.title("⚡ TRẠM ĐIỀU HÀNH THỰC CHIẾN")
st.sidebar.markdown("---")

# 1. Cấu hình các API Endpoint đã đăng ký của Binance (Giải quyết vấn đề chặn IP)
st.sidebar.subheader("🌐 Cổng API Binance Futures")
api_endpoint_options = {
    "https://fapi.binance.com": "API Mặc định (fapi)",
    "https://fapi1.binance.com": "API Dự phòng 1 (fapi1)",
    "https://fapi2.binance.com": "API Dự phòng 2 (fapi2)",
    "https://fapi3.binance.com": "API Dự phòng 3 (fapi3)",
    "https://fapi-ext.binance.com": "Cổng API Ngoài (fapi-ext)"
}
selected_base_url = st.sidebar.selectbox(
    "Chọn máy chủ Binance kết nối trực tiếp:",
    options=list(api_endpoint_options.keys()),
    format_func=lambda x: api_endpoint_options[x]
)

# 2. Cấu hình Telegram Bot
st.sidebar.subheader("🤖 Cấu Hình Telegram Bot")
telegram_token = st.sidebar.text_input("Telegram Bot Token", type="password", placeholder="Nhập Token của @BotFather...")
telegram_chat_id = st.sidebar.text_input("Telegram Chat ID", placeholder="Nhập Chat ID từ @userinfobot...")

# Nút test kết nối Telegram
if st.sidebar.button("🔔 Gửi Tin Nhắn Thử Nghiệm"):
    if telegram_token and telegram_chat_id:
        test_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        test_payload = {
            "chat_id": telegram_chat_id,
            "text": "⚡ *Kết nối thành công!* Hệ thống cảnh báo phân kỳ H4 của bạn đã sẵn sàng.",
            "parse_mode": "Markdown"
        }
        try:
            r = requests.post(test_url, json=test_payload, timeout=5)
            if r.status_code == 200:
                st.sidebar.success("Đã gửi tin nhắn test thành công!")
            else:
                st.sidebar.error(f"Lỗi gửi tin: {r.text}")
        except Exception as e:
            st.sidebar.error(f"Không thể kết nối Telegram: {e}")
    else:
        st.sidebar.warning("Vui lòng điền đủ Token và Chat ID.")

# 3. Quản lý vốn cốt lõi
st.sidebar.subheader("💰 Quản Lý Vốn (Sếp Jess)")
total_capital = st.sidebar.number_input("Tổng Vốn Tài Khoản ($)", min_value=10.0, value=2000.0, step=100.0)
risk_percentage = st.sidebar.slider("Hạn mức rủi ro tối đa/lệnh (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
allowed_loss = total_capital * (risk_percentage / 100.0)
st.sidebar.info(f"Số tiền chấp nhận mất tối đa/lệnh: **${allowed_loss:.2f}** (Quy tắc {risk_percentage}%)")

# --- DANH SÁCH COIN THEO DÕI ---
watchlist_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT"]

# --- HÀM TẢI DỮ LIỆU TỪ BINANCE ---
@st.cache_data(ttl=15)
def fetch_binance_klines(symbol, interval='4h', limit=150, base_url="https://fapi.binance.com"):
    """
    Tải dữ liệu nến Futures trực tiếp từ cổng API được cấu hình.
    Tự động fallback sang Mock Data nếu gặp sự cố mạng/IP bị chặn.
    """
    url = f"{base_url}/fapi/v1/klines"
    params = {
        "symbol": symbol,
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
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df, False  # Trả về df thật, is_mock = False
    except Exception as e:
        pass
    
    # --- CHẾ ĐỘ DỰ PHÒNG NGOẠI TUYẾN (MOCK DATA FALLBACK) ---
    # Sinh dữ liệu ngẫu nhiên có xu hướng tăng/giảm giống thị trường thật
    np.random.seed(hash(symbol) % 1000)
    dates = pd.date_range(end=datetime.datetime.now(), periods=limit, freq='4h')
    
    # Bắt đầu với một giá cơ sở phù hợp với từng coin
    prices = {"BTCUSDT": 65000, "ETHUSDT": 3500, "BNBUSDT": 580, "SOLUSDT": 140, "LINKUSDT": 15, "ADAUSDT": 0.45}
    base_price = prices.get(symbol, 100)
    
    close_prices = [base_price]
    for _ in range(1, limit):
        # Mô phỏng quá trình dịch chuyển ngẫu nhiên
        change = np.random.normal(loc=0.0005, scale=0.015) 
        close_prices.append(close_prices[-1] * (1 + change))
        
    df = pd.DataFrame({
        'open_time': dates,
        'close': close_prices
    })
    
    df['open'] = df['close'].shift(1).fillna(base_price * 0.99)
    # Thêm một chút dao động ngẫu nhiên cho high và low
    df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.abs(np.random.normal(0, 0.008, limit)))
    df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.abs(np.random.normal(0, 0.008, limit)))
    df['volume'] = np.random.exponential(scale=1000, size=limit)
    
    return df, True  # Trả về df giả lập, is_mock = True

def get_funding_rate(symbol, base_url="https://fapi.binance.com"):
    """Lấy Funding Rate thời gian thực của Binance Futures"""
    url = f"{base_url}/fapi/v1/premiumIndex"
    params = {"symbol": symbol}
    try:
        r = requests.get(url, params=params, timeout=3)
        if r.status_code == 200:
            data = r.json()
            return float(data.get("lastFundingRate", 0.0001))
    except:
        pass
    return 0.0001 # Giá trị mặc định 0.01%

# --- THUẬT TOÁN KỸ THUẬT PHÂN TÍCH ---

def compute_indicators(df):
    """Tính EMA, RSI, MACD"""
    # 1. EMA 34 & EMA 89
    df['ema_34'] = df['close'].ewm(span=34, adjust=False).mean()
    df['ema_89'] = df['close'].ewm(span=89, adjust=False).mean()
    
    # 2. RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. MACD (12, 26, 9)
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema_12 - ema_26
    df['signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['signal_line']
    
    return df

def find_dow_points(df, window=5):
    """Tìm điểm đỉnh/đáy cục bộ để xác định cấu trúc DOW"""
    highs = []
    lows = []
    for i in range(window, len(df) - window):
        is_high = True
        is_low = True
        for j in range(1, window + 1):
            if df['high'].iloc[i] < df['high'].iloc[i-j] or df['high'].iloc[i] < df['high'].iloc[i+j]:
                is_high = False
            if df['low'].iloc[i] > df['low'].iloc[i-j] or df['low'].iloc[i] > df['low'].iloc[i+j]:
                is_low = False
        if is_high:
            highs.append(i)
        if is_low:
            lows.append(i)
    return highs, lows

def scan_divergence(df, highs, lows):
    """Quét phân kỳ / hội tụ RSI trên khung H4"""
    divergence_signal = "Không phát hiện"
    
    if len(highs) >= 2:
        # Lấy 2 đỉnh Dow gần nhất
        h1, h2 = highs[-2], highs[-1]
        price_diff = df['high'].iloc[h2] - df['high'].iloc[h1]
        rsi_diff = df['rsi'].iloc[h2] - df['rsi'].iloc[h1]
        
        # Đỉnh sau cao hơn đỉnh trước nhưng RSI đỉnh sau thấp hơn đỉnh trước -> Phân kỳ giảm
        if price_diff > 0 and rsi_diff < 0 and df['rsi'].iloc[h2] > 60:
            divergence_signal = "⚠️ BEARISH DIVERG_ENCE (Phân Kỳ Giảm H4 - Nguy Cơ Đảo Chiều!)"
            
    if len(lows) >= 2:
        # Lấy 2 đáy Dow gần nhất
        l1, l2 = lows[-2], lows[-1]
        price_diff = df['low'].iloc[l2] - df['low'].iloc[l1]
        rsi_diff = df['rsi'].iloc[l2] - df['rsi'].iloc[l1]
        
        # Đáy sau thấp hơn đáy trước nhưng RSI đáy sau cao hơn đáy trước -> Hội tụ tăng
        if price_diff < 0 and rsi_diff > 0 and df['rsi'].iloc[l2] < 40:
            divergence_signal = "🟢 BULLISH CONVERGENCE (Hội Tụ Tăng H4 - Tín Hiệu Gom Hàng Cá Mập!)"
            
    return divergence_signal


# --- THIẾT KẾ CÁC TAB ỨNG DỤNG ---

st.title("🛡️ UNDERGROUND TRADING TERMINAL V5")
st.markdown("Hệ thống đồng bộ hóa xu hướng & tính toán Volume chuẩn chỉ Jess UG.")

tab1, tab2, tab3 = st.tabs([
    "📈 Phân Tích & Quét Xu Hướng", 
    "🧮 Volume & Phí Thực Chiến (Quản Lý Vốn)", 
    "📒 Nhật Ký Giao Dịch & Sửa Sai"
])

# --- TAB 1: PHÂN TÍCH XU HƯỚNG ---
with tab1:
    col_coin, col_info = st.columns([1, 3])
    
    with col_coin:
        st.subheader("📋 Cặp Giao Dịch")
        selected_coin = st.selectbox("Chọn coin phân tích:", watchlist_symbols)
        
        # Tải dữ liệu
        df, is_mock = fetch_binance_klines(selected_coin, interval='4h', limit=150, base_url=selected_base_url)
        df = compute_indicators(df)
        highs, lows = find_dow_points(df, window=5)
        div_signal = scan_divergence(df, highs, lows)
        
        current_price = df['close'].iloc[-1]
        ema34 = df['ema_34'].iloc[-1]
        ema89 = df['ema_89'].iloc[-1]
        current_rsi = df['rsi'].iloc[-1]
        
        # Xác định xu hướng
        if current_price > ema34 and current_price > ema89:
            trend_status = "🟢 UPTREND (Canh Mua)"
            trend_color = "green"
        elif current_price < ema34 and current_price < ema89:
            trend_status = "🔴 DOWNTREND (Canh Bán / Đứng Ngoài)"
            trend_color = "red"
        else:
            trend_status = "🟡 SID_EWAY (Đứng Ngoài Quan Sát)"
            trend_color = "yellow"
            
        st.markdown(f"**Trạng Thái:** <span style='color:{trend_color};font-size:1.2rem;font-weight:bold;'>{trend_status}</span>", unsafe_allow_html=True)
        st.markdown(f"**Giá hiện tại:** `{current_price:.4f}`")
        st.markdown(f"**EMA 34:** `{ema34:.4f}` | **EMA 89:** `{ema89:.4f}`")
        st.markdown(f"**RSI (14):** `{current_rsi:.2f}`")
        
        st.markdown("---")
        st.markdown("### 🔔 Cảnh Báo Phân Kỳ H4")
        if "BEARISH" in div_signal:
            st.warning(div_signal)
        elif "BULLISH" in div_signal:
            st.success(div_signal)
        else:
            st.info(f"RSI/MACD: {div_signal}")
            
        # Nút gửi cảnh báo nhanh về Telegram
        if telegram_token and telegram_chat_id and div_signal != "Không phát hiện":
            if st.button("🚀 Bắn Tín Hiệu Qua Telegram"):
                text_msg = (
                    f"🔔 *CẢNH BÁO TÍN HIỆU TỪ TRẠM BỔ TÚC*\n\n"
                    f"👉 *Cặp:* {selected_coin}\n"
                    f"👉 *Trạng thái:* {trend_status}\n"
                    f"👉 *Tín hiệu:* {div_signal}\n"
                    f"👉 *Giá hiện tại:* {current_price:.4f}\n"
                    f"⚠️ *Kỷ luật:* Trade what you see, not what you think!"
                )
                url_tg = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                try:
                    requests.post(url_tg, json={"chat_id": telegram_chat_id, "text": text_msg, "parse_mode": "Markdown"}, timeout=3)
                    st.toast("Đã gửi tin nhắn Telegram thành công!")
                except Exception as e:
                    st.error(f"Lỗi: {e}")
                    
    with col_info:
        st.subheader(f"📊 Đồ Thị Kỹ Thuật {selected_coin} (Khung H4)")
        
        if is_mock:
            st.warning("⚠️ Đang sử dụng chế độ Dữ liệu giả lập Offline do lỗi kết nối tới API Binance (Có thể do mạng bị chặn).")
        else:
            st.success(f"✔️ Đã kết nối thành công và đang lấy dữ liệu trực tiếp từ cổng: **{selected_base_url}**")
            
        # Lấy Funding Rate thời gian thực
        fr = get_funding_rate(selected_coin, base_url=selected_base_url)
        
        col_metrics1, col_metrics2 = st.columns(2)
        with col_metrics1:
            st.metric("Funding Rate thời gian thực", f"{fr * 100:.4f}%", delta="Sát giờ đóng")
        with col_metrics2:
            st.metric("Kỳ thanh toán tiếp theo", "Sau 8 giờ", "07:00 | 15:00 | 23:00 VN")
            
        # Vẽ biểu đồ tương tác 2 bảng phụ (Subplots) bằng Plotly
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.08, row_heights=[0.7, 0.3])
        
        # Bảng 1: Candlestick & EMAs
        fig.add_trace(go.Candlestick(
            x=df['open_time'],
            open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name="Giá nến H4"
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_34'], name='EMA 34', line=dict(color='yellow', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_89'], name='EMA 89', line=dict(color='cyan', width=1.5)), row=1, col=1)
        
        # Đánh dấu Đỉnh/Đáy DOW một cách chuẩn chỉ và không lỗi chú thích
        for idx in highs:
            if idx < len(df):
                val = df['high'].iloc[idx]
                fig.add_annotation(
                    x=df['open_time'].iloc[idx], y=val,
                    text="Đỉnh DOW", showarrow=True, arrowhead=1,
                    font=dict(color='orange', size=10),
                    arrowcolor='orange', bgcolor='#1f2937', row=1, col=1
                )
        for idx in lows:
            if idx < len(df):
                val = df['low'].iloc[idx]
                fig.add_annotation(
                    x=df['open_time'].iloc[idx], y=val,
                    text="Đáy DOW", showarrow=True, arrowhead=1,
                    font=dict(color='lightgreen', size=10),
                    arrowcolor='lightgreen', bgcolor='#1f2937', row=1, col=1
                )
                
        # Bảng 2: RSI
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['rsi'], name='RSI', line=dict(color='magenta', width=1.5)), row=2, col=1)
        fig.add_shape(type="line", x0=df['open_time'].iloc[0], y0=70, x1=df['open_time'].iloc[-1], y1=70, line=dict(color="red", width=1, dash="dash"), row=2, col=1)
        fig.add_shape(type="line", x0=df['open_time'].iloc[0], y0=30, x1=df['open_time'].iloc[-1], y1=30, line=dict(color="green", width=1, dash="dash"), row=2, col=1)
        
        fig.update_layout(
            height=600,
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            margin=dict(l=10, r=10, t=10, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: BẢNG TÍNH VOLUME ---
with tab2:
    st.subheader("🧮 Máy Tính Volume Lệnh Thuận Xu Hướng & Tối Ưu Phí")
    st.markdown("Thiết lập kịch bản cắt lỗ trước khi vào lệnh. Bảo vệ tài sản theo đúng triết lý sếp Jess.")
    
    col_input, col_output = st.columns(2)
    
    with col_input:
        st.markdown("### 📝 Điền thông số kịch bản lệnh")
        direction = st.selectbox("Vị thế giao dịch:", ["LONG (Mua)", "SHORT (Bán)"])
        entry_price = st.number_input("Giá vào lệnh (Entry)", min_value=0.0001, value=current_price, format="%.5f")
        stop_loss = st.number_input("Điểm cắt lỗ (Stop Loss - SL)", min_value=0.0001, value=current_price * 0.98 if "LONG" in direction else current_price * 1.02, format="%.5f")
        target_price = st.number_input("Điểm chốt lời mục tiêu (Take Profit - TP)", min_value=0.0001, value=current_price * 1.04 if "LONG" in direction else current_price * 0.96, format="%.5f")
        leverage = st.slider("Đòn bẩy dự kiến (Leverage)", min_value=1, max_value=125, value=20)
        
        st.markdown("---")
        st.markdown("### 🎫 Biểu phí Binance & Tối ưu phí")
        vip_level = st.selectbox("Cấp độ VIP của bạn:", [f"VIP {i}" for i in range(10)])
        order_type = st.radio("Loại lệnh mở vị thế:", ["Maker (Lệnh Limit - Giảm phí)", "Taker (Lệnh Market - Khớp ngay)"])
        
        use_bnb_discount = st.checkbox("Sử dụng BNB để thanh toán phí (Giảm thêm 10% phí Futures)", value=True)
        is_promo_eligible = st.checkbox("Áp dụng ưu đãi cặp giao dịch U-margin BTC/ETH (0% Maker, giảm thêm Taker)", value=False)
        
    with col_output:
        st.markdown("### 🏆 Kết Quả Tính Toán Đi Tiền Cực Hạn")
        
        # Tính toán rủi ro và khoảng cách SL
        if "LONG" in direction:
            sl_distance_pct = ((entry_price - stop_loss) / entry_price) * 100.0
            tp_distance_pct = ((target_price - entry_price) / entry_price) * 100.0
        else:
            sl_distance_pct = ((stop_loss - entry_price) / entry_price) * 100.0
            tp_distance_pct = ((entry_price - target_price) / entry_price) * 100.0
            
        if sl_distance_pct <= 0:
            st.error("Lỗi: Điểm cắt lỗ (SL) không đúng hướng với vị thế giao dịch.")
        else:
            # 1. Tính Volume lệnh tối đa
            raw_vol_usdt = allowed_loss / (sl_distance_pct / 100.0)
            margin_required = raw_vol_usdt / leverage
            coin_quantity = raw_vol_usdt / entry_price
            
            # 2. Tính phí giao dịch dựa trên VIP và ưu đãi
            # Phí mặc định
            # Maker: 0.02% | Taker: 0.05%
            vip_idx = int(vip_level.split(" ")[1])
            
            # Tra cứu biểu phí Maker/Taker theo cấp độ VIP trên Binance
            maker_rates = [0.02, 0.018, 0.016, 0.012, 0.010, 0.008, 0.006, 0.004, 0.002, 0.0]
            taker_rates = [0.05, 0.050, 0.040, 0.032, 0.030, 0.027, 0.025, 0.022, 0.020, 0.017]
            
            base_maker_rate = maker_rates[min(vip_idx, 9)] / 100.0
            base_taker_rate = taker_rates[min(vip_idx, 9)] / 100.0
            
            # Áp dụng chương trình khuyến mãi giảm phí Maker 0% & giảm Taker cho U-margined BTC & ETH
            if is_promo_eligible and selected_coin in ["BTCUSDT", "ETHUSDT"]:
                base_maker_rate = 0.0
                if vip_idx <= 3:
                    # Giảm 20% phí taker
                    base_taker_rate *= 0.8
                else:
                    # Giảm 50% phí taker
                    base_taker_rate *= 0.5
                    
            # Phí áp dụng thực tế
            fee_rate_open = base_maker_rate if "Maker" in order_type else base_taker_rate
            # Thường lệnh đóng là lệnh đóng chủ động (Taker) hoặc đặt sẵn (Maker)
            fee_rate_close = base_maker_rate if "Maker" in order_type else base_taker_rate
            
            # Chiết khấu BNB
            if use_bnb_discount:
                fee_rate_open *= 0.9
                fee_rate_close *= 0.9
                
            fee_open = raw_vol_usdt * fee_rate_open
            fee_close = (raw_vol_usdt * (target_price / entry_price)) * fee_rate_close
            total_fee = fee_open + fee_close
            
            # 3. Tính toán lợi nhuận gộp và ròng
            gross_profit_usdt = raw_vol_usdt * (tp_distance_pct / 100.0)
            net_profit_usdt = gross_profit_usdt - total_fee
            
            # 4. Tỷ lệ Risk / Reward thực tế sau phí (Net R:R)
            net_rr = net_profit_usdt / allowed_loss
            
            # Hiển thị dữ liệu
            st.metric("Volume Lệnh Tối Đa (Position Size)", f"${raw_vol_usdt:.2f} USDT")
            st.metric("Ký Quỹ Bắt Buộc (Margin)", f"${margin_required:.2f} USDT", f"Đòn bẩy x{leverage}")
            
            st.markdown("---")
            st.markdown("### 📊 Chi Tiết Lợi Nhuận & Phí Giao Dịch")
            col_stat1, col_metrics_fee = st.columns(2)
            with col_stat1:
                st.markdown(f"**Khoảng cách Cắt lỗ (SL):** `{sl_distance_pct:.2f}%`")
                st.markdown(f"**Khoảng cách Chốt lời (TP):** `{tp_distance_pct:.2f}%`")
                st.markdown(f"**Số lượng coin cần mua:** `{coin_quantity:.4f}`")
            with col_metrics_fee:
                st.markdown(f"**Phí Mở vị thế:** `${fee_open:.4f} USDT` (`{fee_rate_open*100:.4f}%`)")
                st.markdown(f"**Phí Đóng vị thế:** `${fee_close:.4f} USDT` (`{fee_rate_close*100:.4f}%`)")
                st.markdown(f"**Tổng Phí Rò Rỉ:** `<span style='color:orange;font-weight:bold;'>${total_fee:.2f} USDT</span>`", unsafe_allow_html=True)
                
            st.markdown("---")
            if net_rr < 1.0:
                st.markdown(f"### **Tỷ Lệ Net R:R:** <span style='color:red;font-weight:bold;'>1:{net_rr:.2f}</span> (Khuyến cáo: **KHÔNG CHƠI** do lợi nhuận ròng không bù được rủi ro!)", unsafe_allow_html=True)
            else:
                st.markdown(f"### **Tỷ Lệ Net R:R:** <span style='color:green;font-weight:bold;'>1:{net_rr:.2f}</span> (Mức R:R tối ưu để mở vị thế!)", unsafe_allow_html=True)
                
            st.metric("Lợi Nhuận Ròng Thực Tế (Khấu Trừ Phí)", f"${net_profit_usdt:.2f} USDT", f"Đã trừ ${total_fee:.2f} phí")
            
            # Gửi tín hiệu vị thế qua Telegram
            if telegram_token and telegram_chat_id:
                if st.button("📤 Bắn Lệnh Đã Tính Lên Telegram"):
                    text_msg = (
                        f"📊 *THIẾT LẬP KỊCH BẢN VỊ THẾ*\n\n"
                        f"👉 *Cặp:* {selected_coin}\n"
                        f"👉 *Vị thế:* {direction}\n"
                        f"👉 *Entry:* {entry_price:.4f}\n"
                        f"👉 *Stop Loss (Cắt lỗ):* {stop_loss:.4f} (Khoảng {sl_distance_pct:.2f}%)\n"
                        f"👉 *Take Profit (Chốt lời):* {target_price:.4f} (Khoảng {tp_distance_pct:.2f}%)\n"
                        f"👉 *Đòn bẩy:* x{leverage}\n"
                        f"👉 *Ký quỹ:* ${margin_required:.2f} USDT\n"
                        f"👉 *Volume (Size):* ${raw_vol_usdt:.2f} USDT\n"
                        f"👉 *Lợi nhuận ròng ước tính:* ${net_profit_usdt:.2f} USDT\n"
                        f"👉 *Tỷ lệ Net R:R:* 1:{net_rr:.2f}\n\n"
                        f"⚠️ *Kỷ luật:* Gồng lời chứ không bao giờ gồng lỗ! Sẵn sàng thích ứng kịch bản xấu nhất!"
                    )
                    url_tg = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                    try:
                        requests.post(url_tg, json={"chat_id": telegram_chat_id, "text": text_msg, "parse_mode": "Markdown"}, timeout=3)
                        st.toast("Đã bắn kịch bản lệnh thành công!")
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

# --- TAB 3: NHẬT KÝ GIAO DỊCH ---
with tab3:
    st.subheader("📒 Nhật Ký Giao Dịch Của Bản Thân (Trading Journal)")
    st.markdown("*" + "Tôi rút hàng nghìn mét sợi dây kinh nghiệm. Mỗi một lần thua là ghi vào nhật ký giao dịch... Hãy hiểu bản thân chúng mày trước khi muốn hiểu thị trường." + "* — **Sếp Jess**")
    
    # Khởi tạo Nhật ký trong Session State nếu chưa có
    if "journal" not in st.session_state:
        st.session_state.journal = [
            {
                "Thời gian": "2026-07-15 10:30",
                "Coin": "BTCUSDT",
                "Vị thế": "LONG (Mua)",
                "Entry": 64200.0,
                "Cắt Lỗ (SL)": 63500.0,
                "Chốt Lời (TP)": 65600.0,
                "Trạng thái": "WIN (Thắng)",
                "Lợi nhuận ($)": 80.0,
                "Bài học xương máu": "Vào lệnh đúng vùng giá trị EMA 34/89 trên H4. Giá rút chân nến đẹp."
            },
            {
                "Thời gian": "2026-07-16 01:15",
                "Coin": "ETHUSDT",
                "Vị thế": "SHORT (Bán)",
                "Entry": 3480.0,
                "Cắt Lỗ (SL)": 3520.0,
                "Chốt Lời (TP)": 3380.0,
                "Trạng thái": "LOSS (Thua)",
                "Lợi nhuận ($)": -35.0,
                "Bài học xương máu": "Đánh ngược xu thế chính trên H4. Giá đục thủng EMA 89 rút chân nhưng fomo bán đuổi."
            }
        ]
        
    # Form điền thêm nhật ký giao dịch mới
    st.markdown("### ➕ Ghi Chép Lệnh Mới Đã Thực Hiện")
    col_j1, col_j2, col_j3 = st.columns(3)
    with col_j1:
        j_coin = st.selectbox("Coin đã chơi:", watchlist_symbols, key="j_coin")
        j_direction = st.selectbox("Vị thế:", ["LONG (Mua)", "SHORT (Bán)"], key="j_direction")
        j_status = st.selectbox("Kết quả thực tế:", ["WIN (Thắng)", "LOSS (Thua)", "HÒA VỐN"], key="j_status")
    with col_j2:
        j_entry = st.number_input("Giá Entry", value=current_price, format="%.5f", key="j_entry")
        j_sl = st.number_input("Giá Stop Loss (SL)", value=current_price * 0.98, format="%.5f", key="j_sl")
        j_tp = st.number_input("Giá Take Profit (TP)", value=current_price * 1.04, format="%.5f", key="j_tp")
    with col_j3:
        j_pnl = st.number_input("Lợi nhuận thực tế ($) [PNL sau phí]", value=0.0, step=5.0, key="j_pnl")
        j_lesson = st.text_area("Bài học xương máu rút ra:", placeholder="Tại sao vào lệnh này? Đã tuân thủ quy tắc EMA/DOW chưa?", key="j_lesson")
        
    if st.button("💾 Lưu Lại Bài Học Vào Nhật Ký"):
        new_entry = {
            "Thời gian": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Coin": j_coin,
            "Vị thế": j_direction,
            "Entry": j_entry,
            "Cắt Lỗ (SL)": j_sl,
            "Chốt Lời (TP)": j_tp,
            "Trạng thái": j_status,
            "Lợi nhuận ($)": j_pnl,
            "Bài học xương máu": j_lesson if j_lesson else "Không ghi chép bài học (Dễ lặp lại sai lầm cũ!)."
        }
        st.session_state.journal.insert(0, new_entry)
        st.toast("Đã lưu thành công nhật ký!")
        st.rerun()
        
    # Hiển thị Thống Kê & Bảng Nhật ký
    st.markdown("---")
    st.markdown("### 📊 Thống Kê Hiệu Suất Cá Nhân")
    
    if len(st.session_state.journal) > 0:
        df_j = pd.DataFrame(st.session_state.journal)
        
        total_trades = len(df_j)
        win_trades = len(df_j[df_j["Trạng thái"] == "WIN (Thắng)"])
        loss_trades = len(df_j[df_j["Trạng thái"] == "LOSS (Thua)"])
        win_rate = (win_trades / total_trades) * 100.0 if total_trades > 0 else 0
        total_pnl = df_j["Lợi nhuận ($)"].sum()
        
        col_st1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_st1:
            st.metric("Tổng Số Lệnh", f"{total_trades} Lệnh")
        with col_stat2:
            st.metric("Tỷ Lệ Thắng (Win Rate)", f"{win_rate:.1f}%", f"{win_trades} Thắng / {loss_trades} Thua")
        with col_stat3:
            st.metric("Tổng PnL Tích Lũy", f"${total_pnl:.2f} USDT", delta="Tịnh tiến dương" if total_pnl >= 0 else "Đang lỗ rò rỉ")
        with col_stat4:
            st.markdown(f"**Khuyên dùng:** " + ("🟢 Duy trì quy mô volume hiện tại" if win_rate >= 50 else "🔴 Giảm ngay volume hoặc Đóng máy đứng ngoài quan sát!"))
            
        st.markdown("### 📅 Danh Sách Nhật Ký")
        st.dataframe(df_j, use_container_width=True)
    else:
        st.info("Nhật ký hiện tại đang trống. Hãy bắt đầu ghi chép lệnh để hoàn thiện kỷ luật giao dịch của mình.")
