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

def get_meal_option(rice, side):
    replace_rice = None
    suffix = ""
    soup_suffix = ""

    if rice == "일반밥" and side == "일반찬":
        suffix = ""
    elif rice == "일반밥" and side == "다진찬":
        suffix = "_다진찬"
        soup_suffix = "_건더기잘게"
    elif rice == "일반죽" and side == "다진찬":
        suffix = "_다진찬"
        soup_suffix = "_건더기잘게"
        replace_rice = {"잡곡밥": "야채죽", "쌀밥": "야채죽"}
    elif rice == "일반죽" and side == "갈찬":
            suffix = "_갈찬"
            soup_suffix = "_국물만"
            replace_rice = {"잡곡밥": "야채죽", "쌀밥": "야채죽"}
    elif rice == "갈죽" and side == "갈찬":
        suffix = "_갈찬"
        soup_suffix = "_국물만"
        replace_rice = {"잡곡밥": "야채죽_갈죽", "쌀밥": "야채죽_갈죽", "야채죽": "야채죽_갈죽"}

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
        menus = category_df[category_df["Disease"] == disease]
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
            
    
    def round_to_nearest_ratio(value, allowed_ratios=[0.25, 0.5, 1.0, 1.25, 2.0]):
        return min(allowed_ratios, key=lambda x: abs(x - value))


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
    
    #개인 권장 범위를 얼마나 벗어났는지에 따라 조정 비율 계산        
    def compute_ratio(actual, min_val, max_val, adjust_val, name):
        if adjust_val == 0:
            return 1.0, f"✅ <b>{name}</b>: 기준 충족 → 비율 <b>1.00</b>"
    
        if actual < min_val:
            needed = min_val - actual
            ratio = (adjust_val + needed) / adjust_val
            return ratio, f"🔻 <b>{name}</b>: 부족 {needed:.2f} → 비율 <b>{ratio:.2f}</b>"
    
        elif actual > max_val:
            excess = actual - max_val
            ratio = (adjust_val - excess) / adjust_val
            return ratio, f"🔺 <b>{name}</b>: 초과 {excess:.2f} → 비율 <b>{ratio:.2f}</b>"
    
        return 1.0, f"✅ <b>{name}</b>: 기준 충족 → 비율 <b>1.00</b>"
    
    ratio_msgs = []
    ratios = []
    for nutrient, min_val, max_val in zip(
        ["에너지(kcal)", "탄수화물(g)", "단백질(g)", "지방(g)"],
        [kcal_min, carb_min, protein_min, fat_min],
        [kcal_max, carb_max, protein_max, fat_max]
    ):
        ratio, msg = compute_ratio(totals[nutrient], min_val, max_val, current_vals[nutrient], nutrient.replace("(g)", "").replace("(kcal)", "").strip())
        ratios.append(ratio)
        ratio_msgs.append(msg)
        
    st.markdown(
        f"""
        <div style="display: flex; flex-wrap: wrap; gap: 14px; margin: 10px 0;">
            {"".join([f"<div style='white-space: nowrap; font-size: 14px;'>{m}</div>" for m in ratio_msgs])}
        </div>
        """,
        unsafe_allow_html=True
    )


    
    # 가장 조정이 필요한 비율 (1에서 가장 멀리 떨어진 값)
    most_significant_ratio = max(ratios, key=lambda r: abs(r - 1.0))
    
    # # 0.2 ~ 1.5로 클립
    # ratio = min(max(most_significant_ratio, 0.2), 1.5)

    rounded_ratio = round_to_nearest_ratio(most_significant_ratio)

    # if ratio != 1.0:
    #     st.write(f"🍚 {selected_id} 밥+주찬 조절 비율: {ratio:.2f}")
    #     for col in nutrient_cols:
    #         match.loc[idxs, col] = match.loc[idxs, col] * ratio

    if rounded_ratio != 1.0:
        st.write(f"🍽️ {selected_id} 밥+주찬 조절 비율: {rounded_ratio:.2f}")
        for col in nutrient_cols:
            match.loc[idxs, col] = match.loc[idxs, col] * rounded_ratio

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

st.set_page_config(page_title="사랑과선행 요양원 맞춤 푸드 솔루션", layout="wide")

st.image("./logo.png", width=300)

