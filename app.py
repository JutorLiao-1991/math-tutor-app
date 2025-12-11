import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components # 用來執行 JavaScript 控制震動

# --- 頁面設定 ---
st.set_page_config(page_title="鳩特數理ＡＩ小幫手", page_icon="🦔", layout="centered")

# --- 初始化 Session State ---
if 'step_index' not in st.session_state:
    st.session_state.step_index = 0
if 'solution_steps' not in st.session_state:
    st.session_state.solution_steps = []
if 'is_solving' not in st.session_state:
    st.session_state.is_solving = False
if 'streaming_done' not in st.session_state: # 用來判斷該步驟是否已經「打字」完畢
    st.session_state.streaming_done = False

# --- 函數：打字機效果產生器 ---
def stream_text(text):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.05) # 調整打字速度，數字越小越快

# --- 函數：觸發手機震動 (JavaScript) ---
def trigger_vibration():
    #這段 JS 會呼叫手機瀏覽器的震動 API (navigator.vibrate)
    # 震動 50 毫秒 (輕微震動)
    vibrate_js = """
    <script>
    if (navigator.vibrate) {
        navigator.vibrate(50);
    }
    </script>
    """
    components.html(vibrate_js, height=0, width=0)

# --- 介面設計 ---
col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", use_column_width=True)
    else:
        st.write("🦔") 
with col2:
    st.title("鳩特數理ＡＩ小幫手")

st.markdown("同學你好！📸 **上傳照片**，Jutor 會用最白話的方式帶你解題！")
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
                with st.spinner(f'Jutor 正在用「生活化」的方式分析【{question_target}】...'):
                    try:
                        # --- 核心 Prompt (加入譬喻教學指令) ---
                        prompt = f"""
                        你是一位幽默、親切且名叫「Jutor」的數學家教。
                        學生年級：【{selected_grade}】。
                        指定題目：【{question_target}】。
                        
                        【極重要指令 1 - 去術語化教學】
                        請假設學生的數學基礎非常薄弱，對專業術語感到恐懼。
                        1. **嚴格禁止**直接使用艱澀的數學名詞（如：分配律、結合律、移項法則）。
                        2. **必須使用**生活譬喻或直觀說法。
                           - 例如：不要說「使用分配律展開」，要說「括號外面的人要跟裡面每個人都握手（人人有獎）」。
                           - 例如：不要說「移項變號」，要說「搬家過橋要付過路費（變號）」。
                        3. 語氣要像朋友聊天，多用「我們試試看」、「你看喔」這種口語。

                        【極重要指令 2 - 分步教學模式】
                        請不要一次給出所有答案。請將你的講解切分成多個「小步驟」。
                        請在每個步驟之間插入這個分隔符號： ===STEP===
                        
                        內容結構：
                        1. 第一段：用最白話的方式重述題目 (確認我們看的是同一題) ===STEP===
                        2. 第二段：解題的想法 (用譬喻解釋為什麼要這樣算) ===STEP===
                        3. 第三段起：一步一步的計算 (每一步都要用 ===STEP=== 分隔) ===STEP===
                        4. 最後一段：答案與【驗收類題】。

                        排版：公式請用 LaTeX (如 $x^2$)。
                        """
                        
                        response = model.generate_content([prompt, image])
                        
                        # --- 處理回傳資料 ---
                        raw_steps = response.text.split("===STEP===")
                        st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                        st.session_state.step_index = 0
                        st.session_state.is_solving = True
                        st.session_state.streaming_done = False # 重置打字狀態
                        st.rerun()

                    except Exception as e:
                        st.error(f"連線錯誤：{e}")

# --- 顯示解題步驟區 ---
if st.session_state.is_solving and st.session_state.solution_steps:
    st.markdown("---")
    st.subheader("2️⃣ Jutor 老師教學中")
    
    # 這裡的邏輯比較複雜，為了實現「舊的步驟直接顯示，新的步驟才打字」
    
    # 1. 先顯示「之前已經看過」的步驟 (靜態顯示，不用打字特效)
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar="🦔"):
            st.markdown(st.session_state.solution_steps[i])
            
    # 2. 顯示「當前最新」的步驟
    with st.chat_message("assistant", avatar="🦔"):
        current_text = st.session_state.solution_steps[st.session_state.step_index]
        
        # 如果這一頁剛剛刷新(使用者剛按下一步)，執行打字特效 + 震動
        if not st.session_state.streaming_done:
            trigger_vibration() # 呼叫手機震動
            st.write_stream(stream_text(current_text)) # 打字特效
            st.session_state.streaming_done = True # 標記為打完了，避免重新整理時又打一次
        else:
            # 如果已經打過字了，就直接顯示文字 (避免重複特效)
            st.markdown(current_text)

    # --- 互動控制區 ---
    total_steps = len(st.session_state.solution_steps)
    
    if st.session_state.step_index < total_steps - 1:
        col_next, col_empty = st.columns([2, 3])
        with col_next:
            # 這裡我們用 callback 來處理狀態，確保按下去時重置打字狀態
            def next_step():
                st.session_state.step_index += 1
                st.session_state.streaming_done = False # 重置，讓下一步驟可以再次打字
                
            st.button("✅ 我懂了，下一步！", on_click=next_step)
            
    else:
        st.success("🎉 恭喜你完成這題了！快試試看上面的類題吧！")
        if st.button("🔄 重新問別題"):
            st.session_state.is_solving = False
            st.session_state.solution_steps = []
            st.session_state.step_index = 0
            st.session_state.streaming_done = False
            st.rerun()
