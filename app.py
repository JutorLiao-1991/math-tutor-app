import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components

# --- 頁面設定 ---
st.set_page_config(page_title="鳩特數理ＡＩ小幫手", page_icon="🦔", layout="centered")

# --- 初始化 Session State ---
if 'step_index' not in st.session_state:
    st.session_state.step_index = 0
if 'solution_steps' not in st.session_state:
    st.session_state.solution_steps = []
if 'is_solving' not in st.session_state:
    st.session_state.is_solving = False
if 'streaming_done' not in st.session_state:
    st.session_state.streaming_done = False
if 'in_qa_mode' not in st.session_state:
    st.session_state.in_qa_mode = False
if 'qa_history' not in st.session_state:
    st.session_state.qa_history = []
if 'solve_mode' not in st.session_state:
    st.session_state.solve_mode = "verbal" 

# --- 函數：打字機效果 (逐字元) ---
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.02)

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

# ================= 介面設計 =================

col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", use_column_width=True)
    else:
        st.write("🦔") 
with col2:
    st.title("鳩特數理ＡＩ小幫手")

# --- 年級 ---
st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整難度。")
with col_grade_select:
    selected_grade = st.selectbox(
        "年級選單",
        ("國一", "國二", "國三", "高一", "高二", "高三"),
        label_visibility="collapsed"
    )
st.markdown("---")

