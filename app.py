import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- 頁面設定 ---
st.set_page_config(page_title="數學解題小幫手", page_icon="🎓")

# --- 介面設計 ---
st.title("🎓 數學解題小幫手")
st.markdown("同學你好！遇到不會的題目嗎？📸 **上傳照片**，讓 AI 老師幫你詳解，再出兩題讓你練習！")

# --- 從 Streamlit Secrets 讀取 API Key (安全做法) ---
# 注意：不要將 Key 直接寫在程式碼中
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # 【關鍵修改】這裡換成了你診斷出來的最新模型
    model = genai.GenerativeModel('models/gemini-2.5-flash')

except Exception as e:
    st.error("系統設定錯誤：找不到 API Key，請聯繫老師處理。")
    st.stop()

# --- 上傳圖片區 ---
uploaded_file = st.file_uploader("請點此上傳題目照片 (支援手機截圖/拍照)", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    # 顯示預覽圖
    image = Image.open(uploaded_file)
    st.image(image, caption='你的題目', use_column_width=True)
    
    # 按鈕
    if st.button("🚀 開始解題與練習"):
        with st.spinner('正在分析題目並撰寫詳解中，請稍等...'):
            try:
                # 定義給學生的提示詞
                prompt = """
                你是一位親切且專業的中學數學老師。請針對學生上傳的圖片執行以下教學：

                第一部分：【題目詳解】
                請辨識圖片中的數學題目，並用淺顯易懂的方式，一步步寫出解題過程與最終答案。
                如果題目有圖形，請用文字描述解題關鍵。

                第二部分：【舉一反三】
                為了確認學生是否學會，請修改原題目的數字（保持考點與邏輯不變），
                新出 2 題「類題」讓學生練習。

                第三部分：【類題參考答案】
                請提供上述 2 題類題的答案（只需答案或簡略過程，讓學生核對）。

                排版要求：
                1. 使用繁體中文。
                2. 數學公式請務必使用 LaTeX 格式 (例如 $x^2 + y^2 = 10$)。
                3. 請用 Markdown 的標題 (#) 與分隔線 (---) 讓版面整潔易讀。
                """
                
                response = model.generate_content([prompt, image])
                
                st.markdown("---")
                st.markdown(response.text)
                st.success("分析完成！如果不滿意，可以重新上傳再試一次。")

            except Exception as e:
                st.error(f"連線發生錯誤，請稍後再試。錯誤訊息：{e}")
