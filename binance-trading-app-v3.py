import streamlit as st
import pandas as pd
import numpy as np
import requests
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Set Streamlit Page configuration
st.set_page_config(
    page_title="Underground Trading Terminal v3",
    page_icon="⚡",
    layout="wide"
)

# App Title & Styling
st.title("⚡ Underground Trading Terminal (v3)")
st.caption("Hệ thống giao dịch thực chiến theo triết lý sếp Jesse J.L & Downcome — Bản nâng cấp bảo mật và sửa lỗi đồ thị")

# Session State for Trading Journal
if "journal" not in st.session_state:
    st.session_state.journal = []

# Watchlist configuration
WATCHLIST = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT"]

# Sidebar settings
st.sidebar.header("⚙️ CẤU HÌNH HỆ THỐNG")
selected_coin = st.sidebar.selectbox("Chọn cặp giao dịch", WATCHLIST, index=0)

# Telegram Bot configuration
st.sidebar.subheader("💬 TELEGRAM BOT ALERTS")
tg_token = st.sidebar.text_input("Telegram Bot Token", placeholder="123456789:ABC...", type="password")
tg_chat_id = st.sidebar.text_input("Telegram Chat ID", placeholder="987654321")

# Helper function to send telegram messages
def send_telegram_alert(message):
    if not tg_token or not tg_chat_id:
        st.sidebar.error("Vui lòng điền đủ Token và Chat ID để gửi thông báo!")
        return False
    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
    payload = {
        "chat_id": tg_chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            st.sidebar.success("✅ Đã gửi thông báo Telegram thành công!")
            return True
        else:
            st.sidebar.error(f"Lỗi gửi Telegram: {response.text}")
            return False
    except Exception as e:
        st.sidebar.error(f"Không thể kết nối Telegram API: {e}")
        return False

if st.sidebar.button("🔔 Gửi Tin Nhắn Thử Nghiệm"):
    test_msg = f"<b>[TEST TERMINAL]</b>\n🔔 Telegram Bot của bạn đã được cấu hình thành công với Underground Terminal!\n🕒 Thời gian: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    send_telegram_alert(test_msg)

# Cache data fetch to avoid API bans
@st.cache_data(ttl=60)
def fetch_binance_data(symbol, interval="4h", limit=120):
    url = "https://fapi.binance.com/fapi/v1/klines"
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
                'close_time', 'quote_volume', 'count', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df, False
        else:
            return None, f"Lỗi API Binance: Mã {response.status_code}"
    except Exception as e:
        return None, f"Lỗi kết nối API: {str(e)}"

@st.cache_data(ttl=60)
def fetch_funding_info(symbol):
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    params = {"symbol": symbol}
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            return response.json(), False
        return None, "Lỗi API"
    except:
        return None, "Lỗi kết nối"

# Check API status or load dummy offline data if needed
df, err = fetch_binance_data(selected_coin)
funding_data, f_err = fetch_funding_info(selected_coin)

# Fallback to Offline Mock Data if API is unavailable (or inside secure sandbox)
is_offline_mode = False
if err:
    is_offline_mode = True
    st.warning("⚠️ Hiện tại Terminal đang chạy ở chế độ GIẢ LẬP DỮ LIỆU (Offline Mock Data). Khi chạy thực tế trên máy tính có mạng, Terminal sẽ tự động tải dữ liệu thật từ Binance.")
    
    # Generate mock candles
    np.random.seed(42)
    dates = pd.date_range(end=datetime.datetime.now(), periods=120, freq='4H')
    close_price = 60000.0
    data = []
    for d in dates:
        change = np.random.normal(10, 500)
        o = close_price
        c = o + change
        h = max(o, c) + abs(np.random.normal(50, 100))
        l = min(o, c) - abs(np.random.normal(50, 100))
        v = abs(np.random.normal(100, 50))
        close_price = c
        data.append([d, o, h, l, c, v])
    df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])
    funding_data = {"lastFundingRate": "0.00010000", "nextFundingTime": int((datetime.datetime.now() + datetime.timedelta(hours=4)).timestamp() * 1000)}

