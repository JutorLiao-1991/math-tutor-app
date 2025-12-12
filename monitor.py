import streamlit as st
import google.generativeai as genai
import time
import gspread
from google.oauth2.service_account import Credentials
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime, timedelta, timezone
from collections import Counter
import os

# --- 頁面設定 ---
st.set_page_config(page_title="Jutor 戰情監控室", page_icon="📊", layout="wide")

# --- 設定台灣時區 (UTC+8) ---
tz_tw = timezone(timedelta(hours=8))
current_time = datetime.now(tz_tw)
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

# --- 設定中文字體 (Matplotlib 用) ---
# 監控室通常是您自己看，如果沒有中文字體檔，Matplotlib 預設中文會變框框
# 這裡嘗試設定一個保險機制，盡量抓系統字體，或是直接顯示英文以免亂碼
def get_font_prop():
    font_file = "NotoSansTC-Regular.ttf" # 嘗試抓專案內的字體
    if os.path.exists(font_file):
        return fm.FontProperties(fname=font_file)
    return None # 如果沒有，就用預設 (中文可能變框框)

font_prop = get_font_prop()

st.title("📊 Jutor 戰情監控室")
st.caption(f"目前台灣時間：{current_time_str}")

# ==========================================
#  第一部分：數據儀表板 (Dashboard)
# ==========================================

# --- 連線 Google Sheets 取得數據 ---
@st.cache_data(ttl=60) # 快取 60 秒
def load_data_raw():
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # 讀取所有資料 (回傳的是 List of Dictionaries)
            sheet = client.open("Jutor_Learning_Data").sheet1
            data = sheet.get_all_records()
            return data
    except Exception as e:
        st.error(f"無法讀取數據: {e}")
        return []

data = load_data_raw()

st.markdown("### 📈 用量分析 (Analytics)")

if data:
    # --- 1. 數據清洗與統計 (純 Python 處理，不依賴 Pandas) ---
    
    # 初始化統計變數
    today_count = 0
    grade_counter = Counter()
    hour_counter = {i: 0 for i in range(24)} # 0~23 小時的計數器
    
    # 取得今天的日期 (字串格式，用於比對)
    today_str = current_time.strftime("%Y-%m-%d")
    
    last_active_time = "無"

    for row in data:
        # 假設 Sheets 的結構：[時間, 年級, 模式, 描述, 回覆]
        # 使用者第一欄是時間，Key 可能是 "時間" 或 row 的第一個 Key
        # 這裡我們取第一個 Key 的值當作時間
        keys = list(row.keys())
        timestamp_str = str(row[keys[0]]) # 時間字串
        grade = str(row[keys[1]])         # 年級
        
        try:
            # 解析時間字串 (格式需對應您 Sheets 裡的樣子，通常是 YYYY-MM-DD HH:MM:SS)
            # 注意：Sheets 存的時間通常是 UTC 或者您寫入時的時區
            # 假設您 app.py 寫入的是台灣時間字串
            dt_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            
            # 比對是否為今天
            if dt_obj.strftime("%Y-%m-%d") == today_str:
                today_count += 1
                
                # 統計年級
                grade_counter[grade] += 1
                
                # 統計小時 (0-23)
                hour_counter[dt_obj.hour] += 1
                
                # 紀錄最後活躍時間
                last_active_time = dt_obj.strftime("%H:%M")
                
            # 統計歷史總年級 (不管是不是今天)
            # 若只想看今天的分佈，把這行移到 if 裡面
            # grade_counter_all[grade] += 1 
            
        except ValueError:
            continue # 如果時間格式解析失敗就跳過

    # --- 2. 顯示卡片指標 ---
    daily_requests = today_count
    estimated_tokens = daily_requests * 1200 
    
    # 找出今日最熱門年級
    if grade_counter:
        top_grade = grade_counter.most_common(1)[0][0]
    else:
        top_grade = "無資料"

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("今日解題數", f"{daily_requests} 題")
    with col2: st.metric("今日估算 Token", f"{estimated_tokens:,}")
    with col3: st.metric("今日熱門年級", top_grade)
    with col4: st.metric("最後活躍時間", last_active_time)

    # --- 3. 繪製圖表 (使用 Matplotlib) ---
    col_chart1, col_chart2 = st.columns(2)
    
    # (左圖) 提問熱點時段 - 長條圖
    with col_chart1:
        st.markdown("#### 🕐 今日提問熱點 (小時)")
        if today_count > 0:
            hours = list(hour_counter.keys())
            counts = list(hour_counter.values())
            
            fig1, ax1 = plt.subplots(figsize=(5, 3))
            ax1.bar(hours, counts, color='skyblue')
            ax1.set_xlabel('Hour (0-23)', fontproperties=font_prop)
            ax1.set_ylabel('Count', fontproperties=font_prop)
            ax1.set_xticks(range(0, 24, 2)) # 每2小時顯示一個刻度
            ax1.grid(axis='y', linestyle='--', alpha=0.5)
            st.pyplot(fig1)
        else:
            st.info("今天還沒有人問問題喔")

    # (右圖) 年級佔比 - 圓餅圖
    with col_chart2:
        st.markdown("#### 🏆 今日年級分佈")
        if today_count > 0:
            # 準備數據
            grades = list(grade_counter.keys())
            sizes = list(grade_counter.values())
            
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            # 圓餅圖
            wedges, texts, autotexts = ax2.pie(sizes, labels=grades, autopct='%1.1f%%', startangle=90, textprops=dict(color="black"))
            
            # 設定字體以免亂碼
            if font_prop:
                for text in texts: text.set_fontproperties(font_prop)
                for autotext in autotexts: autotext.set_fontproperties(font_prop)
            
            ax2.axis('equal') # 保持圓形
            st.pyplot(fig2)
        else:
            st.info("尚無年級數據")

