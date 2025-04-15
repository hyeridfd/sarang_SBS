
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
    if rice == "일반밥" and side == "일반찬":
        suffix = ""
    elif rice == "일반밥" and side == "다진찬":
        suffix = "_다진찬"
    elif rice == "일반죽" and side == "다진찬":
        suffix = "_다진찬"
        if disease == "신장":
            replace_rice = {"잡곡밥": "야채죽", "쌀밥": "야채죽"}
    elif rice == "갈죽" and side == "갈찬":
        suffix = "_갈찬"
        if disease == "신장":
            replace_rice = {"잡곡밥": "야채죽_갈죽", "쌀밥": "야채죽_갈죽"}
    return {"suffix": suffix, "replace_rice": replace_rice}

def apply_meal_customization(menu_df, option):
    suffix = option["suffix"]
    replace_rice = option["replace_rice"]
    modified_df = menu_df.copy()
    if replace_rice:
        for old_val, new_val in replace_rice.items():
            modified_df.loc[(modified_df["Category"] == "밥") & (modified_df["Menu"] == old_val), "Menu"] = new_val
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

st.set_page_config(page_title="맞춤형 식단 추천", layout="wide")
st.title("🍱 어르신 맞춤형 식단 추천 시스템")

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
