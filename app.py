import streamlit as st
import google.generativeai as genai

st.title("🔧 AI 模型診斷工具")

# 1. 讀取 API Key
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    st.success("✅ API Key 讀取成功")
except Exception as e:
    st.error(f"❌ 無法讀取 API Key: {e}")
    st.stop()

# 2. 測試列出模型
st.write("正在查詢您的 Key 可用的模型清單...")
try:
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            st.write(f"- 找到模型: `{m.name}`")
    
    if not available_models:
        st.error("❌ 您的 API Key 連線成功，但 Google 回傳「沒有可用模型」。")
        st.info("💡 解法：這通常代表您的 Google Cloud 專案有問題。請去 Google AI Studio 建立一個「全新的 Project」並取得新的 API Key。")
    else:
        st.success(f"✅ 測試成功！共找到 {len(available_models)} 個模型。")
        st.info(f"請複製這個名稱到原本的程式碼中使用： {available_models[0]}")

except Exception as e:
    st.error(f"❌ 連線發生致命錯誤: {e}")
    st.warning("這可能是您的 requirements.txt 沒有更新，或者 Google 服務在您所在的地區受限。")
