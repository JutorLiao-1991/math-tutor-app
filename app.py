import streamlit as st
import google.generativeai as genai
from PIL import Image
import os

# --- 頁面設定 ---
st.set_page_config(page_title="鳩特數理ＡＩ小幫手", page_icon="🦉", layout="centered")

# --- 介面設計 ---

# 1. 嘗試顯示 Logo (如果有上傳 logo.png 的話)
# 使用兩欄排版：左邊放 Logo，右邊放標題，看起來比較專業
col1, col2 = st.columns([1, 4]) # 比例 1:4

with col1:
    # 這裡預設檔名為 logo.png，如果你上傳的是 jpg，請改成 logo.jpg
    if os.path.exists("logo.png"):
        st.image("logo.png", use_column_width=True)
    else:
        # 如果找不到圖片，顯示一個替代圖示
        st.write("🦉") 

with col2:
    st.title("鳩特數理ＡＩ小幫手")

st.markdown("同學你好！遇到不會的題目嗎？📸 **上傳照片**，讓 AI Jutor 幫你詳解，再出一題讓你驗收！")
st.markdown("---")

# --- 側邊欄：學生設定 ---
st.sidebar.header("📋 學生資料設定")

# 這裡也可以放一個小 Logo 在側邊欄 (選用)
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_column_width=True)

st.sidebar.write("請選擇你的年級，AI Jutor 會用適合你的方式講解喔！")
selected_grade = st.sidebar.selectbox(
    "選擇年級：",
    ("國一", "國二", "國三", "高一", "高二", "高三")
)

# --- 從 Streamlit Secrets 讀取 API Key ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    # 維持使用 Gemini 2.5 Flash
    model = genai.GenerativeModel('models/gemini-2.5-flash')

except Exception as e:
    st.error("系統設定錯誤：找不到 API Key，請聯繫老師處理。")
    st.stop()

# --- 上傳圖片區 ---
st.subheader("1️⃣ 上傳題目")
uploaded_file = st.file_uploader("請支援手機截圖/拍照 (JPG, PNG)", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    # 顯示預覽圖
    image = Image.open(uploaded_file)
    st.image(image, caption='已上傳的題目預覽', use_column_width=True)
    
    st.subheader("2️⃣ 開始解題")
    st.write(f"當前設定學生年級：**{selected_grade}**")
    
    # 按鈕
    if st.button("🚀 呼叫 Jutor 老師詳解"):
        with st.spinner(f'Jutor 正在用適合【{selected_grade}】的方式分析題目中，請稍等...'):
            try:
                # --- Prompt ---
                prompt = f"""
                你是一位專業、有耐心且名叫「Jutor」的數學家教。
                你現在面對的學生年級是：【{selected_grade}】。

                請針對學生上傳的圖片執行以下教學任務，請務必確保你的講解方式、語氣和使用的數學工具嚴格限制在適合該年級學生已學過的範圍內（例如：對國中生絕對不要使用微積分或他們沒學過的定理）：

                第一部分：【Jutor 詳解】
                請辨識圖片中的數學題目，並用淺顯易懂、適合【{selected_grade}】程度的方式，一步步寫出解題過程與最終答案。
                *重要：如果題目涉及幾何圖形，請用清晰的文字描述圖形的特徵、輔助線的畫法和解題關鍵，讓學生腦中能構建圖像。*

                第二部分：【驗收一題】
                為了確認學生是否真正學會核心觀念，請修改原題目的數字或情境（保持核心考點與邏輯完全不變），
                新出「1 題」類題讓學生立刻練習。

                第三部分：【驗收題參考答案】
                請提供上述該題驗收題的答案與簡略過程，讓學生寫完後核對。

                排版要求：
                1. 使用繁體中文。
                2. 數學公式請務必使用 LaTeX 格式包覆 (例如 $x^2 + y^2 = 10$ )，以確保在網頁上顯示正常。
                3. 請善用 Markdown 的標題 (#, ##) 與條列式，讓版面整潔易讀。
                4. 你的角色是 Jutor，語氣要溫和且常給予鼓勵。
                """
                
                # 發送請求
                response = model.generate_content([prompt, image])
                
                # 顯示結果
                st.markdown("---")
                st.success("分析完成！以下是 Jutor 的講解：")
                st.markdown(response.text)
                st.balloons() 

            except Exception as e:
                st.error(f"連線發生錯誤，請稍後再試。錯誤訊息：{e}")
