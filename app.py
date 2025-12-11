import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components
import random
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

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
if 'data_saved' not in st.session_state: 
    st.session_state.data_saved = False

# --- 函數：打字機效果 ---
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.02)

# --- 函數：觸發震動 ---
def trigger_vibration():
    vibrate_js = """<script>if(navigator.vibrate){navigator.vibrate(30);}</script>"""
    components.html(vibrate_js, height=0, width=0)

# --- 函數：寫入 Google Sheets (背景執行) ---
def save_to_google_sheets(grade, question, mode, full_response):
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # 請確保 Sheet 名稱正確
            sheet = client.open("Jutor_Learning_Data").sheet1
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, grade, mode, question, full_response])
            return True
    except Exception as e:
        print(f"雲端存檔失敗: {e}")
        return False

# --- 函數：API 呼叫與負載平衡 ---
def call_gemini_with_rotation(prompt_content, image_input=None):
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): keys = [keys]
    except:
        st.error("系統錯誤：請檢查 Secrets 中的 API_KEYS 設定。")
        st.stop()

    shuffled_keys = keys.copy()
    random.shuffle(shuffled_keys)
    last_error = None
    
    for key in shuffled_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            if image_input:
                response = model.generate_content([prompt_content, image_input])
            else:
                response = model.generate_content(prompt_content)
                
            return response
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Quota exceeded" in error_str or "503" in error_str:
                last_error = e
                continue 
            else:
                raise e
    raise last_error

# ================= 介面設計 =================

col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", use_column_width=True)
    else:
        st.write("🦔") 
with col2:
    st.title("鳩特數理ＡＩ小幫手")

# 【已移除】老師後台的 Expander 區塊已完全刪除

