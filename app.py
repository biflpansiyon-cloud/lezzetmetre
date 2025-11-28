import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import google.generativeai as genai
import re

# --- AYARLAR VE BAĞLANTILAR ---
st.set_page_config(page_title="LezzetMetre", page_icon="🍽️", layout="wide")

# Google Sheets Bağlantısı
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client

# Gemini API Bağlantısı
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except Exception as e:
    st.error(f"API Anahtarı hatası: {e}")

# --- YARDIMCI FONKSİYONLAR ---

def get_available_gemini_models():
    """Google hesabında tanımlı, içerik üretebilen TÜM modelleri canlı çeker."""
    try:
        model_list = []
        for m in genai.list_models():
            # Sadece metin üretebilen modelleri al (generateContent destekleyenler)
            if 'generateContent' in m.supported_generation_methods:
                # Model isminin başındaki 'models/' kısmını temizle
                clean_name = m.name.split("/")[-1]
                model_list.append(clean_name)
        return sorted(model_list, reverse=True) # En yeni versiyonlar üste gelsin diye ters sırala
    except Exception as e:
        # API bağlantısında sorun olursa manuel yedek liste dönsün
        return ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

def parse_yemek_listesi(hucre_verisi):
    if not hucre_verisi: return []
    text = str(hucre_verisi)
    lines = re.split(r'[\r\n]+', text)
    return [line.strip() for line in lines if line.strip()]

def get_todays_menu():
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("aktif_menu")
    all_values = sheet.get_all_values()
    
    now = datetime.now()
    bugun = f"{now.day}.{now.month}.{now.year}"
    
    target_row_index = -1
    for i, row in enumerate(all_values):
        if row[0].strip() == bugun:
            target_row_index = i
            break
            
    if target_row_index == -1: return None

    limit = min(target_row_index + 4, len(all_values))
    kahvalti_raw = all_values[target_row_index][2]
    ara_ogun_raw = all_values[target_row_index][5]
    
    ogle_listesi = []
    aksam_listesi = []
    for r in range(target_row_index, limit):
        if all_values[r][3].strip(): ogle_listesi.append(all_values[r][3].strip())
        if all_values[r][4].strip(): aksam_listesi.append(all_values[r][4].strip())

    return {
        "KAHVALTI": kahvalti_raw,
        "ÖĞLE": "\n".join(ogle_listesi),
        "AKŞAM": "\n".join(aksam_listesi),
        "ARA ÖĞÜN": ara_ogun_raw
    }

def save_feedback(data_list):
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("geribildirim")
    sheet.append_row(data_list)

def get_all_feedback():
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("geribildirim")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

def analyze_comments_with_ai(comments_text, stats_text, role="admin", model_name="gemini-2.5-flash"):
    """Seçilen model ile analiz yapar."""
    try:
        model = genai.GenerativeModel(model_name)
    except:
        # Eğer model adında hata varsa en yakını dener
        model = genai.GenerativeModel('gemini-1.5-flash')

    if role == "cook":
        prompt = f"""
        Sen bir mutfak şefisin. Verileri ekibine aktarıyorsun.
        İSTATİSTİKLER: {stats_text}
        ÖĞRENCİ YORUMLARI: {comments_text}
        GÖREVİN: "Ustam" diye hitap eden, kısa, samimi, madde imi kullanmayan, paragraf şeklinde bir konuşma hazırla. İyileri öv, kötüleri yapıcı uyar.
        """
    else:
        prompt = f"""
        Sen bir gıda mühendisisin.
        İSTATİSTİKLER: {stats_text}
        ÖĞRENCİ YORUMLARI: {comments_text}
        RAPOR FORMATI:
        1. **Genel Durum:**
        2. **Pozitifler:**
        3. **Negatifler:**
        4. **Öneri:**
        """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Hata ({model_name}): {str(e)}"

# --- ARAYÜZ (UI) ---

page_mode = st.sidebar.radio("Sistem Modu", ["Öğrenci Ekranı", "Yönetici Paneli"])

