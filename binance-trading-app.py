import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import requests
import time

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Underground Trading Room - Jesse System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Thiết lập style CSS tùy chỉnh chuyên nghiệp
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        color: #f0b90b !important; /* Màu vàng Binance */
        font-family: 'Courier New', Courier, monospace;
    }
    .stAlert {
        border-radius: 8px;
    }
    .css-11e55zq {
        background-color: #161a1e;
    }
    .metric-box {
        background-color: #1e2329;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #2b3139;
        margin-bottom: 10px;
    }
    .trend-up {
        color: #0ecb81;
        font-weight: bold;
    }
    .trend-down {
        color: #f6465d;
        font-weight: bold;
    }
    .trend-sideway {
        color: #929aa5;
        font-weight: bold;
    }
</style>
""", unsafe_html=True)

# -----------------------------------------------------------------------------
# 1. QUẢN LÝ DỮ LIỆU & GỌI API BINANCE (Có Mock Data dự phòng khi offline)
# -----------------------------------------------------------------------------

def fetch_binance_futures_klines(symbol, interval='4h', limit=150):
    """
    Tải dữ liệu nến từ Binance Futures API.
    Nếu thất bại (không có mạng), tự động chuyển sang Mock Data để chạy thử nghiệm.
    """
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            cols_to_numeric = ['open', 'high', 'low', 'close', 'volume']
            for col in cols_to_numeric:
                df[col] = pd.to_numeric(df[col])
            df.set_index('open_time', inplace=True)
            return df, False  # Trả về df và trạng thái Offline=False
    except Exception as e:
        pass
    
    # Sinh dữ liệu Mock Data nếu API lỗi (Môi trường offline)
    return generate_mock_klines(symbol, limit), True

def generate_mock_klines(symbol, limit=150):
    """
    Tạo dữ liệu nến giả lập chất lượng cao bám sát chuyển động thực tế
    để trải nghiệm mượt mà trong môi trường offline.
    """
    np.random.seed(42)
    dates = pd.date_range(end=datetime.datetime.now(), periods=limit, freq='4h')
    
    # Giá khởi điểm phù hợp cho từng loại coin
    start_price = 60000.0
    if "ETH" in symbol:
        start_price = 3300.0
    elif "BNB" in symbol:
        start_price = 580.0
    elif "SOL" in symbol:
        start_price = 140.0
    elif "LINK" in symbol:
        start_price = 14.0
    elif "ADA" in symbol:
        start_price = 0.38
        
    prices = [start_price]
    for _ in range(1, limit):
        # Giả lập xu hướng sóng có nhịp hồi và các chu kỳ tăng giảm
        change = np.random.normal(0.001, 0.015)  # Biến động nến
        prices.append(prices[-1] * (1 + change))
        
    df_data = []
    for i, p in enumerate(prices):
        # Tạo cấu trúc râu nến và thân nến
        noise = p * 0.012
        high = p + abs(np.random.normal(noise, noise*0.5))
        low = p - abs(np.random.normal(noise, noise*0.5))
        open_p = p * (1 + np.random.normal(0, 0.005))
        close_p = p * (1 + np.random.normal(0, 0.005))
        # Đảm bảo râu nến bao ngoài thân nến
        final_high = max(open_p, close_p, high)
        final_low = min(open_p, close_p, low)
        volume = np.random.uniform(500, 5000)
        df_data.append([open_p, final_high, final_low, close_p, volume])
        
    df = pd.DataFrame(df_data, index=dates, columns=['open', 'high', 'low', 'close', 'volume'])
    df.index.name = 'open_time'
    return df

def fetch_funding_info(symbol):
    """
    Tải thông tin Funding Rate thời gian thực của Binance Futures.
    """
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            res = response.json()
            return {
                'funding_rate': float(res.get('lastFundingRate', 0.0001)),
                'next_funding_time': int(res.get('nextFundingTime', 0)),
                'mark_price': float(res.get('markPrice', 0))
            }
    except Exception:
        pass
    
    # Mock data cho Funding rate
    return {
        'funding_rate': 0.00015 if "BTC" in symbol or "ETH" in symbol else 0.0003,
        'next_funding_time': int(time.time() * 1000) + 12000000, # ~3.3 tiếng nữa
        'mark_price': 65000.0 if "BTC" in symbol else 3400.0
    }

# -----------------------------------------------------------------------------
# 2. CÔNG CỤ TÍNH TOÁN KỸ THUẬT (EMA, RSI, MACD, DOW THEORY)
# -----------------------------------------------------------------------------

def calculate_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def detect_peaks_troughs(df, window=5):
    """
    Xác định đỉnh/đáy cục bộ dựa theo hành vi giá của Lý thuyết Dow
    """
    peaks = []
    troughs = []
    
    for i in range(window, len(df) - window):
        is_peak = True
        is_trough = True
        for j in range(i - window, i + window + 1):
            if df['high'].iloc[j] > df['high'].iloc[i]:
                is_peak = False
            if df['low'].iloc[j] < df['low'].iloc[i]:
                is_trough = False
                
        if is_peak:
            peaks.append((df.index[i], df['high'].iloc[i]))
        if is_trough:
            troughs.append((df.index[i], df['low'].iloc[i]))
            
    return peaks, troughs

def check_divergence_convergence(df, peaks, troughs, rsi, macd_hist):
    """
    Kiểm tra tín hiệu Phân kỳ giảm (Bearish Divergence) hoặc Hội tụ tăng (Bullish Convergence)
    """
    divergence_signal = "Không có"
    
    if len(peaks) >= 2:
        # Lấy 2 đỉnh gần nhất
        p1_time, p1_val = peaks[-2]
        p2_time, p2_val = peaks[-1]
        
        # Nếu đỉnh giá sau cao hơn đỉnh trước (xu hướng tăng vẫn tiếp tục theo Price Action)
        if p2_val > p1_val:
            try:
                rsi_p1 = rsi.loc[p1_time]
                rsi_p2 = rsi.loc[p2_time]
                # Nhưng RSI đỉnh sau lại thấp hơn đỉnh trước -> PHÂN KỲ GIẢM (Lực mua yếu đi)
                if rsi_p2 < rsi_p1:
                    divergence_signal = "⚠️ PHÂN KỲ GIẢM (RSI): Lực mua cạn kiệt, nguy cơ đảo chiều cao!"
            except KeyError:
                pass
                
    if len(troughs) >= 2 and divergence_signal == "Không có":
        # Lấy 2 đáy gần nhất
        t1_time, t1_val = troughs[-2]
        t2_time, t2_val = troughs[-1]
        
        # Nếu đáy sau thấp hơn đáy trước (Price Action tiếp tục giảm)
        if t2_val < t1_val:
            try:
                rsi_t1 = rsi.loc[t1_time]
                rsi_t2 = rsi.loc[t2_time]
                # Nhưng RSI đáy sau lại cao hơn đáy trước -> HỘI TỰ TĂNG (Gom hàng âm thầm)
                if rsi_t2 > rsi_t1:
                    divergence_signal = "🟢 HỘI TỤ TĂNG (RSI): Lực bán đã cạn, cá mập đang âm thầm gom hàng!"
            except KeyError:
                pass
                
    return divergence_signal

# -----------------------------------------------------------------------------
# GIAO DIỆN CHÍNH CỦA ỨNG DỤNG STREAMLIT
# -----------------------------------------------------------------------------

st.title("⚡ UNDERGROUND TRADING ROOM - SYSTEM V1.0")
st.caption("Hệ thống nhận diện xu hướng theo Lý thuyết Dow, EMA 34/89 & Quản lý vốn thực chiến của sếp Jesse và Downcome.")

# -----------------------------------------------------------------------------
# SIDEBAR - DANH SÁCH THEO DÕI VÀ CẤU HÌNH TÀI KHOẢN
# -----------------------------------------------------------------------------
st.sidebar.header("🔑 Cấu hình & Watchlist")

# Watchlist mặc định theo yêu cầu của user
watchlist = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT"]
selected_symbol = st.sidebar.selectbox("Chọn Coin Theo Dõi:", watchlist)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Quản Lý Vốn Cá Nhân")
total_capital = st.sidebar.number_input("Tổng vốn tài khoản (USDT):", min_value=10.0, value=5000.0, step=100.0)
risk_percentage = st.sidebar.slider("Rủi ro chấp nhận cho mỗi lệnh (%):", min_value=0.5, max_value=5.0, value=2.0, step=0.1)
leverage = st.sidebar.slider("Đòn bẩy khuyên dùng (Leverage):", min_value=1, max_value=125, value=20, step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("🧾 Biểu Phí Binance Futures")
vip_tier = st.sidebar.selectbox("Cấp độ VIP của bạn:", [f"VIP {i}" for i in range(10)])
use_bnb_fee = st.sidebar.checkbox("Bật sử dụng BNB để trả phí (Giảm 10%)", value=True)
use_promo_fee = st.sidebar.checkbox("Áp dụng ưu đãi Maker 0% & Giảm Taker", value=True)

# -----------------------------------------------------------------------------
# LẤY DỮ LIỆU THỰC TẾ
# -----------------------------------------------------------------------------
df, is_offline = fetch_binance_futures_klines(selected_symbol, interval='4h', limit=150)
funding_data = fetch_funding_info(selected_symbol)

# Banner cảnh báo nếu app đang chạy ở chế độ offline (Mock data)
if is_offline:
    st.warning("⚠️ Đang chạy ở chế độ **NGOẠI TUYẾN (Offline Mock Data)** do không có kết nối tới máy chủ Binance. Khi bạn cài đặt và chạy file python này cục bộ trên máy tính cá nhân, ứng dụng sẽ tự động tải dữ liệu và biểu đồ thời gian thực từ Binance API!")

# -----------------------------------------------------------------------------
# THỰC HIỆN TÍNH TOÁN KỸ THUẬT
# -----------------------------------------------------------------------------
df['ema34'] = calculate_ema(df['close'], 34)
df['ema89'] = calculate_ema(df['close'], 89)
df['rsi'] = calculate_rsi(df['close'], 14)
df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(df['close'])

# Tìm các đỉnh đáy cục bộ của DOW
peaks, troughs = detect_peaks_troughs(df, window=5)

# Kiểm tra phân kỳ
div_signal = check_divergence_convergence(df, peaks, troughs, df['rsi'], df['macd_hist'])

# Xác định xu hướng chính dựa trên logic sếp Jess
latest_close = df['close'].iloc[-1]
latest_ema34 = df['ema34'].iloc[-1]
latest_ema89 = df['ema89'].iloc[-1]

if latest_close > latest_ema34 and latest_ema34 > latest_ema89:
    trend_status = "CANH MUA (UPTREND)"
    trend_color = "trend-up"
    trend_desc = "Giá nằm trên cả hai đường EMA 34 & 89. Phe mua đang làm chủ xu thế chính. Hãy canh điểm giá điều chỉnh về vùng giá trị EMA hoặc phá đỉnh Dow để vào lệnh Mua thuận xu hướng."
elif latest_close < latest_ema34 and latest_ema34 < latest_ema89:
    trend_status = "CANH BÁN / ĐỨNG NGOÀI (DOWNTREND)"
    trend_color = "trend-down"
    trend_desc = "Giá nằm dưới cả hai đường EMA 34 & 89. Phe bán đang kiểm soát hoàn toàn thị trường. Tuyệt đối không được 'bắt dao rơi' mua ngược bão. Ưu tiên canh các nhịp hồi về EMA để bán khống hoặc đứng ngoài bảo vệ tiền."
else:
    trend_status = "ĐỨNG NGOÀI QUAN SÁT (SIDEWAY)"
    trend_color = "trend-sideway"
    trend_desc = "Giá đang cắt qua cắt lại các đường EMA 34 & 89, đường trung bình có xu hướng đi ngang kẹt giữa biên độ. Tâm lý thị trường đang lưỡng lự cực độ. Hãy kiên nhẫn đứng ngoài chờ đợi một xu thế bứt phá rõ ràng."

# -----------------------------------------------------------------------------
# TABS HOẠT ĐỘNG CHÍNH
# -----------------------------------------------------------------------------
tab_analysis, tab_calc, tab_journal = st.tabs([
    "📈 Xu Hướng & Phân Tích Kỹ Thuật", 
    "🧮 Bảng Tính Volume & Phí Thực Chiến", 
    "📔 Nhật Ký Giao Dịch Ghi Chép Lỗi"
])

# =============================================================================
# TAB 1: XU HƯỚNG & PHÂN TÍCH KỸ THUẬT
# =============================================================================
with tab_analysis:
    col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
    
    with col_metric1:
        st.markdown(f"""
        <div class="metric-box">
            <span style="font-size: 0.9rem; color: #929aa5;">GIÁ HIỆN TẠI ({selected_symbol})</span>
            <h2 style="margin: 0; color: #ffffff !important;">${latest_close:,.4f}</h2>
        </div>
        """, unsafe_html=True)
        
    with col_metric2:
        st.markdown(f"""
        <div class="metric-box">
            <span style="font-size: 0.9rem; color: #929aa5;">XU THẾ CHÍNH (EMA H4)</span>
            <h2 class="{trend_color}" style="margin: 0;">{trend_status}</h2>
        </div>
        """, unsafe_html=True)
        
    with col_metric3:
        st.markdown(f"""
        <div class="metric-box">
            <span style="font-size: 0.9rem; color: #929aa5;">FUNDING RATE HIỆN TẠI</span>
            <h2 style="margin: 0; color: #0ecb81 !important;">{funding_data['funding_rate']*100:.4f}%</h2>
        </div>
        """, unsafe_html=True)
        
    with col_metric4:
        # Tính toán countdown thời gian cho Funding tiếp theo
        next_funding_dt = datetime.datetime.fromtimestamp(funding_data['next_funding_time']/1000)
        now_dt = datetime.datetime.now()
        time_diff = next_funding_dt - now_dt
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        # Nếu gần giờ funding hiển thị đỏ cảnh báo
        warn_style = "color: #f6465d !important;" if hours == 0 and minutes <= 30 else "color: #ffffff !important;"
        
        st.markdown(f"""
        <div class="metric-box">
            <span style="font-size: 0.9rem; color: #929aa5;">KỲ FUNDING TIẾP THEO IN</span>
            <h2 style="margin: 0; {warn_style}">{hours:02d} giờ {minutes:02d} phút</h2>
        </div>
        """, unsafe_html=True)

    # Hiển thị nhận định chi tiết dựa trên sếp Jess
    st.info(f"💡 **NHẬN ĐỊNH BẢO VỆ VỐN:** {trend_desc}")
    
    if div_signal != "Không có":
        st.warning(div_signal)

    # -------------------------------------------------------------------------
    # BIỂU ĐỒ TRỰC QUAN ĐA CHỈ BÁO BẰNG PLOTLY
    # -------------------------------------------------------------------------
    st.subheader("📊 Biểu Đồ Kỹ Thuật Đa Khung Thời Gian Giao Thoa Chỉ Báo")
    
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.6, 0.2, 0.2]
    )
    
    # 1. Đường giá nến Nhật
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="Đường giá",
        increasing_line_color='#0ecb81', decreasing_line_color='#f6465d'
    ), row=1, col=1)
    
    # 2. Đường EMA 34 & EMA 89
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ema34'], 
        line=dict(color='#f0b90b', width=2), 
        name="EMA 34 (Cản động ngắn)"
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ema89'], 
        line=dict(color='#9b51e0', width=2.5), 
        name="EMA 89 (Cản xu thế chính)"
    ), row=1, col=1)
    
    # 3. Đánh dấu Đỉnh / Đáy Dow Theory
    if len(peaks) > 0:
        p_times, p_vals = zip(*peaks)
        fig.add_trace(go.Scatter(
            x=p_times, y=p_vals,
            mode='markers+text',
            marker=dict(symbol='triangle-down', size=10, color='#f6465d'),
            text=['▼ Đỉnh Dow' for _ in p_vals],
            textposition='top center',
            name='Đỉnh DOW (Kháng cự)'
        ), row=1, col=1)
        
    if len(troughs) > 0:
        t_times, t_vals = zip(*troughs)
        fig.add_trace(go.Scatter(
            x=t_times, y=t_vals,
            mode='markers+text',
            marker=dict(symbol='triangle-up', size=10, color='#0ecb81'),
            text=['▲ Đáy Dow' for _ in t_vals],
            textposition='bottom center',
            name='Đáy DOW (Hỗ trợ)'
        ), row=1, col=1)

    # 4. Chỉ báo MACD Subplot
    # Màu sắc Histogram
    macd_colors = []
    for val in df['macd_hist']:
        if val >= 0:
            macd_colors.append('#0ecb81')
        else:
            macd_colors.append('#f6465d')
            
    fig.add_trace(go.Bar(
        x=df.index, y=df['macd_hist'], 
        marker_color=macd_colors, 
        name='MACD Hist'
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index, y=df['macd'], 
        line=dict(color='#4fc3f7', width=1.5), 
        name='MACD Line'
    ), row=2, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index, y=df['macd_signal'], 
        line=dict(color='#ffb74d', width=1.5), 
        name='Signal Line'
    ), row=2, col=1)

    # 5. Chỉ báo RSI Subplot
    fig.add_trace(go.Scatter(
        x=df.index, y=df['rsi'], 
        line=dict(color='#e040fb', width=2), 
        name='RSI (14)'
    ), row=3, col=1)
    
    # Thêm các đường ranh giới RSI Quá mua / Quá bán
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=70, y1=70, line=dict(color="#f6465d", width=1, dash="dash"), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=30, y1=30, line=dict(color="#0ecb81", width=1, dash="dash"), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=50, y1=50, line=dict(color="#929aa5", width=1, dash="dot"), row=3, col=1)

    # Cấu hình giao diện biểu đồ tổng quan
    fig.update_layout(
        height=750,
        theme='seaborn',
        paper_bgcolor='#0e1117',
        plot_bgcolor='#161a1e',
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB 2: BẢNG TÍNH VOLUME & PHÍ THỰC CHIẾN
# =============================================================================
with tab_calc:
    st.subheader("🧮 Bảng Tính Volume Theo Quản Lý Vốn Nghiêm Ngặt Tránh Bẫy Phí")
    st.caption("Hãy nhập các mức thông số của đồ thị dưới đây. Máy sẽ tự động tính toán Volume tối ưu và phí giao dịch dự kiến.")
    
    col_inp1, col_inp2 = st.columns(2)
    
    with col_inp1:
        st.markdown("##### 📌 Thông số điểm vào lệnh:")
        order_direction = st.radio("Vị thế giao dịch:", ["LONG (Mua lên)", "SHORT (Bán xuống)"])
        entry_price = st.number_input("Điểm vào lệnh mong muốn (Entry Price - USDT):", min_value=0.0001, value=latest_close, format="%.5f")
        stop_loss = st.number_input("Điểm dừng lỗ bắt buộc (Stop Loss - USDT):", min_value=0.0001, value=latest_close*0.97 if order_direction == "LONG (Mua lên)" else latest_close*1.03, format="%.5f")
        take_profit = st.number_input("Điểm chốt lời kỳ vọng (Take Profit - USDT):", min_value=0.0001, value=latest_close*1.06 if order_direction == "LONG (Mua lên)" else latest_close*0.94, format="%.5f")

    # Xác định khoảng cách Stoploss và Rủi ro số tiền cụ thể
    risk_cash = total_capital * (risk_percentage / 100.0)
    
    # Tính toán khoảng cách % SL và % TP
    if order_direction == "LONG (Mua lên)":
        sl_pct = (entry_price - stop_loss) / entry_price
        tp_pct = (take_profit - entry_price) / entry_price
    else:
        sl_pct = (stop_loss - entry_price) / entry_price
        tp_pct = (entry_price - take_profit) / entry_price

    # -------------------------------------------------------------------------
    # PHẦN QUYẾT ĐỊNH PHÍ GIAO DỊCH DỰA TRÊN TÀI LIỆU BINANCE
    # -------------------------------------------------------------------------
    # Mặc định lấy phí theo VIP tier được chọn từ sidebar
    # Cấu trúc phí USDT-Margined Futures (Passage 160-169)
    fee_table = {
        'VIP 0': {'maker': 0.0200, 'taker': 0.0500},
        'VIP 1': {'maker': 0.0180, 'taker': 0.0500},
        'VIP 2': {'maker': 0.0160, 'taker': 0.0400},
        'VIP 3': {'maker': 0.0120, 'taker': 0.0320},
        'VIP 4': {'maker': 0.0100, 'taker': 0.0300},
        'VIP 5': {'maker': 0.0080, 'taker': 0.0270},
        'VIP 6': {'maker': 0.0060, 'taker': 0.0250},
        'VIP 7': {'maker': 0.0040, 'taker': 0.0220},
        'VIP 8': {'maker': 0.0020, 'taker': 0.0200},
        'VIP 9': {'maker': 0.0000, 'taker': 0.0170},
    }
    
    # Ưu đãi Promo (Passage 1 & 2)
    promo_fee_table = {
        'VIP 0': {'maker': 0.0000, 'taker': 0.0400},
        'VIP 1': {'maker': 0.0000, 'taker': 0.0400},
        'VIP 2': {'maker': 0.0000, 'taker': 0.0320},
        'VIP 3': {'maker': 0.0000, 'taker': 0.0256},
        'VIP 4': {'maker': 0.0000, 'taker': 0.0150},
        'VIP 5': {'maker': 0.0000, 'taker': 0.0135},
        'VIP 6': {'maker': 0.0000, 'taker': 0.0125},
        'VIP 7': {'maker': 0.0000, 'taker': 0.0110},
        'VIP 8': {'maker': 0.0000, 'taker': 0.0100},
        'VIP 9': {'maker': 0.0000, 'taker': 0.0085},
    }
    
    current_fees = promo_fee_table[vip_tier] if use_promo_fee else fee_table[vip_tier]
    
    maker_fee_rate = current_fees['maker'] / 100.0
    taker_fee_rate = current_fees['taker'] / 100.0
    
    # Áp dụng chiết khấu BNB Fee (giảm 10% phí Futures)
    if use_bnb_fee:
        maker_fee_rate *= 0.90
        taker_fee_rate *= 0.90

    with col_inp2:
        st.markdown("##### 📌 Cấu hình khớp lệnh & Tính phí:")
        opening_order_type = st.selectbox("Loại lệnh khi Mở vị thế (Entry):", ["Taker (Khớp Market ngay lập tức)", "Maker (Đặt Limit chờ khớp)"])
        closing_order_type = st.selectbox("Loại lệnh khi Đóng vị thế (TP / SL):", ["Taker (Market chốt nhanh)", "Maker (Limit chốt lời treo sẵn)"])
        
        # Thiết lập phí tương ứng
        op_fee_rate = taker_fee_rate if "Taker" in opening_order_type else maker_fee_rate
        cl_fee_rate = taker_fee_rate if "Taker" in closing_order_type else maker_fee_rate
        
        st.markdown(f"""
        <div style="background-color: #1e2329; padding: 15px; border-radius: 8px; border: 1px solid #f0b90b;">
            <p style="margin: 0; color: #f0b90b; font-weight: bold;">Tỷ lệ phí áp dụng thực tế:</p>
            <ul style="margin: 5px 0 0 0; padding-left: 20px; color: #ffffff;">
                <li>Phí Mở vị thế: <b>{op_fee_rate*100:.4f}%</b></li>
                <li>Phí Đóng vị thế: <b>{cl_fee_rate*100:.4f}%</b></li>
                <li>Phí tài trợ Funding (dự kiến giữ 1 kỳ): <b>{funding_data['funding_rate']*100:.4f}%</b></li>
            </ul>
        </div>
        """, unsafe_html=True)

    # Tính toán Volume và đòn bẩy
    st.markdown("---")
    st.subheader("💡 Kế Hoạch Đóng Gói Vị Thế Thực Chiến")
    
    if sl_pct <= 0:
        st.error("❌ LỖI NGỚ NGẨN: Mức dừng lỗ Stop Loss bạn đặt không hợp lệ so với vị thế của bạn. Hãy kiểm tra lại!")
    else:
        # Volume tính toán để rủi ro mất tiền cố định đúng bằng risk_cash
        position_size_usdt = risk_cash / sl_pct
        coin_quantity = position_size_usdt / entry_price
        margin_required = position_size_usdt / leverage
        risk_reward_ratio = tp_pct / sl_pct if sl_pct > 0 else 0
        
        # Tính toán phí giao dịch thực tế
        opening_fee_cost = position_size_usdt * op_fee_rate
        closing_fee_cost = position_size_usdt * cl_fee_rate
        total_trading_fee = opening_fee_cost + closing_fee_cost
        
        # Funding fee dự kiến cho 1 kỳ giữ lệnh
        estimated_funding_fee = position_size_usdt * funding_data['funding_rate']
        
        # Tổng phí vận hành
        total_operational_cost = total_trading_fee + estimated_funding_fee
        
        # Gross profit vs Net profit
        gross_profit = position_size_usdt * tp_pct
        net_profit = gross_profit - total_operational_cost
        
        # Gross loss vs Net loss
        gross_loss = position_size_usdt * sl_pct # Sẽ bằng risk_cash
        net_loss = gross_loss + total_operational_cost

        col_res1, col_res2, col_res3 = st.columns(3)
        
        with col_res1:
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">RỦI RO THIỆT HẠI ĐÃ ĐỊNH HẠN</span>
                <h3 style="color: #f6465d !important; margin: 0;">${risk_cash:.2f} ({risk_percentage}%)</h3>
                <small style="color: #929aa5;">Số tiền tối đa mất đi nếu quét Stop Loss.</small>
            </div>
            """, unsafe_html=True)
            
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">KHỐI LƯỢNG VÀO LỆNH (VOLUME)</span>
                <h3 style="color: #f0b90b !important; margin: 0;">${position_size_usdt:,.2f}</h3>
                <small style="color: #929aa5;">Số lượng Coin cần mở: <b>{coin_quantity:.4f} {selected_symbol[:-4]}</b></small>
            </div>
            """, unsafe_html=True)

        with col_res2:
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">KÝ QUỸ BẮT BUỘC (MARGIN)</span>
                <h3 style="color: #ffffff !important; margin: 0;">${margin_required:.2f}</h3>
                <small style="color: #929aa5;">Đòn bẩy áp dụng thực tế: <b>{leverage}x</b></small>
            </div>
            """, unsafe_html=True)
            
            # Cảnh báo ký quỹ quá cao so với đòn bẩy
            if margin_required > total_capital * 0.3:
                st.warning("⚠️ CẢNH BÁO: Ký quỹ bắt buộc vượt quá 30% tài sản. Hãy cẩn trọng khả năng thanh lý sớm!")
            else:
                st.success("✅ Ký quỹ an toàn trong vùng quản lý vốn cho phép.")
                
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">KHOẢNG CÁCH KỸ THUẬT</span>
                <p style="margin: 0; color: #ffffff;">Khoảng cách dừng lỗ: <b style="color: #f6465d;">{sl_pct*100:.2f}%</b></p>
                <p style="margin: 0; color: #ffffff;">Khoảng cách chốt lời: <b style="color: #0ecb81;">{tp_pct*100:.2f}%</b></p>
            </div>
            """, unsafe_html=True)

        with col_res3:
            rr_color = "#0ecb81" if risk_reward_ratio >= 1.5 else "#f0b90b" if risk_reward_ratio >= 1.0 else "#f6465d"
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">TỶ LỆ RỦI RO / LỢI NHUẬN (R:R)</span>
                <h3 style="color: {rr_color} !important; margin: 0;">1 : {risk_reward_ratio:.2f}</h3>
                <small style="color: #929aa5;">Mức kỳ vọng tối thiểu được khuyên là <b>1:1</b>.</small>
            </div>
            """, unsafe_html=True)
            
            # Cảnh báo R:R quá thấp
            if risk_reward_ratio < 1.0:
                st.error("❌ CẢNH BÁO: Kế hoạch R:R nhỏ hơn 1:1. Không xứng đáng mạo hiểm rủi ro tài khoản!")
                
            st.markdown(f"""
            <div class="metric-box">
                <span style="color: #929aa5;">BỘ TÍNH PHÍ THỰC TẾ & LỢI NHUẬN RÒNG</span>
                <p style="margin: 0; color: #ffffff;">Phí giao dịch + Funding: <b>${total_operational_cost:.2f}</b></p>
                <p style="margin: 0; color: #ffffff;">Lợi nhuận gộp (Gross): <b style="color: #0ecb81;">${gross_profit:.2f}</b></p>
                <p style="margin: 0; color: #ffffff; border-top: 1px solid #2b3139; padding-top: 5px;">LỢI NHUẬN THỰC (NET): <b style="color: #0ecb81;">${net_profit:.2f}</b></p>
            </div>
            """, unsafe_html=True)

        # -------------------------------------------------------------------------
        # BẢN PHÁC THẢO CHIẾN THUẬT (TRADING BLUEPRINT)
        # -------------------------------------------------------------------------
        st.markdown("#### 📝 Kế hoạch Giao dịch Tinh gọn (Trading Blueprint)")
        blueprint_text = f"""🚀 CHỈ THỊ VÀO LỆNH: {order_direction.upper()} {selected_symbol}
-------------------------------------------------------------------
- VÙNG GIÁ VÀO LỆNH (ENTRY): {entry_price:,.5f}
- VÙNG CẮT LỖ BẮT BUỘC (STOP LOSS): {stop_loss:,.5f} (Rủi ro mất đúng ${risk_cash:.2f})
- VÙNG CHỐT LỜI KỲ VỌNG (TAKE PROFIT): {take_profit:,.5f}
- KHỐI LƯỢNG HỢP ĐỒNG (VOLUME): {position_size_usdt:,.2f} USDT ({coin_quantity:.4f} {selected_symbol[:-4]})
- TỶ LỆ R:R KỲ VỌNG: 1 : {risk_reward_ratio:.2f}
- PHÍ VẬN HÀNH DỰ KIẾN: ${total_operational_cost:.2f} 
-------------------------------------------------------------------
Mantra: "Trade what you see, not what you think!" - Tuyệt đối tuân thủ, sai thì cắt lỗ, không hối hận!"""
        
        st.code(blueprint_text, language="markdown")

