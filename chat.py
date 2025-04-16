import streamlit as st
import pandas as pd
from io import BytesIO
import re

standard_df = pd.read_excel("./MFDS(1).xlsx", sheet_name=0, index_col=0)
standard_df = standard_df.T.fillna("")

# 인덱스를 기준으로 정렬된 키 생성
disease_standards = {}
for disease, row in standard_df.iterrows():
    sorted_key = ", ".join(sorted([d.strip() for d in disease.split(",")]))
    disease_standards[sorted_key] = row.to_dict()
# ========== 함수 정의 ==========

def assign_primary_disease(row):
    if row["연하곤란"] == 1:
        return "연하곤란"
    elif row["고혈압"] == 1 and row["신장질환"] == 1:
        return "신장질환"
    elif row["당뇨"] == 1 and row["신장질환"] == 1:
        return "신장질환"
    elif row["당뇨"] == 1 and row["고혈압"] == 1:
        return "고혈압"
    elif row["신장질환"] == 1:
        return "신장질환"
    elif row["고혈압"] == 1:
        return "고혈압"
    elif row["당뇨"] == 1:
        return "당뇨"
    return "질환없음"

def assign_all_diseases(row):
    diseases = []
    for d in ["당뇨", "고혈압", "신장질환", "연하곤란"]:
        if row[d] == 1:
            diseases.append(d)
    return ", ".join(diseases) if diseases else "질환없음"

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
    elif rice == "일반죽" and side == "갈찬":
            suffix = "_갈찬"
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
    disease_types = ["질환없음", "당뇨", "고혈압", "신장질환", "연하곤란"]
    required_categories = ["밥", "국", "주찬", "부찬1", "부찬2", "김치"]
    category_order = pd.CategoricalDtype(categories=required_categories, ordered=True)
    final_results = {}
    for disease in disease_types:
        menus = category_df[category_df["Disease"].str.contains(disease, na=False)]
        results = []
        for _, row in patient_df[patient_df["대표질환"] == disease].iterrows():
            patient_id = row["수급자ID"]
            option = row["식단옵션"]
            selected = menus[menus["Category"].isin(required_categories)].drop_duplicates("Category")
            if set(required_categories).issubset(set(selected["Category"])):
                customized = apply_meal_customization(selected, option)
                customized["Category"] = customized["Category"].astype(category_order)
                customized = customized.sort_values("Category")

                if "Disease" in customized.columns:
                    customized = customized.drop(columns=["Disease"])
       
                customized.insert(0, "수급자ID", patient_id)
                diseases = patient_df.loc[patient_df["수급자ID"] == patient_id, "질환"].values
                if len(diseases) > 0:
                    customized.insert(1, "질환", diseases[0])  # 수급자ID 다음 열에 삽입
                results.append(customized)
        if results:
            final_results[disease] = pd.concat(results, ignore_index=True)
    return final_results

def update_rice_nutrient(match, category_df):
    rice_row = match[match["Category"] == "밥"]
    if rice_row.empty:
        return match

    rice_idx = rice_row.index[0]
    rice_menu = rice_row["Menu"].values[0]

    # category_df에서 같은 메뉴의 영양성분 찾기
    actual_rice = category_df[(category_df["Category"] == "밥") & (category_df["Menu"] == rice_menu)]
    
    if not actual_rice.empty:
        for col in ["총 중량", "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)", "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"]:
            match.loc[rice_idx, col] = actual_rice[col].values[0]

    return match