# --- 上傳區 ---
if not st.session_state.is_solving:
    st.subheader("📸 1️⃣ 上傳題目 & 指定")
    st.caption("手機拍照或截圖上傳，告訴我你想問哪一題。")
    uploaded_file = st.file_uploader("選擇圖片 (JPG, PNG)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='題目預覽', use_column_width=True)
        
        question_target = st.text_input("你想問圖片中的哪一題？", placeholder="例如：第 5 題...")
        
        st.markdown("### 🚀 選擇解題模式：")
        
        col_btn_verbal, col_btn_math = st.columns(2)
        
        with col_btn_verbal:
            start_verbal = st.button("🗣️ Jutor 指令教學", use_container_width=True, type="primary")
        
        with col_btn_math:
            start_math = st.button("🔢 純算式解法", use_container_width=True)

        if start_verbal or start_math:
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                mode = "verbal" if start_verbal else "math"
                st.session_state.solve_mode = mode
                
                loading_text = "Jutor 正在進行原子化指令拆解..." if mode == "verbal" else "Jutor 正在列出純數學算式..."
                
                with st.spinner(loading_text):
                    try:
                        # --- Prompt 修改重點：強制將類題與答案拆分 ---
                        
                        if mode == "verbal":
                            prompt = f"""
                            角色：你是一位精簡、直接、口令化的數學家教「Jutor」。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。

                            【最高指令 1：極簡口令風格】
                            1. **嚴禁廢話**。使用**祈使句**直接下指令。例如：「設邊長為 x」、「移項化簡」。
                            2. 每個步驟請附帶簡短的中文口令，解釋「做什麼」。

                            【最高指令 2：原子化步驟拆解】
                            1. 將解題過程切分為「最小的邏輯單位」。
                            2. **每一個**小動作之後，必須插入分隔符號： ===STEP===
                            
                            【最高指令 3：幾何題處理】
                            若遇幾何題，請用「精準文字指令」代替作圖 (例如：指令：在正方形邊上標註 x)。

                            【最高指令 4：結尾結構 (必須嚴格遵守)】
                            解題結束後，請依照順序提供以下三段內容，並用 STEP 分隔：
                            1. 本題最終答案 ===STEP===
                            2. 【驗收類題】(請出一題數字不同但邏輯相同的題目讓學生練習，不要附答案) ===STEP===
                            3. 【類題詳解】(請提供剛才那題類題的答案與簡略過程)

                            內容結構範例：
                            確認題目 ===STEP===
                            核心思路 ===STEP===
                            步驟1 ===STEP===
                            ...
                            本題答案 ===STEP===
                            驗收類題題目 ===STEP===
                            類題解答
                            """
                        else:
                            # 純算式模式
                            prompt = f"""
                            角色：你是一個純數學運算引擎。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。

                            【最高指令 1：純算式模式】
                            1. **嚴格禁止**冗長的中文解釋。
                            2. 內容以 **LaTeX 算式** 為主。
                            3. 中文僅限於極簡短的連接詞。

                            【最高指令 2：原子化步驟拆解】
                            1. 請將每一個數學運算變換拆成獨立的一步。
                            2. **每一個**算式變換後，必須插入分隔符號： ===STEP===

                            【最高指令 3：結尾結構 (必須嚴格遵守)】
                            解題結束後，請依照順序提供以下三段內容，並用 STEP 分隔：
                            1. 本題最終答案 ===STEP===
                            2. 【驗收類題】(請出一題類題，僅題目) ===STEP===
                            3. 【類題解答】(請提供類題答案)
                            
                            內容結構範例：
                            已知條件 ===STEP===
                            算式1 ===STEP===
                            ...
                            本題答案 ===STEP===
                            驗收類題題目 ===STEP===
                            類題解答
                            """

                        response = model.generate_content([prompt, image])
                        raw_steps = response.text.split("===STEP===")
                        st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                        st.session_state.step_index = 0
                        st.session_state.is_solving = True
                        st.session_state.streaming_done = False
                        st.session_state.in_qa_mode = False
                        st.session_state.qa_history = []
                        st.rerun()

                    except Exception as e:
                        st.error(f"連線錯誤：{e}")

# ================= 解題互動 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    header_text = "📝 Jutor 口令教學中" if st.session_state.solve_mode == "verbal" else "🔢 純算式推導中"
    st.subheader(header_text)
    
    # 顯示舊步驟
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar="🦔"):
            st.markdown(st.session_state.solution_steps[i])
            
    # 顯示當前步驟
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar="🦔"):
        if not st.session_state.streaming_done:
            trigger_vibration()
            st.write_stream(stream_text(current_step_text))
            st.session_state.streaming_done = True
        else:
            st.markdown(current_step_text)

    # --- 控制按鈕 ---
    total_steps = len(st.session_state.solution_steps)
    if st.session_state.step_index < total_steps - 1:
        
        if not st.session_state.in_qa_mode:
            st.markdown("---")
            col_next, col_ask = st.columns([3, 2])
            
            # 判斷按鈕文字：如果是最後一步的前一步，按鈕改成「看類題解答」
            # 邏輯：step_index 是 current， total-1 是最後一個(解答)，total-2 是類題題目
            btn_label = "✅ 我懂了，下一步！"
            if st.session_state.step_index == total_steps - 2:
                btn_label = "👀 核對類題答案"
            
            with col_next:
                def next_step():
                    st.session_state.step_index += 1
                    st.session_state.streaming_done = False
                st.button(btn_label, on_click=next_step, use_container_width=True, type="primary")
            
            with col_ask:
                def enter_qa_mode():
                    st.session_state.in_qa_mode = True
                    context_prompt = f"你正在講解這個步驟：{current_step_text}。"
                    if st.session_state.solve_mode == "math":
                        context_prompt += "目前是【純算式模式】，但學生看不懂這一步，請解釋。"
                    st.session_state.qa_history = [{"role": "model", "parts": [context_prompt]}]
                st.button("🤔 不太懂，我想問...", on_click=enter_qa_mode, use_container_width=True)

        else:
            # 問答模式介面 (保持不變)
            with st.container(border=True):
                st.markdown("#### 💡 提問時間")
                for msg in st.session_state.qa_history[1:]:
                     with st.chat_message("user" if msg["role"] == "user" else "assistant", avatar="👤" if msg["role"] == "user" else "🦔"):
                         st.markdown(msg["parts"][0])

                user_question = st.chat_input("請輸入問題...")
                if user_question:
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(user_question)
                    st.session_state.qa_history.append({"role": "user", "parts": [user_question]})
                    
                    with st.chat_message("assistant", avatar="🦔"):
                        with st.spinner("..."):
                            chat = model.start_chat(history=st.session_state.qa_history)
                            response = chat.send_message(user_question)
                            st.write_stream(stream_text(response.text))
                            st.session_state.qa_history.append({"role": "model", "parts": [response.text]})
                    st.rerun()

                def exit_qa_mode():
                    st.session_state.in_qa_mode = False
                    st.session_state.qa_history = []
                st.button("👌 回到主流程", on_click=exit_qa_mode, use_container_width=True)

    else:
        st.markdown("---")
        st.success("🎉 恭喜完成本題學習！")
        if st.button("🔄 重新問別題", use_container_width=True):
            st.session_state.is_solving = False
            st.session_state.solution_steps = []
            st.session_state.step_index = 0
            st.session_state.streaming_done = False
            st.session_state.in_qa_mode = False
            st.rerun()