# =============================================================================
# TAB 3: NHẬT KÝ GIAO DỊCH GHI CHÉP LỖI
# =============================================================================
with tab_journal:
    st.subheader("📔 Nhật Ký Giao Dịch Sửa Sai Bản Thân")
    st.caption("Jesse khẳng định việc lưu lại nhật ký để tự phê bình và sửa chữa những thói quen cay cú, gồng lỗ, chốt non là chìa khóa 75% dẫn tới thành công.")

    # Sử dụng Session State để lưu danh sách lệnh đã lưu
    if 'journal_entries' not in st.session_state:
        st.session_state['journal_entries'] = [
            {
                'Ngày': '2026-07-15 08:30',
                'Coin': 'BTCUSDT',
                'Vị thế': 'LONG',
                'Entry': 62500.0,
                'Stop Loss': 61500.0,
                'Take Profit': 64500.0,
                'Net PnL ($)': 150.0,
                'Trạng thái': 'Thắng (Hit TP)',
                'Bài học xương máu': 'Kỷ luật kiên nhẫn chờ giá hồi về EMA 34 khung H4 rút chân mới vào lệnh. Gồng lời đúng kế hoạch.'
            },
            {
                'Ngày': '2026-07-15 15:45',
                'Coin': 'ETHUSDT',
                'Vị thế': 'SHORT',
                'Entry': 3450.0,
                'Stop Loss': 3500.0,
                'Take Profit': 3300.0,
                'Net PnL ($)': -40.0,
                'Trạng thái': 'Thua (Hit SL)',
                'Bài học xương máu': 'Vào lệnh vội vàng do hưng phấn fomo khi nến H4 chưa đóng cửa rõ ràng qua cản. Sai lầm cần tránh.'
            }
        ]

    # Form thêm lệnh mới vào nhật ký
    with st.expander("➕ Ghi thêm 1 giao dịch mới vào sổ tay"):
        col_form1, col_form2 = st.columns(2)
        with col_form1:
            j_date = st.date_input("Ngày giao dịch:", datetime.date.today())
            j_time = st.time_input("Giờ giao dịch:", datetime.datetime.now().time())
            j_coin = st.selectbox("Đồng coin:", watchlist, key="j_coin")
            j_dir = st.selectbox("Vị thế:", ["LONG", "SHORT"])
            j_entry = st.number_input("Giá Entry thực tế:", min_value=0.0, value=latest_close)
        with col_form2:
            j_sl = st.number_input("Giá Stop Loss thực tế:", min_value=0.0, value=latest_close*0.97)
            j_tp = st.number_input("Giá Take Profit thực tế:", min_value=0.0, value=latest_close*1.05)
            j_pnl = st.number_input("Lợi nhuận/Thua lỗ thực tế sau phí ($):", value=0.0)
            j_status = st.selectbox("Kết quả giao dịch:", ["Thắng (Hit TP)", "Thua (Hit SL)", "Đang chạy (Pending)", "Đóng hòa vốn"])
            j_lesson = st.text_area("Bài học xương máu rút ra (Tâm lý, Kỷ luật, Quản lý vốn):", "")

        if st.button("💾 Ghi Lại Vào Sổ Nhật Ký"):
            new_entry = {
                'Ngày': f"{j_date} {j_time.strftime('%H:%M')}",
                'Coin': j_coin,
                'Vị thế': j_dir,
                'Entry': j_entry,
                'Stop Loss': j_sl,
                'Take Profit': j_tp,
                'Net PnL ($)': j_pnl,
                'Trạng thái': j_status,
                'Bài học xương máu': j_lesson if j_lesson else "Không ghi chép bài học là biểu hiện của lười suy nghĩ."
            }
            st.session_state['journal_entries'].append(new_entry)
            st.success("🎉 Đã lưu trữ thành công vào Nhật ký giao dịch của Underground!")

    # Hiển thị bảng nhật ký
    if len(st.session_state['journal_entries']) > 0:
        journal_df = pd.DataFrame(st.session_state['journal_entries'])
        st.dataframe(journal_df, use_container_width=True)
        
        # Thống kê nhanh tỷ lệ thắng thua
        pnl_sum = journal_df['Net PnL ($)'].sum()
        total_trades = len(journal_df)
        win_trades = len(journal_df[journal_df['Trạng thái'].str.contains('Thắng')])
        win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
        
        col_st1, col_res_pnl, col_st3 = st.columns(3)
        with col_st1:
            st.metric("Tổng số lệnh đã đi", total_trades)
        with col_res_pnl:
            st.metric("Tổng PnL thực tế ($)", f"${pnl_sum:,.2f}", delta=f"{pnl_sum:.2f}")
        with col_st3:
            st.metric("Tỷ lệ thắng hệ thống (Win Rate)", f"{win_rate:.1f}%")
    else:
        st.info("Nhật ký hiện tại đang trống. Hãy kỷ luật ghi chép từng lệnh nhé!")

# -----------------------------------------------------------------------------
# CHÂN TRANG - TRÍCH DẪN SẾP JESSE
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("""
<div style="text-align: center; padding: 20px; color: #929aa5;">
    <p style="font-style: italic; font-size: 1.1rem;">"Kẻ thù lớn nhất của nhà giao dịch không phải thị trường, mà chính là lòng tham và nỗi sợ hãi bên trong bản thân mình. Hãy Trade những gì bạn NHÌN thấy, chứ không phải những gì bạn NGHĨ!"</p>
    <p style="font-weight: bold; color: #f0b90b;">- Jesse J.L - Trường Đại học Underground</p>
</div>
""", unsafe_html=True)
