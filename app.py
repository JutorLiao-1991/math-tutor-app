import streamlit as st
import google.generativeai as genai
from PIL import Image
import os

# --- 頁面設定 (圖示換成刺蝟) ---
st.set_page_config(page_title="鳩特數理ＡＩ小幫手", page_icon="🦔", layout="centered")

# --- 初始化 Session State ---
if 'step_index' not in st.session_state:
    st.session_state.step_index = 0
if 'solution_steps' not in st.session_state:
    st.session_state.solution_steps = []
if 'is_solving' not in st.session_state:
    st.session_state.is_solving = False

# --- 介面設計 ---
col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", use_column_width=True)
    else:
        # 如果沒上傳 Logo，顯示小刺蝟
        st.write("🦔") 
with col2:
    st.title("鳩特數理ＡＩ小幫手")

st.markdown("同學你好！📸 **上傳照片**，Jutor 會一步一步帶著你解題喔！")
st.markdown("---")

# --- 側邊欄 ---
st.sidebar.header("📋 學生資料設定")
if os.path.exists("logo.jpg"):
    st.sidebar.image("logo.jpg", use_column_width=True)

st.sidebar.write("請選擇你的年級，Jutor 會用適合你的方式講解喔！")
selected_grade = st.sidebar.selectbox(
    "選擇年級：",
    ("國一", "國二", "國三", "高一", "高二", "高三")
)

# --- API 設定 ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except Exception as e:
    st.error("系統設定錯誤：找不到 API Key。")
    st.stop()

# --- 上傳與輸入區 ---
st.subheader("1️⃣ 上傳題目 & 指定")
uploaded_file = st.file_uploader("上傳考卷/講義 (JPG, PNG)", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='題目預覽', use_column_width=True)
    
    question_target = st.text_input("你想問圖片中的哪一題？", placeholder="例如：第 5 題...")
    st.write(f"當前設定：**{selected_grade}** | 目標題目：**{question_target if question_target else '尚未輸入'}**")
    
    # --- 按鈕邏輯區 ---
    if not st.session_state.is_solving:
        if st.button("🚀 呼叫 Jutor 老師開始教學"):
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                with st.spinner(f'Jutor 正在分析【{question_target}】，準備進行分步教學...'):
                    try:
                        # --- 核心 Prompt ---
                        prompt = f"""
                        你是一位專業、有耐心且名叫「Jutor」的數學家教。
                        學生年級：【{selected_grade}】。
                        指定題目：【{question_target}】。
                        
                        【極重要指令 - 分步教學模式】
                        請不要一次給出所有答案。請將你的講解切分成多個「小步驟」。
                        請在每個步驟之間插入這個分隔符號： ===STEP===
                        
                        內容結構如下：
                        1. 第一段：重述題目與確認 (作為開場) ===STEP===
                        2. 第二段：解題思路引導 (不要直接算，先講想法) ===STEP===
                        3. 第三段起：逐步的計算或推導過程 (每一步都要用 ===STEP=== 分隔) ===STEP===
                        4. 最後一段：給出最終答案，並加上【驗收類題】與【類題答案】。

                        教學要求：
                        1. 針對【{selected_grade}】程度。
                        2. 幾何題請用文字清晰描述圖形。
                        3. 數學公式用 LaTeX (如 $x^2$)。
                        4. 語氣要像在對話，每個步驟結尾可以問學生「這樣懂了嗎？」
                        """
                        
                        response = model.generate_content([prompt, image])
                        
                        # --- 處理回傳資料 ---
                        raw_steps = response.text.split("
