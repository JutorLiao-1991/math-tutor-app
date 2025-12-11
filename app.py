import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
import time
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import random
import re # 用來抓取錯誤訊息中的等待秒數

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
if 'daily_records' not in st.session_state:
    st.session_state.daily_records = []

# --- 函數：打字機效果 ---
def stream_text(text):
    for char in text:
        yield char
        time.sleep(0.02)

# --- 函數：觸發震動 ---
def trigger_vibration():
    vibrate_js = """<script>if(navigator.vibrate){navigator.vibrate(30);}</script>"""
    components.html(vibrate_js, height=0, width=0)

# --- 核心函數：強大的 API 呼叫器 (含自動換鑰匙功能) ---
def call_gemini_with_rotation(prompt_content, image_input=None):
    # 1. 取得所有鑰匙
    try:
        keys = st.secrets["API_KEYS"]
        if isinstance(keys, str): # 相容舊設定 (如果只填了一行字串)
            keys = [keys]
    except:
        st.error("系統錯誤：找不到 API_KEYS 設定，請檢查 Secrets。")
        st.stop()

    # 2. 隨機打亂鑰匙順序 (負載平衡)
    # 這樣大家不會都擠在第一把鑰匙
    shuffled_keys = keys.copy()
    random.shuffle(shuffled_keys)
    
    last_error = None
    
    # 3. 嘗試迴圈
    for key in shuffled_keys:
        try:
            # 設定目前的鑰匙
            genai.configure(api_key=key)
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            # 發送請求 (判斷有沒有圖片)
            if image_input:
                response = model.generate_content([prompt_content, image_input])
            else:
                # 這是給問答模式用的 (純文字 history)
                # 注意：Gemini 的 chat session 需要特殊的換鑰匙處理，這裡簡化為直接調用
                # 如果是多輪對話，換 Key 可能會導致上下文遺失，
                # 但為了救急 429 錯誤，我們這邊採用單次生成或需重建 history
                # 這裡為了簡化，若是 QA 模式建議使用 generate_content 帶入完整 history text
                response = model.generate_content(prompt_content)
                
            return response # 成功就直接回傳，結束迴圈

        except Exception as e:
            error_str = str(e)
            # 如果是 429 (Quota Exceeded) 或 503 (Server Busy)，就換下一把鑰匙
            if "429" in error_str or "Quota exceeded" in error_str or "503" in error_str:
                print(f"Key ...{key[-4:]} 額度已滿，切換下一把...") # 後台紀錄
                last_error = e
                continue # 繼續迴圈，試下一把
            else:
                # 如果是其他嚴重錯誤 (如 400 參數錯誤)，直接報錯，不用換鑰匙試了
                raise e
    
    # 4. 如果所有鑰匙都試過了還是失敗
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

