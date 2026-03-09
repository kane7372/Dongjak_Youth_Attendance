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
TABLE_NAME = "term_2026_1"                  # 🌟 이번 학기 수파베이스 테이블 이름! (학기마다 여기만 변경)

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
        st.subheader(f"📊 출석 데이터 관리 ({TABLE_NAME})")
        admin_pw_input = st.text_input("데이터를 보려면 관리자 암호를 입력하세요.", type="password")
        
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
                    
                    # 🌟 2. [마법의 코드] '둘 다'로 뭉쳐있는 데이터를 1쿼터/2쿼터 두 줄로 쪼개기
                    if "1, 2쿼터 모두 (둘 다)" in df['quarter'].values:
                        # '둘 다'라고 적힌 데이터들만 따로 뽑아냅니다.
                        both_df = df[df['quarter'] == "1, 2쿼터 모두 (둘 다)"].copy()
                        # 원래 표에서는 저 긴 글씨를 삭제합니다.
                        df = df[df['quarter'] != "1, 2쿼터 모두 (둘 다)"]
                        
                        # 1쿼터용으로 이름표를 바꿔서 한 묶음 만듭니다.
                        q1_df = both_df.copy()
                        q1_df['quarter'] = "1쿼터"
                        
                        # 2쿼터용으로 이름표를 바꿔서 한 묶음 만듭니다.
                        q2_df = both_df.copy()
                        q2_df['quarter'] = "2쿼터"
                        
                        # 쪼개진 1쿼터, 2쿼터 묶음을 원래 표에 다시 합쳐버립니다!
                        df = pd.concat([df, q1_df, q2_df], ignore_index=True)

                    # 3. 화면에 보여줄 이름 만들기
                    df['display_name'] = df['grade'] + " " + df['name'] + " (" + df['nickname'] + ")"                    
                    with tab1:
                        st.markdown("#### 📊 출석 요약")
                        
                        # 1. 쿼터별 총 출석 건수 계산
                        # == 대신 .str.contains()를 써서 공백 변수로부터 완벽하게 보호합니다.
                        q1_total = len(df[df['quarter'].str.contains('미사', na=False)])
                        q2_total = len(df[df['quarter'].str.contains('교리', na=False)])
                        total_attendance = len(df)
                        
                        # 상단에 깔끔하게 카드 형태로 숫자 표시
                        m1, m2, m3 = st.columns(3)
                        m1.metric(label="미사 총 출석", value=f"{q1_total}건")
                        m2.metric(label="교리 총 출석", value=f"{q2_total}건")
                        m3.metric(label="전체(종합) 출석", value=f"{total_attendance}건")
                        
                        st.markdown("---")
                        
                        st.markdown("#### 📈 일별 출석 추이 (쿼터 비교)")
                        if not df.empty and 'date' in df.columns and 'quarter' in df.columns:
                            # 날짜별, 쿼터별로 카운트하여 표(데이터프레임)로 변환
                            chart_data = df.groupby(['date', 'quarter']).size().unstack(fill_value=0)
                            # 막대 차트로 출력 (자동으로 색상이 나뉘어 쌓입니다!)
                            st.bar_chart(chart_data)
                        
                        st.markdown("---")
                        
                        st.markdown("#### 🥇 누적 출석 랭킹 (Top 5)")
                        if not df.empty and 'display_name' in df.columns:
                            # 학생별 1쿼터, 2쿼터 출석 횟수 피벗 테이블 생성
                            pivot_stats = df.groupby(['display_name', 'quarter']).size().unstack(fill_value=0)
                            
                            # 혹시 아직 1쿼터나 2쿼터 기록이 아예 없을 때를 대비한 안전장치
                            for q in ['미사', '교리']:
                                if q not in pivot_stats.columns:
                                    pivot_stats[q] = 0
                                    
                            # 종합 점수 계산 (1쿼터 + 2쿼터)
                            pivot_stats['종합'] = pivot_stats['미사'] + pivot_stats['교리']
                            
                            # 종합 점수 기준으로 내림차순 정렬
                            pivot_stats = pivot_stats.sort_values(by='종합', ascending=False).reset_index()
                            pivot_stats.rename(columns={'display_name': '학생 정보'}, inplace=True)
                            
                            # 보여줄 컬럼 순서 깔끔하게 정리
                            pivot_stats = pivot_stats[['학생 정보', '미사', '교리', '종합']]
                            
                            # 상위 5명만 표로 보여주기
                            st.dataframe(pivot_stats.head(5), use_container_width=True)
                            
                            # 접었다 펼칠 수 있는 공간에 전체 학생 기록 제공
                            with st.expander("👀 모든 학생 전체 요약 보기 (클릭)"):
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
            except Exception as e:
                st.error(f"데이터를 불러올 수 없습니다: {e}")
                
            with tab3:
                st.markdown("#### ✍️ 관리자 수동 출석 기록")
                st.info("스마트폰이 없는 학생이나 기기 오류가 발생한 학생을 직접 등록합니다.")
                
                with st.form("manual_attendance_form"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        # 🌟 쿼터 선택지에 '1, 2쿼터 모두 (둘 다)' 추가
                        m_quarter = st.selectbox("출석 유형", ["미사", "교리", "미사, 교리 둘 다"])
                        m_grade = st.selectbox("학년", ["선택", "중학교 1학년", "중학교 2학년", "중학교 3학년", "고등학교 1학년", "고등학교 2학년", "고등학교 3학년", "교사"])
                        # (1) 달력 부분 변경
                        m_date = st.date_input("출석 날짜", value=datetime.datetime.now(KST).date())
                    with col_b:
                        m_name = st.text_input("이름")
                        m_nickname = st.text_input("세례명")
                    
                    submit_btn = st.form_submit_button("✅ 수동 출석 등록하기")
                    
                    if submit_btn:
                        m_name = m_name.strip()
                        m_nickname = m_nickname.strip() if m_nickname.strip() else "수동입력"
                        
                        if m_grade == "선택" or not m_name:
                            st.error("학년과 이름은 반드시 입력해주세요.")
                        else:
                            try:
                                # 🌟 '둘 다'를 선택하면 1쿼터, 2쿼터를 각각 리스트에 담습니다.
                                if m_quarter == "미사, 교리 모두 (둘 다)":
                                    quarters_to_insert = ["미사", "교리"]
                                else:
                                    quarters_to_insert = [m_quarter]
                                
                                # 리스트에 담긴 쿼터 수만큼 반복해서 수파베이스에 저장합니다. (둘 다 선택 시 2번 반복)
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
                                
                                st.success(f"🎊 {m_grade} {m_name} 학생의 '{m_quarter}' 출석이 수동으로 정상 등록되었습니다! (새로고침 시 통계 반영)")
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
                    today = datetime.datetime.now(KST).date().isoformat()
                    
                    # 🌟 TABLE_NAME 변수를 사용하여 중복 검사
                    name_check = supabase.table(TABLE_NAME).select("*").eq("name", name).eq("grade", grade).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    fp_check = supabase.table(TABLE_NAME).select("*").eq("fp", str(fp_id)).eq("date", today).eq("quarter", st.session_state.current_quarter).execute()
                    
                    if len(name_check.data) > 0:
                        st.warning(f"'{grade} {name}'님은 오늘 {st.session_state.current_quarter}에 이미 출석하셨습니다.")
                    elif len(fp_check.data) > 0:
                        st.error(f"이 기기로는 오늘 {st.session_state.current_quarter}에 이미 다른 분이 출석했습니다 (1인 1기기).")
                    else:
                        # 🌟 TABLE_NAME 변수를 사용하여 데이터 저장
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










