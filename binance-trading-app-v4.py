import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import requests

# 1. Page Config
st.set_page_config(
    layout="wide",
    page_title="Underground Trading Terminal - sếp Jesse & Downcome",
    page_icon="📈"
)

# Initialize Session States
if "journal" not in st.session_state:
    st.session_state.journal = []

# Title & Description
st.title("🎛️ Underground Trading Terminal")
st.caption("Hệ thống phân tích xu hướng EMA 34/89, cấu trúc Lý thuyết DOW, quét Phân Kỳ H4 và bảng tính Volume quản lý vốn 1-2% thực chiến.")

# 2. Sidebar Config
st.sidebar.header("🛠️ Cấu hình hệ thống")

# Watchlist coins
watchlist = ["BTC", "ETH", "BNB", "SOL", "LINK", "ADA"]
symbol = st.sidebar.selectbox("Chọn cặp coin phân tích:", watchlist)

# Telegram Config
st.sidebar.subheader("📢 Cấu hình Telegram Bot")
tg_token = st.sidebar.text_input("Telegram Bot Token:", placeholder="123456789:ABC...", type="password")
tg_chat_id = st.sidebar.text_input("Telegram Chat ID:", placeholder="987654321")

if st.sidebar.button("🔔 Gửi Tin Nhắn Thử Nghiệm"):
    if tg_token and tg_chat_id:
        test_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        payload = {
            "chat_id": tg_chat_id,
            "text": "<b>[Underground Terminal]</b> Kết nối thành công! Hệ thống cảnh báo phân kỳ đã sẵn sàng hoạt động. Chúc bạn trade gì thấy nấy! 🚀",
            "parse_mode": "HTML"
        }
        try:
            r = requests.post(test_url, json=payload, timeout=5)
            if r.status_code == 200:
                st.sidebar.success("Đã gửi tin nhắn test thành công!")
            else:
                st.sidebar.error(f"Gửi thất bại. Mã phản hồi: {r.status_code}")
        except Exception as e:
            st.sidebar.error(f"Lỗi kết nối: {str(e)}")
    else:
        st.sidebar.warning("Vui lòng điền đủ Bot Token và Chat ID!")

# Real-time / Mock data status
is_mock = False

# 3. Data Fetching & Processing Function
@st.cache_data(ttl=60)
def get_klines_data(symbol):
    limit = 120
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}USDT&interval=4h&limit={limit}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'num_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df, False
    except Exception:
        pass
    
    # FIX: Using lowercase '4h' for modern Pandas 2.0+ compatibility
    dates = pd.date_range(end=datetime.datetime.now(), periods=limit, freq='4h')
    
    np.random.seed(42)
    prices = [100.0]
    for _ in range(limit - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0.0005, 0.018)))
    df = pd.DataFrame({'open_time': dates})
    df['close'] = prices
    df['high'] = df['close'] * (1 + np.abs(np.random.normal(0.005, 0.004, limit)))
    df['low'] = df['close'] * (1 - np.abs(np.random.normal(0.005, 0.004, limit)))
    df['open'] = df['close'].shift(1).fillna(prices[0])
    df['volume'] = np.random.randint(1000, 10000, limit)
    return df, True

