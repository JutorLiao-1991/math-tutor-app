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
import matplotlib.font_manager as fm
import numpy as np
import requests

# --- 注入自定義 CSS ---
def inject_custom_css():
    st.markdown(
        """
        <style>
        .katex-html { overflow-x: auto; overflow-y: hidden; max-width: 100%; display: block; padding-bottom: 5px; }
        .stMarkdown { max-width: 100%; overflow-wrap: break-word; }
        .stChatMessage .stChatMessageAvatar {
            width: 2.8rem; /* 稍微放大一點頭像 */
            height: 2.8rem;
            background-color: #f0f2f6; 
            border-radius: 50%; /* 讓頭像變圓形 */
            object-fit: cover;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- 自動下載並設定中文字型 ---
def configure_chinese_font():
    font_name = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_name):
        # 靜默下載，不印出太多訊息
        try:
            url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
            response = requests.get(url)
            with open(font_name, 'wb') as f:
                f.write(response.content)
        except:
            pass 

    try:
        fm.fontManager.addfont(font_name)
        plt.rcParams['font.family'] = 'Noto Sans CJK TC'
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass

# --- 圖片與頭像設定邏輯 ---
# 1. 網站主 Logo (顯示在左上角)
main_logo_path = "logo.jpg"
if os.path.exists(main_logo_path):
    page_icon_set = Image.open(main_logo_path)
else:
    page_icon_set = "🐦"

# 2. 助手對話頭像 (顯示在對話框)
# 優先找 avatar.jpg -> 其次找 logo.jpg -> 最後用 Emoji
avatar_file_path = "avatar.jpg" 

if os.path.exists(avatar_file_path):
    assistant_avatar = avatar_file_path
elif os.path.exists(main_logo_path):
    assistant_avatar = main_logo_path
else:
    assistant_avatar = "🐦"

# --- 頁面設定 ---
st.set_page_config(page_title="AI 鳩特解題 v4.6", page_icon=page_icon_set, layout="centered")
inject_custom_css()
configure_chinese_font()

# --- 初始化 Session State ---
if 'step_index' not in st.session_state: st.session_state.step_index = 0
if 'solution_steps' not in st.session_state: st.session_state.solution_steps = []
if 'is_solving' not in st.session_state: st.session_state.is_solving = False
if 'streaming_done' not in st.session_state: st.session_state.streaming_done = False
if 'in_qa_mode' not in st.session_state: st.session_state.in_qa_mode = False
if 'qa_history' not in st.session_state: st.session_state.qa_history = []
if 'solve_mode' not in st.session_state: st.session_state.solve_mode = "verbal"
if 'data_saved' not in st.session_state: st.session_state.data_saved = False
if 'plot_code' not in st.session_state: st.session_state.plot_code = None
if 'use_pro_model' not in st.session_state: st.session_state.use_pro_model = False

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

def execute_and_show_plot(code_snippet):
    try:
        # 重設字型確保中文正常
        plt.rcParams['font.family'] = 'Noto Sans CJK TC'
        plt.rcParams['axes.unicode_minus'] = False
        
        plt.figure(figsize=(6, 4))
        plt.style.use('seaborn-v0_8-whitegrid') 
        local_scope = {'plt': plt, 'np': np}
        exec(code_snippet, globals(), local_scope)
        st.pyplot(plt)
        plt.close()
    except Exception as e:
        st.warning(f"圖形繪製失敗: {e}")

def call_gemini_with_rotation(prompt_content, image_input=None, use_pro=False):
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): keys = [keys]
    except:
        st.error("API_KEYS 設定錯誤")
        st.stop()
    
    shuffled_keys = keys.copy()
    random.shuffle(shuffled_keys)
    
    # Flash: 2.5-flash
    # Pro: 2.5-pro
    model_name = 'models/gemini-2.5-pro' if use_pro else 'models/gemini-2.5-flash'
    
    last_error = None
    
    for key in shuffled_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name)
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
    # 這裡始終顯示主 Logo
    if os.path.exists(main_logo_path): 
        st.image(main_logo_path, use_column_width=True)
    else: 
        st.markdown("<h1 style='text-align: center;'>鳩</h1>", unsafe_allow_html=True)
with col2:
    st.title("鳩特數理ＡＩ小幫手")
    st.caption("AI 鳩特解題 v4.6 (獨立頭像版)")

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
        
        use_pro = st.checkbox("🔥 啟用 2.5 Pro 深度思考 (適合難題或 Flash 解錯時)", value=False)
        
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
                st.session_state.use_pro_model = use_pro
                
                engine_name = "Jutor 2.5 Pro" if use_pro else "Jutor 2.5 Flash"
                loading_text = f"{engine_name} 正在啟動繪圖引擎與分析..."
                
                with st.spinner(loading_text):
                    try:
                        guardrail = "【最高防護】非課業相關(自拍/風景)請回傳: REFUSE_OFF_TOPIC"
                        transcription = f"【隱藏任務】將題目 '{question_target}' 轉譯為文字，並將幾何特徵轉為文字描述，包在 `===DESC===` 與 `===DESC_END===` 之間。"
                        formatting = "【排版】文字算式分行。長算式用 `\\\\` 換行。"
                        plotting = """
                        【繪圖能力啟動】
                        如果題目涉及「函數圖形」或「幾何座標」，請產生 Python 程式碼 (matplotlib + numpy)。
                        1. 程式碼必須能直接執行。
                        2. 必須包在 `===PLOT===` 與 `===PLOT_END===` 之間。
                        3. 圖表標題、座標軸若有中文，請直接使用中文(不用擔心字型問題，後台已設定好)。
                        """

                        common_role = f"角色：你是 Jutor。年級：{selected_grade}。題目：{question_target}。"
                        if mode == "verbal":
                            style = "風格：幽默口語、譬喻教學、步驟化。"
                        else:
                            style = "風格：純算式、LaTeX、極簡。"

                        prompt = f"""
                        {guardrail}
                        {transcription}
                        {formatting}
                        {plotting}
                        {common_role}
                        {style}

                        結構要求：
                        (描述) ===DESC=== ... ===DESC_END===
                        (繪圖-選用) ===PLOT=== python code ===PLOT_END===
                        (解題)
                        確認題目 ===STEP===
                        解題過程(每一步STEP分隔) ===STEP===
                        ...
                        本題答案 ===STEP=== 【驗收類題】 ===STEP=== 【類題詳解】
                        """

                        response = call_gemini_with_rotation(prompt, image, use_pro=use_pro)
                        
                        if "REFUSE_OFF_TOPIC" in response.text:
                            st.error("🙅‍♂️ 這個學校好像不會考喔！")
                        else:
                            full_text = response.text
                            image_desc = "無描述"
                            desc_match = re.search(r"===DESC===(.*?)===DESC_END===", full_text, re.DOTALL)
                            if desc_match:
                                image_desc = desc_match.group(1).strip()
                                full_text = full_text.replace(desc_match.group(0), "")

                            plot_code = None
                            plot_match = re.search(r"===PLOT===(.*?)===PLOT_END===", full_text, re.DOTALL)
                            if plot_match:
                                plot_code = plot_match.group(1).strip()
                                plot_code = plot_code.replace("```python", "").replace("```", "")
                                full_text = full_text.replace(plot_match.group(0), "")
                            
                            st.session_state.plot_code = plot_code
                            
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
                        if "429" in str(e) or "Quota" in str(e): 
                            st.warning("🥵 系統忙碌中...")
                            st.error("請稍候重試！")
                        else: st.error(f"錯誤：{e}")

# ================= 解題互動 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    header_text = "🗣️ Jutor 口語教學中" if st.session_state.solve_mode == "verbal" else "🔢 純算式推導中"
    if st.session_state.use_pro_model:
        header_text += " (🔥 2.5 Pro)"
    st.subheader(header_text)
    
    if st.session_state.plot_code:
        with st.expander("📊 查看幾何/函數圖形 (AI 繪製)", expanded=True):
            execute_and_show_plot(st.session_state.plot_code)

    for i in range(st.session_state.step_index):
        # 這裡會讀取新的 avatar.jpg
        with st.chat_message("assistant", avatar=assistant_avatar):
            st.markdown(st.session_state.solution_steps[i])
            
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar=assistant_avatar):
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
                     if msg["role"] == "user": 
                         icon = "👤"
                     else: 
                         # 這裡也會讀取新的 avatar.jpg
                         icon = assistant_avatar
                     
                     with st.chat_message(msg["role"], avatar=icon):
                         st.markdown(msg["parts"][0])
                         
                user_question = st.chat_input("請輸入問題...")
                if user_question:
                    with st.chat_message("user", avatar="👤"): st.markdown(user_question)
                    st.session_state.qa_history.append({"role": "user", "parts": [user_question]})
                    
                    with st.chat_message("assistant", avatar=assistant_avatar):
                        with st.spinner("思考中..."):
                            try:
                                full_prompt = "對話紀錄:\n" + "\n".join([f"{h['role']}:{h['parts'][0]}" for h in st.session_state.qa_history]) + f"\n新問題:{user_question}"
                                response = call_gemini_with_rotation(full_prompt, use_pro=st.session_state.use_pro_model)
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
                st.session_state.plot_code = None
                st.session_state.use_pro_model = False
                st.rerun()