# --------------------------
# 🎓 ÖĞRENCİ EKRANI
# --------------------------
if page_mode == "Öğrenci Ekranı":
    st.title("🍽️ LezzetMetre")
    anlik_zaman = datetime.now()
    tarih_gosterim = anlik_zaman.strftime("%d.%m.%Y")
    st.info(f"📅 Tarih: **{tarih_gosterim}**")
    
    ogun = st.selectbox("Hangi öğün için oy veriyorsun?", ["Seçiniz...", "KAHVALTI", "ÖĞLE", "AKŞAM", "ARA ÖĞÜN"])
    
    if ogun != "Seçiniz...":
        menu_data = get_todays_menu()
        if menu_data is None:
            st.error(f"⚠️ {tarih_gosterim} tarihi için menü bulunamadı.")
        else:
            raw_menu_text = menu_data.get(ogun, "")
            yemekler = parse_yemek_listesi(raw_menu_text)
            with st.form("oylama_formu"):
                if ogun in ["ÖĞLE", "AKŞAM"]:
                    st.markdown("### 🍲 Menüde Ne Var?")
                    if yemekler:
                        for y in yemekler: st.success(f"• {y}")
                    else: st.warning("Menü bilgisi boş.")
                elif ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    st.markdown(f"**{ogun} İçeriği:**")
                    if yemekler: st.info(", ".join(yemekler))
                st.write("---")
                if ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    c1, c2, c3 = st.columns(3)
                    with c1: puan_lezzet = st.slider("😋 Lezzet", 1, 5, 3)
                    with c2: puan_hijyen = st.slider("🧼 Hijyen", 1, 5, 3)
                    with c3: puan_servis = st.slider("💁‍♂️ Servis", 1, 5, 3)
                    begenilen, sikayet = "", ""
                else:
                    st.write("#### Puanlaman:")
                    c1, c2, c3 = st.columns(3)
                    with c1: puan_lezzet = st.selectbox("😋 Lezzet", [1,2,3,4,5], index=2)
                    with c2: puan_hijyen = st.selectbox("🧼 Hijyen", [1,2,3,4,5], index=2)
                    with c3: puan_servis = st.selectbox("💁‍♂️ Servis", [1,2,3,4,5], index=2)
                    if yemekler:
                        st.write("#### Detaylar (Opsiyonel):")
                        col_a, col_b = st.columns(2)
                        with col_a: begenilen = st.selectbox("🏆 En Beğendiğin?", ["Seçim Yok"] + yemekler)
                        with col_b: sikayet = st.selectbox("👎 Sorunlu Olan?", ["Seçim Yok"] + yemekler)
                    else: begenilen, sikayet = "", ""
                yorum = st.text_area("Eklemek istediklerin:", placeholder="Fikrin bizim için değerli...")
                submit = st.form_submit_button("GÖNDER 🚀")
                if submit:
                    if begenilen == "Seçim Yok": begenilen = ""
                    if sikayet == "Seçim Yok": sikayet = ""
                    kayit = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tarih_gosterim, ogun, puan_lezzet, puan_hijyen, puan_servis, yorum, begenilen, sikayet]
                    save_feedback(kayit)
                    st.balloons()
                    st.success("Görüşün başarıyla kaydedildi! Teşekkürler.")

