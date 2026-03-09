import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import qrcode
import hashlib
import time
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
from streamlit_js_eval import streamlit_js_eval

# --- 초기 설정 ---
st.set_page_config(page_title="완성형 QR 출석 시스템", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)
SECRET_KEY = "attendance_master_key" # QR 토큰용
STUDENT_LIST = ["홍길동", "김철수", "이영희", "박지민", "최유진"]

# 15초 토큰 생성 함수
def get_token():
    return hashlib.sha256(f"{int(time.time()) // 15}{SECRET_KEY}".encode()).hexdigest()[:8]

# --- 사이드바: 관리자 로그인 ---
with st.sidebar:
    st.header("🔐 관리자 메뉴")
    admin_pw = st.text_input("관리자 암호 입력", type="password")
    is_admin = (admin_pw == st.secrets["admin"]["password"])

# --- 메인 로직 ---
query_params = st.query_params
mode = query_params.get("mode", "user")

# 1. 관리자 모드
if mode == "admin":
    if not is_admin:
        st.warning("관리자 암호를 먼저 입력해주세요.")
    else:
        st.title("📢 실시간 출석 현황 & QR")
        st_autorefresh(interval=15000)
        
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
            st.subheader("현재 출석 QR")
            token = get_token()
            base_url = "https://dongjakyouthattendance.streamlit.app/" # 실제 배포 주소로 변경
            qr_url = f"{base_url}/?token={token}"
            
            qr = qrcode.make(qr_url)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            st.image(buf, caption=f"갱신 토큰: {token}")

        with col2:
            st.subheader("🏆 오늘 출석 랭킹 (Top 5)")
            try:
                df = conn.read(ttl="5s")
                if not df.empty:
                    # 누적 통계
                    stats = df['name'].value_counts().reset_index()
                    stats.columns = ['이름', '총 출석 횟수']
                    st.table(stats.head(5))
                    
                    st.subheader("전체 기록")
                    st.dataframe(df.sort_values(by="timestamp", ascending=False))
            except:
                st.info("아직 데이터가 없습니다.")

# 2. 학생 모드
else:
    st.title("📝 스마트 출석 체크")
    
    # 기기 지문 생성
    fp_id = streamlit_js_eval(js_expressions="window.screen.width + '-' + navigator.userAgent", key="fp")
    
    if not fp_id:
        st.info("기기 식별 중입니다...")
        st.stop()

    url_token = query_params.get("token")
    if url_token != get_token():
        st.error("❌ 만료된 QR 코드입니다. 화면을 다시 확인해 주세요.")
    else:
        st.success("✅ 유효한 접속입니다.")
        name = st.selectbox("본인 이름을 선택하세요", ["선택하세요"] + STUDENT_LIST)
        
        if st.button("출석 확인"):
            if name == "선택하세요":
                st.error("이름을 선택해 주세요.")
            else:
                # 구글 시트 데이터 로드하여 중복 체크
                existing_df = conn.read(ttl="0s")
                today = datetime.date.today().isoformat()
                
                # 중복 조건: (오늘 날짜) + (이름) 혹은 (오늘 날짜) + (기기지문)
                is_name_duplicated = not existing_df[(existing_df['name'] == name) & (existing_df['date'] == today)].empty
                is_fp_duplicated = not existing_df[(existing_df['fp'] == fp_id) & (existing_df['date'] == today)].empty
                
                if is_name_duplicated:
                    st.warning(f"'{name}'님은 오늘 이미 출석하셨습니다.")
                elif is_fp_duplicated:
                    st.error("이 기기로는 오늘 이미 다른 분이 출석했습니다 (1인 1기기).")
                else:
                    # 데이터 저장
                    new_data = pd.DataFrame([{
                        "name": name,
                        "date": today,
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "fp": fp_id
                    }])
                    
                    updated_df = pd.concat([existing_df, new_data], ignore_index=True)
                    conn.update(data=updated_df) # 구글 시트로 전송
                    
                    st.balloons()

                    st.success(f"{name}님, 출석이 성공적으로 기록되었습니다!")

