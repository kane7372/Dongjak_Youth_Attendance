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
KST = datetime.timezone(datetime.timedelta(hours=9))

# ⚠️ [매우 중요] 설정 변수
base_url = "https://dongjakyouthattendance-d57rqgsqjtumzwaftmyp3p.streamlit.app/"  # 본인의 Streamlit 앱 주소
ADMIN_PASSWORD = "wndrhemdqn2026"                     # 관리자 비밀번호
TABLE_NAME = "term_2026_1"                  # 🌟 이번 학기 수파베이스 테이블 이름!

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
    st.title("📢 QR 출석체크")
    
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("현재 출석 QR")
        current_quarter = st.radio("현재 진행 중인 출석을 선택하세요:", ["미사", "교리"], horizontal=True)
        
        token = get_token()
        qr_url = f"{base_url}?token={token}&quarter={current_quarter}"
        
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        
        st.info(f"👉 현재 **[{current_quarter}]** 출석을 받고 있습니다.")
        st.image(buf, width=300, caption=f"고정 QR 코드 ({current_quarter}용)")
        st.write("접속 주소:")
        st.code(qr_url)

    with col2:
        st.subheader(f"📊 출석 데이터 관리")
        admin_pw_input = st.text_input("데이터를 보려면 관리자 암호를 입력하세요.", type="password")
        if admin_pw_input == ADMIN_PASSWORD:
            try:
                response = supabase.table(TABLE_NAME).select("*").execute()
                df = pd.DataFrame(response.data)
                
                if not df.empty:
                    # 1. 빈칸 채우기 및 띄어쓰기 찌꺼기 제거
                    for col in ['quarter', 'grade', 'name', 'nickname', 'date']:
                        if col not in df.columns:
                            df[col] = ""
                    df['quarter'] = df['quarter'].fillna("").astype(str).str.strip()
                    df['grade'] = df['grade'].fillna("")
                    df['name'] = df['name'].fillna("")
                    df['nickname'] = df['nickname'].fillna("")
                    df['date'] = df['date'].fillna("")
                    
                    # 🌟 2. [마법의 코드 수정 완료] '미사, 교리 둘 다'로 뭉쳐있는 데이터를 미사/교리 두 줄로 쪼개기
                    if "미사, 교리 둘 다" in df['quarter'].values:
                        both_df = df[df['quarter'] == "미사, 교리 둘 다"].copy()
                        df = df[df['quarter'] != "미사, 교리 둘 다"]
                        
                        q1_df = both_df.copy()
                        q1_df['quarter'] = "미사"
                        
                        q2_df = both_df.copy()
                        q2_df['quarter'] = "교리"
                        
                        df = pd.concat([df, q1_df, q2_df], ignore_index=True)

                    # 3. 화면에 보여줄 이름 만들기
                    df['display_name'] = df['grade'] + " " + df['name'] + " (" + df['nickname'] + ")"                  
                    
                    tab1, tab2, tab3 = st.tabs(["📊 요약 및 시각화", "📅 날짜별 조회", "✍️ 수동 출석 입력"])
                    
                    with tab1:
                        st.markdown("#### 📊 출석 요약")
                        
                        # 1. 쿼터별 총 출석 건수 계산
                        q1_total = len(df[df['quarter'].str.contains('미사', na=False)])
                        q2_total = len(df[df['quarter'].str.contains('교리', na=False)])
                        total_attendance = len(df)
                        
                        # 상단에 깔끔하게 카드 형태로 숫자 표시
                        m1, m2, m3 = st.columns(3)
                        m1.metric(label="미사 총 출석", value=f"{q1_total}건")
                        m2.metric(label="교리 총 출석", value=f"{q2_total}건")
                        m3.metric(label="전체(종합) 출석", value=f"{total_attendance}건")
                        
                        st.markdown("---")
                        
                        st.markdown("#### 📈 일별 출석 추이 (유형 비교)")
                        if not df.empty and 'date' in df.columns and 'quarter' in df.columns:
                            chart_data = df.groupby(['date', 'quarter']).size().unstack(fill_value=0)
                            st.bar_chart(chart_data)
                        
                        st.markdown("---")
                        
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        if not df.empty and 'display_name' in df.columns:
                            pivot_stats = df.groupby(['display_name', 'quarter']).size().unstack(fill_value=0)
                            
                            # 빈 쿼터 안전장치
                            for q in ['미사', '교리']:
                                if q not in pivot_stats.columns:
                                    pivot_stats[q] = 0
                                    
                            pivot_stats['종합'] = pivot_stats['미사'] + pivot_stats['교리']
                            pivot_stats = pivot_stats.sort_values(by='종합', ascending=False).reset_index()
                            pivot_stats.rename(columns={'display_name': '학생 정보'}, inplace=True)
                            
                            pivot_stats = pivot_stats[['학생 정보', '미사', '교리', '종합']]
                            
                            st.dataframe(pivot_stats.head(5), use_container_width=True)
                            
                            with st.expander("👀 모든 인원 전체 요약 보기 (클릭)"):
                                st.dataframe(pivot_stats, use_container_width=True)
                        
                    with tab2:
                        st.markdown("#### 🔎 특정 날짜 출석 확인")
                        selected_date = st.date_input("조회할 날짜를 선택하세요.", value=datetime.datetime.now(KST).date())
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
                    st.info(f"[{TABLE_NAME}] 테이블에 아직 기록된 출석 데이터가 없습니다.")
                    # 데이터가 없을 때도 수동 입력 탭은 보이도록 밖으로 뺌
                    tab1, tab2, tab3 = st.tabs(["📊 요약 및 시각화", "📅 날짜별 조회", "✍️ 수동 출석 입력"])
                    
            except Exception as e:
                st.error(f"데이터를 불러올 수 없습니다: {e}")
                tab1, tab2, tab3 = st.tabs(["📊 요약 및 시각화", "📅 날짜별 조회", "✍️ 수동 출석 입력"])
                
            with tab3:
                st.markdown("#### ✍️ 관리자 수동 출석 기록")
                st.info("스마트폰이 없는 분을 직접 등록합니다.")
                
                with st.form("manual_attendance_form"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        m_quarter = st.selectbox("출석 유형", ["미사", "교리", "미사, 교리 둘 다"])
                        m_grade = st.selectbox("학년", ["선택", "중학교 1학년", "중학교 2학년", "중학교 3학년", "고등학교 1학년", "고등학교 2학년", "고등학교 3학년", "교사"])
                        m_date = st.date_input("출석 날짜", value=datetime.datetime.now(KST).date())
                    with col_b:
                        m_name = st.text_input("이름")
                        m_nickname = st.text_input("세례명 (선택)", placeholder="입력하지 않으면 '수동입력' 저장")
                    
                    submit_btn = st.form_submit_button("✅ 수동 출석 등록하기")
                    
                    if submit_btn:
                        m_name = m_name.strip()
                        m_nickname = m_nickname.strip() if m_nickname.strip() else "수동입력"
                        
                        if m_grade == "선택" or not m_name:
                            st.error("학년과 이름은 반드시 입력해주세요.")
                        else:
                            try:
                                # 🌟 '둘 다' 처리 로직 글자 수정
                                if m_quarter == "미사, 교리 둘 다":
                                    quarters_to_insert = ["미사", "교리"]
                                else:
                                    quarters_to_insert = [m_quarter]
                                
                                for q in quarters_to_insert:
                                    supabase.table(TABLE_NAME).insert({
                                        "quarter": q,
                                        "grade": m_grade,
                                        "name": m_name,
                                        "nickname": m_nickname,
                                        "date": m_date.isoformat(),
                                        "timestamp": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                                        "fp": "관리자_수동입력"
                                    }).execute()
                                
                                st.success(f"🎊 {m_grade} {m_name} 님의 '{m_quarter}' 출석이 수동으로 정상 등록되었습니다! (새로고침 시 통계 반영)")
                            except Exception as e:
                                st.error(f"수동 입력 중 문제가 발생했습니다: {e}")
                                
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
        
        grade_options = ["선택", "중학교 1학년", "중학교 2학년", "중학교 3학년", "고등학교 1학년", "고등학교 2학년", "고등학교 3학년", "교사"]
        grade = st.selectbox("학년/소속을 선택하세요", grade_options) 
        
        name = st.text_input("이름을 입력하세요")
        nickname = st.text_input("세례명을 입력하세요 (없으면 '없음' 입력)")
        
        if st.button(f"{st.session_state.current_quarter} 출석 확인"):
            name = name.strip() 
            nickname = nickname.strip()

            if grade == "선택" or not name or not nickname:
                st.error("학년, 이름, 세례명을 모두 입력해 주세요.")
            else:
                try:
                    today = datetime.datetime.now(KST).date().isoformat()
                    
                    name_check = supabase.table(TABLE_NAME).select("*").eq("name", name).eq("grade", grade).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    fp_check = supabase.table(TABLE_NAME).select("*").eq("fp", str(fp_id)).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    
                    if len(name_check.data) > 0:
                        st.warning(f"'{grade} {name}'님은 오늘 {st.session_state.current_quarter}에 이미 출석하셨습니다.")
                    elif len(fp_check.data) > 0:
                        st.error(f"이 기기로는 오늘 {st.session_state.current_quarter}에 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        supabase.table(TABLE_NAME).insert({
                            "quarter": st.session_state.current_quarter,
                            "grade": grade,
                            "name": name,
                            "nickname": nickname,
                            "date": today,
                            "timestamp": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                            "fp": str(fp_id)
                        }).execute()
                        
                        st.balloons()
                        st.success(f"🎊 {grade} {name}({nickname})님, {st.session_state.current_quarter} 출석이 성공적으로 기록되었습니다!")
                except Exception as e:
                    st.error(f"데이터 저장 중 문제가 발생했습니다. 관리자에게 문의하세요. ({e})")

