import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import google.generativeai as genai
import re

# --- AYARLAR VE BAĞLANTILAR ---
st.set_page_config(page_title="LezzetMetre", page_icon="🍽️", layout="centered")

# Google Sheets Bağlantısı
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client

# Gemini API Bağlantısı
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- YARDIMCI FONKSİYONLAR ---

def parse_yemek_listesi(hucre_verisi):
    """Metin halindeki listeyi düzgün bir Python listesine çevirir."""
    if not hucre_verisi:
        return []
    
    text = str(hucre_verisi)
    # Her türlü satır sonu karakterine göre böl (Regex)
    lines = re.split(r'[\r\n]+', text)
    # Boşlukları temizle
    yemekler = [line.strip() for line in lines if line.strip()]
    return yemekler

def get_todays_menu():
    """Google Sheets'ten bugünün menüsünü 4 SATIRLIK BLOK mantığıyla çeker."""
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("aktif_menu")
    
    # Tüm veriyi ham liste olarak çek (Merged hücreler için en sağlıklısı)
    all_values = sheet.get_all_values()
    
    # Bugünün tarihini hazırla (Örn: 1.12.2025 veya 01.12.2025)
    now = datetime.now()
    bugun = f"{now.day}.{now.month}.{now.year}"
    
    target_row_index = -1
    
    # 1. TARİHİ BUL
    for i, row in enumerate(all_values):
        # row[0] -> Tarih sütunu
        # Excel'den gelen string bazen boşluklu olabilir, strip() ile temizle
        if row[0].strip() == bugun:
            target_row_index = i
            break
            
    if target_row_index == -1:
        return None

    # 2. 4 SATIRLIK BLOĞU OKU
    # Tablo yapısına göre: Tarih satırı ve altındaki 3 satır (Toplam 4)
    limit = min(target_row_index + 4, len(all_values))
    
    # Kahvaltı (C sütunu - index 2) ve Ara Öğün (F sütunu - index 5)
    # Bunlar merged olduğu için sadece ilk satırı alırız.
    kahvalti_raw = all_values[target_row_index][2]
    ara_ogun_raw = all_values[target_row_index][5]
    
    ogle_listesi = []
    aksam_listesi = []
    
    # Öğle (D - index 3) ve Akşam (E - index 4) için 4 satırı da tara
    for r in range(target_row_index, limit):
        val_ogle = all_values[r][3].strip()
        if val_ogle:
            ogle_listesi.append(val_ogle)
            
        val_aksam = all_values[r][4].strip()
        if val_aksam:
            aksam_listesi.append(val_aksam)

    return {
        "KAHVALTI": kahvalti_raw,
        "ÖĞLE": "\n".join(ogle_listesi),
        "AKŞAM": "\n".join(aksam_listesi),
        "ARA ÖĞÜN": ara_ogun_raw
    }

def save_feedback(data_list):
    """Veriyi Google Sheets'e kaydeder."""
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("geribildirim")
    sheet.append_row(data_list)

# --- ARAYÜZ (UI) ---

# Mod seçimi (Sidebar)
page_mode = st.sidebar.radio("Sistem Modu", ["Öğrenci Ekranı", "Yönetici Paneli"])

if page_mode == "Öğrenci Ekranı":
    st.title("🍽️ LezzetMetre")
    st.subheader("Pansiyon Yemek Değerlendirme")
    
    # Tarih Gösterimi
    anlik_zaman = datetime.now()
    tarih_gosterim = anlik_zaman.strftime("%d.%m.%Y")
    st.info(f"📅 Tarih: **{tarih_gosterim}**")
    
    # Öğün Seçimi
    ogun = st.selectbox("Hangi öğün için oy veriyorsun?", 
                        ["Seçiniz...", "KAHVALTI", "ÖĞLE", "AKŞAM", "ARA ÖĞÜN"])
    
    if ogun != "Seçiniz...":
        menu_data = get_todays_menu()
        
        if menu_data is None:
            st.error(f"⚠️ {tarih_gosterim} tarihi için menü bulunamadı.")
            st.caption("Lütfen idare ile iletişime geçin.")
        else:
            # Seçilen öğünün verisini çek
            raw_menu_text = menu_data.get(ogun, "")
            yemekler = parse_yemek_listesi(raw_menu_text)
            
            with st.form("oylama_formu"):
                
                # --- MENÜ GÖSTERİMİ ---
                if ogun in ["ÖĞLE", "AKŞAM"]:
                    st.markdown("### 🍲 Menüde Ne Var?")
                    if yemekler:
                        for y in yemekler:
                            st.success(f"• {y}")
                    else:
                        st.warning("Menü bilgisi boş.")
                
                elif ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    st.markdown(f"**{ogun} İçeriği:**")
                    if yemekler:
                        st.info(", ".join(yemekler))
                
                st.write("---")
                
                # --- PUANLAMA ALANI ---
                # Kahvaltı/Ara Öğün için basit slider, diğerleri için detaylı seçim
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
                    
                    # Yemek seçimi (Sadece öğle/akşam)
                    if yemekler:
                        st.write("#### Detaylar (Opsiyonel):")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            begenilen = st.selectbox("🏆 En Beğendiğin?", ["Seçim Yok"] + yemekler)
                        with col_b:
                            sikayet = st.selectbox("👎 Sorunlu Olan?", ["Seçim Yok"] + yemekler)
                    else:
                        begenilen, sikayet = "", ""

                # --- YORUM ALANI ---
                yorum = st.text_area("Eklemek istediklerin:", placeholder="Fikrin bizim için değerli...")
                
                # --- GÖNDER ---
                submit = st.form_submit_button("GÖNDER 🚀")
                
                if submit:
                    if begenilen == "Seçim Yok": begenilen = ""
                    if sikayet == "Seçim Yok": sikayet = ""
                    
                    # Veri paketi
                    kayit = [
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tarih_gosterim,
                        ogun,
                        puan_lezzet,
                        puan_hijyen,
                        puan_servis,
                        yorum,
                        begenilen,
                        sikayet
                    ]
                    
                    save_feedback(kayit)
                    st.balloons()
                    st.success("Görüşün başarıyla kaydedildi! Teşekkürler.")

elif page_mode == "Yönetici Paneli":
    st.header("🔐 Yönetici Paneli")
    pwd = st.text_input("Şifre", type="password")
    if pwd == "admin123":
        st.success("Giriş Başarılı.")
        st.write("Raporlama modülü bir sonraki güncellemede aktif olacak.")
