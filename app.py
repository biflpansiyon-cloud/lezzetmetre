import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import google.generativeai as genai

# --- AYARLAR VE BAĞLANTILAR ---
st.set_page_config(page_title="LezzetMetre", page_icon="🍽️", layout="centered")

# Google Sheets Bağlantısı (Secrets'tan okur)
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client

# Gemini API Bağlantısı
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- YARDIMCI FONKSİYONLAR ---

def get_todays_menu():
    """Google Sheets'ten bugünün menüsünü çeker ve parse eder."""
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("aktif_menu")
    
    # Tüm veriyi çek
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # Bugünün tarihini bul (Senin formatın: 1.12.2025 - gün.ay.yıl)
    # Excel'den gelen tarih bazen string bazen datetime olabilir, garantiye alalım:
    today_str = datetime.now().strftime("%-d.%m.%Y") # Linux/Mac için %-d, Windows için %#d gerekebilir.
    # Garanti yöntem: String karşılaştırması yerine datetime objesine çevirip bakalım.
    
    # Basit eşleşme deneyelim, senin formatına göre:
    bugun = datetime.now()
    tarih_format = f"{bugun.day}.{bugun.month}.{bugun.year}" # Örn: 1.12.2025 veya 28.11.2025
    
    # Menüde bugünü bul
    gunluk_menu = df[df['TARİH'] == tarih_format]
    
    if gunluk_menu.empty:
        return None
    
    return gunluk_menu.iloc[0]

def parse_yemek_listesi(hucre_verisi):
    """Hücre içindeki alt alta yazılmış yemekleri listeye çevirir."""
    if not hucre_verisi:
        return []
    # Alt+Enter (\n) karakterine göre böl ve boşlukları temizle
    yemekler = [y.strip() for y in hucre_verisi.split('\n') if y.strip()]
    return yemekler

def save_feedback(data_list):
    """Geri bildirimi kaydeder."""
    client = get_google_sheet_client()
    sheet = client.open("Pansiyon_Yemek_DB").worksheet("geribildirim")
    sheet.append_row(data_list)

# --- ARAYÜZ (UI) ---

# Mod Seçimi (URL parametresi ile gizlenebilir, şimdilik sidebar)
page_mode = st.sidebar.radio("Mod", ["Öğrenci Ekranı", "Yönetici Paneli"])

if page_mode == "Öğrenci Ekranı":
    st.title("🍽️ LezzetMetre")
    st.subheader("Pansiyon Yemek Değerlendirme Sistemi")
    
    # Tarih Bilgisi (Değiştirilemez)
    anlik_zaman = datetime.now()
    tarih_gosterim = anlik_zaman.strftime("%d.%m.%Y")
    st.info(f"📅 Tarih: **{tarih_gosterim}**")
    
    # Öğün Seçimi
    ogun = st.selectbox("Hangi öğün için oy veriyorsun?", 
                        ["Seçiniz...", "KAHVALTI", "ÖĞLE", "AKŞAM", "ARA ÖĞÜN"])
    
    if ogun != "Seçiniz...":
        menu_row = get_todays_menu()
        
        if menu_row is None:
            st.error("⚠️ Bugün için menü planı bulunamadı! Lütfen idareye bildir.")
        else:
            # --- FORM BAŞLANGICI ---
            with st.form("oylama_formu"):
                
                # 1. KAHVALTI VE ARA ÖĞÜN (BASİT MOD)
                if ogun in ["KAHVALTI", "ARA ÖĞÜN"]:
                    st.write(f"Afiyet olsun! **{ogun}** nasıldı?")
                    # Menü içeriğini sadece bilgi olarak göster, seçim yaptırma
                    yemekler = parse_yemek_listesi(str(menu_row[ogun]))
                    if yemekler:
                        st.markdown(f"**Menü:** {', '.join(yemekler)}")
                    
                    puan_lezzet = st.slider("😋 Lezzet Puanın", 1, 5, 3)
                    puan_hijyen = st.slider("🧼 Temizlik/Hijyen Puanın", 1, 5, 3)
                    puan_servis = st.slider("💁‍♂️ Servis/Personel Puanın", 1, 5, 3)
                    
                    begenilen = ""
                    sikayet = ""
                    
                # 2. ÖĞLE VE AKŞAM (DETAYLI MOD)
                else:
                    # Menüyü çek ve ayrıştır
                    yemekler = parse_yemek_listesi(str(menu_row[ogun]))
                    
                    if not yemekler:
                        st.warning("Bu öğün için menü girilmemiş görünüyor.")
                    
                    st.write("### Genel Değerlendirme")
                    c1, c2, c3 = st.columns(3)
                    with c1: puan_lezzet = st.selectbox("😋 Lezzet", [1,2,3,4,5], index=2)
                    with c2: puan_hijyen = st.selectbox("🧼 Hijyen", [1,2,3,4,5], index=2)
                    with c3: puan_servis = st.selectbox("💁‍♂️ Servis", [1,2,3,4,5], index=2)
                    
                    st.write("### Yemek Bazlı Yorum (Opsiyonel)")
                    # Yemekleri seçenek olarak sun
                    if yemekler:
                        begenilen = st.selectbox("En beğendiğin yemek hangisiydi?", ["Seçim Yok"] + yemekler)
                        sikayet = st.selectbox("Hangi yemekte sorun vardı?", ["Seçim Yok"] + yemekler)
                    else:
                        begenilen = "Listelenmedi"
                        sikayet = "Listelenmedi"

                # ORTAK ALAN: YORUM
                yorum = st.text_area("Varsa notun/önerin:", placeholder="Örn: Tuz çok azdı, elinize sağlık...")
                
                # GÖNDER BUTONU
                submit = st.form_submit_button("Görüşünü Gönder 🚀")
                
                if submit:
                    # Veriyi hazırla
                    zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Seçim Yok ise boş gönder
                    if begenilen == "Seçim Yok": begenilen = ""
                    if sikayet == "Seçim Yok": sikayet = ""
                    
                    kayit_verisi = [
                        zaman_damgasi,
                        tarih_gosterim,
                        ogun,
                        puan_lezzet,
                        puan_hijyen,
                        puan_servis,
                        yorum,
                        begenilen,
                        sikayet
                    ]
                    
                    # Sheet'e kaydet
                    save_feedback(kayit_verisi)
                    st.success("Görüşün alındı! Teşekkürler.")

# --- YÖNETİCİ KISMI (ŞİMDİLİK BOŞ) ---
elif page_mode == "Yönetici Paneli":
    st.header("🔐 Yönetici Girişi")
    pwd = st.text_input("Şifre", type="password")
    if pwd == "admin123": # Şifreyi sonra secrets'a alırız
        st.success("Giriş Başarılı")
        st.write("Analiz ekranı yakında burada olacak...")