# --- 年級 ---
st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整講解口吻。")
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
    uploaded_file = st.file_uploader("選擇圖片 (JPG, PNG)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='題目預覽', use_column_width=True)
        
        question_target = st.text_input("你想問圖片中的哪一題？", placeholder="例如：第 5 題...")
        
        st.markdown("### 🚀 選擇解題模式：")
        col_btn_verbal, col_btn_math = st.columns(2)
        with col_btn_verbal:
            start_verbal = st.button("🗣️ Jutor 口語教學", use_container_width=True, type="primary")
        with col_btn_math:
            start_math = st.button("🔢 純算式解法", use_container_width=True)

        if start_verbal or start_math:
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                mode = "verbal" if start_verbal else "math"
                st.session_state.solve_mode = mode
                loading_text = "Jutor 正在思考譬喻與講解..." if mode == "verbal" else "Jutor 正在列出純數學算式..."
                
                with st.spinner(loading_text):
                    try:
                        # 防護網指令
                        guardrail_instruction = """
                        【最高防護指令：非課業過濾】
                        請先檢查圖片內容與使用者問題。
                        如果這完全不是數學、理化或學校課業相關的問題（例如：自拍、風景照、純聊天、問天氣），
                        請**務必**只回傳這行代碼，不要多說任何字： REFUSE_OFF_TOPIC
                        如果是課業問題，請繼續執行解題。
                        """

                        if mode == "verbal":
                            prompt = f"""
                            {guardrail_instruction}
                            角色：你是一位幽默、親切、很會講譬喻的數學家教「Jutor」。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。

                            【核心風格：口語化教學】
                            1. **白話解釋**：把數學觀念變成生活例子。例如：不要只說「分配律」，要說「括號外面的人跟裡面每個人握手」。
                            2. **禁止說教**：語氣要像朋友，多用「我們來試試看」、「你看喔」。
                            3. **原子化步驟**：雖然是口語，但還是要拆成小步驟，讓學生一步一步跟上。

                            【結構要求】
                            每個步驟之間插入分隔符號： ===STEP===
                            1. 第一步：用白話確認題目 ===STEP===
                            2. 第二步：解題思路（用譬喻法） ===STEP===
                            3. 第三步開始：逐步計算與講解 ===STEP===
                            ...
                            最後結構：本題答案 ===STEP=== 【驗收類題】(數字不同邏輯相同，僅題目) ===STEP=== 【類題詳解】
                            """
                        else:
                            prompt = f"""
                            {guardrail_instruction}
                            角色：你是一個純數學運算引擎。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。
                            【核心風格：純算式模式】
                            1. **嚴禁冗長中文**。內容以 LaTeX 算式為主。
                            2. **原子化步驟**：每一個數學變換都要拆成獨立步驟。
                            3. 每一個步驟後插入分隔符號： ===STEP===
                            最後結構：本題答案 ===STEP=== 【驗收類題】(僅題目) ===STEP=== 【類題解答】
                            """

                        response = call_gemini_with_rotation(prompt, image)
                        
                        if "REFUSE_OFF_TOPIC" in response.text:
                            st.error("🙅‍♂️ 這個學校好像不會考喔！請上傳數學或理化相關的題目。")
                        else:
                            raw_steps = response.text.split("===STEP===")
                            st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                            st.session_state.step_index = 0
                            st.session_state.is_solving = True
                            st.session_state.streaming_done = False
                            st.session_state.in_qa_mode = False
                            st.session_state.qa_history = []
                            st.session_state.data_saved = False

                            save_to_google_sheets(selected_grade, question_target, "指令教學" if mode=="verbal" else "純算式", response.text)
                            st.rerun()

                    except Exception as e:
                        error_msg = str(e)
                        if "429" in error_msg or "Quota exceeded" in error_msg:
                            wait_time = "60"
                            match = re.search(r"retry in (\d+(\.\d+)?)", error_msg)
                            if match: wait_time = str(int(float(match.group(1))) + 5)
                            st.warning(f"🥵 太多人問問題了，鳩特老師需要喝口水...")
                            st.error(f"請等待 {wait_time} 秒後再試一次！")
                        else:
                            st.error(f"連線發生錯誤：{e}")

# ================= 解題互動主流程 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    header_text = "🗣️ Jutor 口語教學中" if st.session_state.solve_mode == "verbal" else "🔢 純算式推導中"
    st.subheader(header_text)
    
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar="🦔"):
            st.markdown(st.session_state.solution_steps[i])
            
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar="🦔"):
        if not st.session_state.streaming_done:
            trigger_vibration()
            st.write_stream(stream_text(current_step_text))
            st.session_state.streaming_done = True
        else:
            st.markdown(current_step_text)

    total_steps = len(st.session_state.solution_steps)
    if st.session_state.step_index < total_steps - 1:
        if not st.session_state.in_qa_mode:
            st.markdown("---")
            col_back, col_ask, col_next = st.columns([1, 1, 2])
            
            with col_back:
                def prev_step():
                    if st.session_state.step_index > 0:
                        st.session_state.step_index -= 1
                        st.session_state.streaming_done = True 
                st.button("⬅️ 上一步", on_click=prev_step, disabled=(st.session_state.step_index == 0), use_container_width=True)

            with col_ask:
                def enter_qa_mode():
                    st.session_state.in_qa_mode = True
                    context_prompt = f"你正在講解這個步驟：{current_step_text}。"
                    if st.session_state.solve_mode == "math":
                        context_prompt += "目前是【純算式模式】，但學生看不懂這一步，請解釋。"
                    st.session_state.qa_history = [
                        {"role": "user", "parts": [context_prompt]},
                        {"role": "model", "parts": ["了解，請說出你的問題。"]}
                    ]
                st.button("🤔 我想問...", on_click=enter_qa_mode, use_container_width=True)

            with col_next:
                btn_label = "✅ 我懂了，下一步！"
                if st.session_state.step_index == total_steps - 2:
                    btn_label = "👀 核對類題答案"
                def next_step():
                    st.session_state.step_index += 1
                    st.session_state.streaming_done = False
                st.button(btn_label, on_click=next_step, use_container_width=True, type="primary")

        else:
            with st.container(border=True):
                st.markdown("#### 💡 提問時間")
                for msg in st.session_state.qa_history[2:]:
                     with st.chat_message("user" if msg["role"] == "user" else "assistant", avatar="👤" if msg["role"] == "user" else "🦔"):
                         st.markdown(msg["parts"][0])
                user_question = st.chat_input("請輸入問題...")
                if user_question:
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(user_question)
                    st.session_state.qa_history.append({"role": "user", "parts": [user_question]})
                    
                    with st.chat_message("assistant", avatar="🦔"):
                        with st.spinner("思考中..."):
                            try:
                                full_prompt_text = "以下是對話歷史：\n"
                                for h in st.session_state.qa_history:
                                    role = "學生" if h["role"] == "user" else "Jutor"
                                    full_prompt_text += f"{role}: {h['parts'][0]}\n"
                                full_prompt_text += f"學生最新問題: {user_question}\n請回答學生的問題。"
                                response = call_gemini_with_rotation(full_prompt_text)
                                st.write_stream(stream_text(response.text))
                                st.session_state.qa_history.append({"role": "model", "parts": [response.text]})
                            except Exception as e:
                                st.error("連線忙碌，請稍後再試。")
                    st.rerun()
                def exit_qa_mode():
                    st.session_state.in_qa_mode = False
                    st.session_state.qa_history = []
                st.button("👌 回到主流程", on_click=exit_qa_mode, use_container_width=True)

    else:
        st.markdown("---")
        st.success("🎉 恭喜完成本題學習！")
        col_end_back, col_end_reset = st.columns([1, 2])
        with col_end_back:
            def prev_step_end():
                st.session_state.step_index -= 1
                st.session_state.streaming_done = True
            st.button("⬅️ 上一步", on_click=prev_step_end, use_container_width=True)
        with col_end_reset:
            if st.button("🔄 重新問別題", use_container_width=True):
                st.session_state.is_solving = False
                st.session_state.solution_steps = []
                st.session_state.step_index = 0
                st.session_state.streaming_done = False
                st.session_state.in_qa_mode = False
                st.session_state.data_saved = False
                st.rerun()
