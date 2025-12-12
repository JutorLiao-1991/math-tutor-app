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

# --- 注入自定義 CSS ---
def inject_custom_css():
    st.markdown(
        """
        <style>
        .katex-html { overflow-x: auto; overflow-y: hidden; max-width: 100%; display: block; padding-bottom: 5px; }
        .stMarkdown { max-width: 100%; overflow-wrap: break-word; }
        .stChatMessage .stChatMessageAvatar {
            width: 2.8rem;
            height: 2.8rem;
            background-color: #f0f2f6; 
            border-radius: 50%;
            object-fit: cover;
            font-size: 1.8rem; /* 調整 Emoji 大小 */
            display: flex;
            align-items: center;
            justify-content: center;
        }
        /* 隱藏預設的 Hamburger Menu (選用) */
        /* #MainMenu {visibility: hidden;} */
        </style>
        """,
        unsafe_allow_html=True,
    )

# --- 【新版】字型設定：直接讀取本地檔案 ---
def configure_chinese_font():
    # 使用你上傳到 Github 的檔案
    font_file = "NotoSansTC-Regular.ttf"
    
    if os.path.exists(font_file):
        try:
            # 註冊字體
            fm.fontManager.addfont(font_file)
            prop = fm.FontProperties(fname=font_file)
            font_name = prop.get_name()
            
            # 設定 Matplotlib 預設
            plt.rcParams['font.family'] = font_name
            plt.rcParams['axes.unicode_minus'] = False 
            return font_name
        except Exception as e:
            print(f"字體載入錯誤: {e}")
            return "sans-serif"
    else:
        # 如果真的找不到檔案，回退到系統預設
        return "sans-serif"

# --- 圖片與頭像設定 ---
# 這裡修改為優先使用刺蝟 Emoji
main_logo_path = "logo.jpg"
if os.path.exists(main_logo_path):
    page_icon_set = Image.open(main_logo_path)
else:
    page_icon_set = "🦔"

# 設定 AI 頭像
assistant_avatar = "🦔" 

# --- 頁面設定 ---
st.set_page_config(page_title="AI 鳩特解題 v4.9", page_icon=page_icon_set, layout="centered")
inject_custom_css()

# --- 啟動時執行字型設定 ---
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
# 新增：觸發救援模式的開關
if 'trigger_rescue' not in st.session_state: st.session_state.trigger_rescue = False 

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

# --- 執行繪圖 (加入強制字型設定) ---
def execute_and_show_plot(code_snippet):
    try:
        # 在每次畫圖前，再次強制指定正確的字型名稱
        plt.rcParams['font.family'] = CORRECT_FONT_NAME
        plt.rcParams['axes.unicode_minus'] = False
        
        plt.figure(figsize=(6, 4))
        plt.style.use('seaborn-v0_8-whitegrid') 
        
        local_scope = {'plt': plt, 'np': np}
        exec(code_snippet, globals(), local_scope)
        
        # 再次確保 title/label 沒被程式碼覆蓋成預設字體 (Safe guard)
        ax = plt.gca()
        if ax.get_title(): ax.set_title(ax.get_title(), fontname=CORRECT_FONT_NAME)
        if ax.get_xlabel(): ax.set_xlabel(ax.get_xlabel(), fontname=CORRECT_FONT_NAME)
        if ax.get_ylabel(): ax.set_ylabel(ax.get_ylabel(), fontname=CORRECT_FONT_NAME)
        # 圖例字體
        legend = ax.get_legend()
        if legend:
            plt.setp(legend.get_texts(), fontname=CORRECT_FONT_NAME)

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
    
    # --- 關鍵修正：使用你清單中確認存在的 2.5 模型 ---
    if use_pro:
        model_name = 'models/gemini-2.5-pro'   # 救援模式
    else:
        model_name = 'models/gemini-2.5-flash' # 一般模式
    
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
            # 處理 Quota 限制 (429) 或 服務過載 (503)
            if "429" in str(e) or "Quota" in str(e) or "503" in str(e):
                last_error = e
                continue
            else:
                raise e
    raise last_error

# ================= 介面設計 =================

col1, col2 = st.columns([1, 4]) 
with col1:
    # 頭像顯示邏輯
    st.markdown("<div style='font-size: 3rem; text-align: center;'>🦔</div>", unsafe_allow_html=True)

