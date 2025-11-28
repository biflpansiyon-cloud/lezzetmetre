import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, time
import google.generativeai as genai
import re
import pytz # Saat dilimi için gerekli

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

def get_turkey_time():
    """Sunucu saati ne olursa olsun Türkiye saatini döndürür."""
    utc_now = datetime.now(pytz.utc)
    turkey_tz = pytz.timezone('Europe/Istanbul')
    return utc_now.astimezone(turkey_tz)

def get_active_meal(current_time):
    """Şu anki saate göre aktif öğünü belirler."""
    # Saat aralıkları (Senin verdiğin kurallar)
    
    # Kahvaltı: 07:00 - 08:20
    if time(7, 0) <= current_time <= time(8, 20):
        return "KAHVALTI"
    
    # Öğle: 12:00 - 14:30
    elif time(12, 0) <= current_time <= time(14, 30):
        return "ÖĞLE"
    
    # Akşam: 18:00 - 19:00
    elif time(18, 0) <= current_time <= time(19, 0):
        return "AKŞAM"
    
    # Ara Öğün: 21:15 - 22:00
    elif time(21, 15) <= current_time <= time(22, 0):
        return "ARA ÖĞÜN"
    
    else:
        return None # Hiçbir aralıkta değilse

def get_available_gemini_models():
    try:
        model_list = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                clean_name = m.name.split("/")[-1]
                model_list.append(clean_name)
        return sorted(model_list, reverse=True)
    except:
        return ["gemini-2.5-flash", "gemini-1.5-flash"]

def parse_yemek_listesi(hucre_verisi):
    if not hucre_verisi: return []
    text = str(hucre_verisi)
    lines = re.split(r'[\r\n]+', text)
    return [line.strip() for line in lines if line.strip()]

def get_todays_menu():
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("aktif_menu")
    all_values = sheet.get_all_values()
    
    # Türkiye saatine göre tarihi al
    now = get_turkey_time()
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

def save_ai_log(scope, role, model, report_text):
    try:
        client = get_google_sheet_client()
        sheet = client.open("Pansiyon_Yemek_DB").worksheet("ai_arsiv")
        timestamp = get_turkey_time().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([timestamp, scope, role, model, report_text])
    except Exception as e:
        st.error(f"Arşivleme Hatası: {e}")

def get_ai_logs():
    try:
        client = get_google_sheet_client()
        sheet = client.open("Pansiyon_Yemek_DB").worksheet("ai_arsiv")
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def analyze_comments_with_ai(comments_text, stats_text, role="admin", model_name="gemini-2.5-flash"):
    try:
        model = genai.GenerativeModel(model_name)
    except:
        model = genai.GenerativeModel('gemini-1.5-flash')

    if role == "cook":
        prompt = f"""
        Sen bir mutfak şefisin. Verileri ekibine aktarıyorsun.
        İSTATİSTİKLER: {stats_text}
        ÖĞRENCİ YORUMLARI: {comments_text}
        GÖREVİN: "Ustam" diye hitap eden, kısa, samimi, paragraf şeklinde konuşma hazırla. İyileri öv, kötüleri yapıcı uyar.
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
        return f"⚠️ Hata: {str(e)}"

def display_colored_metric(label, value):
    if value < 3.0: color = "#FF4B4B"
    elif value > 3.0: color = "#09AB3B"
    else: color = "#FFA500"
    html_code = f"""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
        <p style="font-size: 16px; margin-bottom: 5px; color: #555; font-weight: bold;">{label}</p>
        <h1 style="color: {color}; font-size: 45px; margin: 0; font-weight: 800;">{value:.1f}</h1>
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)

def color_dataframe_cells(val):
    if isinstance(val, (int, float)):
        if val < 3: return 'color: #FF4B4B; font-weight: bold'
        elif val > 3: return 'color: #09AB3B; font-weight: bold'
        else: return 'color: #FFA500; font-weight: bold'
    return ''

# --- ARAYÜZ (UI) ---

page_mode = st.sidebar.radio("Sistem Modu", ["Öğrenci Ekranı", "Yönetici Paneli"])

