import streamlit as st
import google.generativeai as genai
import time
import random
from datetime import datetime, timedelta, timezone # 引入時間模組

st.set_page_config(page_title="Jutor API 監控室", page_icon="🕵️", layout="centered")

# --- 設定台灣時區 (UTC+8) ---
tz_tw = timezone(timedelta(hours=8))
current_time = datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")

st.title("🕵️ Jutor API 多重分身監控室")
st.caption(f"目前台灣時間：{current_time}") # 顯示當前時間
st.markdown("這裡可以幫你測試每一把 API Key 目前是否還活著。")

# --- 1. 輸入鑰匙區 ---
use_secrets = st.checkbox("直接讀取 Secrets 裡的鑰匙", value=True)

api_keys = []

if use_secrets:
    try:
        # 嘗試讀取 secrets
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): 
            api_keys = [keys]
        else:
            api_keys = keys
        st.success(f"已從後台讀取到 {len(api_keys)} 把鑰匙。")
    except:
        st.warning("找不到 Secrets 設定，請手動輸入。")
else:
    # 手動輸入模式
    user_input = st.text_area("請輸入 API Keys (一行一個，或用逗號分隔)", height=150)
    if user_input:
        raw_keys = user_input.replace("\n", ",").split(",")
        api_keys = [k.strip() for k in raw_keys if k.strip()]

# --- 2. 開始診斷 ---
if st.button("🚀 開始全系統診斷", type="primary"):
    # 更新按下按鈕時的時間
    diagnosis_time = datetime.now(tz_tw).strftime("%Y-%m-%d %H:%M:%S")
    
    if not api_keys:
        st.error("沒有鑰匙可以測試！")
    else:
        st.markdown("---")
        st.markdown(f"**診斷啟動時間：** `{diagnosis_time}`") # 顯示診斷當下時間
        progress_bar = st.progress(0)
        
        results = []
        
        # --- 這裡不需要 Shuffle，保持你在 secrets 中的順序 ---
        # 如果你有付費 Key 放在最後，它就會在最後才被測到
        target_keys = api_keys.copy()
        
        for i, key in enumerate(target_keys):
            # 遮罩顯示 Key
            masked_key = f"...{key[-4:]}"
            
            try:
                # 設定鑰匙
                genai.configure(api_key=key)
                # 測試用 Flash 模型最省最快
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # 計時開始
                start_time = time.time()
                
                # 發送訊號
                response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                
                # 計時結束 (這就是括號內顯示的秒數：延遲時間)
                duration = time.time() - start_time
                
                # 成功！
                status = "✅ 正常 (Active)"
                detail = f"{duration:.2f}s" # 顯示延遲秒數
                color = "green"
                
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota exceeded" in error_msg:
                    status = "🔴 額度已滿 (Overload)"
                    detail = "需冷卻等待"
                    color = "red"
                elif "API key not valid" in error_msg:
                    status = "Is ❌ 無效鑰匙 (Invalid)"
                    detail = "Key 有誤"
                    color = "grey"
                else:
                    status = "⚠️ 連線錯誤 (Error)"
                    detail = "未知錯誤"
                    color = "orange"
            
            # 更新進度條
            progress_bar.progress((i + 1) / len(target_keys))
            
            # 顯示結果卡片
            col1, col2, col3 = st.columns([2, 3, 2])
            with col1:
                st.code(masked_key)
            with col2:
                if color == "green":
                    st.success(status)
                elif color == "red":
                    st.error(status)
                else:
                    st.warning(status)
            with col3:
                st.caption(detail)
            
            time.sleep(0.2) # 避免測試本身過快觸發限制
            
        st.success(f"診斷完成！(時間: {diagnosis_time})")
