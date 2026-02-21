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
if 'trigger_retry' not in st.session_state: st.session_state.trigger_retry = False 
if 'used_key_suffix' not in st.session_state: st.session_state.used_key_suffix = "" 
if 'image_desc_cache' not in st.session_state: st.session_state.image_desc_cache = "" 
if 'full_text_cache' not in st.session_state: st.session_state.full_text_cache = ""   
if 'is_reporting' not in st.session_state: st.session_state.is_reporting = False
if 'uploaded_file_bytes' not in st.session_state: st.session_state.uploaded_file_bytes = None
if 'last_question_text' not in st.session_state: st.session_state.last_question_text = ""

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

# --- v10.0 智慧內顯修復邏輯 ---
import re

def clean_output_format(text):
    if not text:
        return text
    text = text.strip().lstrip("'\"").rstrip("'\"")

    # ── Step 1：貨幣保護，$100 → \$100，避免被誤判為數學開始 ──
    text = re.sub(r'(?<!\\)\$(\d+)', r'\\$\1', text)

    # ── Step 2：移除 Code Blocks ──
    text = re.sub(r'```python[\s\S]*?```', '', text)
    text = text.replace("```latex", "").replace("```", "")
    # 反引號包住的內容，改成 $ 包裹
    text = re.sub(r'`([^`\n]+)`', r'$\1$', text)

    # ── Step 3：程式碼洩漏消音（避免 plt / np 代碼出現在說明文字裡）──
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        l = line.strip()
        if (re.match(r'^[a-zA-Z0-9_]+(\s*,\s*[a-zA-Z0-9_]+)*\s*=\s*[-0-9./]+', l) and 'plt' in text) or \
           l.startswith('plt.') or \
           l.startswith('np.') or \
           'matplotlib' in l:
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # ── Step 4：裸奔矩陣修復（\begin{} 沒有 $$ 包裹）──
    text = re.sub(
        r'(?<!\$)(\\begin\{[a-z\*]+\}[\s\S]*?\\end\{[a-z\*]+\})(?!\$)',
        r'$$\1$$',
        text
    )

    # ── Step 5：核心 — 先把換行切斷的 LaTeX 接回來 ──
    # 狀況：一個算式被換行拆成多段，例如：
    #   \cos C =
    #   \frac{2}{4\sqrt{7}}
    # 先把以 LaTeX 命令或運算符結尾的行，和下一行合併
    for _ in range(5):  # 多跑幾輪，處理多層斷行
        # 以 LaTeX 命令或 = + - * / 結尾的行 → 和下一行合併
        text = re.sub(r'(\\[a-zA-Z]+(?:\{[^}]*\})*)\s*\n\s*(\\[a-zA-Z{(])', r'\1 \2', text)
        text = re.sub(r'([=+\-*/^_,])\s*\n\s*(\\[a-zA-Z{(0-9\-])', r'\1 \2', text)
        # 以 { 結尾（分數分子還沒結束）→ 合併
        text = re.sub(r'(\{[^}]*)\n\s*([^}]*\})', r'\1 \2', text)
        # 孤立的 ^2 C、^2 開頭的行 → 合併到上一行
        text = re.sub(r'\n\s*(\^[0-9a-zA-Z])', r'\1', text)

    # ── Step 6：智慧穿衣 — 把還沒被 $ 包住的 LaTeX 命令包起來 ──

    def wrap_if_naked(pattern, replacement_fn, text):
        """只在不在 $ ... $ 範圍內的地方套用替換"""
        result = []
        last = 0
        # 先找出所有已經在 $ 內的區段，跳過它們
        dollar_ranges = []
        for m in re.finditer(r'\$\$[\s\S]*?\$\$|\$[^\$\n]+?\$', text):
            dollar_ranges.append((m.start(), m.end()))

        def in_dollar(pos):
            for s, e in dollar_ranges:
                if s <= pos < e:
                    return True
            return False

        for m in re.finditer(pattern, text):
            if not in_dollar(m.start()):
                result.append(text[last:m.start()])
                result.append(replacement_fn(m))
                last = m.end()
        result.append(text[last:])
        return ''.join(result)

    # 複雜算式（含有 \frac, \sqrt, \left, \right 的整段）
    text = wrap_if_naked(
        r'\\frac\{[^}]+\}\{[^}]+\}',
        lambda m: f'${m.group(0)}$',
        text
    )
    text = wrap_if_naked(
        r'\\sqrt\{[^}]+\}',
        lambda m: f'${m.group(0)}$',
        text
    )
    text = wrap_if_naked(
        r'\\vec\{[^}]+\}',
        lambda m: f'${m.group(0)}$',
        text
    )

    # 帶參數的三角函數式，例如 \cos C、\sin^2 C
    text = wrap_if_naked(
        r'\\(sin|cos|tan|cot|sec|csc)\s*[\^]?[0-9]?\s*[A-Za-z]',
        lambda m: f'${m.group(0)}$',
        text
    )

    # 無參數符號：\theta \pi \cdot \times \approx \pm \leq \geq \neq \infty
    text = wrap_if_naked(
        r'\\(theta|alpha|beta|gamma|delta|pi|infty|cdot|times|approx|pm|leq|geq|neq|sum|int|lim)(?![a-zA-Z])',
        lambda m: f'${m.group(0)}$',
        text
    )

    # 行內含有 ^ 或 _ 但沒有 $ 的算式（例如 x^2、a_1）
    text = wrap_if_naked(
        r'[a-zA-Z][_\^][{0-9a-zA-Z][^$\n]{0,20}',
        lambda m: f'${m.group(0)}$',
        text
    )

    # ── Step 7：整行掃尾 — 整行都是裸 LaTeX 的，整行包起來 ──
    lines = text.split('\n')
    fixed_lines = []
    for line in lines:
        stripped = line.strip()
        # 這行含有 LaTeX 命令但完全沒有 $
        if re.search(r'\\[a-zA-Z]', stripped) and '$' not in stripped and stripped:
            line = '$' + stripped + '$'
        fixed_lines.append(line)
    text = '\n'.join(fixed_lines)

    # ── Step 8：清理多餘的 $$ 巢狀（$$$ 或 $$$$）──
    text = re.sub(r'\$\$\$+', '$$', text)
    # 清理空的 $ $ 或 $  $
    text = re.sub(r'\$\s*\$', '', text)

    # ── Step 9：垂直膠水 — 中文句子裡不必要的換行 ──
    for _ in range(2):
        text = re.sub(r'\n\s*([，。、！？：,.?])', r'\1', text)
        cjk = r'[\u4e00-\u9fa5]'
        short_content = r'(?:(?!\n|•|- |\* ).){1,30}'
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

