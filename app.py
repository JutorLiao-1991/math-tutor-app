import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components

# --- 頁面設定 ---
st.set_page_config(page_title="鳩特數理ＡＩ小幫手", page_icon="🦔", layout="centered")

# --- 初始化 Session State (新增問答相關狀態) ---
if 'step_index' not in st.session_state:
    st.session_state.step_index = 0
if 'solution_steps' not in st.session_state:
    st.session_state.solution_steps = []
if 'is_solving' not in st.session_state:
    st.session_state.is_solving = False
if 'streaming_done' not in st.session_state:
    st.session_state.streaming_done = False
# 【新增】紀錄是否處於中途提問模式
if 'in_qa_mode' not in st.session_state:
    st.session_state.in_qa_mode = False
# 【新增】紀錄中途提問的對話歷史
if 'qa_history' not in st.session_state:
    st.session_state.qa_history = []

# --- 函數：打字機效果產生器 (速度調快一點以配合口令化) ---
def stream_text(text):
    for word in text.split(" "):
        yield word + " "
        time.sleep(0.03) 

# --- 函數：觸發手機震動 ---
def trigger_vibration():
    vibrate_js = """<script>if(navigator.vibrate){navigator.vibrate(30);}</script>"""
    components.html(vibrate_js, height=0, width=0)

# --- API 設定 ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-2.5-flash')
except Exception as e:
    st.error("系統設定錯誤：找不到 API Key。")
    st.stop()

# ================= 介面設計開始 =================

# --- Logo 與標題 ---
col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", use_column_width=True)
    else:
        st.write("🦔") 
with col2:
    st.title("鳩特數理ＡＩ小幫手")

# --- 【修改 1】年級選擇移到主頁面 ---
st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整講解口吻。")
with col_grade_select:
    selected_grade = st.selectbox(
        "年級選單", # label 隱藏，用上面的 markdown 代替
        ("國一", "國二", "國三", "高一", "高二", "高三"),
        label_visibility="collapsed"
    )
st.markdown("---")

