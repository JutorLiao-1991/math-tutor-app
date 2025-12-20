import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components
import random
import re
import gspread
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# --- 頁面設定 ---
main_logo_path = "logo.jpg"
if os.path.exists(main_logo_path):
    page_icon_set = Image.open(main_logo_path)
else:
    page_icon_set = "🦔"
assistant_avatar = "🦔" 

st.set_page_config(page_title="鳩特數理-AI Jutor", page_icon=page_icon_set, layout="centered")

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
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }
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

# --- 快取資源 ---
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
            timestamp = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
            sheet.insert_row([timestamp, grade, mode, image_desc, full_response, key_info], index=2)
            return True
    except Exception as e:
        st.cache_resource.clear()
        return False

# --- Telegram 回報函式 ---
def send_telegram_alert(grade, question_desc, ai_response, student_comment, student_name, image_bytes=None):
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"]["bot_token"]
            chat_id = st.secrets["telegram"]["chat_id"]
            
            if image_bytes:
                try:
                    files = {'photo': image_bytes}
                    data = {'chat_id': chat_id, 'caption': f"📸 {student_name} 上傳的原題 ({grade})"}
                    requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data=data, files=files)
                except Exception as img_err:
                    print(f"圖片發送失敗: {img_err}")

            safe_response = ai_response[:3500] 
            if len(ai_response) > 3500:
                safe_response += "\n...(後續內容過長，請至 Sheet 查看)"

            message = f"""
🚨 **Jutor 錯誤回報** 🚨
-----------------------
📅 時間: {(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')}
🎓 年級: {grade}
👤 **回報學生:** {student_name}
🗣️ **學生意見:** {student_comment}

📝 題目描述: {question_desc[:100]}...
🤖 **AI 的回答:**
{safe_response}
-----------------------
            """
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload)
            return True
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")
        return False

# --- 初始化 ---
inject_custom_css()
CORRECT_FONT_NAME = configure_chinese_font()

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
if 'image_desc_cache' not in st.session_state: st.session_state.image_desc_cache = "" 
if 'full_text_cache' not in st.session_state: st.session_state.full_text_cache = ""   
if 'is_reporting' not in st.session_state: st.session_state.is_reporting = False
if 'uploaded_file_bytes' not in st.session_state: st.session_state.uploaded_file_bytes = None

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
        st.warning(f"圖形繪製失敗: {e}")

# --- 強力排版修復 v8 (針對矩陣紅字、三角函數、向量修復) ---
def clean_output_format(text):
    if not text: return text
    text = text.strip().lstrip("'").lstrip('"').rstrip("'").rstrip('"')
    
    # 1. 移除 Markdown Code Block (避免 ```latex ... ``` 造成不渲染)
    text = re.sub(r'```[a-zA-Z]*\n([\s\S]*?)\n```', r'\1', text)

    # 2. 綠色/紅色代碼轉 LaTeX (將 `...` 轉為 $...$)
    # 這是解決紅色字體的關鍵
    text = re.sub(r'(?<!`)`([^`\n]+)`(?!`)', r'$\1$', text)

    # 3. Block Math 轉 Inline (Streamlit 有時對 $$ 支援不穩，轉為 $)
    def block_to_inline(match):
        content = match.group(1)
        if len(content) < 50 and '\\\\' not in content and 'align' not in content:
            return f"${content.strip()}$"
        return match.group(0)
    text = re.sub(r'\$\$([\s\S]*?)\$\$', block_to_inline, text)
    
    # 4. 裸奔矩陣/環境修復 (偵測到 \begin{...} 但沒被 $ 包圍)
    text = re.sub(r'(?<!\$)(\\begin\{[a-z]+\}[\s\S]*?\\end\{[a-z]+\})(?!\$)', r'$$\1$$', text)

    # 5. 裸奔常用數學關鍵字修復
    # 包含：向量(vec), 分數(frac), 三角函數(sin/cos/tan), 極限(lim), 總和(sum), 積分(int)
    text = re.sub(r'(?<!\$)(\\(?:vec|frac|sin|cos|tan|cot|lim|sum|int)\{?[^}]*}?)(?!\$)', r'$\1$', text)

    # 6. 程式碼洩漏消音
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if "plt." in line or "np." in line or "matplotlib" in line:
            continue 
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # 7. 基本標點修復
    text = re.sub(r'([\(（])\s*\n\s*(.*?)\s*\n\s*([\)）])', r'\1\2\3', text)
    text = re.sub(r'\n\s*([，。、！？：,.?])', r'\1', text)
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

col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists(main_logo_path):
        st.image(main_logo_path, use_column_width=True)
    else:
        st.markdown("<div style='font-size: 3rem; text-align: center;'>🦔</div>", unsafe_allow_html=True)

with col2:
    st.title("鳩特數理-AI Jutor")
    st.caption("Jutor AI 教學系統 v8.8 (矩陣紅字修復版 12/19)")

st.markdown("---")
col_grade_label, col_grade_select = st.columns([2, 3])
with col_grade_label:
    st.markdown("### 📋 請先選擇年級：")
    st.caption("Jutor 會依此調整講解口吻。")
with col_grade_select:
    selected_grade = st.selectbox("年級", ("小五", "小六", "國一", "國二", "國三", "高一", "高二", "高三"), label_visibility="collapsed")
st.markdown("---")

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
                    loading_text = "Jutor AI (2.5) 正在思考怎麼教會你這題..."
                
                with st.spinner(loading_text):
                    try:
                        if uploaded_file is not None:
                            st.session_state.uploaded_file_bytes = uploaded_file.getvalue()

                        guardrail = "【過濾機制】請辨識圖片內容。若明顯為「自拍照、風景照、寵物照」等與學習無關的圖片，請回傳 REFUSE_OFF_TOPIC。若是數學題目、文字截圖、圖表分析，即使模糊或非典型格式，也請回答。"
                        transcription = f"【隱藏任務】將題目 '{question_target}' 轉譯為文字，並將幾何特徵轉為文字描述，包在 `===DESC===` 與 `===DESC_END===` 之間。"
                        formatting = """
                        【排版嚴格指令】
                        1. **數學式強制 LaTeX**：所有算式、方程式(如 x^2+1=0)、變數(x, y)、數字運算，**務必**使用 `$ ... $` 包裹 (例如 `$x^2+x-1=0$