# --- CALCULATE INDICATORS ---
# 1. EMA 34 & 89
df['ema_34'] = df['close'].ewm(span=34, adjust=False).mean()
df['ema_89'] = df['close'].ewm(span=89, adjust=False).mean()

# 2. RSI
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / (loss + 1e-9)
df['rsi'] = 100 - (100 / (1 + rs))

# 3. MACD
exp1 = df['close'].ewm(span=12, adjust=False).mean()
exp2 = df['close'].ewm(span=26, adjust=False).mean()
df['macd'] = exp1 - exp2
df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
df['hist'] = df['macd'] - df['signal']

# Determine trend based on EMA
latest_close = df['close'].iloc[-1]
latest_ema34 = df['ema_34'].iloc[-1]
latest_ema89 = df['ema_89'].iloc[-1]

if latest_close > latest_ema34 and latest_close > latest_ema89 and latest_ema34 > latest_ema89:
    trend = "UPTREND (CANH MUA 🟢)"
    trend_color = "green"
elif latest_close < latest_ema34 and latest_close < latest_ema89 and latest_ema34 < latest_ema89:
    trend = "DOWNTREND (ĐỨNG NGOÀI HOẶC BÁN 🔴)"
    trend_color = "red"
else:
    trend = "SIDEWAY (HẠN CHẾ GIAO DỊCH 🟡)"
    trend_color = "yellow"

# Peaks and Valleys for Dow Theory (window=3)
def find_dow_points(df, window=3):
    peaks = []
    valleys = []
    for i in range(window, len(df) - window):
        if df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max():
            peaks.append((i, df['high'].iloc[i]))
        if df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min():
            valleys.append((i, df['low'].iloc[i]))
    return peaks, valleys

peaks, valleys = find_dow_points(df)

# --- DETECT DIVERGENCE (PHÂN KỲ) ---
divergence_msg = ""
divergence_status = "Bình thường"
divergence_color = "grey"

if len(peaks) >= 2:
    p1_idx, p1_val = peaks[-2]
    p2_idx, p2_val = peaks[-1]
    # Bearish Divergence
    if p2_val > p1_val:
        if df['rsi'].iloc[p2_idx] < df['rsi'].iloc[p1_idx] or df['macd'].iloc[p2_idx] < df['macd'].iloc[p1_idx]:
            divergence_status = "⚠️ CẢNH BÁO PHÂN KỲ GIẢM (BEARISH DIVERGENCE)"
            divergence_color = "red"
            divergence_msg = f"Phát hiện phân kỳ giảm tại đỉnh giá {p2_val:.2f} so với đỉnh cũ {p1_val:.2f}. Lực mua đang yếu dần! KHÔNG FOMO!"

if len(valleys) >= 2:
    v1_idx, v1_val = valleys[-2]
    v2_idx, v2_val = valleys[-1]
    # Bullish Divergence / Convergence
    if v2_val < v1_val:
        if df['rsi'].iloc[v2_idx] > df['rsi'].iloc[v1_idx] or df['macd'].iloc[v2_idx] > df['macd'].iloc[v1_idx]:
            divergence_status = "🟢 CƠ HỘI HỘI TỤ TĂNG (BULLISH CONVERGENCE)"
            divergence_color = "green"
            divergence_msg = f"Phát hiện hội tụ tăng tại đáy giá {v2_val:.2f} so với đáy cũ {v1_val:.2f}. Lực bán đã cạn kiệt, cá mập đang gom hàng!"


# --- RENDER TABBED WORKSPACE ---
tab1, tab2, tab3 = st.tabs(["📈 PHÂN TÍCH XU HƯỚNG & DOW", "🧮 BẢNG TÍNH VOL & PHÍ", "📓 NHẬT KÝ GIAO DỊCH"])

