import streamlit as st
import pandas as pd
import datetime
import qrcode
import hashlib
import time
from io import BytesIO
from streamlit_js_eval import streamlit_js_eval
from pyairtable import Api # 에어테이블 전용 라이브러리

# --- 초기 설정 ---
st.set_page_config(page_title="스마트 QR 출석 시스템", layout="wide")

# ⚠️ [매우 중요] 설정 변수
base_url = "https://dongjakyouthattendance-d57rqgsqjtumzwaftmyp3p.streamlit.app/"  # 본인의 Streamlit 앱 주소
ADMIN_PASSWORD = "1234"                     # 출결 현황을 보기 위한 관리자 비밀번호

# --- 에어테이블 연결 설정 ---
try:
    api = Api(st.secrets["airtable"]["api_key"])
    table = api.table(st.secrets["airtable"]["base_id"], st.secrets["airtable"]["table_name"])
except Exception as e:
    st.error("에어테이블 연결 설정(Secrets)을 확인해주세요.")

SECRET_KEY = "attendance_master_key"

# --- 함수 정의 (3시간 단위 고정 QR) ---
def get_token():
    interval = int(time.time()) // 10800
    return hashlib.sha256(f"{interval}{SECRET_KEY}".encode()).hexdigest()[:8]

def is_valid_token(user_token):
    interval = int(time.time()) // 10800
    token_now = hashlib.sha256(f"{interval}{SECRET_KEY}".encode()).hexdigest()[:8]
    token_prev = hashlib.sha256(f"{interval - 1}{SECRET_KEY}".encode()).hexdigest()[:8]
    return user_token in [token_now, token_prev]

# --- 메인 로직 ---
query_params = st.query_params
mode = query_params.get("mode", "user")

# [1. 관리자 모드]
if mode == "admin":
    st.title("📢 실시간 출석 현황 & QR")
    
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("현재 출석 QR")
        token = get_token()
        qr_url = f"{base_url}/?token={token}"
        
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        
        st.image(buf, width=300, caption="고정 QR 코드 (3시간마다 갱신)")
        st.write("접속 주소:")
        st.code(qr_url)

    with col2:
        st.subheader("📊 출석 데이터 관리")
        
        admin_pw_input = st.text_input("데이터를 보려면 관리자 암호를 입력하세요.", type="password")
        
        if admin_pw_input == ADMIN_PASSWORD:
            st.success("✅ 관리자 인증 완료")
            show_stats = st.toggle("🏆 출석 랭킹 및 전체 기록 보기")
            
            if show_stats:
                try:
                    # 에어테이블에서 모든 데이터 불러오기
                    records = table.all()
                    df_records = [r['fields'] for r in records]
                    df = pd.DataFrame(df_records)
                    
                    if not df.empty:
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        
                        if 'nickname' in df.columns and 'grade' in df.columns:
                            # NaN(빈칸) 처리 후 문자열 합치기
                            df['grade'] = df['grade'].fillna("")
                            df['name'] = df['name'].fillna("")
                            df['nickname'] = df['nickname'].fillna("")
                            df['display_name'] = df['grade'] + " " + df['name'] + " (" + df['nickname'] + ")"
                        elif 'grade' in df.columns:
                            df['display_name'] = df['grade'] + " " + df['name']
                        else:
                            df['display_name'] = df['name']
                            
                        stats = df['display_name'].value_counts().reset_index()
                        stats.columns = ['학생 정보', '총 출석 횟수']
                        
                        st.table(stats.head(5))
                        
                        st.markdown("#### 📝 전체 출석 기록")
                        # 최신순 정렬 (timestamp 기준)
                        if 'timestamp' in df.columns:
                            st.dataframe(df.sort_values(by="timestamp", ascending=False), use_container_width=True)
                        else:
                            st.dataframe(df, use_container_width=True)
                    else:
                        st.info("에어테이블에 아직 기록된 출석 데이터가 없습니다.")
                except Exception as e:
                    st.error(f"데이터를 불러올 수 없습니다: {e}")
                    
        elif admin_pw_input != "":
            st.error("❌ 비밀번호가 틀렸습니다.")
        else:
            st.info("🔒 보안을 위해 암호가 필요합니다.")

# [2. 학생 모드]
else:
    st.title("📝 스마트 출석 체크")
    
    fp_id = streamlit_js_eval(js_expressions="window.screen.width + '-' + navigator.userAgent", key="fp")
    
    if not fp_id:
        st.info("기기 식별 중입니다. 잠시만 기다려주세요...")
        st.stop()

    url_token = query_params.get("token")
    
    if "token_verified" not in st.session_state:
        st.session_state.token_verified = False

    if not st.session_state.token_verified:
        if not url_token:
            st.error("카메라로 QR 코드를 스캔하여 접속해주세요.")
            st.stop()
        elif is_valid_token(url_token):
            st.session_state.token_verified = True 
            st.rerun() 
        else:
            st.error("❌ 유효하지 않은 QR 코드입니다. 관리자 화면의 새 QR을 스캔해 주세요.")
            st.stop()

    if st.session_state.token_verified:
        st.success("✅ 유효한 접속입니다. 정보를 입력해주세요.") 
        
        grade_options = ["선택", "중학교 1학년", "중학교 2학년", "중학교 3학년", "고등학교 1학년", "고등학교 2학년", "고등학교 3학년"]
        grade = st.selectbox("학년을 선택하세요", grade_options) 
        
        name = st.text_input("이름을 입력하세요")
        nickname = st.text_input("세례명을 입력하세요 (없으면 '없음' 입력)")
        
        if st.button("출석 확인"):
            name = name.strip() 
            nickname = nickname.strip()

            if grade == "선택" or not name or not nickname:
                st.error("학년, 이름, 세례명을 모두 입력해 주세요.")
            else:
                try:
                    # 중복 체크를 위해 오늘 날짜 데이터만 가져오기
                    today = datetime.date.today().isoformat()
                    # 에어테이블 데이터 가져오기
                    records = table.all()
                    df_records = [r['fields'] for r in records]
                    df = pd.DataFrame(df_records)
                    
                    # 빈 데이터프레임 방어 로직
                    if df.empty:
                        df = pd.DataFrame(columns=['grade', 'name', 'nickname', 'date', 'timestamp', 'fp'])
                    else:
                        # 누락된 컬럼이 있으면 채워주기
                        for col in ['grade', 'name', 'nickname', 'date', 'timestamp', 'fp']:
                            if col not in df.columns:
                                df[col] = ""

                    # 중복 검사 로직
                    is_name_duplicated = not df[(df['name'] == name) & (df['grade'] == grade) & (df['date'] == today)].empty
                    is_fp_duplicated = not df[(df['fp'] == fp_id) & (df['date'] == today)].empty
                    
                    if is_name_duplicated:
                        st.warning(f"'{grade} {name}'님은 오늘 이미 출석하셨습니다.")
                    elif is_fp_duplicated:
                        st.error("이 기기로는 오늘 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        # 🌟 에어테이블에 새 데이터 한 줄 추가하기 (create)
                        table.create({
                            "grade": grade,
                            "name": name,
                            "nickname": nickname,
                            "date": today,
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "fp": str(fp_id)
                        })
                        
                        st.balloons()
                        st.success(f"🎊 {grade} {name}({nickname})님, 출석이 성공적으로 기록되었습니다!")
                except Exception as e:
                    st.error(f"데이터 저장 중 문제가 발생했습니다. 관리자에게 문의하세요. ({e})")