def adjust_rice_if_nutrient_insufficient(match, patient_df, selected_id):
    # def parse_range(value):
    #     try:
    #         return list(map(lambda x: float(x.strip()), value.split("~")))
    #     except:
    #         return [0.0, 0.0]
    def parse_range(value):
        try:
            if isinstance(value, str) and "~" in value:
                parts = value.split("~")
                return [float(parts[0].strip()), float(parts[1].strip())]
            elif isinstance(value, (float, int)):
                return [value, value]
        except Exception as e:
            st.warning(f"⚠️ parse_range 오류: {value}, 에러: {e}")
        return [0.0, 0.0]

    # 수급자 기준 정보 가져오기
    row = patient_df[patient_df["수급자ID"] == selected_id]
    if row.empty or "개인_에너지(kcal)" not in row.columns:
        return match

    # 권장 범위 파싱
    kcal_min, kcal_max = parse_range(row["개인_에너지(kcal)"].values[0])
    carb_min, carb_max = parse_range(row["개인_탄수화물(g)"].values[0])
    protein_min, protein_max = parse_range(row["개인_단백질(g)"].values[0])
    fat_min, fat_max = parse_range(row["개인_지방(g)"].values[0])

    nutrient_cols = ["총 중량", "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)", "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"]
    if not set(nutrient_cols).issubset(match.columns) or "Category" not in match.columns:
        return match

    match = match.copy()  # SettingWithCopyWarning 방지
    totals = match[nutrient_cols].sum(numeric_only=True)

    adjust_targets = match[match["Category"].isin(["밥", "주찬"])]
    if adjust_targets.empty:
        return match

    idxs = adjust_targets.index.tolist()
    
    current_vals = match.loc[idxs, nutrient_cols].sum(numeric_only=True)
    
    def compute_ratio(actual, min_val, max_val, adjust_val, name):
        if adjust_val == 0:
            return 1.0
        if actual < min_val:
            needed = min_val - actual
            ratio = (adjust_val + needed) / adjust_val
            st.markdown(f"<small>🔺 <b>{name}</b>: 부족 {needed:.2f} → 비율 <b>{ratio:.2f}</b></small>", unsafe_allow_html=True)
            return ratio
        elif actual > max_val:
            excess = actual - max_val
            ratio = (adjust_val - excess) / adjust_val
            st.markdown(f"<small>🔻 <b>{name}</b>: 초과 {excess:.2f} → 비율 <b>{ratio:.2f}</b></small>", unsafe_allow_html=True)
            return ratio
        else:
            st.markdown(f"<small>✅ <b>{name}</b>: 기준 충족 → 비율 <b>1.00</b></small>", unsafe_allow_html=True)
            return 1.0

    ratios = [
        compute_ratio(totals["에너지(kcal)"], kcal_min, kcal_max, current_vals["에너지(kcal)"], "에너지"),
        compute_ratio(totals["탄수화물(g)"], carb_min, carb_max, current_vals["탄수화물(g)"], "탄수화물"),
        compute_ratio(totals["단백질(g)"], protein_min, protein_max, current_vals["단백질(g)"], "단백질"),
        compute_ratio(totals["지방(g)"], fat_min, fat_max, current_vals["지방(g)"], "지방")
    ]
    
    # 가장 조정이 필요한 비율 (1에서 가장 멀리 떨어진 값)
    most_significant_ratio = max(ratios, key=lambda r: abs(r - 1.0))
    
    # 0.2 ~ 1.5로 클립
    ratio = min(max(most_significant_ratio, 0.2), 1.5)

    if ratio != 1.0:
        st.write(f"🍚 {selected_id} 밥+주찬 조절 비율: {ratio:.2f}")
        for col in nutrient_cols:
            match.loc[idxs, col] = match.loc[idxs, col] * ratio

    return match

def extract_float(text):
    match = re.search(r"[-+]?\d*\.?\d+", str(text))
    return float(match.group()) if match else None

def evaluate_nutrient_criteria(nutrient, value, rule, total_energy=None):
    rule = str(rule).strip()
    print(f"🔍 기준 판별 → nutrient: {nutrient}, value: {value}, rule: {rule}")


    if "%" in rule and total_energy:
        if nutrient in ["포화지방(g)", "지방(g)"]:
            ratio = (value * 9 / total_energy) * 100
        elif nutrient in ["단백질(g)", "탄수화물(g)", "당류(g)"]:
            ratio = (value * 4 / total_energy) * 100
        else:
            return ""

        if "~" in rule:
            parts = rule.replace("%", "").split("~")
            low, high = extract_float(parts[0]), extract_float(parts[1])
            return "충족" if low <= ratio <= high else "미달"
            
        limit = extract_float(rule)
        if "이하" in rule:
            return "충족" if ratio <= limit else "미달"
        elif "미만" in rule:
            return "충족" if ratio < limit else "미달"
        elif "이상" in rule:
            return "충족" if ratio >= limit else "미달"
        return ""

    # 일반 수치 기준 처리
    if rule.endswith("이하"):
        limit = extract_float(rule)
        return "충족" if value <= limit else "미달"
    elif rule.endswith("이상"):
        limit = extract_float(rule)
        return "충족" if value >= limit else "미달"
    elif rule.endswith("미만"):
        limit = extract_float(rule)
        return "충족" if value < limit else "미달"
    elif "~" in rule:
        parts = rule.split("~")
        low, high = extract_float(parts[0]), extract_float(parts[1])
        return "충족" if low <= value <= high else "미달"

    return ""


def generate_evaluation_summary(total_nutrients, diseases):
    evaluation = {}
    disease_key = ", ".join(sorted([d.strip() for d in diseases]))  # 질환명을 알파벳 순서로 정렬하여 키 생성
    standard = disease_standards.get(disease_key, {})
    #st.write("📋 현재 기준표에 등록된 키 목록:", list(disease_standards.keys()))

    total_energy = total_nutrients.get("에너지(kcal)", 0)

    for nutrient in [
        "에너지(kcal)", "당류(g)", "식이섬유(g)", "단백질(g)",
        "지방(g)", "포화지방(g)", "나트륨(mg)", "칼륨(mg)"
    ]:
        rule = standard.get(nutrient, "")
        value = total_nutrients.get(nutrient, 0)

        evaluation[nutrient + "_기준"] = rule
        evaluation[nutrient + "_평가"] = evaluate_nutrient_criteria(nutrient, value, rule, total_energy)

    return evaluation

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

