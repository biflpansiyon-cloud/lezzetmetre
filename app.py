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
    """Google hesabında tanımlı modelleri çeker."""
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

# --- GÖRSELLEŞTİRME FONKSİYONLARI (YENİ) ---

def display_colored_metric(label, value):
    """Puanı HTML ile renkli ve büyük gösterir."""
    # Renk Mantığı
    if value < 3.0:
        color = "#FF4B4B" # Kırmızı (Streamlit kırmızısı)
    elif value > 3.0:
        color = "#09AB3B" # Yeşil (Streamlit yeşili)
    else:
        color = "#FFA500" # Turuncu (Tam 3 ise)
    
    # HTML Kartı
    st.markdown(f"""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 2px 2px 5px rgba(0,0,0,0