# --- 上傳與輸入區 (只有在沒開始解題時顯示) ---
if not st.session_state.is_solving:
    st.subheader("📸 1️⃣ 上傳題目 & 指定")
    st.caption("手機拍照或截圖上傳，告訴我你想問哪一題。")
    uploaded_file = st.file_uploader("選擇圖片 (JPG, PNG)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='題目預覽', use_column_width=True)
        
        question_target = st.text_input("你想問圖片中的哪一題？", placeholder="例如：第 5 題、選擇題第二題...")
        
        # --- 開始解題按鈕 ---
        if st.button("🚀 呼叫 Jutor 開始口令教學"):
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                with st.spinner(f'Jutor 正在鎖定【{question_target}】，準備進行原子化拆解...'):
                    try:
                        # --- 【修改 2, 3, 4】核心 Prompt：口令化、原子化步驟 ---
                        prompt = f"""
                        角色：你是一位精簡、直接、口令化的數學家教「Jutor」。
                        學生年級：【{selected_grade}】。指定題目：【{question_target}】。

                        【最高指令 1：極簡口令風格】
                        1. **嚴禁廢話**。不要說「我們來看看」、「接著我們觀察」。
                        2. 使用**祈使句**直接下指令。例如：「設邊長為 x」、「將 x 代入第一式」、「移項化簡」。
                        3. 對於{selected_grade}不熟悉的術語，用直觀動作代替，但保持簡潔。(例：不要說「利用分配律」，說「括號外乘進去，人人有獎」)。

                        【最高指令 2：原子化步驟拆解】
                        1. 將解題過程切分為「最小的邏輯單位」。
                        2. **每一個**小動作、小計算之後，都必須插入分隔符號： ===STEP===
                        3. 目標是讓學生每看一個小動作就要按一次確認。不要把多個計算擠在同一步。

                        【最高指令 3：幾何題處理 (重要)】
                        由於無法即時作圖，若遇到幾何題需要標示變數或輔助線時，請用「最精準的文字描述指令」代替作圖。
                        例如：「指令：在心中(或紙上)的正方形邊上標註 x」、「指令：連接 AC 兩點作對角線」。

                        內容結構：
                        1. 確認題目(極簡重述) ===STEP===
                        2. 核心思路(一句話點破) ===STEP===
                        3. 原子步驟1 ===STEP===
                        4. 原子步驟2 ===STEP===
                        5. ... (依此類推，步驟切越細越好) ===STEP===
                        6. 最終答案與【驗收類題】。

                        排版：公式請用 LaTeX (如 $x^2$)。
                        """
                        
                        response = model.generate_content([prompt, image])
                        raw_steps = response.text.split("===STEP===")
                        st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                        st.session_state.step_index = 0
                        st.session_state.is_solving = True
                        st.session_state.streaming_done = False
                        st.session_state.in_qa_mode = False # 確保問答模式關閉
                        st.session_state.qa_history = [] # 清空問答歷史
                        st.rerun()

                    except Exception as e:
                        st.error(f"連線錯誤：{e}")

# ================= 解題互動主流程 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    st.subheader("📝 2️⃣ Jutor 口令教學中")
    
    # 1. 顯示舊步驟 (靜態)
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar="🦔"):
            st.markdown(st.session_state.solution_steps[i])
            
    # 2. 顯示當前步驟 (打字特效 + 震動)
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar="🦔"):
        if not st.session_state.streaming_done:
            trigger_vibration()
            st.write_stream(stream_text(current_step_text))
            st.session_state.streaming_done = True
        else:
            st.markdown(current_step_text)

    # --- 【修改 5】中途提問插播功能 ---
    
    # 判斷是否顯示控制按鈕區 (如果還沒到最後一步)
    total_steps = len(st.session_state.solution_steps)
    if st.session_state.step_index < total_steps - 1:
        
        # 如果不在問答模式，顯示「下一步」和「我想問」按鈕
        if not st.session_state.in_qa_mode:
            st.markdown("---")
            col_next, col_ask = st.columns([3, 2])
            
            # 下一步按鈕
            with col_next:
                def next_step():
                    st.session_state.step_index += 1
                    st.session_state.streaming_done = False
                st.button("✅ 我懂了，下一步！", on_click=next_step, use_container_width=True, type="primary")
            
            # 我想問按鈕
            with col_ask:
                def enter_qa_mode():
                    st.session_state.in_qa_mode = True
                    # 進入問答模式時，先把當前步驟加入歷史紀錄，當作背景知識
                    st.session_state.qa_history = [
                        {"role": "model", "parts": [f"你正在講解這個步驟：{current_step_text}。學生對這一步有疑問。請簡短回答他的問題，不要劇透後面的步驟。"]}
                    ]
                st.button("🤔 不太懂，我想問...", on_click=enter_qa_mode, use_container_width=True)

        # 如果進入了問答模式 (插播畫面)
        else:
            with st.container(border=True):
                st.markdown("#### 💡 針對此步驟提問")
                st.caption("Jutor 會優先回答你關於這個步驟的問題。")
                
                # 顯示目前的問答紀錄
                for msg in st.session_state.qa_history[1:]: # 跳過第一條背景設定資訊
                     with st.chat_message("user" if msg["role"] == "user" else "assistant", avatar="👤" if msg["role"] == "user" else "🦔"):
                         st.markdown(msg["parts"][0])

                # 學生輸入問題
                user_question = st.chat_input("請輸入你的問題 (例如：為什麼要乘以 2？)...")
                if user_question:
                    # 顯示學生的問題
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(user_question)
                    st.session_state.qa_history.append({"role": "user", "parts": [user_question]})
                    
                    # 呼叫 AI 回答
                    with st.chat_message("assistant", avatar="🦔"):
                        with st.spinner("思考中..."):
                            chat = model.start_chat(history=st.session_state.qa_history)
                            response = chat.send_message(user_question)
                            st.markdown(response.text)
                            st.session_state.qa_history.append({"role": "model", "parts": [response.text]})
                    st.rerun() # 重新整理以顯示對話

                # 回到主流程按鈕
                def exit_qa_mode():
                    st.session_state.in_qa_mode = False
                    st.session_state.qa_history = [] # 清空問答歷史
                st.button("👌 OK，我懂了，回到主流程", on_click=exit_qa_mode, use_container_width=True)

    # 如果已經是最後一步
    else:
        st.markdown("---")
        st.success("🎉 恭喜完成！請嘗試上方的類題。")
        if st.button("🔄 重新問別題", use_container_width=True):
            st.session_state.is_solving = False
            st.session_state.solution_steps = []
            st.session_state.step_index = 0
            st.session_state.streaming_done = False
            st.session_state.in_qa_mode = False
            st.rerun()
