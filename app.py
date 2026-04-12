import streamlit as st
import pandas as pd
import gspread
import datetime
import os
import traceback

# 1. إعداد الصفحة مع دعم RTL
st.set_page_config(page_title="متابعة حالة المدارس في التقويم المدرسي الذاتي", page_icon="", layout="wide")

st.markdown("""
<style>
    .stApp, body { direction: rtl; text-align: right; }
    h1, h2, h3, h4, h5, h6, p, div { text-align: right !important; }
    .stSelectbox > div, .stDateInput > div, .stTextArea > div { direction: rtl; text-align: right; }
    .stAlert { direction: rtl; text-align: right; }
    .stButton button { display: block; margin: 0 auto; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 2. دالة الاتصال بـ Google Sheets
def connect_to_gsheet():
    from google.oauth2.service_account import Credentials
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=scope
    )
    client = gspread.authorize(creds)
    try:
        return client.open("سجل تقارير الزيارات").sheet1 
    except Exception as e:
        print(f"خطأ في فتح الملف: {e}")
        return None

# 3. دالة جلب الأرقام الوزارية للمدارس التي تمت زيارتها
def get_visited_school_ids(sheet):
    try:
        records = sheet.get_all_values()
        if len(records) > 1:
            return [str(row[1]) for row in records[1:]]
        return []
    except:
        return []

# 4. دالة قراءة ملف المدارس من السيرفر
@st.cache_data
def load_school_data():
    file_path = 'schools.csv'
    if os.path.exists(file_path):
        return pd.read_csv(file_path, sep=';')
    else:
        return None

# ----------------- واجهة المستخدم -----------------
st.title("متابعة حالة المدارس في التقويم المدرسي الذاتي")
st.markdown("**الواجهة المخصصة لمشرفي قسم الإدارة المدرسية**")
st.markdown("---")

df = load_school_data()

if df is not None:
    sheet = connect_to_gsheet()
    visited_ids = get_visited_school_ids(sheet) if sheet else []

    if 'مشرف الإدارة المدرسية' in df.columns:
        st.subheader("اختيار المشرف/ة")
        supervisors = df['مشرف الإدارة المدرسية'].dropna().unique()
        selected_supervisor = st.selectbox("يرجى اختيار اسم المشرف من القائمة:", ["-- اختر المشرف --"] + list(supervisors))

        if selected_supervisor != "-- اختر المشرف --":
            supervisor_schools = df[df['مشرف الإدارة المدرسية'] == selected_supervisor].copy()
            
            # تمييز المدارس التي تمت زيارتها
            def mark_visited(row):
                if str(row['رقم وزاري']) in visited_ids:
                    return f"{row['اسم المدرسة']} (تمت الزيارة ✅)"
                return row['اسم المدرسة']

            supervisor_schools['display_name'] = supervisor_schools.apply(mark_visited, axis=1)
            
            st.markdown("---")
            st.subheader(" المدارس المسندة ")
            selected_display_name = st.selectbox("اختر المدرسة التي قمت بزيارتها:", ["-- اختر المدرسة --"] + supervisor_schools['display_name'].tolist())
            
            if selected_display_name != "-- اختر المدرسة --":
                school_info = supervisor_schools[supervisor_schools['display_name'] == selected_display_name].iloc[0]
                school_id = school_info['رقم وزاري']
                original_school_name = school_info['اسم المدرسة']
                
                if str(school_id) in visited_ids:
                    st.warning("⚠️ تنبيه: هذه المدرسة تم رفع تقرير زيارة لها مسبقاً.")

                st.info(f"المدرسة المختارة: **{original_school_name}** | الرقم الوزاري: **{school_id}**")
                
                st.markdown("---")
                st.subheader(" بنود الزيارة")
                
                col1, col2 = st.columns(2)
                with col2:
                    visit_date = st.date_input("تاريخ الزيارة", datetime.date.today())
                with col1:
                    status = st.selectbox("حالة المدرسة في التقويم الذاتي", ["لم تبدأ التقويم الذاتي", "بدأت التقويم الذاتي ولم تنتهي", "أنهت التقويم الذاتي وبإنتظار صدور التقرير"])
                
                # --- المنطق الشرطي الذكي لصندوقي المبررات والدعم ---
                if status in ["لم تبدأ التقويم الذاتي", "بدأت التقويم الذاتي ولم تنتهي"]:
                    justifications = st.text_area("مبررات عدم الإنتهاء من التقويم الذاتي *", placeholder="اكتب أسباب عدم الانتهاء من التقويم الذاتي هنا...")
                    required_support = st.text_area("الدعم المطلوب *", placeholder="حدد نوع الدعم الذي تحتاجه المدرسة لإكمال التقويم...")
                    needs_inputs = True
                else:
                    st.success("✨ جميل..! بما أن المدرسة (أنهت) عملية التقويم الذاتي، يمكنك الحفظ وإرسال تقرير الزيارة.")
                    justifications = "أنهت المدرسة التقويم الذاتي ولا يوجد مبررات."
                    required_support = "أنهت المدرسة التقويم الذاتي ولا يوجد دعم مطلوب."
                    needs_inputs = False
                
                # إظهار ملاحظة الحقول الإلزامية فقط إذا كانت الحقول ظاهرة
                if needs_inputs:
                    st.caption("* الحقول المشار إليها بعلامة نجمة هي حقول إلزامية")
                    
                submit = st.button("إرسال التقرير", use_container_width=True, type="primary")
                
                if submit:
                    # التحقق من إلزامية الحقول فقط إذا كانت المدرسة لم تنهِ التقويم
                    if needs_inputs and (not justifications.strip() or not required_support.strip()):
                        st.error("❌ عذراً، يجب تعبئة حقلي (المبررات) و (الدعم المطلوب) لأن المدرسة لم تنهِ التقويم الذاتي بعد.")
                    else:
                        try:
                            if sheet:
                                row_to_add = [
                                    selected_supervisor, 
                                    str(school_id), 
                                    original_school_name, 
                                    str(visit_date), 
                                    status, 
                                    justifications, 
                                    required_support
                                ]
                                sheet.append_row(row_to_add)
                                st.success(f"✅ تم حفظ تقرير مدرسة {original_school_name} بنجاح.")
                                st.balloons() 
                                st.cache_data.clear()
                            else:
                                st.error("❌ فشل الاتصال بالسجل السحابي.")
                        except Exception as e:
                            traceback.print_exc()
                            st.error(f"حدث خطأ أثناء الحفظ: {e}")
    else:
        st.error("لم يتم العثور على عمود المشرفين في ملف البيانات.")