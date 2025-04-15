
import streamlit as st
import pandas as pd
from io import BytesIO

# ========== 함수 정의 ==========

def assign_disease(row):
    if row["연하곤란"] == 1:
        return "연하곤란"
    elif row["고혈압"] == 1 and row["신장질환"] == 1:
        return "신장"
    elif row["당뇨"] == 1 and row["신장질환"] == 1:
        return "신장"
    elif row["당뇨"] == 1 and row["고혈압"] == 1:
        return "고혈압"
    elif row["신장질환"] == 1:
        return "신장"
    elif row["고혈압"] == 1:
        return "고혈압"
    elif row["당뇨"] == 1:
        return "당뇨"
    return None

def get_meal_option(rice, side, disease):
    replace_rice = None
    suffix = ""
    soup_suffix = ""

    if rice == "일반밥" and side == "일반찬":
        suffix = ""
    elif rice == "일반밥" and side == "다진찬":
        suffix = "_다진"
        soup_suffix = "_건더기잘게"
    elif rice == "일반죽" and side == "다진찬":
        suffix = "_다진"
        soup_suffix = "_건더기잘게"
        replace_rice = {"잡곡밥": "야채죽", "쌀밥": "야채죽"}
    elif rice == "갈죽" and side == "갈찬":
        suffix = "_갈찬"
        soup_suffix = "_국물만"
        replace_rice = {"잡곡밥": "야채죽_갈죽", "쌀밥": "야채죽_갈죽"}

    return {"suffix": suffix, "soup_suffix": soup_suffix, "replace_rice": replace_rice}


def apply_meal_customization(menu_df, option):
    suffix = option["suffix"]
    soup_suffix = option["soup_suffix"]
    replace_rice = option["replace_rice"]

    modified_df = menu_df.copy()

    # 밥 대체
    if replace_rice:
        for old_val, new_val in replace_rice.items():
            modified_df.loc[(modified_df["Category"] == "밥") & (modified_df["Menu"] == old_val), "Menu"] = new_val

    # 국: 별도 suffix 적용
    modified_df.loc[modified_df["Category"] == "국", "Menu"] += soup_suffix

    # 부찬류: 공통 suffix 적용
    for cat in ["주찬", "부찬1", "부찬2", "김치"]:
        modified_df.loc[modified_df["Category"] == cat, "Menu"] += suffix

    return modified_df

def generate_final_results(patient_df, category_df):
    disease_types = ["당뇨", "고혈압", "신장"]
    required_categories = ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]
    category_order = pd.CategoricalDtype(categories=required_categories, ordered=True)
    final_results = {}
    for disease in disease_types:
        menus = category_df[category_df["Disease"].str.contains(disease, na=False)]
        results = []
        for _, row in patient_df[patient_df["질환"] == disease].iterrows():
            patient_id = row["수급자ID"]
            option = row["식단옵션"]
            selected = menus[menus["Category"].isin(required_categories)].drop_duplicates("Category")
            if set(required_categories).issubset(set(selected["Category"])):
                customized = apply_meal_customization(selected, option)
                customized["Category"] = customized["Category"].astype(category_order)
                customized = customized.sort_values("Category")
                customized.insert(0, "질환", disease)
                customized.insert(0, "수급자ID", patient_id)
                results.append(customized)
        if results:
            final_results[disease] = pd.concat(results, ignore_index=True)
    return final_results

# ========== Streamlit 앱 시작 ==========

st.set_page_config(page_title="사랑과선행 요양원 맞춤 식단 추천 시스템", layout="wide")

st.image("./logo.png", width=300)