# 4. Fetch Funding rate info
def get_funding_info(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingInfo?symbol={symbol}USDT"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            info = res.json()
            # return dict with rate
            return info[0] if isinstance(info, list) else info
    except Exception:
        pass
    return {"lastFundingRate": "0.000100", "nextFundingTime": int((datetime.datetime.now() + datetime.timedelta(hours=4)).timestamp() * 1000)}

# Fetch Data
df, is_mock = get_klines_data(symbol)
funding_data = get_funding_info(symbol)

# Calculate indicators
df['ema_34'] = df['close'].ewm(span=34, adjust=False).mean()
df['ema_89'] = df['close'].ewm(span=89, adjust=False).mean()

# RSI
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / (loss + 1e-9)
df['rsi'] = 100 - (100 / (1 + rs))

# MACD
df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
df['macd'] = df['ema_12'] - df['ema_26']
df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
df['hist'] = df['macd'] - df['signal']

# Identify DOW structure
df['is_peak'] = False
df['is_valley'] = False
window = 3
for i in range(window, len(df) - window):
    if df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max():
        df.at[df.index[i], 'is_peak'] = True
    if df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min():
        df.at[df.index[i], 'is_valley'] = True

peak_indices = df[df['is_peak']].index.tolist()
valley_indices = df[df['is_valley']].index.tolist()

# Divergence Scanner
divergence_msg = "Không phát hiện phân kỳ/hội tụ trên RSI."
divergence_type = "None"
if len(peak_indices) >= 2:
    p2, p1 = peak_indices[-1], peak_indices[-2]
    if df['close'].iloc[p2] > df['close'].iloc[p1] and df['rsi'].iloc[p2] < df['rsi'].iloc[p1]:
        divergence_msg = "🚨 CẢNH BÁO: PHÂN KỲ GIẢM (Bearish Divergence) H4 - Phe mua yếu thế, đề phòng bẫy phá vỡ giả!"
        divergence_type = "Bearish"

if len(valley_indices) >= 2:
    v2, v1 = valley_indices[-1], valley_indices[-2]
    if df['close'].iloc[v2] < df['close'].iloc[v1] and df['rsi'].iloc[v2] > df['rsi'].iloc[v1]:
        divergence_msg = "🟢 TÍN HIỆU: HỘI TỤ TĂNG (Bullish Convergence) H4 - Lực bán cạn kiệt, phe mua đang gom hàng!"
        divergence_type = "Bullish"

# 5. TAB SYSTEM
tab1, tab2, tab3 = st.tabs([
    "📈 Xu Hướng & Phân Tích (H4)",
    "🧮 Bảng Tính Volume & Phí",
    "📔 Nhật Ký Giao Dịch Sửa Sai"
])

# ---- TAB 1: TECH ANALYSIS ----
with tab1:
    st.subheader(f"Biểu đồ phân tích xu hướng {symbol}USDT (Khung H4)")
    
    if is_mock:
        st.warning("⚠️ Đang sử dụng chế độ Dữ liệu giả lập Offline do lỗi kết nối tới API Binance.")
    else:
        st.success("⚡ Hệ thống kết nối trực tiếp API thời gian thực từ Binance Futures thành công.")

    # Funding rate Info Display
    last_fr = float(funding_data.get("lastFundingRate", 0))
    next_ft_ms = funding_data.get("nextFundingTime", 0)
    next_ft = datetime.datetime.fromtimestamp(next_ft_ms / 1000.0)
    time_left = next_ft - datetime.datetime.now()
    
    st.metric(
        label=f"Funding Rate hiện tại ({symbol}USDT)",
        value=f"{last_fr * 100:.4f}%",
        delta=f"Kỳ tiếp theo sau: {str(time_left).split('.')[0]}" if time_left.total_seconds() > 0 else "Đang thanh toán"
    )

    # Main Chart with subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.7, 0.3])

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df['open_time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="Giá nến"
    ), row=1, col=1)

    # EMA 34/89
    fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_34'], name="EMA 34 (Hồi quy)", line=dict(color='orange', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['open_time'], y=df['ema_89'], name="EMA 89 (Xu thế chính)", line=dict(color='blue', width=1.5)), row=1, col=1)

    # Annotate DOW peaks and valleys safely (avoiding directly 'color' in add_annotation)
    for idx in peak_indices[-5:]:
        fig.add_annotation(
            x=df['open_time'].iloc[idx], y=df['high'].iloc[idx],
            text="Đỉnh DOW", showarrow=True, arrowhead=1,
            font=dict(color='red', size=9), arrowcolor='red',
            row=1, col=1
        )
    for idx in valley_indices[-5:]:
        fig.add_annotation(
            x=df['open_time'].iloc[idx], y=df['low'].iloc[idx],
            text="Đáy DOW", showarrow=True, arrowhead=1,
            font=dict(color='green', size=9), arrowcolor='green',
            row=1, col=1
        )

    # RSI Subplot
    fig.add_trace(go.Scatter(x=df['open_time'], y=df['rsi'], name="RSI (14)", line=dict(color='purple', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(height=600, xaxis_rangeslider_visible=False, template='plotly_dark')
    st.plotly_chart(fig, use_container_width=True)

    # Divergence warning Box
    st.subheader("⚠️ Quét tín hiệu Phân kỳ & Cấu trúc xu hướng")
    if divergence_type == "Bearish":
        st.error(divergence_msg)
    elif divergence_type == "Bullish":
        st.success(divergence_msg)
    else:
        st.info(divergence_msg)

    # Alert to Telegram Button
    if st.button("🚀 Gửi Cảnh Báo Phân Kỳ Lên Kênh Telegram"):
        if tg_token and tg_chat_id:
            alert_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            alert_msg = f"<b>[Underground Cảnh Báo]</b>\n" \
                        f"🪙 Cặp coin: <b>{symbol}USDT</b> (Khung H4)\n" \
                        f"📊 Tín hiệu quét: <b>{divergence_msg}</b>\n" \
                        f"🕒 Thời gian: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n" \
                        f"⚠️ <i>Lưu ý: Luôn tuân thủ kỷ luật, 'Trade what you see, not what you think'! Đóng máy nếu bị dừng lỗ 3 lần liên tiếp.</i>"
            payload = {
                "chat_id": tg_chat_id,
                "text": alert_msg,
                "parse_mode": "HTML"
            }
            try:
                r = requests.post(alert_url, json=payload, timeout=5)
                if r.status_code == 200:
                    st.success("Đã gửi thông báo cảnh báo phân kỳ về Telegram thành công!")
                else:
                    st.error(f"Không thể gửi thông báo. Lỗi sàn/mã phản hồi: {r.status_code}")
            except Exception as e:
                st.error(f"Lỗi gửi cảnh báo: {str(e)}")
        else:
            st.warning("Vui lòng thiết lập cấu hình Token Telegram Bot và Chat ID ở Sidebar!")


# ---- TAB 2: VOLUME & FEES CALCULATOR ----
with tab2:
    st.subheader("🧮 Bảng Tính Volume Vào Lệnh & Phí Thực Tế")
    st.caption("Hãy nhập các thông số dưới đây, hệ thống sẽ tự động tính khối lượng vị thế (Position Size) tối ưu dựa trên kỷ luật quản lý vốn của sếp Jesse.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 1. Cấu hình Vốn & Rủi ro")
        total_balance = st.number_input("Tổng Vốn Tài Khoản (USDT):", min_value=10.0, value=2000.0, step=100.0)
        risk_pct = st.slider("Hạn mức Rủi ro chấp nhận cho lệnh (%) :", min_value=0.5, max_value=5.0, value=1.5, step=0.1)
        leverage = st.number_input("Đòn bẩy (Leverage) dự kiến:", min_value=1, max_value=125, value=10, step=1)
        
        st.markdown("#### 2. Kế hoạch Lệnh (Entry & SL)")
        entry_price = st.number_input("Điểm vào lệnh (Entry Price):", min_value=0.00001, value=float(df['close'].iloc[-1]))
        stop_loss = st.number_input("Điểm dừng lỗ (Stop Loss - SL):", min_value=0.00001, value=float(df['close'].iloc[-1]*0.97))
        target_rr = st.slider("Tỷ lệ R:R mong muốn (Risk/Reward):", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

    with col2:
        st.markdown("#### 3. Biểu Phí Binance & BNB")
        vip_tier = st.selectbox("Cấp độ VIP của bạn:", [f"VIP {i}" for i in range(10)])
        vip_idx = int(vip_tier.split()[1])
        
        use_bnb = st.checkbox("Sử dụng BNB để thanh toán phí (Giảm 10% phí Futures)", value=True)
        is_promo = st.checkbox("Áp dụng Chương trình ưu đãi (Maker 0% cho cặp U-Margined)", value=False)
        order_type = st.radio("Loại lệnh thực thi:", ["Taker (Khớp lệnh Market)", "Maker (Khớp lệnh Limit)"])
        is_maker = (order_type == "Maker (Khớp lệnh Limit)")

        # Calculations
        max_risk_usdt = total_balance * (risk_pct / 100.0)
        sl_distance_pct = abs(entry_price - stop_loss) / entry_price * 100.0
        
        if sl_distance_pct > 0:
            position_size_usdt = max_risk_usdt / (sl_distance_pct / 100.0)
        else:
            position_size_usdt = 0.0

        required_margin = position_size_usdt / leverage
        coin_amount = position_size_usdt / entry_price
        
        # Take Profit Target
        take_profit = entry_price + (entry_price - stop_loss) * target_rr if entry_price > stop_loss else entry_price - (stop_loss - entry_price) * target_rr

        # Fees Calculation
        maker_rates = [0.02, 0.016, 0.015, 0.014, 0.013, 0.012, 0.011, 0.010, 0.008, 0.006] # %
        taker_rates = [0.04, 0.040, 0.038, 0.036, 0.034, 0.032, 0.030, 0.028, 0.024, 0.020] # %
        
        m_rate = maker_rates[vip_idx] / 100.0
        t_rate = taker_rates[vip_idx] / 100.0
        
        if is_promo:
            m_rate = 0.0
            t_rate = min(t_rate, 0.035 / 100.0)
            
        rate = m_rate if is_maker else t_rate
        if use_bnb:
            rate = rate * 0.9

        open_fee = position_size_usdt * rate
        close_fee = position_size_usdt * rate
        total_fee = open_fee + close_fee

        # Gross PnL
        target_pnl_gross = (take_profit - entry_price) * coin_amount if entry_price > stop_loss else (entry_price - take_profit) * coin_amount
        net_profit = target_pnl_gross - total_fee

        st.markdown("---")
        st.markdown("#### 🎯 Kết quả tính toán Volume vị thế")
        
        # Alert check if leverage is too high
        if required_margin > total_balance:
            st.error("🚨 CẢNH BÁO: Ký quỹ vượt quá tổng vốn khả dụng! Hãy giảm Volume rủi ro hoặc hạ đòn bẩy.")
        
        # Display Metrics
        st.write(f"• Số tiền rủi ro tối đa cố định ({risk_pct}% vốn): **{max_risk_usdt:.2f} USDT**")
        st.write(f"• Khoảng cách dừng lỗ thực tế: **{sl_distance_pct:.2f}%**")
        st.write(f"• **KHỐI LƯỢNG VÀO LỆNH (Volume size):** :green[**{position_size_usdt:.2f} USDT**]")
        st.write(f"• Số lượng coin tương ứng: **{coin_amount:.4f} {symbol}**")
        st.write(f"• **Số ký quỹ cần có (Margin):** **{required_margin:.2f} USDT** (ở đòn bẩy {leverage}x)")
        st.write(f"• Ước tính Phí giao dịch (Mở + Đóng): :red[**{total_fee:.4f} USDT**] (Thuế suất: {rate*100:.4f}%)")
        st.write(f"• Điểm chốt lời (Take Profit) gợi ý (R:R = 1:{target_rr}): **{take_profit:.4f}**")
        st.write(f"• **Lợi nhuận ròng bỏ túi sau phí (Net Profit):** :green[**{net_profit:.2f} USDT**]")

        # RR check Warning
        if target_rr < 1.0:
            st.warning("⚠️ Cảnh báo rủi ro: Tỷ lệ R:R thấp hơn 1:1 vi phạm quy tắc kỷ luật Underground!")
        else:
            st.info("✅ Vị thế đạt tiêu chuẩn kỷ luật R:R an toàn tối thiểu 1:1.")

        # Quick record to Journal Button
        if st.button("📓 Lưu Nhanh Lệnh Này Vào Nhật Ký Giao Dịch"):
            trade_log = {
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": f"{symbol}USDT",
                "side": "LONG" if entry_price > stop_loss else "SHORT",
                "entry": entry_price,
                "sl": stop_loss,
                "tp": take_profit,
                "vol": position_size_usdt,
                "net_profit": net_profit,
                "lesson": "Lệnh lưu tự động từ bảng tính volume."
            }
            st.session_state.journal.append(trade_log)
            st.success("Đã ghi nhận kế hoạch vị thế thành công! Hãy chuyển sang Tab 3 để kiểm tra.")


# ---- TAB 3: TRADING JOURNAL ----
with tab3:
    st.subheader("📔 Nhật Ký Giao Dịch Cá Nhân & Sửa Sai")
    st.caption("“Cắt lỗ giống như đi vệ sinh xong phải chùi đít, là thói quen sinh lý bình thường.” Hãy ghi chép lại đầy đủ hành trình để sửa các thói quen xấu của bản thân.")

    # Form to add custom entry
    with st.expander("➕ Ghi chép một lệnh giao dịch mới thủ công"):
        with st.form("add_trade_form"):
            c1, c2 = st.columns(2)
            with c1:
                j_symbol = st.text_input("Đồng coin:", value=f"{symbol}USDT")
                j_side = st.selectbox("Vị thế:", ["LONG", "SHORT"])
                j_entry = st.number_input("Giá Entry:", min_value=0.0, value=1.0)
                j_sl = st.number_input("Giá Stop Loss:", min_value=0.0, value=0.9)
                j_tp = st.number_input("Giá Take Profit:", min_value=0.0, value=1.2)
            with c2:
                j_vol = st.number_input("Volume vào lệnh (USDT):", min_value=0.0, value=500.0)
                j_pnl = st.number_input("PnL Thực tế bỏ túi sau phí (USDT):", value=0.0)
                j_lesson = st.text_area("Bài học rút ra (Tâm lý, FOMO, vội vã,...):", placeholder="Tôi đã vội vã mua đuổi khi chưa đóng nến...")
            
            submit_btn = st.form_submit_button("📓 Lưu vào Nhật ký")
            if submit_btn:
                new_log = {
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": j_symbol,
                    "side": j_side,
                    "entry": j_entry,
                    "sl": j_sl,
                    "tp": j_tp,
                    "vol": j_vol,
                    "net_profit": j_pnl,
                    "lesson": j_lesson
                }
                st.session_state.journal.append(new_log)
                st.success("Đã lưu bài học giao dịch thành công!")

    # Display entries
    if len(st.session_state.journal) > 0:
        st.markdown("### Danh sách lịch sử lệnh")
        df_journal = pd.DataFrame(st.session_state.journal)
        
        # Statistics
        total_trades = len(df_journal)
        total_pnl = df_journal['net_profit'].sum()
        winning_trades = len(df_journal[df_journal['net_profit'] > 0])
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng Số Lệnh", f"{total_trades}")
        m2.metric("Tỷ Lệ Thắng (Win Rate)", f"{win_rate:.1f}%")
        m3.metric("Tổng PnL thực tế sau phí", f"{total_pnl:.2f} USDT")

        # Table Display
        st.dataframe(df_journal, use_container_width=True)

        if st.button("🗑️ Xóa toàn bộ Nhật ký"):
            st.session_state.journal = []
            st.rerun()
    else:
        st.info("Nhật ký giao dịch hiện tại đang trống. Hãy lên kế hoạch vị thế ở Tab 2 và bấm nút lưu tự động nhé!")