# --------------------------
# 🎓 ÖĞRENCİ EKRANI (ZAMAN AYARLI)
# --------------------------
if page_mode == "Öğrenci Ekranı":
    st.title("🍽️ LezzetMetre")
    
    # Türkiye Saatini Al
    anlik_tr = get_turkey_time()
    tarih_gosterim = anlik_tr.strftime("%d.%m.%Y")
    saat_gosterim = anlik_tr.strftime("%H:%M")
    
    st.info(f"📅 Tarih: **{tarih_gosterim}** | 🕒 Saat: **{saat_gosterim}**")
    
    # Aktif Öğünü Otomatik Belirle
    aktif_ogun = get_active_meal(anlik_tr.time())
    
    # EĞER AKTİF BİR YEMEK SAATİNDEYSEK
    if aktif_ogun:
        st.success(f"🍽️ Şu an **{aktif_ogun}** değerlendirmesi açık.")
        
        # Öğün adını değişkene atıyoruz (Eskiden selectbox'tan geliyordu)
        ogun = aktif_ogun 
        
        menu_data = get_todays_menu()
        if menu_data is None:
            st.error(f"⚠️ {tarih_gosterim} tarihi için menü planı bulunamadı.")
            st.caption("İdare ile görüşünüz.")
        else:
            raw_menu_text = menu_data.get(ogun, "")
            yemekler = parse_yemek_listesi(raw_menu_text)
            
            with st.form("oylama_formu"):
                # Menü Gösterimi
                if ogun in ["ÖĞLE", "AKŞAM"]:
                    st.markdown("### 🍲 Menüde Ne Var?")
                    if yemekler:
                        for y in yemekler: st.success(f"• {y}")
                    else: st.warning("Menü bilgisi girilmemiş.")
                elif ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    st.markdown(f"**{ogun} İçeriği:**")
                    if yemekler: st.info(", ".join(yemekler))
                
                st.write("---")
                
                # Puanlama
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
                    # Kayıt zamanı da TR saati olsun
                    zaman_damgasi = anlik_tr.strftime("%Y-%m-%d %H:%M:%S")
                    
                    kayit = [zaman_damgasi, tarih_gosterim, ogun, puan_lezzet, puan_hijyen, puan_servis, yorum, begenilen, sikayet]
                    save_feedback(kayit)
                    st.balloons()
                    st.success("Görüşün başarıyla kaydedildi! Teşekkürler.")

    # EĞER YEMEK SAATİ DEĞİLSE
    else:
        st.warning("⛔ **Şu an aktif bir yemek saati değil.**")
        st.markdown("""
        Değerlendirme ekranı sadece yemek saatlerinde otomatik olarak açılır.
        
        **Yemek Saatleri:**
        * 🍳 **Kahvaltı:** 07:00 - 08:20
        * 🍲 **Öğle:** 12:00 - 14:30
        * 🥗 **Akşam:** 18:00 - 19:00
        * 🍪 **Ara Öğün:** 21:15 - 22:00
        """)

