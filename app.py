import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components
import random
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

# --- 注入自定義 CSS ---
def inject_custom_css():
    st.markdown(
        """
        <style>
        .katex-html { overflow-x: auto; overflow-y: hidden; max-width: 100%; display: block; padding-bottom: 5px; }
        .stMarkdown { max-width: 100%; overflow-wrap: break-word; }
        .stChatMessage .stChatMessageAvatar { background-color: #f0f2f6; color: #31333F; font-weight: bold; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- 頁面設定 ---
st.set_page_config(page_title="AI 鳩特解題 v3.8", page_icon="🐦", layout="centered")
inject_custom_css()

# --- 初始化 Session State ---
if 'step_index' not in st.session_state: st.session_state.step_index = 0
if 'solution_steps' not in st.session_state: st.session_state.solution_steps = []
if 'is_solving' not in st.session_state: st.session_state.is_solving = False
if 'streaming_done' not in st.session_state: st.session_state.streaming_done = False
if 'in_qa_mode' not in st.session_state: st.session_state.in_qa_mode = False
if 'qa_history' not in st.session_state: st.session_state.qa_history = []
if 'solve_mode' not in st.session_state: st.session_state.solve_mode = "verbal"
if 'data_saved' not in st.session_state: st.session_state.data_saved = False
# 【新增】存儲繪圖代碼
if 'plot_code' not in st.session_state: st.session_state.plot_code = None

# --- 函數區 ---
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.02)

def trigger_vibration():
    vibrate_js = """<script>if(navigator.vibrate){navigator.vibrate(30);}</script>"""
    components.html(vibrate_js, height=0, width=0)

def save_to_google_sheets(grade, mode, image_desc, full_response):
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open("Jutor_Learning_Data").sheet1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, grade, mode, image_desc, full_response])
            return True
    except Exception as e:
        print(f"存檔失敗: {e}")
        return False

# --- 【核心新增】執行 AI 給的繪圖程式碼 ---
def execute_and_show_plot(code_snippet):
    try:
        # 建立一個全新的圖表，避免重疊
        plt.figure(figsize=(6, 4))
        
        # 為了安全，我們限制 exec 能存取的環境
        # 讓 AI 可以使用 plt (matplotlib) 和 np (numpy)
        local_scope = {'plt': plt, 'np': np}
        
        # 執行 AI 寫的程式碼
        exec(code_snippet, globals(), local_scope)
        
        # 在 Streamlit 顯示
        st.pyplot(plt)
        
        # 關閉圖表釋放記憶體
        plt.close()
    except Exception as e:
        st.warning(f"圖形繪製失敗 (代碼錯誤): {e}")

# --- API 呼叫 ---
def call_gemini_with_rotation(prompt_content, image_input=None):
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): keys = [keys]
    except:
        st.error("API_KEYS 設定錯誤")
        st.stop()
    
    shuffled_keys = keys.copy()
    random.shuffle(shuffled_keys)
    last_error = None
    
    for key in shuffled_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash') # 使用 1.5 Flash 穩定版
            if image_input:
                response = model.generate_content([prompt_content, image_input])
            else:
                response = model.generate_content(prompt_content)
            return response
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e) or "503" in str(e):
                last_error = e
                continue
            else:
                raise e
    raise last_error

# ================= 介面設計 =================

col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists("logo.jpg"): st.image("logo.jpg", use_column_width=True)
    else: st.markdown("<h1 style='text-align: center;'>鳩</h1>", unsafe_allow_html=True)
with col2:
    st.title("鳩特數理ＡＩ小幫手")
    st.caption("AI 鳩特解題 v3.8 (繪圖升級版)")

st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整講解口吻。")
with col_grade_select:
    selected_grade = st.selectbox("年級", ("國一", "國二", "國三", "高一", "高二", "高三"), label_visibility="collapsed")
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
                loading_text = "Jutor 正在思考..."
                
                with st.spinner(loading_text):
                    try:
                        # 防護網
                        guardrail_instruction = "【最高防護指令】非課業相關(自拍/風景)請回傳: REFUSE_OFF_TOPIC"
                        transcription_instruction = f"【隱藏任務】將題目 '{question_target}' 轉譯為文字，並將幾何特徵轉為文字描述，包在 `===DESC===` 與 `===DESC_END===` 之間。"
                        formatting_instruction = "【排版】文字算式分行。長算式用 `\\\\` 換行。"

                        # --- 【新增】繪圖指令 ---
                        plotting_instruction = """
                        【繪圖能力啟動】
                        如果題目涉及「函數圖形」或「幾何座標」，請**務必**產生一段 Python 程式碼來繪製該圖形。
                        1. 程式碼必須使用 `import matplotlib.pyplot as plt` 和 `import numpy as np`。
                        2. 圖形必須有清楚的標示 (Title, Labels, Grid)。
                        3. 請將這段程式碼包在 `===PLOT===` 與 `===PLOT_END===` 之間。
                        4. 若不需要繪圖，則不需要回傳此區塊。
                        """

                        common_role = f"角色：你是 Jutor。年級：{selected_grade}。題目：{question_target}。"
                        if mode == "verbal":
                            style = "風格：幽默口語、譬喻教學、步驟化。"
                        else:
                            style = "風格：純算式、LaTeX、極簡。"

                        prompt = f"""
                        {guardrail_instruction}
                        {transcription_instruction}
                        {formatting_instruction}
                        {plotting_instruction}
                        
                        {common_role}
                        {style}

                        最後結構：
                        (描述區塊) ===DESC=== ... ===DESC_END===
                        (繪圖區塊-選用) ===PLOT=== python程式碼 ===PLOT_END===
                        (解題區塊)
                        確認題目 ===STEP===
                        解題過程(每一步用STEP分隔) ===STEP===
                        ...
                        本題答案 ===STEP=== 【驗收類題】 ===STEP=== 【類題詳解】
                        """

                        response = call_gemini_with_rotation(prompt, image)
                        
                        if "REFUSE_OFF_TOPIC" in response.text:
                            st.error("🙅‍♂️ 這個學校好像不會考喔！")
                        else:
                            full_text = response.text
                            
                            # 1. 提取描述
                            image_desc = "無描述"
                            desc_match = re.search(r"===DESC===(.*?)===DESC_END===", full_text, re.DOTALL)
                            if desc_match:
                                image_desc = desc_match.group(1).strip()
                                full_text = full_text.replace(desc_match.group(0), "")

                            # 2. 【新增】提取繪圖代碼
                            plot_code = None
                            plot_match = re.search(r"===PLOT===(.*?)===PLOT_END===", full_text, re.DOTALL)
                            if plot_match:
                                plot_code = plot_match.group(1).strip()
                                # 移除 markdown 的 ```python 標記 (如果 AI 雞婆加上的話)
                                plot_code = plot_code.replace("```python", "").replace("```", "")
                                full_text = full_text.replace(plot_match.group(0), "")
                            
                            # 存入 Session
                            st.session_state.plot_code = plot_code
                            
                            # 3. 處理步驟
                            raw_steps = full_text.split("===STEP===")
                            st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                            st.session_state.step_index = 0
                            st.session_state.is_solving = True
                            st.session_state.streaming_done = False
                            st.session_state.in_qa_mode = False
                            st.session_state.qa_history = []
                            st.session_state.data_saved = False

                            save_to_google_sheets(selected_grade, mode, image_desc, full_text)
                            st.rerun()

                    except Exception as e:
                        if "429" in str(e) or "Quota" in str(e): st.warning("🥵 鳩特老師喝口水休息中... (請稍候重試)")
                        else: st.error(f"錯誤：{e}")

# ================= 解題互動 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    header_text = "🗣️ Jutor 口語教學中" if st.session_state.solve_mode == "verbal" else "🔢 純算式推導中"
    st.subheader(header_text)
    
    # --- 【新增】 如果有圖，先畫出來 ---
    if st.session_state.plot_code:
        with st.expander("📊 查看幾何/函數圖形 (AI 繪製)", expanded=True):
            execute_and_show_plot(st.session_state.plot_code)

    # 顯示步驟
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar="鳩"):
            st.markdown(st.session_state.solution_steps[i])
            
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar="鳩"):
        if not st.session_state.streaming_done:
            trigger_vibration()
            st.write_stream(stream_text(current_step_text))
            st.session_state.streaming_done = True
        else:
            st.markdown(current_step_text)

    # 按鈕控制區
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
                    context_prompt = f"講解步驟：{current_step_text}。"
                    if st.session_state.solve_mode == "math": context_prompt += "目前是純算式模式，學生不懂。"
                    st.session_state.qa_history = [{"role": "user", "parts": [context_prompt]}, {"role": "model", "parts": ["請提問。"]}]
                st.button("🤔 我想問...", on_click=enter_qa_mode, use_container_width=True)

            with col_next:
                btn_label = "✅ 我懂了，下一步！"
                if st.session_state.step_index == total_steps - 2: btn_label = "👀 核對類題答案"
                def next_step():
                    st.session_state.step_index += 1
                    st.session_state.streaming_done = False
                st.button(btn_label, on_click=next_step, use_container_width=True, type="primary")

        else:
            with st.container(border=True):
                st.markdown("#### 💡 提問時間")
                for msg in st.session_state.qa_history[2:]:
                     with st.chat_message("user" if msg["role"] == "user" else "assistant", avatar="👤" if msg["role"] == "user" else "鳩"):
                         st.markdown(msg["parts"][0])
                user_question = st.chat_input("請輸入問題...")
                if user_question:
                    with st.chat_message("user", avatar="👤"): st.markdown(user_question)
                    st.session_state.qa_history.append({"role": "user", "parts": [user_question]})
                    with st.chat_message("assistant", avatar="鳩"):
                        with st.spinner("思考中..."):
                            try:
                                full_prompt = "對話紀錄:\n" + "\n".join([f"{h['role']}:{h['parts'][0]}" for h in st.session_state.qa_history]) + f"\n新問題:{user_question}"
                                response = call_gemini_with_rotation(full_prompt)
                                st.write_stream(stream_text(response.text))
                                st.session_state.qa_history.append({"role": "model", "parts": [response.text]})
                            except: st.error("忙碌中")
                    st.rerun()
                def exit_qa_mode():
                    st.session_state.in_qa_mode = False
                    st.session_state.qa_history = []
                st.button("👌 回到主流程", on_click=exit_qa_mode, use_container_width=True)

    else:
        st.markdown("---")
        st.success("🎉 恭喜完成！")
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
                st.session_state.plot_code = None # 清除繪圖
                st.rerun()