# --------------------------
# 🔐 YÖNETİCİ PANELİ
# --------------------------
elif page_mode == "Yönetici Paneli":
    st.sidebar.title("🔐 Giriş Paneli")
    pwd = st.sidebar.text_input("Şifre", type="password")
    
    ADMIN_PWD = st.secrets["passwords"]["admin"]
    CHEF_PWD = st.secrets["passwords"]["chef"]

    try:
        df = get_all_feedback()
        if not df.empty:
            df['Zaman'] = pd.to_datetime(df['Zaman_Damgasi'])
    except:
        df = pd.DataFrame()

    # --- ROL: SÜPER ADMIN ---
    if pwd == ADMIN_PWD:
        st.title("📊 Süper Admin Paneli")
        
        # --- DİNAMİK MODEL SEÇİMİ (API'DEN ÇEKER) ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("🤖 AI Model Seçimi")
        
        # Google'dan tüm modelleri çek
        available_models = get_available_gemini_models()
        
        # Varsayılanı 'gemini-2.5-flash' yapmaya çalış
        target_default = "gemini-2.5-flash"
        default_index = 0
        
        # Eğer listede varsa onu seç, yoksa listenin başındakini seç
        if target_default in available_models:
            default_index = available_models.index(target_default)
            
        selected_model = st.sidebar.selectbox(
            "Aktif Model", 
            available_models,
            index=default_index
        )
        st.sidebar.success(f"Seçili: **{selected_model}**")
        # ---------------------------------------------

        if not df.empty:
            filtre_tarih = st.radio("Zaman Aralığı", ["Bugün", "Son 7 Gün", "Tüm Kayıtlar"], horizontal=True)
            now = datetime.now()
            if filtre_tarih == "Bugün":
                df_filtered = df[df['Zaman'].dt.date == now.date()]
            elif filtre_tarih == "Son 7 Gün":
                df_filtered = df[df['Zaman'] >= (now - timedelta(days=7))]
            else:
                df_filtered = df
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam Oy", len(df_filtered))
            c2.metric("Lezzet", f"{df_filtered['Puan_Lezzet'].mean():.1f}")
            c3.metric("Hijyen", f"{df_filtered['Puan_Hijyen'].mean():.1f}")
            c4.metric("Servis", f"{df_filtered['Puan_Servis'].mean():.1f}")
            st.divider()
            
            tab1, tab2, tab3 = st.tabs(["🤖 AI Rapor", "📈 Grafikler", "📝 Veriler"])
            with tab1:
                st.caption(f"Analiz Modeli: **{selected_model}**")
                if st.button("Rapor Oluştur"):
                    with st.spinner("Analiz ediliyor..."):
                        yorum_listesi = [str(y) for y in df_filtered['Yorum'] if str(y).strip()]
                        if not yorum_listesi:
                            st.warning("Analiz yapılacak yeterli yorum yok.")
                        else:
                            text_data = "\n".join(yorum_listesi)
                            stats = f"Lezzet: {df_filtered['Puan_Lezzet'].mean():.1f}"
                            analiz = analyze_comments_with_ai(text_data, stats, role="admin", model_name=selected_model)
                            st.markdown(analiz)
            with tab2:
                st.bar_chart(df_filtered[['Puan_Lezzet', 'Puan_Hijyen', 'Puan_Servis']].mean())
                if 'Begenilen_Yemek' in df_filtered.columns:
                    st.write("En Beğenilenler:")
                    st.bar_chart(df_filtered['Begenilen_Yemek'].value_counts().head(5))
            with tab3:
                st.dataframe(df_filtered)
        else:
            st.warning("Henüz veri yok.")

    # --- ROL: AŞÇI ---
    elif pwd == CHEF_PWD:
        st.title("👨‍🍳 Mutfak Ekibi Paneli")
        if not df.empty:
            now = datetime.now()
            df_today = df[df['Zaman'].dt.date == now.date()]
            if not df_today.empty:
                st.subheader(f"📅 Bugünün ({now.strftime('%d.%m.%Y')}) Karnesi")
                k1, k2, k3 = st.columns(3)
                lezzet_puan = df_today['Puan_Lezzet'].mean()
                k1.metric("😋 Lezzet Puanı", f"{lezzet_puan:.1f}/5")
                k2.metric("🧼 Temizlik", f"{df_today['Puan_Hijyen'].mean():.1f}/5")
                k3.metric("Oy Sayısı", len(df_today))
                st.divider()
                if st.button("Günün Özetini Oku (AI)"):
                    with st.spinner("Hazırlanıyor..."):
                        yorum_listesi = [str(y) for y in df_today['Yorum'] if str(y).strip()]
                        if not yorum_listesi:
                            st.info("Yorum yok ustam.")
                        else:
                            text_data = "\n".join(yorum_listesi)
                            stats = f"Lezzet Puanı: {lezzet_puan:.1f}"
                            # Aşçılar için varsayılan olarak seçili modeli kullanmayalım, her zaman en hızlısı kalsın mı?
                            # Hayır, senin tercihinle orası da gemini-2.5-flash olsun.
                            ozet = analyze_comments_with_ai(text_data, stats, role="cook", model_name="gemini-2.5-flash")
                            st.info(ozet)
            else:
                st.info("Bugün veri yok.")
        else:
            st.warning("Sistemde veri yok.")

    elif pwd:
        st.error("Hatalı Şifre!")
