import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import google.generativeai as genai
import re  # YENİ: Regex kütüphanesi eklendi

# --- AYARLAR VE BAĞLANTILAR ---
st.set_page_config(page_title="LezzetMetre", page_icon="🍽️", layout="centered")

# Google Sheets Bağlantısı
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client

# Gemini API
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- YENİLENEN PARÇALAMA FONKSİYONU ---
def parse_yemek_listesi(hucre_verisi):
    """Hücre içindeki alt alta yazılmış yemekleri listeye çevirir."""
    if not hucre_verisi:
        return []
    
    # 1. Veriyi string'e çevir (bazen sayı gelirse hata vermesin)
    text = str(hucre_verisi)
    
    # 2. Regex ile her türlü yeni satır karakterine göre böl (\n, \r\n, \r)
    # Bu yöntem "Alt+Enter"ı kesin yakalar.
    lines = re.split(r'[\r\n]+', text)
    
    # 3. Boşlukları temizle ve boş satırları at
    yemekler = [line.strip() for line in lines if line.strip()]
    
    return yemekler

def get_todays_menu():
    """Google Sheets'ten bugünün menüsünü çeker."""
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("aktif_menu")
    
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Bugünün tarihini bul (Format: 1.12.2025)
    bugun = datetime.now()
    tarih_format = f"{bugun.day}.{bugun.month}.{bugun.year}"
    
    # Tarih sütununu string yaparak ara (Excel format hatasını önler)
    df['TARİH'] = df['TARİH'].astype(str)
    
    gunluk_menu = df[df['TARİH'] == tarih_format]
    
    if gunluk_menu.empty:
        return None
    return gunluk_menu.iloc[0]

def save_feedback(data_list):
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("geribildirim")
    sheet.append_row(data_list)

# --- ARAYÜZ (UI) ---

page_mode = st.sidebar.radio("Mod", ["Öğrenci Ekranı", "Yönetici Paneli"])

if page_mode == "Öğrenci Ekranı":
    st.title("🍽️ LezzetMetre")
    
    # Tarih
    anlik_zaman = datetime.now()
    tarih_gosterim = anlik_zaman.strftime("%d.%m.%Y")
    st.info(f"📅 Tarih: **{tarih_gosterim}**")
    
    ogun = st.selectbox("Hangi öğün için oy veriyorsun?", 
                        ["Seçiniz...", "KAHVALTI", "ÖĞLE", "AKŞAM", "ARA ÖĞÜN"])
    
    if ogun != "Seçiniz...":
        menu_row = get_todays_menu()
        
        if menu_row is None:
            st.error("⚠️ Bugün için menü bulunamadı!")
            # Debug için: Eğer menü yoksa bugünün tarih formatını gösterelim
            st.caption(f"Sistem '{tarih_gosterim}' tarihini aradı.")
        else:
            with st.form("oylama_formu"):
                # --- AYIKLAMA İŞLEMİ BURADA YAPILIYOR ---
                raw_data = str(menu_row[ogun]) # Ham veri
                yemekler = parse_yemek_listesi(raw_data) # Ayıklanmış liste
                
                # Menüyü Ekrana Kart Olarak Bas (Görsel Kontrol)
                if ogun in ["ÖĞLE", "AKŞAM"]:
                    st.write("### 🍲 Menüde Ne Var?")
                    if yemekler:
                        for y in yemekler:
                            st.success(f"• {y}")
                    else:
                        st.warning("Menü listesi okunamadı.")
                
                # KAHVALTI / ARA ÖĞÜN (Basit)
                if ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    st.write(f"**{ogun}** değerlendirmesi:")
                    # Kahvaltı içeriğini sadece metin olarak göster
                    if yemekler:
                        st.text(", ".join(yemekler))
                    
                    puan_lezzet = st.slider("😋 Lezzet", 1, 5, 3)
                    puan_hijyen = st.slider("🧼 Hijyen", 1, 5, 3)
                    puan_servis = st.slider("💁‍♂️ Servis", 1, 5, 3)
                    begenilen, sikayet = "", ""

                # ÖĞLE / AKŞAM (Detaylı)
                else:
                    c1, c2, c3 = st.columns(3)
                    with c1: puan_lezzet = st.selectbox("😋 Lezzet", [1,2,3,4,5], index=2)
                    with c2: puan_hijyen = st.selectbox("🧼 Hijyen", [1,2,3,4,5], index=2)
                    with c3: puan_servis = st.selectbox("💁‍♂️ Servis", [1,2,3,4,5], index=2)
                    
                    st.write("---")
                    col_a, col_b = st.columns(2)
                    
                    # Yemek listesi doğru gelirse burada görünür
                    if yemekler:
                        with col_a:
                            begenilen = st.selectbox("🏆 En Beğendiğin?", ["Seçim Yok"] + yemekler)
                        with col_b:
                            sikayet = st.selectbox("👎 Sorunlu Olan?", ["Seçim Yok"] + yemekler)
                    else:
                        st.error("Yemek listesi ayrıştırılamadı!")
                        begenilen, sikayet = "Hata", "Hata"

                yorum = st.text_area("Yorumun:", placeholder="Düşüncelerin bizim için önemli...")
                submit = st.form_submit_button("GÖNDER 🚀")
                
                if submit:
                    if begenilen == "Seçim Yok": begenilen = ""
                    if sikayet == "Seçim Yok": sikayet = ""
                    
                    kayit = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tarih_gosterim, ogun, puan_lezzet, puan_hijyen, puan_servis, yorum, begenilen, sikayet]
                    save_feedback(kayit)
                    st.success("Kaydedildi!")

            # --- DEBUG ALANI (HATAYI GÖRMEK İÇİN) ---
            with st.expander("🛠️ Teknik Detaylar (Yönetici İçin)"):
                st.write("**Google Sheets'ten Gelen Ham Veri:**")
                st.code(raw_data) # Hücrenin içindeki gerçek veriyi gösterir
                st.write("**Python'ın Algıladığı Liste:**")
                st.write(yemekler)

elif page_mode == "Yönetici Paneli":
    st.header("🔐 Yönetici")
    if st.text_input("Şifre", type="password") == "admin123":
        st.success("Giriş yapıldı.")
