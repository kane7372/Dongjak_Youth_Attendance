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

# ⚠️ [매우 중요] 아래 주소를 본인의 실제 Streamlit 앱 주소로 반드시 변경하세요!
base_url = "https://abcdefg.streamlit.app" 

conn = st.connection("gsheets", type=GSheetsConnection)
SECRET_KEY = "attendance_master_key" # QR 토큰용

# --- 함수 정의 ---
# 1. (관리자용) 현재 15초 토큰 생성
def get_token():
    return hashlib.sha256(f"{int(time.time()) // 15}{SECRET_KEY}".encode()).hexdigest()[:8]

# 2. (학생용) 토큰 검증 함수 (🌟 방금 전 15초 토큰까지 여유롭게 인정)
def is_valid_token(user_token):
    current_interval = int(time.time()) // 15
    token_now = hashlib.sha256(f"{current_interval}{SECRET_KEY}".encode()).hexdigest()[:8]
    token_prev = hashlib.sha256(f"{current_interval - 1}{SECRET_KEY}".encode()).hexdigest()[:8]
    return user_token in [token_now, token_prev]

# --- 사이드바: 관리자 로그인 ---
with st.sidebar:
    st.header("🔐 관리자 메뉴")
    admin_pw = st.text_input("관리자 암호 입력", type="password")
    try:
        is_admin = (admin_pw == st.secrets["admin"]["password"])
    except:
        is_admin = False
        st.info("앱 설정(Secrets)에서 비밀번호를 먼저 세팅해주세요.")

# --- 메인 로직 ---
query_params = st.query_params
mode = query_params.get("mode", "user")

# [1. 관리자 모드]
if mode == "admin":
    if not is_admin:
        st.warning("관리자 암호를 먼저 입력해주세요.")
    else:
        st.title("📢 실시간 출석 현황 & QR")
        st_autorefresh(interval=15000, key="qr_refresh")
        
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
            st.subheader("현재 출석 QR")
            token = get_token()
            qr_url = f"{base_url}/?token={token}"
            
            qr = qrcode.make(qr_url)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            st.image(buf, width=300, caption=f"갱신 토큰: {token}")

        with col2:
            st.subheader("📊 출석 데이터 관리")
            
            # 🌟 원할 때만 켜서 볼 수 있는 스위치 생성
            show_stats = st.toggle("🏆 출석 랭킹 및 전체 기록 보기")
            
            if show_stats:
                # 스위치를 켰을 때만 구글 시트에서 데이터를 불러옵니다.
                try:
                    df = conn.read(ttl="5s")
                    if not df.empty:
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        
                        # 이름과 학년이 같이 보이게 합쳐서 랭킹 계산
                        if 'grade' in df.columns:
                            df['display_name'] = df['grade'] + " " + df['name']
                        else:
                            df['display_name'] = df['name']
                            
                        stats = df['display_name'].value_counts().reset_index()
                        stats.columns = ['학생 정보', '총 출석 횟수']
                        
                        st.table(stats.head(5))
                        
                        st.markdown("#### 📝 전체 출석 기록")
                        st.dataframe(df.sort_values(by="timestamp", ascending=False), use_container_width=True)
                except Exception as e:
                    st.info("아직 데이터가 없거나 불러올 수 없습니다.")
            else:
                # 스위치가 꺼져있을 때 보여줄 안내문
                st.info("👆 위 스위치를 켜면 실시간 랭킹과 전체 명단을 확인할 수 있습니다.")

# [2. 학생 모드] - 🚨 이 아래 부분이 통째로 누락되어 있었습니다!
else:
    st.title("📝 스마트 출석 체크")
    
    # 1. 기기 지문 생성 (1인 1기기용)
    fp_id = streamlit_js_eval(js_expressions="window.screen.width + '-' + navigator.userAgent", key="fp")
    
    if not fp_id:
        st.info("기기 식별 중입니다. 잠시만 기다려주세요...")
        st.stop()

    url_token = query_params.get("token")
    
    # 2. 세션을 이용해 새로고침 시 만료되는 현상 방지
    if "token_verified" not in st.session_state:
        st.session_state.token_verified = False

    # 3. 아직 검증 전이라면 토큰 검사
    if not st.session_state.token_verified:
        if not url_token:
            st.error("카메라로 QR 코드를 스캔하여 접속해주세요.")
            st.stop()
        elif is_valid_token(url_token):
            st.session_state.token_verified = True 
            st.rerun() 
        else:
            st.error("❌ 만료된 QR 코드입니다. 화면의 새 QR을 스캔해 주세요.")
            st.stop()

    # 4. 검증을 무사히 통과한 사용자에게만 출석 입력창 표시
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
                    # 구글 시트에서 데이터 가져오기
                    existing_df = conn.read(ttl="0s")
                    today = datetime.date.today().isoformat()
                    
                    if existing_df.empty:
                        existing_df = pd.DataFrame(columns=['grade', 'name', 'date', 'timestamp', 'fp'])
                    
                    # 중복 체크 
                    is_name_duplicated = not existing_df[(existing_df['name'] == name) & (existing_df['grade'] == grade) & (existing_df['date'] == today)].empty
                    is_fp_duplicated = not existing_df[(existing_df['fp'] == fp_id) & (existing_df['date'] == today)].empty
                    
                    if is_name_duplicated:
                        st.warning(f"'{grade} {name}'님은 오늘 이미 출석하셨습니다.")
                    elif is_fp_duplicated:
                        st.error("이 기기로는 오늘 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        # 새 데이터 추가 
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
