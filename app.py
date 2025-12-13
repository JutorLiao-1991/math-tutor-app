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

# --- 注入自定義 CSS (含手機版字體優化) ---
def inject_custom_css():
    st.markdown(
        """
        <style>
        /* 全域字體設定 */
        .katex-html { overflow-x: auto; overflow-y: hidden; max-width: 100%; display: block; padding-bottom: 5px; }
        .stMarkdown { max-width: 100%; overflow-wrap: break-word; }
        
        /* 頭像樣式 */
        .stChatMessage .stChatMessageAvatar {
            width: 2.8rem;
            height: 2.8rem;
            background-color: #f0f2f6; 
            border-radius: 50%;
            object-fit: cover;
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* --- 手機版 RWD 優化 --- */
        @media only screen and (max-width: 600px) {
            .stMarkdown p, .stMarkdown li, .stMarkdown div, .stChatMessage p {
                font-size: 15px !important;
                line-height: 1.6 !important;
            }
            h1 { font-size: 1.6rem !important; }
            h2 { font-size: 1.4rem !important; }
            h3 { font-size: 1.2rem !important; }
            .katex { font-size: 1.1em !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- 快取字體設定 ---
@st.cache_resource
def configure_chinese_font():
    font_file = "NotoSansTC-Regular.ttf"
    if os.path.exists(font_file):
        try:
            fm.fontManager.addfont(font_file)
            prop = fm.FontProperties(fname=font_file)
            font_name = prop.get_name()
            plt.rcParams['font.family'] = font_name
            plt.rcParams['axes.unicode_minus'] = False 
            return font_name
        except Exception as e:
            return "sans-serif"
    else:
        return "sans-serif"

# --- 快取 Google Sheets 連線 ---
@st.cache_resource
def get_google_sheet_client():
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            return client
    except Exception as e:
        print(f"GCP 連線失敗: {e}")
    return None

def save_to_google_sheets(grade, mode, image_desc, full_response, key_info=""):
    try:
        client = get_google_sheet_client()
        if client:
            sheet = client.open("Jutor_Learning_Data").sheet1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, grade, mode, image_desc, full_response, key_info])
            return True
    except Exception as e:
        st.cache_resource.clear()
        return False

# --- 圖片與頭像 ---
main_logo_path = "logo.jpg"
if os.path.exists(main_logo_path):
    page_icon_set = Image.open(main_logo_path)
else:
    page_icon_set = "🦔"
assistant_avatar = "🦔" 

# --- 頁面設定 (修正標題) ---
st.set_page_config(page_title="鳩特數理-AI Jutor", page_icon=page_icon_set, layout="centered")
inject_custom_css()
CORRECT_FONT_NAME = configure_chinese_font()

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
if 'trigger_rescue' not in st.session_state: st.session_state.trigger_rescue = False
if 'used_key_suffix' not in st.session_state: st.session_state.used_key_suffix = "" 

# --- 函數區 ---
def trigger_vibration():
    vibrate_js = """<script>if(navigator.vibrate){navigator.vibrate(30);}</script>"""
    components.html(vibrate_js, height=0, width=0)

def execute_and_show_plot(code_snippet):
    try:
        plt.rcParams['font.family'] = CORRECT_FONT_NAME
        plt.rcParams['axes.unicode_minus'] = False
        plt.figure(figsize=(6, 4))
        plt.style.use('seaborn-v0_8-whitegrid') 
        local_scope = {'plt': plt, 'np': np}
        exec(code_snippet, globals(), local_scope)
        ax = plt.gca()
        if ax.get_title(): ax.set_title(ax.get_title(), fontname=CORRECT_FONT_NAME)
        if ax.get_xlabel(): ax.set_xlabel(ax.get_xlabel(), fontname=CORRECT_FONT_NAME)
        if ax.get_ylabel(): ax.set_ylabel(ax.get_ylabel(), fontname=CORRECT_FONT_NAME)
        legend = ax.get_legend()
        if legend:
            plt.setp(legend.get_texts(), fontname=CORRECT_FONT_NAME)
        st.pyplot(plt)
        plt.close()
    except Exception as e:
        # 繪圖失敗時的錯誤捕捉
        st.warning(f"圖形繪製失敗: {e}")

# --- 【強力排版修復 v4】 ---
def clean_output_format(text):
    if not text: return text
    
    # 0. 清除開頭結尾的怪異引號 (修復 Bug 3)
    text = text.strip().lstrip("'").lstrip('"').rstrip("'").rstrip('"')

    # 1. 暴力降維: $$...$$ -> $...$
    def block_to_inline(match):
        content = match.group(1)
        if len(content) < 50 and '\\\\' not in content and 'align' not in content:
            return f"${content.strip()}$"
        return match.group(0)
    text = re.sub(r'\$\$([\s\S]*?)\$\$', block_to_inline, text)

    # 2. 括號與標點修復
    text = re.sub(r'([\(（])\s*\n\s*(.*?)\s*\n\s*([\)）])', r'\1\2\3', text)
    text = re.sub(r'\n\s*([，。、！？：,.?])', r'\1', text)

    # 3. 中文黏合劑
    cjk = r'[\u4e00-\u9fa5]'
    short_content = r'(?:(?!\n|•|- |\* ).){1,30}' 
    for _ in range(2):
        pattern = f'(?<={cjk})\s*\\n+\s*({short_content})\s*\\n+\s*(?={cjk}|[，。！？：,.?])'
        text = re.sub(pattern, r' \1 ', text)

    return text

def call_gemini_with_rotation(prompt_content, image_input=None, use_pro=False):
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): keys = [keys]
    except:
        st.error("API_KEYS 設定錯誤")
        st.stop()
    
    target_keys = keys.copy() 
    
    if use_pro:
        model_name = 'models/gemini-2.5-pro'
    else:
        model_name = 'models/gemini-2.5-flash'
    
    last_error = None
    
    for key in target_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(model_name)
            if image_input:
                response = model.generate_content([prompt_content, image_input])
            else:
                response = model.generate_content(prompt_content)
            
            return response, key[-4:] 
            
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
    if os.path.exists(main_logo_path):
        st.image(main_logo_path, use_column_width=True)
    else:
        st.markdown("<div style='font-size: 3rem; text-align: center;'>🦔</div>", unsafe_allow_html=True)

with col2:
    st.title("鳩特數理-AI Jutor")
    st.caption("Jutor AI 教學系統 v6.9 (繪圖修復+步驟細化 12/12 21:30)")

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

        if start_verbal or start_math or st.session_state.trigger_rescue:
            
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                if st.session_state.trigger_rescue:
                    mode = st.session_state.solve_mode
                    use_pro = True 
                    st.session_state.use_pro_model = True
                    st.session_state.trigger_rescue = False 
                else:
                    mode = "verbal" if start_verbal else "math"
                    st.session_state.solve_mode = mode
                    use_pro = False 
                    st.session_state.use_pro_model = False

                if use_pro:
                    loading_text = "Jutor Pro (2.5) 正在深度分析並修復錯誤..."
                else:
                    # 修正 Spinner 文字 (Bug 4)
                    loading_text = "Jutor AI (2.5) 正在思考怎麼教會你這題..."
                
                with st.spinner(loading_text):
                    try:
                        guardrail = "【過濾機制】請辨識圖片內容。若明顯為「自拍照、風景照、寵物照」等與學習無關的圖片，請回傳 REFUSE_OFF_TOPIC。若是數學題目、文字截圖、圖表分析，即使模糊或非典型格式，也請回答。"

                        transcription = f"【隱藏任務】將題目 '{question_target}' 轉譯為文字，並將幾何特徵轉為文字描述，包在 `===DESC===` 與 `===DESC_END===` 之間。"
                        
                        formatting = """
                        【排版嚴格指令】
                        1. **數值與變數不換行**：純數字(如 288, -34)、變數(如 x, y)、短式子(如 a=1)必須使用行內格式(Inline)，**嚴禁換行**，必須與前後中文緊密相連。
                        2. **列表控制**：除非是列舉不同選項，否則不要使用 Bullet Points 來顯示單一數值。
                        3. **直式計算**：只有在長算式推導時，才使用換行對齊。
                        """
                        
                        # --- 修正重點：繪圖 Raw String 強制令 (Bug 1) ---
                        plotting = """
                        【繪圖能力啟動】
                        1. 只有當題目明確涉及「函數圖形」、「幾何座標」、「統計圖表」時，才生成 Python 程式碼。
                        2. 程式碼必須能直接執行，並包在 `===PLOT===` 與 `===PLOT_END===` 之間。
                        3. 圖表標題、座標軸請使用中文。
                        4. ⚠️ 嚴格 LaTeX 規範：所有包含 LaTeX 語法的字串（如標題、標籤），**必須** 使用 Python raw string (例如 r'$y=x^2$')。
                        5. ⚠️ 避免在 title 使用過於複雜的 LaTeX (如 \left, \right)，若必須使用，請確保語法完美閉合。
                        6. ⚠️ 3D繪圖：若是空間坐標題，請務必使用 `ax = fig.add_subplot(111, projection='3d')`。
                        """

                        common_role = f"角色：你是 Jutor。年級：{selected_grade}。題目：{question_target}。"
                        if mode == "verbal":
                            style = "風格：幽默口語、譬喻教學、步驟化。"
                        else:
                            style = "風格：純算式、LaTeX、極簡。"

                        # --- 修正重點：步驟顆粒度與多選題邏輯 (Bug 2) ---
                        prompt = f"""
                        {guardrail}
                        {transcription}
                        {formatting}
                        {plotting}
                        {common_role}
                        {style}
                        
                        【題型辨識】請判斷是否為多選題，若有選出所有正確選項的指令，請逐一檢查。

                        【輸出結構嚴格要求 - 請用 `===STEP===` 分隔】
                        1. **解題過程** (為了避免資訊過載，請將過程拆解為 **4~6 個** 短步驟，每一步只講一個核心觀念)
                        ===STEP===
                        (步驟1...)
                        ===STEP===
                        (步驟2...)
                        ===STEP===
                        ...
                        
                        2. **本題答案** (標題與答案必須在同一個STEP)
                        ### 💡 本題答案
                        (請在此列出最終答案，如 x=16 或 x=18)
                        
                        ===STEP===
                        
                        3. **驗收類題** (標題與題目必須在同一個STEP)
                        ### 🎯 驗收類題
                        (請在此處直接出題，包含所有題目資訊)
                        
                        ===STEP===
                        
                        4. **類題答案** (最後一個STEP)
                        🗝️ 類題答案
                        (僅提供最終答案，不需詳解)
                        """

                        response, key_suffix = call_gemini_with_rotation(prompt, image, use_pro=use_pro)
                        st.session_state.used_key_suffix = key_suffix
                        
                        if "REFUSE_OFF_TOPIC" in response.text:
                            st.error("🙅‍♂️ 這個學校好像不會考喔！(若為誤判，請嘗試裁切圖片)")
                        else:
                            full_text = clean_output_format(response.text)
                            
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
                            # 過濾掉可能的空字串步驟
                            st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                            st.session_state.step_index = 0
                            st.session_state.is_solving = True
                            st.session_state.streaming_done = False
                            st.session_state.in_qa_mode = False
                            st.session_state.qa_history = []
                            st.session_state.data_saved = False

                            save_to_google_sheets(selected_grade, mode, image_desc, full_text, key_suffix)
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
        st.markdown(f"### {header_text} (🔥 2.5 Pro 救援)")
    else:
        st.markdown(f"### {header_text}") 
    
    if st.session_state.plot_code:
        with st.expander("📊 查看幾何/函數圖形", expanded=True):
            execute_and_show_plot(st.session_state.plot_code)

    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar=assistant_avatar):
            st.markdown(st.session_state.solution_steps[i])
            
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar=assistant_avatar):
        trigger_vibration()
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
                st.button("⬅️ 上一步", on_click=prev_step, disabled=(st.session_state.step_index == 0), use_container_width=True)

            with col_ask:
                def enter_qa_mode():
                    st.session_state.in_qa_mode = True
                    context_prompt = f"講解步驟：{current_step_text}。"
                    if st.session_state.solve_mode == "math": context_prompt += "目前是純算式模式，學生不懂。"
                    st.session_state.qa_history = [{"role": "user", "parts": [context_prompt]}, {"role": "model", "parts": ["請提問。"]}]
                st.button("🤔 我想問...", on_click=enter_qa_mode, use_container_width=True)

            with col_next:
                # 流程控制
                btn_label = "✅ 我懂了，下一步！"
                if st.session_state.step_index == total_steps - 2: 
                    btn_label = "👀 核對類題答案"
                
                def next_step():
                    st.session_state.step_index += 1
                st.button(btn_label, on_click=next_step, use_container_width=True, type="primary")

        else:
            with st.container(border=True):
                st.markdown("#### 💡 提問時間")
                for msg in st.session_state.qa_history[2:]:
                      if msg["role"] == "user": 
                          icon = "👤"
                      else: 
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
                                response, _ = call_gemini_with_rotation(full_prompt, use_pro=st.session_state.use_pro_model)
                                st.markdown(response.text)
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
            st.button("⬅️ 上一步", on_click=prev_step_end, use_container_width=True)
        with col_end_reset:
            if st.button("🔄 重新問別題", use_container_width=True):
                st.session_state.is_solving = False
                st.session_state.solution_steps = []
                st.session_state.step_index = 0
                st.session_state.in_qa_mode = False
                st.session_state.data_saved = False
                st.session_state.plot_code = None
                st.session_state.use_pro_model = False
                st.rerun()

        if not st.session_state.use_pro_model:
            st.markdown("")
            st.markdown("")
            st.markdown("---")
            warn_col1, warn_col2 = st.columns([2, 1])
            with warn_col2:
                 if st.button("🚨 答案有錯！請 Jutor Pro 支援", use_container_width=True):
                     st.session_state.trigger_rescue = True
                     st.toast("正在召喚 Jutor Pro (2.5) 專家...", icon="🔥")
                     time.sleep(1)
                     st.rerun()
