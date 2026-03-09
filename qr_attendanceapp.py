import streamlit as st
import pandas as pd
import datetime
import qrcode
import hashlib
import time
from io import BytesIO
from streamlit_js_eval import streamlit_js_eval
from supabase import create_client, Client

# --- 초기 설정 ---
st.set_page_config(page_title="스마트 QR 출석 시스템", layout="wide")

base_url = "https://dongjakyouthattendance-d57rqgsqjtumzwaftmyp3p.streamlit.app/"  # 본인의 Streamlit 앱 주소
ADMIN_PASSWORD = "wndrhemdqn2026"                     # 관리자 비밀번호

# --- 수파베이스 연결 설정 ---
try:
    url: str = st.secrets["supabase"]["url"]
    key: str = st.secrets["supabase"]["key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("수파베이스 연결 설정(Secrets)을 확인해주세요.")

SECRET_KEY = "attendance_master_key"

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
        current_quarter = st.radio("현재 진행 중인 출석을 선택하세요:", ["미사", "교리"], horizontal=True)
        
        token = get_token()
        qr_url = f"{base_url}/?token={token}&quarter={current_quarter}"
        
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        
        st.info(f"👉 현재 **[{current_quarter}]** 출석을 받고 있습니다.")
        st.image(buf, width=300, caption=f"고정 QR 코드 ({current_quarter}용)")
        st.write("접속 주소:")
        st.code(qr_url)

    with col2:
        st.subheader("📊 출석 데이터 관리")
        admin_pw_input = st.text_input("데이터를 보려면 관리자 암호를 입력하세요.", type="password")
        
        if admin_pw_input == ADMIN_PASSWORD:
            st.success("✅ 관리자 인증 완료")
            tab1, tab2 = st.tabs(["📊 요약 및 시각화", "📅 날짜별 출석부 조회"])
            
            try:
                # 🌟 수파베이스에서 모든 데이터 불러오기
                response = supabase.table("attendance").select("*").execute()
                df = pd.DataFrame(response.data)
                
                if not df.empty:
                    # 빈 데이터 채우기
                    for col in ['quarter', 'grade', 'name', 'nickname', 'date']:
                        if col not in df.columns:
                            df[col] = ""
                    df['quarter'] = df['quarter'].fillna("")
                    df['grade'] = df['grade'].fillna("")
                    df['name'] = df['name'].fillna("")
                    df['nickname'] = df['nickname'].fillna("")
                    df['date'] = df['date'].fillna("")
                    
                    df['display_name'] = df['grade'] + " " + df['name'] + " (" + df['nickname'] + ")"
                    
                    with tab1:
                        st.markdown("#### 📈 일별 출석 추이")
                        daily_counts = df['date'].value_counts().sort_index()
                        st.bar_chart(daily_counts)
                        
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        stats = df['display_name'].value_counts().reset_index()
                        stats.columns = ['학생 정보', '총 출석 횟수']
                        st.table(stats.head(5))
                        
                    with tab2:
                        st.markdown("#### 🔎 특정 날짜 출석 확인")
                        selected_date = st.date_input("조회할 날짜를 달력에서 선택하세요.")
                        selected_date_str = selected_date.isoformat()
                        
                        filtered_df = df[df['date'] == selected_date_str]
                        
                        if not filtered_df.empty:
                            st.info(f"📅 {selected_date_str} 출석 인원: 총 {len(filtered_df)}건")
                            if 'timestamp' in filtered_df.columns:
                                display_cols = ['timestamp', 'quarter', 'grade', 'name', 'nickname']
                                display_cols = [c for c in display_cols if c in filtered_df.columns]
                                st.dataframe(filtered_df[display_cols].sort_values(by="timestamp", ascending=False), use_container_width=True)
                            else:
                                st.dataframe(filtered_df, use_container_width=True)
                        else:
                            st.warning("선택한 날짜의 출석 기록이 없습니다.")
                else:
                    st.info("수파베이스에 아직 기록된 출석 데이터가 없습니다.")
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
    url_quarter = query_params.get("quarter")
    
    if "token_verified" not in st.session_state:
        st.session_state.token_verified = False

    if not st.session_state.token_verified:
        if not url_token or not url_quarter:
            st.error("카메라로 QR 코드를 스캔하여 접속해주세요. (URL 직접 입력 불가)")
            st.stop()
        elif is_valid_token(url_token):
            st.session_state.token_verified = True 
            st.session_state.current_quarter = url_quarter
            st.rerun() 
        else:
            st.error("❌ 유효하지 않은 QR 코드입니다. 관리자 화면의 새 QR을 스캔해 주세요.")
            st.stop()

    if st.session_state.token_verified:
        st.success(f"✅ 유효한 접속입니다. 현재 **[{st.session_state.current_quarter}]** 출석 중입니다.") 
        
        grade_options = ["선택", "중학교 1학년", "중학교 2학년", "중학교 3학년", "고등학교 1학년", "고등학교 2학년", "고등학교 3학년"]
        grade = st.selectbox("학년을 선택하세요", grade_options) 
        
        name = st.text_input("이름을 입력하세요")
        nickname = st.text_input("세례명을 입력하세요 (없으면 '없음' 입력)")
        
        if st.button(f"{st.session_state.current_quarter} 출석 확인"):
            name = name.strip() 
            nickname = nickname.strip()

            if grade == "선택" or not name or not nickname:
                st.error("학년, 이름, 세례명을 모두 입력해 주세요.")
            else:
                try:
                    today = datetime.date.today().isoformat()
                    
                    # 🌟 수파베이스의 초고속 필터링 기능 활용 (중복 체크)
                    # 1. 이름+학년+날짜+쿼터가 모두 똑같은 데이터가 있는지 검색
                    name_check = supabase.table("attendance").select("*").eq("name", name).eq("grade", grade).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    
                    # 2. 기기지문(fp)+날짜+쿼터가 모두 똑같은 데이터가 있는지 검색
                    fp_check = supabase.table("attendance").select("*").eq("fp", str(fp_id)).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    
                    if len(name_check.data) > 0:
                        st.warning(f"'{grade} {name}'님은 오늘 {st.session_state.current_quarter}에 이미 출석하셨습니다.")
                    elif len(fp_check.data) > 0:
                        st.error(f"이 기기로는 오늘 {st.session_state.current_quarter}에 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        # 🌟 수파베이스에 데이터 한 줄 삽입(Insert)
                        supabase.table("attendance").insert({
                            "quarter": st.session_state.current_quarter,
                            "grade": grade,
                            "name": name,
                            "nickname": nickname,
                            "date": today,
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "fp": str(fp_id)
                        }).execute()
                        
                        st.balloons()
                        st.success(f"🎊 {grade} {name}({nickname})님, {st.session_state.current_quarter} 출석이 성공적으로 기록되었습니다!")
                except Exception as e:
                    st.error(f"데이터 저장 중 문제가 발생했습니다. 관리자에게 문의하세요. ({e})")
