import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- 頁面設定 ---
st.set_page_config(page_title="鳩特解題AI", page_icon="🦉")

# --- 1. 修改標題與歡迎詞 ---
st.title("鳩特解題AI")
st.markdown("同學你好！遇到不會的題目嗎？📸 **上傳照片**，讓AI鳩特幫你詳解，並再出一題讓你驗收。")

# --- 2. 設定 API Key (從 Streamlit Secrets 讀取) ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')
except Exception as e:
    st.error("系統設定錯誤：找不到 API Key，請聯繫老師處理。")
    st.stop()

# --- 3. 追加功能：年級選擇器 ---
# 放在側邊欄或主畫面皆可，這裡放在主畫面讓學生必選
grade = st.selectbox(
    "請先選擇你的年級 (AI 鳩特會根據你的年級調整講解方式)",
    ["國中七年級 (國一)", "國中八年級 (國二)", "國中九年級 (國三)", "高中一年級", "高中二年級", "高中三年級"]
)

# --- 上傳圖片區 ---
uploaded_file = st.file_uploader("請點此上傳題目照片", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='你的題目', use_column_width=True)
    
    if st.button("🚀 開始解題"):
        with st.spinner('AI 鳩特正在思考中，請稍等...'):
            try:
                # --- 4. 修改提示詞 (Prompt) ---
                # 加入年級變數、修改題目數量為 1 題、加入圖形描述指令
                prompt = f"""
                你是一位專業且教學經驗豐富的數學老師，現在要指導一位「{grade}」的學生。
                請針對學生上傳的圖片執行以下教學任務：

                任務一：【題目詳解】
                1. 辨識圖片中的數學題目。
                2. 針對「{grade}」學生已學過的知識點進行講解，避免使用該年級尚未教過的超前公式。
                3. 請提供詳細的步驟與邏輯。
                4. **關於圖形**：如果解題需要參考圖形，請用文字詳細描述圖形的特徵（例如：「這是一個頂角為 30 度的等腰三角形...」），或嘗試用文字符號簡單示意。

                任務二：【驗收練習】
                為了確認學生真的聽懂了，請設計 **"1 題"** 類似的題目（類題）。
                * 請修改原題目的數字，但保持考點與解題邏輯不變。
                * 請直接在題目下方附上這題的【參考答案】與【簡略詳解】。

                排版要求：
                1. 使用繁體中文。
                2. 數學公式務必使用 LaTeX 格式 (例如 $x^2 + y^2 = 10$)。
                3. 版面請用 Markdown 清楚區隔「詳解」與「驗收練習」。
                """
                
                response = model.generate_content([prompt, image])
                
                st.markdown("---")
                st.markdown(response.text)
                st.success("解題完成！試試看下面的練習題吧！")

            except Exception as e:
                st.error(f"發生錯誤，請稍後再試。錯誤訊息：{e}")
