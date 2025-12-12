import streamlit as st
import google.generativeai as genai
import time
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px # 需要安裝 plotly: pip install plotly
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="Jutor 戰情室", page_icon="📊", layout="wide")

st.title("📊 Jutor 戰情室：用量與健康監控")

# --- 1. 連線 Google Sheets 取得數據 ---
@st.cache_data(ttl=60) # 設定快取 60 秒，避免一直讀取浪費額度
def load_data():
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # 讀取所有資料
            sheet = client.open("Jutor_Learning_Data").sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
    except Exception as e:
        st.error(f"無法讀取數據: {e}")
        return pd.DataFrame()

df = load_data()

# --- 2. 儀表板顯示區 ---

if not df.empty:
    # 資料前處理：轉換時間格式
    # 假設 Excel 第一欄是 "時間" (2025-12-11 10:00:00)
    # 如果您的欄位名稱不同，請這裡修改，例如 df['Timestamp']
    # 這裡假設是用我們 app.py 產生的，是第一欄，如果 gspread 讀取有標題，通常 key 是標題
    # 為了保險，我們直接看欄位名稱
    
    # 嘗試找出時間欄位 (通常是第一欄)
    time_col = df.columns[0] 
    df[time_col] = pd.to_datetime(df[time_col])
    
    # 篩選出今天的資料
    today = datetime.now().date()
    df_today = df[df[time_col].dt.date == today]
    
    # 計算指標
    daily_requests = len(df_today)
    daily_limit = 1500 * len(st.secrets["API_KEYS"]) # 假設一把鑰匙 1500 次，你有 N 把
    
    # 估算 Token (非常粗略：假設一題平均回答 500 字，約 800 tokens)
    estimated_tokens = daily_requests * 800 
    
    # --- 顯示大數據卡片 ---
    st.markdown("### 📅 今日戰況 (Daily Usage)")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("今日解題總數", f"{daily_requests} 題", delta=f"剩餘額度約 {daily_limit - daily_requests}")
    with col2:
        st.metric("估算 Token 消耗", f"{estimated_tokens:,}", "僅供參考")
    with col3:
        # 找出最多人問的年級
        try:
            top_grade = df_today[df.columns[1]].mode()[0] # 假設第二欄是年級
        except:
            top_grade = "無資料"
        st.metric("今日最愛問年級", top_grade)
    with col4:
        # 找出今日使用率 (百分比)
        usage_rate = (daily_requests / daily_limit) * 100
        st.metric("系統負載率", f"{usage_rate:.1f}%")

    # --- 顯示圖表 ---
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### 🕐 今日提問熱點時段")
        if not df_today.empty:
            df_today['hour'] = df_today[time_col].dt.hour
            hourly_counts = df_today['hour'].value_counts().sort_index()
            st.bar_chart(hourly_counts)
        else:
            st.info("今天還沒有人問問題喔")

    with col_chart2:
        st.markdown("#### 🏆 各年級提問佔比 (歷史總計)")
        if not df.empty:
            grade_col = df.columns[1] # 假設第二欄是年級
            pie_data = df[grade_col].value_counts()
            fig = px.pie(values=pie_data.values, names=pie_data.index, hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

else:
    st.warning("目前還沒有任何數據，請先讓學生使用 Jutor 解幾題吧！")


# --- 3. (原本的) API 健康診斷區 ---
st.markdown("### 🏥 API 健康診斷 (Real-time Health Check)")
if st.button("🚀 掃描所有鑰匙狀態"):
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): keys = [keys]
    except:
        keys = []
        st.error("找不到 Keys")

    if keys:
        cols = st.columns(len(keys))
        for i, key in enumerate(keys):
            with cols[i]:
                masked = f"Key-{i+1} (...{key[-4:]})"
                try:
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel('models/gemini-2.5-flash')
                    start = time.time()
                    model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                    duration = time.time() - start
                    st.success(f"{masked}\n✅ 正常 ({duration:.2f}s)")
                except Exception as e:
                    if "429" in str(e):
                        st.error(f"{masked}\n🔴 額度滿了")
                    else:
                        st.warning(f"{masked}\n⚠️ 異常")