with col2:
    st.title("鳩特數理 AI 夥伴")
    st.caption("Jutor AI 教學系統 v4.9 (Powered by Gemini 2.5)")

st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整講解口吻。")
with col_grade_select:
    selected_grade = st.selectbox("年級", ("國一", "國二", "國三", "高一", "高二", "高三"), label_visibility="collapsed")
st.markdown("---")

# --- 上傳區 ---
# 如果不在解題中，顯示上傳介面
if not st.session_state.is_solving:
    st.subheader("📸 1️⃣ 上傳題目 & 指定")
    uploaded_file = st.file_uploader("選擇圖片 (JPG, PNG)", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='題目預覽', use_column_width=True)
        question_target = st.text_input("你想問圖片中的哪一題？", placeholder="例如：第 5 題...")
        
        # 隱藏原本的 Pro 勾選框，改為預設 Flash
        
        st.markdown("### 🚀 選擇解題模式：")
        col_btn_verbal, col_btn_math = st.columns(2)
        with col_btn_verbal:
            start_verbal = st.button("🗣️ Jutor 口語教學", use_container_width=True, type="primary")
        with col_btn_math:
            start_math = st.button("🔢 純算式解法", use_container_width=True)

        # 觸發解題的條件：按鈕按下 OR 救援模式觸發
        if start_verbal or start_math or st.session_state.trigger_rescue:
            
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                # 設定模式
                if st.session_state.trigger_rescue:
                    # 如果是救援模式，保持原有模式，但啟用 Pro
                    mode = st.session_state.solve_mode
                    use_pro = True 
                    st.session_state.use_pro_model = True
                    st.session_state.trigger_rescue = False # 重置觸發器
                else:
                    # 正常啟動
                    mode = "verbal" if start_verbal else "math"
                    st.session_state.solve_mode = mode
                    use_pro = False # 預設 Flash
                    st.session_state.use_pro_model = False

                # 設定顯示文案
                if use_pro:
                    # 救援模式的文案
                    loading_text = "Jutor Pro (2.5) 正在深度分析並修復錯誤..."
                    current_avatar = "🔥"
                else:
                    # 一般模式的文案 (你的需求)
                    loading_text = "Jutor AI (2.5) 正在思考怎麼教會你這題，並試著畫圖..."
                    current_avatar = "🦔"
                
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
                        3. 圖表標題、座標軸請使用中文。
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
    
    # 根據是否使用 Pro 顯示不同標頭
    if st.session_state.use_pro_model:
        # 顯示 2.5 Pro
        st.markdown(f"### {header_text} (🔥 2.5 Pro 救援)")
    else:
        st.markdown(f"### {header_text} (⚡ 2.5 Flash)")
    
    if st.session_state.plot_code:
        with st.expander("📊 查看幾何/函數圖形 (AI 繪製)", expanded=True):
            execute_and_show_plot(st.session_state.plot_code)

    # 顯示之前的步驟
    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar=assistant_avatar):
            st.markdown(st.session_state.solution_steps[i])
            
    # 顯示當前步驟
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar=assistant_avatar):
        if not st.session_state.streaming_done:
            trigger_vibration()
            st.write_stream(stream_text(current_step_text))
            st.session_state.streaming_done = True
        else:
            st.markdown(current_step_text)

    total_steps = len(st.session_state.solution_steps)
    
    # --- 步驟導航與功能區 ---
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
            # QA 模式保持不變
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

    # --- 新增：救援按鈕 (在頁面底部) ---
    # 只有在還沒使用 Pro 模式，且不是 QA 模式時顯示
    if not st.session_state.use_pro_model and not st.session_state.in_qa_mode:
        st.markdown("")
        st.markdown("")
        st.markdown("---")
        # 建立一個紅色警告區塊
        warn_col1, warn_col2 = st.columns([2, 1])
        with warn_col2:
             if st.button("🚨 答案有錯！請 Jutor Pro 支援", use_container_width=True):
                 st.session_state.trigger_rescue = True
                 st.toast("正在召喚 Jutor Pro (2.5) 專家...", icon="🔥")
                 time.sleep(1) # 讓提示顯示一下
                 st.rerun()