st.markdown(
    '<h3 style="color:#226f54; font-size:38px; font-weight:bold;">사랑과선행 요양원 맞춤 푸드 솔루션</h3>',
    unsafe_allow_html=True
)
st.sidebar.markdown("""
    <style>
    section[data-testid="stSidebar"] {
        background-color: #f7fadb !important;
    }

    div.stButton > button {
        padding: 1rem 1.5rem;
        font-size: 24px !important;
        font-weight: 600;
        border-radius: 12px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
        transition: all 0.2s ease-in-out;
        background-color: #eaf291;
        border: 1px solid #d6d84c;
        color: #444;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
        transition: all 0.2s ease-in-out;
    }

    div.stButton > button:hover {
        background-color: #dce75b;
        border: 1px solid #a3a93d;
        color: #2e2e2e;
    }

    div.stButton > button:focus {
        outline: none;
        box-shadow: none;
        border: 1px solid #d0d0d0;
    }

    .selected-button {
        background-color: #B8BF3D !important;
        border: 1px solid #90972b !important;
        color: white !important;
    }

    h3.sidebar-title {
        color: #B8BF3D;
        font-size: 28px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.caption("어르신들의 건강 상태를 고려한 식단 솔루션을 제공합니다.")

# 세션 상태 초기화
if 'message_list' not in st.session_state:
    st.session_state.message_list = []

# 세션 초기화
if 'mode' not in st.session_state:
    st.session_state.mode = "🥗 맞춤 식단 솔루션"

st.sidebar.markdown(
    '<h3 style="color:#226f54; font-size:28px; font-weight:bold; margin-bottom:10px;">모드 선택</h3>',
    unsafe_allow_html=True
)

st.sidebar.markdown("무엇을 도와드릴까요?")

if st.sidebar.button("🥗 맞춤 식단 솔루션", use_container_width=True):
    st.session_state.mode = "🥗 맞춤 식단 솔루션"
    st.rerun()

if st.sidebar.button("💬 라이프스타일 코칭", use_container_width=True):
    st.session_state.mode = "💬 라이프스타일 코칭"
    st.rerun()

# ================================
# 🥗 맞춤 식단 솔루션
# ================================

# 🥗 맞춤 식단 솔루션 모드
if st.session_state.mode == "🥗 맞춤 식단 솔루션":
    st.markdown("### 🏥 요양원 선택")
    selected_center = st.selectbox("요양원을 선택하세요", ["헤리티지실버케어 분당", "평택은화케어", "포천제일요양원", "엘레강스요양원", "하계실버센터", "홍천아르떼", "용인프라임실버", "굿케어힐링센터", "대교뉴이프데이케어", "상락원", "마리아의집", "서울간호전문"])
    st.markdown("### 📁 요양원 메뉴 파일과 어르신 정보를 업로드하세요")
    
    menu_file = st.file_uploader("📂 메뉴 파일 업로드 (예: sarang_menu.xlsx)", type="xlsx")
    patient_file = st.file_uploader("📂 어르신 정보 파일 업로드 (예: 헤리티지_어르신정보.xlsx)", type="xlsx")
    
    if menu_file and patient_file:
        category_df = pd.read_excel(menu_file, sheet_name="category")
        category_df = category_df[category_df["Category"].isin(["밥", "국", "주찬", "부찬1", "부찬2", "김치"])]
        patient_df = pd.read_excel(patient_file, sheet_name=0)
    
        patient_df["질환"] = patient_df.apply(assign_disease, axis=1)
        patient_df["식단옵션"] = patient_df.apply(lambda row: get_meal_option(row["밥"], row["반찬"], row["질환"]), axis=1)
    
        final_results = generate_final_results(patient_df, category_df)
    
        selected_id = st.text_input("🔍 수급자ID를 입력하세요:")
        if selected_id:
            found = False
            for disease, df in final_results.items():
                match = df[df["수급자ID"] == selected_id]
                if not match.empty:
                    st.success(f"✅ {selected_id}님의 추천 식단 (질환: {disease})")
                    st.dataframe(match)
                    found = True
            if not found:
                st.warning("해당 수급자ID에 대한 식단을 찾을 수 없습니다.")
    
        # 엑셀 다운로드
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            for disease, df in final_results.items():
                df.to_excel(writer, sheet_name=disease, index=False)
        output.seek(0)
        st.download_button("⬇️ 전체 식단 엑셀 다운로드", data=output, file_name="맞춤_식단_추천.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("먼저 메뉴 파일과 어르신 정보를 업로드해주세요.")