# --- 老師後台 ---
with st.expander("👨‍🏫 老師後台 (下載今日紀錄)"):
    st.write(f"目前已累積 **{len(st.session_state.daily_records)}** 筆紀錄")
    if len(st.session_state.daily_records) > 0:
        df = pd.DataFrame(st.session_state.daily_records)
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載 CSV",
            data=csv,
            file_name=f"jutor_history_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

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
                        # Prompt 設定
                        if mode == "verbal":
                            prompt = f"""
                            角色：你是一位精簡、直接、口令化的數學家教「Jutor」。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。
                            【最高指令 1：極簡口令風格】嚴禁廢話。使用祈使句直接下指令。
                            【最高指令 2：原子化步驟拆解】每一個小動作之後，必須插入分隔符號： ===STEP===
                            【最高指令 3：幾何題處理】若遇幾何題，請用「精準文字指令」代替作圖。
                            【最高指令 4：結尾結構】解題結束後，依照順序：本題最終答案 ===STEP=== 【驗收類題】(數字不同但邏輯相同，不附答案) ===STEP=== 【類題詳解】
                            """
                        else:
                            prompt = f"""
                            角色：你是一個純數學運算引擎。
                            學生年級：【{selected_grade}】。指定題目：【{question_target}】。
                            【最高指令 1：純算式模式】嚴禁冗長中文。以 LaTeX 為主。
                            【最高指令 2：原子化步驟拆解】每一個算式變換後，必須插入分隔符號： ===STEP===
                            【最高指令 3：結尾結構】解題結束後，依照順序：本題最終答案 ===STEP=== 【驗收類題】(僅題目) ===STEP=== 【類題解答】
                            """

                        # --- 改成呼叫我們的「自動換鑰匙」函數 ---
                        response = call_gemini_with_rotation(prompt, image)
                        
                        raw_steps = response.text.split("===STEP===")
                        st.session_state.solution_steps = [step.strip() for step in raw_steps if step.strip()]
                        st.session_state.step_index = 0
                        st.session_state.is_solving = True
                        st.session_state.streaming_done = False
                        st.session_state.in_qa_mode = False
                        st.session_state.qa_history = []
                        st.session_state.data_saved = False

                        # 紀錄
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        mode_str = "指令教學" if mode == "verbal" else "純算式"
                        new_record = {
                            "時間": timestamp,
                            "年級": selected_grade,
                            "模式": mode_str,
                            "題目描述": question_target,
                            "AI完整詳解": response.text
                        }
                        st.session_state.daily_records.append(new_record)
                        
                        st.rerun()

                    except Exception as e:
                        # --- 【關鍵修改】友善的錯誤攔截 ---
                        error_msg = str(e)
                        if "429" in error_msg or "Quota exceeded" in error_msg:
                            # 嘗試抓取等待時間
                            wait_time = "60" # 預設一分鐘
                            match = re.search(r"retry in (\d+(\.\d+)?)", error_msg)
                            if match:
                                wait_time = str(int(float(match.group(1))) + 5) # 無條件進位並多加5秒緩衝
                            
                            st.warning(f"🐢 Jutor 老師目前處理太多學生的問題，正在喝口水休息...")
                            st.error(f"⚠️ 系統過載保護中，請稍候 {wait_time} 秒後再試一次！")
                        else:
                            st.error(f"連線發生非預期錯誤：{e}")

# ================= 解題互動 (部分微調以支援 QA 的換鑰匙) =================

if st.session_state.is_solving and st.session_state.solution_steps:
    
    header_text = "📝 Jutor 口令教學中" if st.session_state.solve_mode == "verbal" else "🔢 純算式推導中"
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
            col_next, col_ask = st.columns([3, 2])
            
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
                    st.session_state.qa_history = [
                        {"role": "user", "parts": [context_prompt]}, # 修正：將背景設定偽裝成第一則 user prompt
                        {"role": "model", "parts": ["了解，請說出你的問題。"]} # 假裝 AI 已經收到
                    ]
                st.button("🤔 不太懂，我想問...", on_click=enter_qa_mode, use_container_width=True)

        else:
            with st.container(border=True):
                st.markdown("#### 💡 提問時間")
                # 顯示歷史對話 (跳過前兩則背景設定)
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
                                # 這裡我們需要把整個 history 轉成文字串，讓換鑰匙函數可以吃
                                # 這是為了避免換 Key 後 session 失效的權宜之計
                                full_prompt_text = "以下是對話歷史：\n"
                                for h in st.session_state.qa_history:
                                    role = "學生" if h["role"] == "user" else "Jutor"
                                    full_prompt_text += f"{role}: {h['parts'][0]}\n"
                                full_prompt_text += f"學生最新問題: {user_question}\n請回答學生的問題。"
                                
                                # 使用自動換鑰匙函數
                                response = call_gemini_with_rotation(full_prompt_text)
                                
                                st.write_stream(stream_text(response.text))
                                st.session_state.qa_history.append({"role": "model", "parts": [response.text]})
                            except Exception as e:
                                st.error(f"連線忙碌中，請重試。")

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
