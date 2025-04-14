import streamlit as st
import pandas as pd
import requests
from io import BytesIO

st.set_page_config(page_title="질환별 5찬 식단 추천 시스템", layout="wide")
st.title("🧓 질환별 맞춤 5찬 식단 추천 시스템")

# GitHub에서 메뉴 파일 불러오기
@st.cache_data
def load_menu_from_github():
    url = "https://github.com/hyeridfd/sarang_SBS/blob/main/sarang_menu.xlsx"  # 사용자 GitHub URL로 교체
    response = requests.get(url)
    return pd.ExcelFile(BytesIO(response.content))

# 어르신 정보 업로드
uploaded_file = st.file_uploader("📁 어르신 정보를 업로드하세요 (예: 헤리티지_어르신정보.xlsx)", type=["xlsx"])

if uploaded_file:
    patient_df = pd.read_excel(uploaded_file)
    xls_menu = load_menu_from_github()
    category_df = xls_menu.parse("category")

    required_categories = ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]
    category_order = pd.CategoricalDtype(categories=required_categories, ordered=True)

    def determine_disease(row):
        if row["고혈압"] and row["신장질환"]:
            return "신장"
        elif row["당뇨"] and row["신장질환"]:
            return "신장"
        elif row["당뇨"] and row["고혈압"]:
            return "고혈압"
        elif row["신장질환"]:
            return "신장"
        elif row["고혈압"]:
            return "고혈압"
        elif row["당뇨"]:
            return "당뇨"
        return None

    patient_df["질환"] = patient_df.apply(determine_disease, axis=1)

    disease_menus = {
        "당뇨": category_df[category_df["Disease"].str.contains("당뇨", na=False)]["Menu"].unique(),
        "고혈압": category_df[category_df["Disease"].str.contains("고혈압", na=False)]["Menu"].unique(),
        "신장": category_df[category_df["Disease"].str.contains("신장", na=False)]["Menu"].unique(),
    }

    final_results = {}
    for disease, menus in disease_menus.items():
        matched_patients = patient_df[patient_df["질환"] == disease][["수급자ID", "질환"]]
        filtered_menus = category_df[
            (category_df["Menu"].isin(menus)) &
            (category_df["Category"].isin(required_categories))
        ]
        selected_menus = (
            filtered_menus
            .drop_duplicates(subset="Category", keep="first")
            .loc[filtered_menus["Category"].isin(required_categories)]
        )
        if set(required_categories).issubset(set(selected_menus["Category"])):
            selected_menus["Category"] = selected_menus["Category"].astype(category_order)
            selected_menus = selected_menus.sort_values("Category")
            selected_menus = selected_menus[[
                "Menu", "Category", "총 중량", "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)",
                "단백질(g)", "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"
            ]]
            combined = matched_patients.assign(key=1).merge(
                selected_menus.assign(key=1), on="key"
            ).drop("key", axis=1)
            final_results[disease] = combined

    # 수급자 ID로 검색
    selected_id = st.text_input("🔎 수급자ID를 입력해 주세요:")
    if selected_id:
        matched_rows = []
        for disease, df in final_results.items():
            match = df[df["수급자ID"] == selected_id]
            if not match.empty:
                st.subheader(f"✅ {selected_id}님의 추천 식단 (질환: {disease})")
                st.dataframe(match.sort_values("Category"))
                matched_rows.append(match)
        if not matched_rows:
            st.warning("해당 수급자ID에 대한 추천 식단이 없습니다.")

    # 전체 엑셀 다운로드
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for disease, df in final_results.items():
            df.to_excel(writer, sheet_name=disease, index=False)
    output.seek(0)
    st.download_button("⬇️ 전체 식단 엑셀 다운로드", data=output, file_name="최신_메뉴기준_질환별_5찬식단.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