with tab1:
    col_t1, col_t2 = st.columns([3, 1])
    
    with col_t1:
        st.subheader("📊 Biểu đồ Phân tích kỹ thuật (Khung H4)")
        
        # Design plot with subplots (Price + RSI)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.08, row_heights=[0.7, 0.3])
        
        # Candlestick chart
        fig.add_trace(go.Candlestick(
            x=df['open_time'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="Giá nến",
            increasing_line_color='green',
            decreasing_line_color='red'
        ), row=1, col=1)
        
        # EMA lines
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_34'], name="EMA 34 (Ngắn hạn)", line=dict(color='cyan', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_89'], name="EMA 89 (Xu hướng)", line=dict(color='magenta', width=2)), row=1, col=1)
        
        # RSI chart
        fig.add_trace(go.Scatter(x=df['open_time'], y=df['rsi'], name="RSI (14)", line=dict(color='yellow', width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        
        # Annotate Dow points safely (Fixing the Plotly Annotation 'color' error)
        for idx, val in peaks[-4:]: # Show last 4 peaks
            fig.add_annotation(
                x=df['open_time'].iloc[idx],
                y=val,
                text="Đỉnh DOW",
                showarrow=True,
                arrowhead=1,
                arrowcolor='orange',
                font=dict(color='orange', size=10),
                row=1, col=1
            )
            
        for idx, val in valleys[-4:]: # Show last 4 valleys
            fig.add_annotation(
                x=df['open_time'].iloc[idx],
                y=val,
                text="Đáy DOW",
                showarrow=True,
                arrowhead=1,
                arrowcolor='lightgreen',
                font=dict(color='lightgreen', size=10),
                row=1, col=1
            )
            
        fig.update_layout(
            height=600,
            xaxis_rangeslider_visible=False,
            paper_bgcolor="#111",
            plot_bgcolor="#111",
            font_color="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
        
    with col_t2:
        st.subheader("⚡ TÌNH TRẠNG THỊ TRƯỜNG")
        
        # Metric block
        st.metric("Giá hiện tại", f"${latest_close:,.2f}")
        st.markdown(f"**Xu thế chủ đạo:** <span style='color:{trend_color};font-weight:bold;'>{trend}</span>", unsafe_allow_html=True)
        st.write(f"EMA 34: **${latest_ema34:,.2f}** | EMA 89: **${latest_ema89:,.2f}**")
        
        # Funding rate widget
        fr = float(funding_data.get("lastFundingRate", 0))
        next_funding_ms = funding_data.get("nextFundingTime", 0)
        next_funding_dt = datetime.datetime.fromtimestamp(next_funding_ms / 1000)
        time_left = next_funding_dt - datetime.datetime.now()
        time_left_str = str(time_left).split('.')[0] if time_left.total_seconds() > 0 else "Hết giờ"
        
        st.info(f"**Phí Funding Rate:** {fr*100:.4f}%\n\n🕒 **Kỳ thanh toán sau:** {time_left_str} ({next_funding_dt.strftime('%H:%M')})")
        
        # Display divergence status
        st.subheader("🔍 QUÉT PHÂN KỲ H4")
        st.markdown(f"Trạng thái: <span style='color:{divergence_color};font-weight:bold;'>{divergence_status}</span>", unsafe_allow_html=True)
        if divergence_msg:
            st.warning(divergence_msg)
            # Notify Telegram
            if tg_token and tg_chat_id:
                if st.button("🚀 GỬI CẢNH BÁO TELEGRAM"):
                    msg = f"<b>[UNDERGROUND SIGNAL - {selected_coin}]</b>\n\n📌 <b>Trạng thái:</b> {divergence_status}\n📊 <b>Giá hiện tại:</b> ${latest_close:,.2f}\n📈 <b>Xu hướng:</b> {trend}\n\n💬 <b>Chi tiết:</b> {divergence_msg}\n🕒 <i>Thời gian quét: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
                    send_telegram_alert(msg)
        else:
            st.success("Không phát hiện tín hiệu phân kỳ bất thường. Xu hướng kỹ thuật hiện tại ổn định.")

with tab2:
    st.subheader("🧮 Bảng tính Volume & Tối ưu phí Binance Futures VIP 0 - 9")
    st.write("Sử dụng công thức tính toán quản lý rủi ro tuyệt đối và so khớp biểu phí để tránh tình trạng 'Lợi nhuận nhỏ hơn phí'.")
    
    col_b1, col_b2 = st.columns(2)
    
    with col_b1:
        st.markdown("#### 1. THAM SỐ GIAO DỊCH")
        capital = st.number_input("Tổng vốn tài khoản (USDT)", min_value=10.0, value=2000.0, step=100.0)
        risk_pct = st.slider("Mức rủi ro chấp nhận cho mỗi lệnh (%)", 0.5, 5.0, 1.5, step=0.1)
        entry_price = st.number_input("Điểm vào lệnh - Entry (USDT)", min_value=0.0, value=latest_close)
        stop_loss = st.number_input("Điểm dừng lỗ - Stop Loss (USDT)", min_value=0.0, value=latest_close * 0.98)
        leverage = st.slider("Tốc độ đòn bẩy đề xuất", 1, 125, 10)
        
        # Fee structure configs
        st.markdown("#### 2. CẤU HÌNH BIỂU PHÍ BINANCE")
        vip_level = st.selectbox("Cấp độ VIP của bạn", [f"VIP {i}" for i in range(10)], index=0)
        use_bnb = st.checkbox("Thanh toán phí bằng BNB (Giảm 10%)", value=True)
        use_maker_promo = st.checkbox("Áp dụng ưu đãi 0% phí Maker (Hợp đồng USDⓈ-M)", value=False)
        
        open_type = st.radio("Loại lệnh khi MỞ vị thế", ["Maker (Lệnh Limit / Chờ khớp)", "Taker (Lệnh Market / Khớp ngay)"], index=0)
        close_type = st.radio("Loại lệnh khi ĐÓNG vị thế", ["Maker (Lệnh Limit / Chờ khớp)", "Taker (Lệnh Market / Khớp ngay)"], index=1)
        
    with col_b2:
        st.markdown("#### 3. KẾT QUẢ TÍNH TOÁN QUẢN LÝ VỐN")
        
        # Calculations
        allowed_loss = capital * (risk_pct / 100)
        sl_distance = abs(entry_price - stop_loss)
        sl_pct = sl_distance / entry_price
        
        if sl_distance == 0:
            st.error("Lỗi: Điểm dừng lỗ trùng với điểm vào lệnh!")
            position_size = 0.0
        else:
            position_size = allowed_loss / sl_pct
            
        margin_required = position_size / leverage
        coin_amount = position_size / entry_price
        
        # Render metrics
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Số tiền chịu rủi ro", f"${allowed_loss:.2f}")
        col_m2.metric("Khoảng cách dừng lỗ", f"{sl_pct*100:.2f}%")
        
        st.info(f"👉 **Khối lượng vị thế (Vol):** **${position_size:,.2f}**\n\n💰 **Ký quỹ cần dùng (Margin):** **${margin_required:.2f}**\n\n🪙 **Số lượng coin cần mua/bán:** **{coin_amount:.4f} {selected_coin.replace('USDT', '')}**")
        
        st.markdown("#### 4. PHÂN TÍCH PHÍ & LỢI NHUẬN RÒNG")
        
        # Calculate rates based on VIP levels
        # Simple VIP fee table representation
        vip_idx = int(vip_level.split(" ")[1])
        base_maker = max(0.0002 - (vip_idx * 0.00002), 0.0)
        base_taker = max(0.0005 - (vip_idx * 0.00004), 0.017)
        
        maker_fee_rate = 0.0 if use_maker_promo else base_maker
        taker_fee_rate = base_taker
        
        # Apply bnb discount
        if use_bnb:
            maker_fee_rate *= 0.9
            taker_fee_rate *= 0.9
            
        o_rate = maker_fee_rate if "Maker" in open_type else taker_fee_rate
        c_rate = maker_fee_rate if "Maker" in close_type else taker_fee_rate
        
        open_fee = position_size * o_rate
        close_fee = position_size * c_rate
        total_fee = open_fee + close_fee
        
        # Profit expectation (target R:R = 1:2)
        target_profit_pct = sl_pct * 2
        gross_profit = position_size * target_profit_pct
        net_profit = gross_profit - total_fee
        
        st.write(f"Phí mở vị thế: **${open_fee:.3f}** ({o_rate*100:.3f}%)")
        st.write(f"Phí đóng vị thế: **${close_fee:.3f}** ({c_rate*100:.3f}%)")
        st.write(f"⚡ **Tổng phí giao dịch (Cả 2 chiều):** **${total_fee:.3f}**")
        
        # Risk-reward visual check
        st.markdown("---")
        st.write(f"Kỳ vọng chốt lời (R:R = 1:2): **+${gross_profit:.2f}** (Lãi {target_profit_pct*100:.2f}%)")
        
        if total_fee >= allowed_loss * 0.5:
            st.error(f"🚨 **BẪY PHÍ CỰC KỲ NGUY HIỂM!** Tổng phí giao dịch (${total_fee:.2f}) chiếm tới {total_fee/allowed_loss*100:.1f}% số tiền bảo hiểm rủi ro của bạn. Hãy điều chỉnh khoảng cách SL dài ra hoặc chuyển sang cấu trúc lệnh Maker để giảm thiểu chi phí!")
        else:
            st.success(f"Lợi nhuận ròng dự kiến sau khi trừ phí: **+${net_profit:.2f}**")

        # Add to journal helper
        if st.button("📓 Đưa vị thế này vào Nhật ký nháp"):
            st.session_state.journal.append({
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "coin": selected_coin,
                "entry": entry_price,
                "sl": stop_loss,
                "vol": position_size,
                "note": f"Vị thế nháp. Rủi ro {risk_pct}%, R:R = 1:2. Tổng phí ước tính: ${total_fee:.2f}"
            })
            st.toast("Đã lưu nháp vị thế thành công! Hãy chuyển sang Tab 3 để kiểm tra.")

with tab3:
    st.subheader("📓 Nhật Ký Giao Dịch & Sửa Sai Bản Thân")
    st.write("Sự khác biệt giữa trader chuyên nghiệp và con bạc nằm ở kỷ luật viết nhật ký giao dịch để sửa sai mỗi ngày.")
    
    # Custom form to add trades manually
    with st.expander("➕ Ghi chép lệnh mới"):
        with st.form("new_trade_form"):
            col_f1, col_f2 = st.columns(2)
            f_coin = col_f1.selectbox("Coin", WATCHLIST, key="form_coin")
            f_type = col_f2.selectbox("Vị thế", ["LONG 🟢", "SHORT 🔴"])
            f_entry = col_f1.number_input("Giá Entry", value=latest_close)
            f_vol = col_f2.number_input("Volume (USDT)", value=500.0)
            f_lesson = st.text_area("Bài học xương máu rút ra (Tự kiểm điểm cái tôi, nỗi sợ hãi hoặc lòng tham)", placeholder="Ví dụ: Lệnh này bị dính SL do vội vàng múc đuổi khi giá chưa hồi về vùng giá trị EMA, hoặc tự ý nâng dời SL do gồng lỗ cảm xúc...")
            submitted = st.form_submit_button("Lưu lệnh vào Nhật ký")
            if submitted:
                st.session_state.journal.append({
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "coin": f"{f_coin} ({f_type})",
                    "entry": f_entry,
                    "sl": 0,
                    "vol": f_vol,
                    "note": f_lesson
                })
                st.success("Đã ghi nhận bài học thành công!")

    # Display list of trades
    if st.session_state.journal:
        df_journal = pd.DataFrame(st.session_state.journal)
        st.dataframe(df_journal, use_container_width=True)
        if st.button("🗑️ Xóa toàn bộ lịch sử nhật ký"):
            st.session_state.journal = []
            st.toast("Đã dọn sạch nhật ký!")
    else:
        st.info("Hiện tại chưa có lịch sử giao dịch nào được lưu trữ. Hãy bắt đầu phân tích và ghi lại bài học của mình.")