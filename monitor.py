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

st.set_page_config(page_title="Jutor 戰情監控室", page_icon="📊", layout="wide")

tz_tw = timezone(timedelta(hours=8))
current_time = datetime.now(tz_tw)
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

def get_font_prop():
    font_file = "NotoSansTC-Regular.ttf"
    if os.path.exists(font_file):
        return fm.FontProperties(fname=font_file)
    return None

font_prop = get_font_prop()

st.title("📊 Jutor 戰情監控室")
st.caption(f"目前台灣時間：{current_time_str}")

# --- 讀取數據 ---
@st.cache_data(ttl=60)
def load_data_raw():
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open("Jutor_Learning_Data").sheet1
            data = sheet.get_all_records()
            return data
    except Exception as e:
        st.error(f"無法讀取數據: {e}")
        return []

data = load_data_raw()

st.markdown("### 📈 用量分析 (Analytics)")

key_usage_counter = Counter() # 用來統計 Key 使用次數

if data:
    today_count = 0
    grade_counter = Counter()
    hour_counter = {i: 0 for i in range(24)}
    today_str = current_time.strftime("%Y-%m-%d")
    last_active_time = "無"

    for row in data:
        keys_in_row = list(row.keys())
        timestamp_str = str(row[keys_in_row[0]])
        grade = str(row[keys_in_row[1]])
        
        # 嘗試讀取最後一欄的 Key 資訊 (假設我們剛加的 app.py 會寫在最後)
        # 如果是舊資料可能沒有這一欄，用 get 避免報錯
        # 假設最後一欄的 key 名稱是 "key_info" 或是我們自己 append 上去的
        # gspread get_all_records 會把第一列當標題
        # 如果你的 Sheet 第一列還沒加標題，可能會抓不到，但 append_row 還是會寫進去
        # 這裡用 values 的最後一個值來猜測
        
        row_values = list(row.values())
        # 簡單判定：如果最後一個值長度是 4 (例如 "1a2b")，那大概就是 key suffix
        possible_key = str(row_values[-1])
        if len(possible_key) == 4:
            key_usage_counter[possible_key] += 1

        try:
            dt_obj = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            if dt_obj.strftime("%Y-%m-%d") == today_str:
                today_count += 1
                grade_counter[grade] += 1
                hour_counter[dt_obj.hour] += 1
                last_active_time = dt_obj.strftime("%H:%M")
        except ValueError:
            continue

    daily_requests = today_count
    estimated_tokens = daily_requests * 1200 
    
    if grade_counter:
        top_grade = grade_counter.most_common(1)[0][0]
    else:
        top_grade = "無資料"

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("今日解題數", f"{daily_requests} 題")
    with col2: st.metric("今日估算 Token", f"{estimated_tokens:,}")
    with col3: st.metric("今日熱門年級", top_grade)
    with col4: st.metric("最後活躍時間", last_active_time)

    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### 🕐 今日提問熱點 (小時)")
        if today_count > 0:
            hours = list(hour_counter.keys())
            counts = list(hour_counter.values())
            fig1, ax1 = plt.subplots(figsize=(5, 3))
            ax1.bar(hours, counts, color='skyblue')
            ax1.set_xlabel('Hour', fontproperties=font_prop)
            ax1.set_ylabel('Count', fontproperties=font_prop)
            ax1.set_xticks(range(0, 24, 2))
            ax1.grid(axis='y', linestyle='--', alpha=0.5)
            st.pyplot(fig1)
        else:
            st.info("今天還沒有人問問題喔")

    with col_chart2:
        st.markdown("#### 🏆 今日年級分佈")
        if today_count > 0:
            grades = list(grade_counter.keys())
            sizes = list(grade_counter.values())
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            wedges, texts, autotexts = ax2.pie(sizes, labels=grades, autopct='%1.1f%%', startangle=90)
            if font_prop:
                for text in texts: text.set_fontproperties(font_prop)
                for autotext in autotexts: autotext.set_fontproperties(font_prop)
            ax2.axis('equal')
            st.pyplot(fig2)
        else:
            st.info("尚無年級數據")

else:
    st.warning("⚠️ 目前讀取不到資料，請確認 Google Sheets 設定。")

st.markdown("---")

st.markdown("### 🏥 API 健康診斷室 (Health Check)")
st.caption("測試連線狀態，並統計歷史使用次數 (需配合 app.py v5.6 以上)。")

use_secrets = st.checkbox("直接讀取 Secrets 裡的鑰匙", value=True)
api_keys = []

if use_secrets:
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): api_keys = [keys]
        else: api_keys = keys
    except: st.warning("找不到 Secrets 設定。")
else:
    user_input = st.text_area("請輸入 API Keys", height=100)
    if user_input:
        raw_keys = user_input.replace("\n", ",").split(",")
        api_keys = [k.strip() for k in raw_keys if k.strip()]

if st.button("🚀 啟動全系統掃描", type="primary"):
    diagnosis_time = datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
    
    if not api_keys:
        st.error("沒有鑰匙可以測試！")
    else:
        st.markdown(f"**掃描時間：** `{diagnosis_time}`")
        progress_bar = st.progress(0)
        target_keys = api_keys.copy()
        
        for i, key in enumerate(target_keys):
            masked_key = f"...{key[-4:]}"
            
            # --- 取得這把 Key 的歷史使用次數 ---
            # 從前面統計的 key_usage_counter 拿資料
            usage_count = key_usage_counter.get(key[-4:], 0)
            
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                start_time = time.time()
                response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                duration = time.time() - start_time
                status = "✅ 正常"
                detail = f"{duration:.2f}s"
                color = "green"
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota exceeded" in error_msg:
                    status = "🔴 額度滿"
                    detail = "需冷卻"
                    color = "red"
                elif "API key not valid" in error_msg:
                    status = "❌ 無效"
                    detail = "Key Error"
                    color = "grey"
                else:
                    status = "⚠️ 錯誤"
                    detail = "Unknown"
                    color = "orange"
            
            progress_bar.progress((i + 1) / len(target_keys))
            
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
            with c1: st.code(masked_key)
            with c2: 
                if color == "green": st.success(status)
                elif color == "red": st.error(status)
                else: st.warning(status)
            with c3: st.caption(detail)
            with c4: 
                # 顯示歷史使用次數
                st.info(f"累計使用: {usage_count} 次")
            
            time.sleep(0.2)
            
        st.success("掃描完成！")