# --- 輔助函式：產生 Prompt ---
def build_prompt(grade, target, mode):
    guardrail = "【過濾機制】請辨識圖片內容。若明顯為「自拍照、風景照、寵物照」等與學習無關的圖片，請回傳 REFUSE_OFF_TOPIC。若是數學題目、文字截圖、圖表分析，即使模糊或非典型格式，也請回答。"
    transcription = f"【隱藏任務】將題目 '{target}' 轉譯為文字，並將幾何特徵轉為文字描述，包在 `===DESC===` 與 `===DESC_END===` 之間。"
    formatting = """
   【排版絕對指令 - 違反即重做】

    ★ 規則 A：每一個數學式，無論長短，必須用 $ 包裹。
       - 錯誤：\\cos C = \\frac{2}{4\\sqrt{7}}
       - 正確：$\\cos C = \\frac{2}{4\\sqrt{7}}$
       - 錯誤：\\sin^2 C + \\cos^2 C = 1
       - 正確：$\\sin^2 C + \\cos^2 C = 1$

    ★ 規則 B：一個完整的算式，必須寫在同一行，嚴禁中途換行。
       - 錯誤：$\\cos C =\n\\frac{2}{4\\sqrt{7}}$
       - 正確：$\\cos C = \\frac{2}{4\\sqrt{7}}$

    ★ 規則 C：禁止在數學式前後加上 Markdown 代碼塊 (``` 或 `)。

    ★ 規則 D：禁止在每個詞語後面換行。段落內容請保持連貫，同一觀念寫在同一段落。

    ★ 規則 E：顯示帶有分數的大型算式時，請使用 $$ 雙錢號讓它獨立一行。
       - 正確：$$\\sin C = \\sqrt{1 - \\left(\\frac{1}{2\\sqrt{7}}\\right)^2}$$
    """
    plotting = """
    【繪圖能力啟動】
    1. 只有當題目明確涉及「函數圖形」、「幾何座標」、「統計圖表」時，才生成 Python 程式碼。
    2. 程式碼必須能直接執行，並包在 `===PLOT===` 與 `===PLOT_END===` 之間。
    3. 圖表標題、座標軸請使用中文。
    4. ⚠️ 嚴格 LaTeX 規範：所有包含 LaTeX 語法的字串（如標題、標籤），**必須** 使用 Python raw string (例如 r'$y=x^2$')。
    5. ⚠️ 避免在 title 使用過於複雜的 LaTeX (如 \left, \right)，若必須使用，請確保語法完美閉合。
    6. ⚠️ 3D繪圖：若是空間坐標題，請務必使用 `ax = fig.add_subplot(111, projection='3d')`。
    """
    common_role = f"角色：你是 Jutor。年級：{grade}。題目：{target}。"
    if grade in ["小五", "小六"]:
        common_role += "【重要】學生為台灣國小生，請嚴格遵守台灣國小數學課綱：1. 避免使用二元一次聯立方程式或過於抽象的代數符號(x,y)。2. 多使用「線段圖」、「基準量比較量」或具體數字推演來解釋。3. 語言要更白話、具體。"

    if mode == "verbal":
        style = "風格：幽默口語、譬喻教學、步驟化。"
    elif mode == "math":
        style = "風格：純算式、LaTeX、極簡。"
    elif mode == "toxic":
        style = """
        風格：【鳩特地獄教練模式 (Toxic Mode)】
        1. 態度：極度諷刺、嘴賤但心軟、恨鐵不成鋼。
        2. 語氣：請模仿台灣補習班嚴厲老師的口氣。
        3. 【鳩特老師專屬口頭禪】(請在回應中自然融入 1~2 句，增強『本人』既視感)：
            - "這題不會可以包一包"
            - "看到想不到，學分全噴掉"
            - "我看你段考想包一個大的"
            - "這個忘了你是想決戰188嗎？"
            - "欸不是，這我3歲就會了耶！"
        4. 任務：除了使用上述金句，請發揮創意繼續吐槽學生的智商，展現出「這種題目也能錯？」的崩潰感，但最後必須「無奈地」把題目教懂。
        """
    else:
        style = "風格：幽默口語。" 

    return f"""
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

col1, col2 = st.columns([1, 4]) 
with col1:
    if os.path.exists(main_logo_path):
        st.image(main_logo_path, use_column_width=True)
    else:
        st.markdown("<div style='font-size: 3rem; text-align: center;'>🦔</div>", unsafe_allow_html=True)

with col2:
    st.title("鳩特數理-AI Jutor")
    st.caption("Jutor AI 教學系統 v10.0 (智慧內顯修復版 12/30)")

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
        
        col_btn_verbal, col_btn_math, col_btn_toxic = st.columns([1, 1, 1])
        
        with col_btn_verbal:
            start_verbal = st.button("🗣️ 口語教學", use_container_width=True, type="primary")
        with col_btn_math:
            start_math = st.button("🔢 純算式", use_container_width=True)
        with col_btn_toxic:
            start_toxic = st.button("☠️ 毒舌模式", use_container_width=True)

        if start_verbal or start_math or start_toxic or st.session_state.trigger_rescue:
            if not question_target:
                st.warning("⚠️ 請先輸入你想問哪一題！")
            else:
                st.session_state.last_question_text = question_target
                
                if st.session_state.trigger_rescue:
                    mode = st.session_state.solve_mode
                    use_pro = True 
                    st.session_state.use_pro_model = True
                    st.session_state.trigger_rescue = False 
                else:
                    if start_toxic: mode = "toxic"
                    elif start_math: mode = "math"
                    else: mode = "verbal"
                    
                    st.session_state.solve_mode = mode
                    use_pro = False 
                    st.session_state.use_pro_model = False

                if use_pro:
                    loading_text = "Jutor Pro (2.5) 正在深度分析並修復錯誤..."
                else:
                    if mode == "toxic":
                        loading_text = "Jutor AI (2.5) 正在深呼吸準備開罵..."
                    else:
                        loading_text = "Jutor AI (2.5) 正在思考怎麼教會你這題..."
                
                with st.spinner(loading_text):
                    try:
                        if uploaded_file is not None:
                            st.session_state.uploaded_file_bytes = uploaded_file.getvalue()

                        prompt = build_prompt(selected_grade, question_target, mode)

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
                            
                            st.session_state.image_desc_cache = image_desc
                            st.session_state.full_text_cache = full_text

                            plot_code = None
                            if "===PLOT===" in full_text and "===PLOT_END===" not in full_text:
                                full_text += "\n===PLOT_END==="
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
                            st.session_state.is_reporting = False

                            save_to_google_sheets(selected_grade, mode, image_desc, full_text, key_suffix)
                            st.rerun()

                    except Exception as e:
                        if "429" in str(e) or "Quota" in str(e): 
                            st.warning("🥵 系統忙碌中...")
                            st.error("請稍候重試！")
                        else: st.error(f"錯誤：{e}")

# ================= 解題互動 =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    if st.session_state.solve_mode == "verbal":
        header_text = "🗣️ Jutor 口語教學中"
    elif st.session_state.solve_mode == "math":
        header_text = "🔢 純算式推導中"
    elif st.session_state.solve_mode == "toxic":
        header_text = "☠️ Jutor 毒舌開罵中"
    else:
        header_text = "Jutor 解題中"

    if st.session_state.use_pro_model:
        st.markdown(f"### {header_text} (🔥 2.5 Pro 救援)")
    else:
        st.markdown(f"### {header_text}") 
    
    if st.session_state.plot_code:
        with st.expander("📊 查看幾何/函數圖形", expanded=True):
            execute_and_show_plot(st.session_state.plot_code)

    if st.session_state.step_index >= len(st.session_state.solution_steps):
        st.session_state.step_index = 0

    for i in range(st.session_state.step_index):
        with st.chat_message("assistant", avatar=assistant_avatar):
            st.markdown(st.session_state.solution_steps[i])
            
    current_step_text = st.session_state.solution_steps[st.session_state.step_index]
    with st.chat_message("assistant", avatar=assistant_avatar):
        trigger_vibration()
        st.markdown(current_step_text)

    total_steps = len(st.session_state.solution_steps)
    
    # --- 回報區塊 ---
    if st.session_state.is_reporting:
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### 🚨 錯誤回報")
            student_name = st.text_input("請輸入你的名字 (方便老師回覆你)：", placeholder="例如：王小明")
            student_comment = st.text_area("請告訴 Jutor 哪裡怪怪的？", height=100)
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("取消", use_container_width=True):
                    st.session_state.is_reporting = False
                    st.rerun()
            with c2:
                if st.button("確認送出", type="primary", use_container_width=True):
                    if not student_comment or not student_name:
                        st.warning("請填寫名字和問題描述喔！")
                    else:
                        success = send_telegram_alert(
                             selected_grade, 
                             st.session_state.image_desc_cache, 
                             st.session_state.full_text_cache,
                             student_comment,
                             student_name,
                             st.session_state.uploaded_file_bytes
                        )
                        if success:
                            st.session_state.is_reporting = False
                            st.toast("已收到您的回覆，我們正在請 Jutor 本人下凡處理，請先繼續寫別題吧！", icon="📨")
                            st.balloons()
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("發送失敗")

    elif st.session_state.step_index < total_steps - 1:
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
                st.session_state.is_reporting = False
                st.session_state.uploaded_file_bytes = None
                st.rerun()

    # --- v9.9 原地復活重刷 (不會白畫面) ---
    if not st.session_state.is_reporting:
        st.markdown("")
        st.markdown("")
        
        col_util_1, col_util_2 = st.columns(2)
        
        with col_util_1:
            if st.button("🔧 內容沒錯但亂碼？點我修復", use_container_width=True):
                st.toast("🚑 正在請求主任醫師 (Pro) 進行微創手術...", icon="👨‍⚕️")
                
                try:
                    bad_text = st.session_state.full_text_cache
                    
                    if not bad_text:
                        st.warning("⚠️ 目前沒有內容可以修復喔！")
                    else:
                        # --- 建構修復專用 Prompt (強化版) ---
                        repair_prompt = f"""
                        【任務：Streamlit LaTeX 格式渲染修復】
                        你是一個 Python Streamlit 介面優化專家。
                        目前的數學教學文本無法在 Streamlit 中正確渲染，因為缺少了 LaTeX 分隔符號。
                        
                        請重新輸出下方的文本，並嚴格遵守以下規則：
                        
                        1. ✅ **強制包裹數學式**：
                           所有的 LaTeX 數學語法（例如 `\\frac`, `\\sqrt`, `^2`, `\\approx`, `\\pm` 等），**必須**前後加上單錢字號 `$` 包裹。
                           - 錯誤範例： `y = x^2`
                           - 正確範例： `$y = x^2$`
                           - 錯誤範例： `\\frac{{1}}{{2}}`
                           - 正確範例： `$\\frac{{1}}{{2}}$`
                        
                        2. 🛡️ **巢狀結構注意**：
                           遇到複雜數學式（如分數內有根號），請確保 `$` 包裹在最外層。
                           - 正確： `$\\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}$`
                        
                        3. 🚫 **禁止更動內容**：
                           嚴禁修改原本的中文解說、數字或計算步驟，僅做格式標記。
                        
                        ---待修復文本---
                        {bad_text}
                        ---結束---
                        """

                        with st.spinner("🔧 Jutor Pro 正在精細排版中..."):
                            # ⚠️ 關鍵修改：這裡強制 use_pro=True，確保指令遵循度最高
                            response, _ = call_gemini_with_rotation(repair_prompt, image_input=None, use_pro=True)
                            
                            # 取得修復後的文字
                            fixed_text = response.text
                            
                            # 再次清洗 (主要為了去除可能多餘的 markdown code block 符號)
                            fixed_text = clean_output_format(fixed_text)
                            
                            # --- 保存與更新狀態 ---
                            st.session_state.full_text_cache = fixed_text
                            
                            # 嘗試保留圖表代碼 (如果修復過程中 AI 遺漏的話)
                            plot_code = None
                            if "===PLOT===" in fixed_text and "===PLOT_END===" not in fixed_text:
                                fixed_text += "\n===PLOT_END==="
                            plot_match = re.search(r"===PLOT===(.*?)===PLOT_END===", fixed_text, re.DOTALL)
                            
                            if plot_match:
                                plot_code = plot_match.group(1).strip()
                                plot_code = plot_code.replace("```python", "").replace("```", "")
                                fixed_text = fixed_text.replace(plot_match.group(0), "")
                            
                            # 如果 AI 修復後把 plot 弄丟了，從舊紀錄找回來
                            if not plot_code and st.session_state.plot_code:
                                plot_code = st.session_state.plot_code
                            else:
                                st.session_state.plot_code = plot_code

                            # 更新步驟
                            raw_steps = fixed_text.split("===STEP===")
                            st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                            
                            # 重新渲染
                            st.rerun()

                except Exception as e:
                    st.error(f"修復失敗：{e}")
        
        with col_util_2:
            if st.button("🚨 答案有錯，回報給鳩特", use_container_width=True, type="secondary"):
                st.session_state.is_reporting = True
                st.rerun()
