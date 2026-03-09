import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import qrcode
import hashlib
import time
from io import BytesIO
from streamlit_js_eval import streamlit_js_eval

# --- 초기 설정 ---
st.set_page_config(page_title="스마트 QR 출석 시스템", layout="wide")

# ⚠️ [매우 중요] 설정 변수 (본인에게 맞게 수정하세요!)
base_url = "https://dongjakyouthattendance-d57rqgsqjtumzwaftmyp3p.streamlit.app"  # 본인의 Streamlit 앱 주소
ADMIN_PASSWORD = "1234"                     # 출결 현황을 보기 위한 관리자 비밀번호

conn = st.connection("gsheets", type=GSheetsConnection)
SECRET_KEY = "attendance_master_key" # QR 토큰용

# --- 함수 정의 (🌟 3시간 단위 고정 QR) ---
def get_token():
    # 3시간 = 10800초. 10800초마다 interval 값이 1씩 증가하여 QR이 바뀜
    interval = int(time.time()) // 10800
    return hashlib.sha256(f"{interval}{SECRET_KEY}".encode()).hexdigest()[:8]

def is_valid_token(user_token):
    interval = int(time.time()) // 10800
    token_now = hashlib.sha256(f"{interval}{SECRET_KEY}".encode()).hexdigest()[:8]
    # 스캔하는 순간 3시간 경계가 넘어가서 튕기는 것을 방지 (직전 3시간 토큰도 허용)
    token_prev = hashlib.sha256(f"{interval - 1}{SECRET_KEY}".encode()).hexdigest()[:8]
    return user_token in [token_now, token_prev]

# --- 메인 로직 ---
query_params = st.query_params
mode = query_params.get("mode", "user")

# [1. 관리자 모드]
if mode == "admin":
    st.title("📢 실시간 출석 현황 & QR")
    
    col1, col2 = st.columns([1, 1.5])
    
    # [왼쪽] 3시간 고정 QR 코드 출력
    with col1:
        st.subheader("현재 출석 QR")
        token = get_token()
        qr_url = f"{base_url}/?token={token}"
        
        # QR 생성 및 화면 출력
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        
        st.image(buf, width=300, caption="고정 QR 코드 (3시간마다 갱신)")
        
        st.write("접속 주소:")
        st.code(qr_url)

    # [오른쪽] 출결 데이터 (비밀번호 보호)
    with col2:
        st.subheader("📊 출석 데이터 관리")
        
        admin_pw_input = st.text_input("데이터를 보려면 관리자 암호를 입력하세요.", type="password")
        
        if admin_pw_input == ADMIN_PASSWORD:
            st.success("✅ 관리자 인증 완료")
            show_stats = st.toggle("🏆 출석 랭킹 및 전체 기록 보기")
            
            if show_stats:
                try:
                    df = conn.read(ttl="5s")
                    if not df.empty:
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        
                        if 'grade' in df.columns:
                            df['display_name'] = df['grade'] + " " + df['name']
                        else:
                            df['display_name'] = df['name']
                            
                        stats = df['display_name'].value_counts().reset_index()
                        stats.columns = ['학생 정보', '총 출석 횟수']
                        
                        st.table(stats.head(5))
                        
                        st.markdown("#### 📝 전체 출석 기록")
                        st.dataframe(df.sort_values(by="timestamp", ascending=False), use_container_width=True)
                    else:
                        st.info("구글 시트에 아직 기록된 출석 데이터가 없습니다.")
                except Exception as e:
                    st.error("데이터를 불러올 수 없습니다. 구글 시트 연결을 확인해주세요.")
                    
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
        
        grade = st.selectbox("학년을 선택하세요", ["선택", "1학년", "2학년", "3학년", "4학년", "5학년", "6학년"]) 
        name = st.text_input("본인 이름을 입력하세요 (예: 홍길동)")
        
        if st.button("출석 확인"):
            name = name.strip() 

            if grade == "선택" or not name:
                st.error("학년과 이름을 모두 입력해 주세요.")
            else:
                try:
                    existing_df = conn.read(ttl="0s")
                    today = datetime.date.today().isoformat()
                    
                    if existing_df.empty:
                        existing_df = pd.DataFrame(columns=['grade', 'name', 'date', 'timestamp', 'fp'])
                    
                    is_name_duplicated = not existing_df[(existing_df['name'] == name) & (existing_df['grade'] == grade) & (existing_df['date'] == today)].empty
                    is_fp_duplicated = not existing_df[(existing_df['fp'] == fp_id) & (existing_df['date'] == today)].empty
                    
                    if is_name_duplicated:
                        st.warning(f"'{grade} {name}'님은 오늘 이미 출석하셨습니다.")
                    elif is_fp_duplicated:
                        st.error("이 기기로는 오늘 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        new_data = pd.DataFrame([{
                            "grade": grade,
                            "name": name,
                            "date": today,
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "fp": fp_id
                        }])
                        updated_df = pd.concat([existing_df, new_data], ignore_index=True)
                        conn.update(data=updated_df)
                        
                        st.balloons()
                        st.success(f"🎊 {grade} {name}님, 출석이 성공적으로 기록되었습니다!")
                except Exception as e:
                    st.error(f"데이터 저장 중 문제가 발생했습니다. 관리자에게 문의하세요. ({e})")