# --------------------------
# 🔐 YÖNETİCİ PANELİ (7/24 AÇIK)
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
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("🤖 AI Model Seçimi")
        available_models = get_available_gemini_models()
        target_default = "gemini-2.5-flash"
        default_index = 0
        if target_default in available_models:
            default_index = available_models.index(target_default)
        selected_model = st.sidebar.selectbox("Aktif Model", available_models, index=default_index)
        st.sidebar.success(f"Seçili: **{selected_model}**")

        if not df.empty:
            filtre_secenekleri = ["Bugün", "Son 7 Gün", "Son 30 Gün", "Son 6 Ay", "Tüm Kayıtlar"]
            filtre_tarih = st.radio("Zaman Aralığı", filtre_secenekleri, horizontal=True)
            
            now = datetime.now()
            if filtre_tarih == "Bugün":
                df_filtered = df[df['Zaman'].dt.date == now.date()]
            elif filtre_tarih == "Son 7 Gün":
                df_filtered = df[df['Zaman'] >= (now - timedelta(days=7))]
            elif filtre_tarih == "Son 30 Gün":
                df_filtered = df[df['Zaman'] >= (now - timedelta(days=30))]
            elif filtre_tarih == "Son 6 Ay":
                df_filtered = df[df['Zaman'] >= (now - timedelta(days=180))]
            else:
                df_filtered = df
            
            st.markdown(f"### 📈 Genel Bakış ({filtre_tarih})")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                html_total = f"""
                <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
                    <p style="font-size: 16px; margin-bottom: 5px; color: #555; font-weight: bold;">Toplam Oy</p>
                    <h1 style="color: #333; font-size: 45px; margin: 0; font-weight: 800;">{len(df_filtered)}</h1>
                </div>
                """
                st.markdown(html_total, unsafe_allow_html=True)
            with c2: display_colored_metric("Lezzet", df_filtered['Puan_Lezzet'].mean())
            with c3: display_colored_metric("Hijyen", df_filtered['Puan_Hijyen'].mean())
            with c4: display_colored_metric("Servis", df_filtered['Puan_Servis'].mean())
            st.divider()
            
            tab1, tab2, tab3, tab4 = st.tabs(["🤖 AI Rapor", "📈 Grafikler", "📝 Veriler", "🗄️ Rapor Arşivi"])
            with tab1:
                if st.button("Rapor Oluştur ve Arşivle"):
                    with st.spinner("Analiz ediliyor..."):
                        yorum_listesi = [str(y) for y in df_filtered['Yorum'] if str(y).strip()]
                        if not yorum_listesi:
                            st.warning("Yorum yok.")
                        else:
                            text_data = "\n".join(yorum_listesi)
                            stats = f"Lezzet: {df_filtered['Puan_Lezzet'].mean():.1f}"
                            analiz = analyze_comments_with_ai(text_data, stats, role="admin", model_name=selected_model)
                            st.markdown(analiz)
                            save_ai_log(scope=filtre_tarih, role="admin", model=selected_model, report_text=analiz)
                            st.success("Arşivlendi!")
            with tab2:
                st.bar_chart(df_filtered[['Puan_Lezzet', 'Puan_Hijyen', 'Puan_Servis']].mean())
                if 'Begenilen_Yemek' in df_filtered.columns:
                    st.write("En Beğenilenler:")
                    st.bar_chart(df_filtered['Begenilen_Yemek'].value_counts().head(5))
            with tab3:
                st.write("Düşük puanlar kırmızı, yüksek puanlar yeşil görünür.")
                st.dataframe(df_filtered.style.map(color_dataframe_cells, subset=['Puan_Lezzet', 'Puan_Hijyen', 'Puan_Servis']))
            with tab4:
                st.subheader("🗄️ Geçmiş AI Raporları")
                arsiv_df = get_ai_logs()
                if not arsiv_df.empty:
                    arsiv_df = arsiv_df.sort_values(by="Zaman", ascending=False)
                    for index, row in arsiv_df.iterrows():
                        with st.expander(f"{row['Zaman']} - {row['Kapsam']} ({row['Role']})"):
                            st.caption(f"Model: {row['Model']}")
                            st.markdown(row['Rapor_Icerigi'])
                else:
                    st.info("Arşiv boş.")
        else:
            st.warning("Veri yok.")

    # --- ROL: AŞÇI ---
    elif pwd == CHEF_PWD:
        st.title("👨‍🍳 Mutfak Ekibi Paneli")
        if not df.empty:
            now = datetime.now()
            df_today = df[df['Zaman'].dt.date == now.date()]
            if not df_today.empty:
                st.subheader(f"📅 Bugünün ({now.strftime('%d.%m.%Y')}) Karnesi")
                k1, k2, k3 = st.columns(3)
                with k1: display_colored_metric("😋 Lezzet", df_today['Puan_Lezzet'].mean())
                with k2: display_colored_metric("🧼 Temizlik", df_today['Puan_Hijyen'].mean())
                with k3: 
                    html_chef_total = f"""
                    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
                        <p style="font-size: 16px; margin-bottom: 5px; color: #555; font-weight: bold;">Oy Sayısı</p>
                        <h1 style="color: #333; font-size: 45px; margin: 0; font-weight: 800;">{len(df_today)}</h1>
                    </div>
                    """
                    st.markdown(html_chef_total, unsafe_allow_html=True)
                st.divider()
                if st.button("Günün Özetini Oku (AI)"):
                    with st.spinner("Hazırlanıyor..."):
                        yorum_listesi = [str(y) for y in df_today['Yorum'] if str(y).strip()]
                        if not yorum_listesi:
                            st.info("Yorum yok ustam.")
                        else:
                            text_data = "\n".join(yorum_listesi)
                            stats = f"Lezzet Puanı: {df_today['Puan_Lezzet'].mean():.1f}"
                            ozet = analyze_comments_with_ai(text_data, stats, role="cook", model_name="gemini-2.5-flash")
                            st.info(ozet)
                            save_ai_log(scope="Bugün", role="cook", model="gemini-2.5-flash", report_text=ozet)
            else:
                st.info("Bugün veri yok.")
        else:
            st.warning("Sistemde veri yok.")

    elif pwd:
        st.error("Hatalı Şifre!")