st.markdown(
    '<h3 style="color:#226f54; font-size:45px; font-weight:bold;">SNU CareFit +</h3>',
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

st.markdown(
    '<h3 style="color:#6c757d; font-size:14px; font-weight:semibold;">건강한 한 끼로 어르신의 일상을 더 따뜻하게, 서울대와 사랑과선행이 함께합니다.</h3>',
    unsafe_allow_html=True
)
#st.caption("서울대와 사랑과선행이 어르신들의 건강 상태를 고려한 푸드 솔루션을 제공합니다.")

# 세션 상태 초기화
if 'message_list' not in st.session_state:
    st.session_state.message_list = []

# 세션 초기화
if 'mode' not in st.session_state:
    st.session_state.mode = "맞춤 푸드 솔루션"

st.sidebar.markdown(
    '<h3 style="color:#226f54; font-size:28px; font-weight:bold; margin-bottom:10px;">모드 선택</h3>',
    unsafe_allow_html=True
)

st.sidebar.markdown("무엇을 도와드릴까요?")

if st.sidebar.button("🥗 맞춤 푸드 솔루션", use_container_width=True):
    st.session_state.mode = "맞춤 푸드 솔루션"
    st.rerun()

# if st.sidebar.button("💬 라이프스타일 코칭", use_container_width=True):
#     st.session_state.mode = "💬 라이프스타일 코칭"
#     st.rerun()

# ================================
# 🥗 맞춤 식단 솔루션
# ================================

# 🥗 맞춤 식단 솔루션 모드
if st.session_state.mode == "맞춤 푸드 솔루션":
    st.markdown("### 🏥 요양원 선택")
    selected_center = st.selectbox("요양원을 선택하세요", ["헤리티지실버케어 분당", "평택은화케어", "포천제일요양원", "엘레강스요양원", "하계실버센터", "홍천아르떼", "용인프라임실버", "굿케어힐링센터", "대교뉴이프데이케어", "상락원", "마리아의집", "서울간호전문"])
    st.markdown("### 🗂️ 요양원 메뉴와 어르신 정보를 업로드하세요")
    
    menu_file = st.file_uploader("📂 메뉴 파일 업로드", type="xlsx")
    patient_file = st.file_uploader("📂 어르신 정보 파일 업로드", type="xlsx")
    
    if menu_file and patient_file:
        category_df = pd.read_excel(menu_file, sheet_name="category")
        category_df = category_df[category_df["Category"].isin(["밥", "국", "주찬", "부찬1", "부찬2", "김치"])]  #간식 메뉴 제외하고 한 끼 식사 구성 요소만 남김
        category_df = category_df[category_df["Disease"] != "저작곤란"]
        
        patient_df = pd.read_excel(patient_file, sheet_name=0)
    
        patient_df["대표질환"] = patient_df.apply(assign_primary_disease, axis=1)
        patient_df["질환"] = patient_df.apply(assign_all_diseases, axis=1)
        patient_df["식단옵션"] = patient_df.apply(lambda row: get_meal_option(row["밥"], row["반찬"]), axis=1)
        
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

        #체질량지수(BMI)에 따른 하루 권장 섭취 칼로리 도출
        def calculate_daily_intake(sex, age, weight, height, pa):
            bmi = weight / (height ** 2)
            eer = calculate_eer(sex, age, weight, height, pa)
            #비만 -> 500~700kcal 줄임
            if bmi >= 25:
                return (eer - 700, eer - 500)
            #비만전단계 -> 300~700kcal 줄임
            elif 23 <= bmi < 25:
                return (eer - 500, eer - 300)
            #정상 -> 범위를 위해 +-10%
            elif 18.5 <= bmi < 23:
                return (eer * 0.9, eer * 1.1)
            #저체중 -> 300~500kcal 보충
            else:
                return (eer + 300, eer + 500)
        
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
            
                            disease_label = patient_df[patient_df["수급자ID"] == sid]["대표질환"].values[0]
                            nutrient_info = patient_df[patient_df["수급자ID"] == sid][
                                ["개인_에너지(kcal)", "개인_탄수화물(g)", "개인_단백질(g)", "개인_지방(g)"]
                            ].iloc[0].to_dict()
                            for key, val in nutrient_info.items():
                                match.loc[:, key] = val

                            nutrient_cols = [
                                                "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)",
                                                "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"
                                            ]

                            st.markdown(f"### 👩🏻‍⚕️ {sid}님의 추천 식단")
                            table_with_total = match.copy()
                            nutrient_cols = [
                                "에너지(kcal)", "탄수화물(g)", "당류(g)", "식이섬유(g)", "단백질(g)",
                                "지방(g)", "포화지방(g)", "나트륨(mg)", "칼슘(mg)", "콜레스테롤", "칼륨(mg)"
                            ]
                            totals = table_with_total[nutrient_cols].sum(numeric_only=True)
                            
                            # 마지막 줄에 총합 row 추가
                            total_row = {col: totals[col] for col in nutrient_cols}
                            total_row.update({
                                "Category": "총 합계"  # 메뉴/카테고리엔 빈칸 or 총합계
                            })
                            table_with_total = pd.concat([table_with_total, pd.DataFrame([total_row])], ignore_index=True)
                            
                            # 표 출력
                            st.dataframe(table_with_total)

                            # if set(nutrient_cols).issubset(match.columns):
                            #     st.markdown("#### 👩🏻‍⚕️ 메뉴 영양성분 정보")
                            #     total_nutrients = match[nutrient_cols].sum(numeric_only=True)
                            #     for col in nutrient_cols:
                            #         st.write(f"- 총 {col}: **{total_nutrients[col]:.1f}**")
            
                            results.append(match)

                            info_row = patient_df[patient_df["수급자ID"] == sid].iloc[0]
                            # 기본 정보 + 개인 영양 기준
                            # st.markdown(
                            #     f"""
                            #     <div style='font-size:16px; line-height:1.6'>
                            #     🧓 <b>{sid}님의 정보</b>:
                            #     <b>성별:{info_row['성별']}</b> /
                            #     <b>나이:{info_row['나이']}세</b> /
                            #     <b>키:{info_row['신장']}cm</b> /
                            #     <b>체중:{info_row['체중']}kg</b> /
                            #     <b>활동수준:{info_row['활동정도']}</b> /
                            #     <b>요양등급:{info_row['요양등급']}</b> /
                            #     <b>밥 종류:{info_row['밥']}</b> /
                            #     <b>반찬 종류:{info_row['반찬']}</b>
                            #     </div>
                            #     """,
                            #     unsafe_allow_html=True
                            # )
                            
                            st.markdown(
                                f"""
                                <div style='font-size:18px; line-height:1.6'>
                                🥗 <b>{sid}님의 추천 메뉴:</b>
                                <b>{disease_label}식</b>
                                """,
                                unsafe_allow_html=True
                            )

                            
                            individual_info = patient_df[patient_df["수급자ID"] == sid][[
                                "개인_에너지(kcal)", "개인_탄수화물(g)", "개인_단백질(g)", "개인_지방(g)"
                            ]].iloc[0]

                            st.markdown(
                                f"""
                                <div style='font-size:18px;'>
                                💡 <b>{sid}님의 한 끼 영양 기준:</b>
                                <b>에너지:{individual_info['개인_에너지(kcal)']} kcal</b> |
                                <b>탄수화물:{individual_info['개인_탄수화물(g)']} g</b> |
                                <b>단백질:{individual_info['개인_단백질(g)']} g</b> |
                                <b>지방:{individual_info['개인_지방(g)']} g</b>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                            st.markdown("---")
                            found = True
                            break
                            
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
                disease_value = patient_df[patient_df["수급자ID"] == sid]["질환"].values[0]
                diseases = [d.strip() for d in disease_value.split(",")] if disease_value else ["질환없음"]
                evaluation = generate_evaluation_summary(total_nutrients, diseases)
                row = {"수급자ID": sid, "질환": disease_value}
                row.update(evaluation)
                evaluation_results.append(row)


        if not adjusted_results:
            st.warning("⚠️ 사용자 정보가 비어 있습니다. 사용자 정보를 입력해주세요.")
        else:
            st.success("✅ 맞춤 식단 데이터가 도출되었습니다.")

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
            # eval_df.to_excel(writer, sheet_name="영양기준_충족여부", index=False)
            # workbook  = writer.book
            # worksheet = writer.sheets["영양기준_충족여부"]
        
            # # '미달' 텍스트가 있는 셀에 빨간 글씨 적용
            # red_format = workbook.add_format({
            #     'font_color': 'red',
            #     'bold': True
            # })
        
            # # 전체 DataFrame 크기에 맞춰 범위 계산
            # nrows, ncols = eval_df.shape
            # for col_idx in range(ncols):
            #     col_letter = chr(65 + col_idx) if col_idx < 26 else f"{chr(64 + col_idx // 26)}{chr(65 + col_idx % 26)}"
            #     cell_range = f"{col_letter}2:{col_letter}{nrows+1}"
            #     worksheet.conditional_format(cell_range, {
            #         'type': 'text',
            #         'criteria': 'containing',
            #         'value': '미달',
            #         'format': red_format
            #     })
        output.seek(0)
        st.download_button(
            "⬇️ 맞춤 식단 데이터 다운로드", 
            data=output, 
            file_name=f"{selected_center}_맞춤식단.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_button_{selected_center}"
        )
    # st.write("category_df['Disease']에 존재하는 질환들:", category_df["Disease"].unique())
    # st.write("patient_df['대표질환'] 값:", patient_df["대표질환"].unique())
    # st.write("patient_df['대표질환'] 유형:", patient_df["대표질환"].dtype)
    # st.write("patient_df['질환'] 값:", patient_df["질환"].unique())