else:
    st.warning("⚠️ 目前讀取不到資料表，請確認 Google Sheets 連線設定是否正確，或檢查 requirements.txt 是否包含 gspread 和 google-auth。")

st.markdown("---")

# ==========================================
#  第二部分：API 健康診斷 (Diagnostics)
# ==========================================

st.markdown("### 🏥 API 健康診斷室 (Health Check)")
st.caption("測試每一把鑰匙的連線速度與剩餘額度狀態。")

# 1. 取得鑰匙
use_secrets = st.checkbox("直接讀取 Secrets 裡的鑰匙", value=True)
api_keys = []

if use_secrets:
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): 
            api_keys = [keys]
        else:
            api_keys = keys
    except:
        st.warning("找不到 Secrets 設定。")
else:
    user_input = st.text_area("請輸入 API Keys (一行一個)", height=100)
    if user_input:
        raw_keys = user_input.replace("\n", ",").split(",")
        api_keys = [k.strip() for k in raw_keys if k.strip()]

# 2. 執行診斷按鈕
if st.button("🚀 啟動全系統掃描", type="primary"):
    diagnosis_time = datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
    
    if not api_keys:
        st.error("沒有鑰匙可以測試！")
    else:
        st.markdown(f"**掃描時間：** `{diagnosis_time}`")
        progress_bar = st.progress(0)
        
        # 依序測試
        target_keys = api_keys.copy()
        
        for i, key in enumerate(target_keys):
            masked_key = f"...{key[-4:]}"
            
            try:
                genai.configure(api_key=key)
                # 測試使用 Flash 模型
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                start_time = time.time()
                # 送出極簡測試封包
                response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                duration = time.time() - start_time
                
                status = "✅ 正常 (Active)"
                detail = f"{duration:.2f}s"
                color = "green"
                
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota exceeded" in error_msg:
                    status = "🔴 額度已滿 (Overload)"
                    detail = "需冷卻"
                    color = "red"
                elif "API key not valid" in error_msg:
                    status = "❌ 無效鑰匙 (Invalid)"
                    detail = "Key Error"
                    color = "grey"
                else:
                    status = "⚠️ 連線錯誤 (Error)"
                    detail = "Unknown"
                    color = "orange"
            
            # 更新進度
            progress_bar.progress((i + 1) / len(target_keys))
            
            # 顯示結果列
            c1, c2, c3 = st.columns([2, 3, 2])
            with c1: st.code(masked_key)
            with c2: 
                if color == "green": st.success(status)
                elif color == "red": st.error(status)
                else: st.warning(status)
            with c3: st.caption(detail)
            
            time.sleep(0.2) # 安全間隔
            
        st.success("所有鑰匙掃描完成！")