# if st.sidebar.button("💬 라이프스타일 코칭", use_container_width=True):
#     st.session_state.mode = "💬 라이프스타일 코칭"
#     st.rerun()

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
    
        patient_df["대표질환"] = patient_df.apply(assign_primary_disease, axis=1)
        patient_df["질환"] = patient_df.apply(assign_all_diseases, axis=1)
        patient_df["식단옵션"] = patient_df.apply(lambda row: get_meal_option(row["밥"], row["반찬"], row["질환"]), axis=1)

        # patient_df["표시질환"] = patient_df.apply(lambda row: "질환없음" if (
        #     row["당뇨"] == 0 and row["고혈압"] == 0 and row["신장질환"] == 0 and row["연하곤란"] == 0
        # ) else row["질환"], axis=1)
    
        final_results = generate_final_results(patient_df, category_df)

        # 🥗 점심 영양소 계산을 위한 함수 정의
        def convert_height_pa(row):
            height_m = row["신장"] / 100  # cm → m
            pa_map = {1: 1.0, 2: 1.1, 3: 1.2}
            pa = pa_map.get(row["활동정도"], 1.0)
            return height_m, pa
        
        def calculate_eer(sex, age, weight, height, pa):
            if sex in ['남성', 'male', '남']:
                return 662 - (9.53 * age) + pa * (15.91 * weight + 539.6 * height)
            elif sex in ['여성', 'female', '여']:
                return 354 - (6.91 * age) + pa * (9.36 * weight + 726 * height)
            else:
                raise ValueError("Invalid sex")
        
        def calculate_daily_intake(sex, age, weight, height, pa, waist=100):
            bmi = weight / (height ** 2)
            eer = calculate_eer(sex, age, weight, height, pa)
            if bmi >= 25 or (sex in ['남성', 'male', '남'] and waist >= 90) or (sex in ['여성', 'female', '여'] and waist >= 85):
                return (eer - 400, eer - 200)
            elif 18.5 <= bmi < 23:
                return (eer + 300, eer + 500)
            else:
                return (eer + 600, eer + 800)
        
        def calculate_meal_distribution(daily_intake_range):
            min_intake, max_intake = daily_intake_range
            return (min_intake * 0.3, max_intake * 0.3)  # 점심 기준 30%
        
        # ✨ 점심 기준 영양소 계산 및 컬럼 추가
        energy_list, carbs_list, protein_list, fat_list = [], [], [], []
        
        for _, row in patient_df.iterrows():
            sex = row["성별"]
            age = row["나이"]
            weight = row["체중"]
            height_m, pa = convert_height_pa(row)
            
            try:
                daily_range = calculate_daily_intake(sex, age, weight, height_m, pa)
                lunch_kcal = calculate_meal_distribution(daily_range)
                
                carbs_min = daily_range[0] * 0.55 / 4
                carbs_max = daily_range[1] * 0.65 / 4
                protein_min = max(50, daily_range[0] * 0.07 / 4) if sex in ['남성', 'male', '남'] else max(40, daily_range[0] * 0.07 / 4)
                protein_max = daily_range[1] * 0.20 / 4
                fat_min = daily_range[0] * 0.15 / 9
                fat_max = daily_range[1] * 0.30 / 9
        
                lunch_carbs = calculate_meal_distribution((carbs_min, carbs_max))
                lunch_protein = calculate_meal_distribution((protein_min, protein_max))
                lunch_fat = calculate_meal_distribution((fat_min, fat_max))
        
                energy_list.append(f"{lunch_kcal[0]:.0f} ~ {lunch_kcal[1]:.0f}")
                carbs_list.append(f"{lunch_carbs[0]:.0f} ~ {lunch_carbs[1]:.0f}")
                protein_list.append(f"{lunch_protein[0]:.0f} ~ {lunch_protein[1]:.0f}")
                fat_list.append(f"{lunch_fat[0]:.0f} ~ {lunch_fat[1]:.0f}")
        
            except:
                energy_list.append("에러")
                carbs_list.append("에러")
                protein_list.append("에러")
                fat_list.append("에러")
        
        patient_df["개인_에너지(kcal)"] = energy_list
        patient_df["개인_탄수화물(g)"] = carbs_list
        patient_df["개인_단백질(g)"] = protein_list
        patient_df["개인_지방(g)"] = fat_list

        # 여러 명의 수급자ID 입력 가능하도록 수정
        selected_ids_input = st.text_area("🔍 수급자ID를 입력하세요 (여러 명은 쉼표 또는 줄바꿈으로 구분)")
        selected_ids = [s.strip() for s in selected_ids_input.replace("\n", ",").split(",") if s.strip()]
        
        adjusted_results = {}
        if selected_ids:
            for selected_id in selected_ids:
                found = False
                for disease, df in final_results.items():
                    results = []
                    for sid in df["수급자ID"].unique():  # ✅ 여기 변수명 sid 등으로 변경
                        if sid != selected_id:
                            continue
                        match = df[df["수급자ID"] == sid]
                        if not match.empty:
                            match = update_rice_nutrient(match, category_df)
                            match = adjust_rice_if_nutrient_insufficient(match, patient_df, sid)
            
                            disease_label = patient_df[patient_df["수급자ID"] == sid]["질환"]
                            nutrient_info = patient_df[patient_df["수급자ID"] == sid][
                                ["개인_에너지(kcal)", "개인_탄수화물(g)", "개인_단백질(g)", "개인_지방(g)"]
                            ].iloc[0].to_dict()
                            for key, val in nutrient_info.items():
                                match.loc[:, key] = val

                            nutrient_cols = [
                                                "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)",
                                                "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"
                                            ]

                            st.markdown(f"### {sid}님의 추천 식단")
                            st.dataframe(match)

                            if set(nutrient_cols).issubset(match.columns):
                                st.markdown("#### 👩🏻‍⚕️ 메뉴 영양성분 정보")
                                total_nutrients = match[nutrient_cols].sum(numeric_only=True)
                                for col in nutrient_cols:
                                    st.write(f"- 총 {col}: **{total_nutrients[col]:.1f}**")
            
                            results.append(match)
                            
                            found = True
                            
                            
                    # if results:
                    #     adjusted_results[disease] = pd.concat(results, ignore_index=True)
                    if results:
                        if disease not in adjusted_results:
                            adjusted_results[disease] = pd.concat(results, ignore_index=True)
                        else:
                            adjusted_results[disease] = pd.concat(
                                [adjusted_results[disease], pd.concat(results, ignore_index=True)],
                                ignore_index=True
                        )

                if not found:
                    st.warning(f"❌ {selected_id} 수급자ID에 대한 식단을 찾을 수 없습니다.")

    
                    #results = []
                    #match = df[df["수급자ID"] == selected_id]
                    #for selected_id in df["수급자ID"].unique():
                        #match = df[df["수급자ID"] == selected_id]
                    
                    # if not match.empty:
                    #     match = adjust_rice_if_nutrient_insufficient(match, patient_df, selected_id)
                    #     disease_label = patient_df[patient_df["수급자ID"] == selected_id]["표시질환"].values[0]
        
        evaluation_results = []
        for disease, df in adjusted_results.items():
            for sid in df["수급자ID"].unique():
                target = df[df["수급자ID"] == sid]
                total_nutrients = target[[
                    "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)", "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"
                ]].sum(numeric_only=True)
                # disease_label = patient_df[patient_df["수급자ID"] == sid]["질환"].values[0]
                # evaluation = generate_evaluation_summary(total_nutrients, disease_label)
                # row = {"수급자ID": sid, "질환": disease_label}
                # row.update(evaluation)
                # evaluation_results.append(row)

                disease_value = patient_df[patient_df["수급자ID"] == sid]["질환"].values
                if len(disease_value) > 0:
                    disease_label = disease_value[0]  # 예: "당뇨, 고혈압"
                    diseases = [d.strip() for d in disease_label.split(",")]  # ['당뇨', '고혈압']
                else:
                    disease_label = "질환없음"
                    diseases = ["질환없음"]
                
                evaluation = generate_evaluation_summary(total_nutrients, diseases)
                row = {"수급자ID": sid, "질환": disease_label}
                row.update(evaluation)
                evaluation_results.append(row)

    
        # 엑셀 다운로드
        output = BytesIO()
        eval_df = pd.DataFrame(evaluation_results)
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            for disease, df in adjusted_results.items():
                # 💡 수급자별 영양소 정보 병합
                merged = df.merge(
                    patient_df[["수급자ID", "개인_에너지(kcal)", "개인_탄수화물(g)", "개인_단백질(g)", "개인_지방(g)"]],
                    on="수급자ID", how="left"
                )
                merged.to_excel(writer, sheet_name=disease, index=False)
            eval_df.to_excel(writer, sheet_name="영양기준_충족여부", index=False)
        output.seek(0)
        st.download_button(
            "⬇️ 전체 식단 엑셀 다운로드", 
            data=output, 
            file_name="맞춤_식단_추천.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_button_{selected_center}"
        )
