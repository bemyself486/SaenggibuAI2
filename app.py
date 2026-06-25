import streamlit as st
import pandas as pd
import pdfplumber
import google.generativeai as genai
import io
import os
import json
import random

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="생기부 교과평어 생성기", layout="wide")

# --- 커스텀 CSS (버튼 디자인 변경) ---
st.markdown("""
    <style>
    /* 1. 메인 버튼 (1단계 분석) - 토스 블루 */
    button[kind="primary"] {
        background-color: #3182F6 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        transition: 0.2s !important;
    }
    button[kind="primary"]:hover {
        background-color: #1B64DA !important;
        color: white !important;
    }
    
    /* 2. 일반 버튼 (2단계 생성하기) - 산뜻한 녹색 */
    button[kind="secondary"] {
        background-color: #107C41 !important; 
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        transition: 0.2s !important;
    }
    button[kind="secondary"]:hover {
        background-color: #0B5A2F !important;
        color: white !important;
    }

    /* 3. 다운로드 전용 버튼 - 카카오톡 노란색 + 검은 글씨 */
    [data-testid="stDownloadButton"] button {
        background-color: #FFD43B !important; 
        color: black !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        transition: 0.2s !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        background-color: #F5B041 !important;
        color: black !important;
    }
    </style>
""", unsafe_allow_html=True)

if 'subjects_dict' not in st.session_state:
    st.session_state['subjects_dict'] = None

def extract_text_from_pdf(pdf_file):
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def get_working_model(api_key):
    genai.configure(api_key=api_key)
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        if not available_models:
            raise Exception("텍스트 생성을 지원하는 모델을 찾을 수 없습니다.")
        target_model = None
        for am in available_models:
            if 'flash' in am.lower():
                target_model = am
                break
        if not target_model:
            for am in available_models:
                if 'pro' not in am.lower():
                    target_model = am
                    break
        if not target_model:
            target_model = available_models[0]
        return genai.GenerativeModel(target_model)
    except Exception as e:
        raise Exception(f"모델 탐색 중 오류 발생: {e}")

def parse_subjects_and_standards(api_key, text):
    model = get_working_model(api_key) 
    prompt = """다음 텍스트는 초등학교 과목별 평가계획서입니다. 
    이 텍스트를 분석하여 '과목명'과 해당 과목의 '성취기준'들을 추출해 주세요.
    반드시 아래의 JSON 형식으로만 출력해야 합니다. 마크다운(```json 등)이나 다른 설명은 절대 추가하지 마세요.
    
    {
        "국어": ["[5국01-01] 성취기준 내용", "[5국01-02] 성취기준 내용"],
        "수학": ["[5수01-01] 성취기준 내용"]
    }
    
    텍스트:
    """ + text
    response = model.generate_content(prompt)
    result = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(result)

def generate_comments(api_key, standard_text, guideline_text):
    model = get_working_model(api_key)
    prompt = f"""{guideline_text}
    
    [데이터 출력 엄격 규칙]
    엑셀로 바로 변환할 수 있도록 반드시 '성취수준|연번|교과평어' 형태로만 출력하십시오. (구분자 | 사용)
    - 매우잘함 30개, 잘함 15개, 보통 5개, 노력요함 3개로 총 53개를 정확히 맞춰주세요.
    - 다른 인사말, 설명, 기호 등은 절대 포함하지 마십시오.
    
    생성할 성취기준:
    {standard_text}
    """
    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 화면 레이아웃 시작
# ==========================================
st.title("📝 생기부 교과평어 초안 생성 도우미")
st.markdown("본 AI는 초안 작성을 돕는 어시스턴트입니다. 생성된 평어는 반드시 선생님의 최종 확인을 거쳐 사용해 주세요.")
st.divider()

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 기본 설정")
    uploaded_file = st.file_uploader("평가계획 PDF 파일을 첨부해 주세요", type=['pdf'])
    
    st.divider()
    st.subheader("🔑 API 키 설정")
    st.info("✅ 현재 기본 제공되는 AI로 원활하게 구동 중입니다. (키 입력 불필요)")
    user_api_key = st.text_input("접속자가 많아 한도 초과 오류가 날 경우에만 아래에 개인 구글 API 키를 입력해 주세요.", type="password")

# --- 핵심 로직: 키 선택 ---
try:
    if user_api_key:
        active_api_key = user_api_key
    else:
        keys = [st.secrets["API_KEY_1"], st.secrets["API_KEY_2"]]
        active_api_key = random.choice(keys)
except Exception as e:
    active_api_key = None
    st.sidebar.error("⚠️ 서버 기본 키가 설정되지 않았습니다. 관리자에게 문의하거나 개인 키를 입력하세요.")

guideline_text = ""
if os.path.exists("guideline.txt"):
    with open("guideline.txt", "r", encoding="utf-8") as f:
        guideline_text = f.read()

# --- 메인 로직 ---
if uploaded_file and active_api_key:
    # 1단계 제목 추가
    st.subheader("🗂️ 1단계: 평가계획 PDF 분석하기")
    
    # 버튼 문구 깔끔하게 수정
    if st.button("📌PDF에서 과목 및 성취기준 추출하기", type="primary"):
        with st.spinner("AI가 문서를 읽고 과목과 성취기준을 분류하고 있습니다... (최초 1회만 필요한 과정, 1분 이내)"):
            try:
                pdf_text = extract_text_from_pdf(uploaded_file)
                parsed_data = parse_subjects_and_standards(active_api_key, pdf_text)
                st.session_state['subjects_dict'] = parsed_data 
                st.success("✅ 문서 분석이 완료되었습니다! 아래에서 과목을 선택해 주세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다. (한도 초과 시 개인 API 키를 입력해 주세요) 에러내용: {e}")

if st.session_state['subjects_dict']:
    st.divider()
    st.subheader("🎯 2단계: 평어 생성하기")
    col1, col2 = st.columns(2)
    with col1:
        subjects = list(st.session_state['subjects_dict'].keys())
        selected_subject = st.selectbox("📂 과목을 선택하세요", subjects)
    
    # 요청하신 문구 수정 반영 구역
    with col2:
        standards = st.session_state['subjects_dict'][selected_subject]
        selected_standard = st.selectbox("📌 성취기준을 선택하세요", standards)
    
    if st.button(f"🚀 '{selected_subject}' 교과평어 53개 생성하기"):
        with st.spinner("지침에 맞춰 수준별 교과평어를 작성하고 있습니다... (버튼 또 누르기X 새로고침X 잠시만 기다려주세요)"):
            try:
                result_text = generate_comments(active_api_key, selected_standard, guideline_text)
                lines = result_text.strip().split('\n')
                data = []
                for line in lines:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        data.append([parts[0].strip(), parts[1].strip(), parts[2].strip()])
                
                if data:
                    df = pd.DataFrame(data, columns=['성취수준', '연번', '교과평어'])
                    st.success("🎉 평어 생성이 완료되었습니다!")
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name=f'{selected_subject}_평어')
                    
                    st.download_button(
                        label="📥 엑셀 파일(.xlsx)로 다운로드",
                        data=output.getvalue(),
                        file_name=f"{selected_subject}_교과평어.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error("데이터 생성 오류. 다시 시도해 주세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다. (1분당 한도 초과일 수 있습니다. 1분 뒤 다시 누르시거나 개인 키를 입력해 주세요) 에러: {e}")
elif not uploaded_file:
    st.info("👈 왼쪽 사이드바에서 평가계획 PDF 파일을 업로드해 주세요.")
