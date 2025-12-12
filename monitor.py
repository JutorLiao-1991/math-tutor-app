import streamlit as st
import google.generativeai as genai
import time
import random

st.set_page_config(page_title="Jutor API 監控室", page_icon="🕵️", layout="centered")

st.title("🕵️ Jutor API 多重分身監控室")
st.markdown("這裡可以幫你測試每一把 API Key 目前是否還活著。")

# --- 1. 輸入鑰匙區 ---
# 為了安全，這裡做成密碼輸入框，或者您可以直接讀取 secrets
# 如果您部署在 Streamlit Cloud，建議直接讀取 secrets (跟主程式一樣)
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
    # 手動輸入模式 (方便臨時測試)
    user_input = st.text_area("請輸入 API Keys (一行一個，或用逗號分隔)", height=150)
    if user_input:
        # 處理換行或逗號
        raw_keys = user_input.replace("\n", ",").split(",")
        api_keys = [k.strip() for k in raw_keys if k.strip()]

# --- 2. 開始診斷 ---
if st.button("🚀 開始全系統診斷", type="primary"):
    if not api_keys:
        st.error("沒有鑰匙可以測試！")
    else:
        st.markdown("---")
        progress_bar = st.progress(0)
        
        # 準備表格數據
        results = []
        
        for i, key in enumerate(api_keys):
            # 遮罩顯示 Key (只顯示後4碼)
            masked_key = f"...{key[-4:]}"
            
            try:
                # 設定鑰匙
                genai.configure(api_key=key)
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # 計時開始
                start_time = time.time()
                
                # 發送極簡訊號 (只生成一個字 'Hi')
                response = model.generate_content("Hi", generation_config={"max_output_tokens": 1})
                
                # 計時結束
                duration = time.time() - start_time
                
                # 成功！
                status = "✅ 正常 (Active)"
                detail = f"{duration:.2f}s"
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
            progress_bar.progress((i + 1) / len(api_keys))
            
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
            
            time.sleep(0.5) # 稍微間隔一下避免測試本身觸發限流
            
        st.success("診斷完成！")
