import streamlit as st
import pandas as pd
import pdfplumber
import google.generativeai as genai
import io
import os
import json

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="생기부 교과평어 생성기", layout="wide")

# --- 세션 상태 초기화 ---
if 'subjects_dict' not in st.session_state:
    st.session_state['subjects_dict'] = None

# --- 1. PDF 텍스트 추출 함수 ---
def extract_text_from_pdf(pdf_file):
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

# --- ✨ 긴급 수정: 무료 요금제용 Flash 모델 최우선 탐색 함수 ---
def get_working_model(api_key):
    genai.configure(api_key=api_key)
    
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            raise Exception("텍스트 생성을 지원하는 모델을 찾을 수 없습니다.")

        # 무료 계정에서 한도가 0으로 막히는 'pro' 모델을 철저히 배제합니다.
        # 한도가 넉넉한 'flash' 모델을 목록에서 가장 먼저 찾아 연결합니다.
        target_model = None
        for am in available_models:
            if 'flash' in am.lower():
                target_model = am
                break
        
        # 만약 목록에 flash 모델이 없다면, 최소한 'pro'라는 글자가 안 들어간 모델을 고릅니다.
        if not target_model:
            for am in available_models:
                if 'pro' not in am.lower():
                    target_model = am
                    break
        
        # 최후의 수단으로만 첫 번째 모델을 사용합니다.
        if not target_model:
            target_model = available_models[0]
            
        # 구글 서버가 인식할 수 있도록 추출된 풀네임(예: models/gemini-1.5-flash)을 그대로 주입합니다.
        return genai.GenerativeModel(target_model)
        
    except Exception as e:
        raise Exception(f"모델 탐색 중 오류 발생: {e}")

# --- 2. 구글 Gemini: 과목 및 성취기준 추출 함수 ---
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

# --- 3. 구글 Gemini: 평어 생성 함수 ---
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
st.title("📝 생기부 교과평어 자동 생성 웹앱")
st.markdown("본 AI는 초안 작성을 돕는 어시스턴트입니다. 생성된 평어는 반드시 선생님의 최종 확인을 거쳐 사용해 주세요.")
st.divider()

# --- 사이드바 ---
with st.sidebar:
    st.header("⚙️ 기본 설정")
    api_key = st.text_input("Google Gemini API 키를 입력하세요", type="password")
    uploaded_file = st.file_uploader("평가계획 PDF 파일을 첨부해 주세요", type=['pdf'])

# 가이드라인 텍스트 읽어오기
guideline_text = ""
if os.path.exists("guideline.txt"):
    with open("guideline.txt", "r", encoding="utf-8") as f:
        guideline_text = f.read()
else:
    st.error("⚠️ guideline.txt 파일이 같은 폴더에 없습니다. 파일을 생성해 주세요!")

# --- 메인 로직 ---
if uploaded_file and api_key:
    # 1단계: 문서 분석
    if st.button("📄 1단계: PDF 자동 분석 (과목 및 성취기준 추출)", type="primary"):
        with st.spinner("AI가 무료 특화 모델(Flash)을 강제 지정하여 분석하고 있습니다..."):
            try:
                pdf_text = extract_text_from_pdf(uploaded_file)
                parsed_data = parse_subjects_and_standards(api_key, pdf_text)
                st.session_state['subjects_dict'] = parsed_data 
                st.success("✅ 문서 분석이 완료되었습니다! 아래에서 과목을 선택해 주세요.")
            except Exception as e:
                st.error(f"오류가 발생했습니다. {e}")

# 2단계: 평어 생성
if st.session_state['subjects_dict']:
    st.divider()
    st.subheader("🎯 2단계: 평어 생성하기")
    
    col1, col2 = st.columns(2)
    
    with col1:
        subjects = list(st.session_state['subjects_dict'].keys())
        selected_subject = st.selectbox("📂 과목을 선택하세요", subjects)
    
    with col2:
        standards = st.session_state['subjects_dict'][selected_subject]
        selected_standard = st.selectbox("📌 성취기준을 선택하세요", standards)
    
    if st.button(f"🚀 '{selected_subject}' 교과평어 53개 생성하기", use_container_width=True):
        with st.spinner("지침에 맞춰 수준별 교과평어를 작성하고 있습니다... (약 10~15초 소요)"):
            try:
                result_text = generate_comments(api_key, selected_standard, guideline_text)
                
                # 데이터 변환
                lines = result_text.strip().split('\n')
                data = []
                for line in lines:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        data.append([parts[0].strip(), parts[1].strip(), parts[2].strip()])
                
                if data:
                    df = pd.DataFrame(data, columns=['성취수준', '연번', '교과평어'])
                    st.success("🎉 평어 생성이 완료되었습니다!")
                    
                    # 엑셀 파일 생성
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name=f'{selected_subject}_평어')
                    
                    st.download_button(
                        label="📥 엑셀 파일(.xlsx)로 다운로드",
                        data=output.getvalue(),
                        file_name=f"{selected_subject}_교과평어.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error("AI가 지정된 표 형식으로 출력하지 못했습니다. 다시 시도해 주세요.")
                    st.write("원시 데이터:", result_text)
                    
            except Exception as e:
                st.error(f"평어 생성 중 오류가 발생했습니다: {e}")
elif not uploaded_file or not api_key:
    st.info("👈 왼쪽 사이드바에 Google Gemini API 키를 입력하고 평가계획 PDF 파일을 업로드해 주세요.")