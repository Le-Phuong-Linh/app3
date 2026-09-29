import streamlit as st
import os
import re
import shutil
import time
from google import genai

# =====================================================
# TRANSLATION PROMPT
# =====================================================

SYSTEM_PROMPT = """You are a professional literary translator from Chinese to Russian.
Your single task is to translate the title of a web novel chapter into fluent, natural, and dramatic Russian suitable for a book title.

CRITICAL RULES:
1. Translate ONLY the core text title.
2. Do NOT include chapter numbers, the word "Глава", or file extensions in your translation.
3. Ignore and completely strip any trailing part/update markers like "（2更）", "(1)", "（上）", "（完）" from the core translation.
4. Output ONLY the raw Russian translation of the text. No quotes, no markdown formatting, no punctuation at the end.

Examples:
Input: 我是破鞋
Output: Я распутная женщина

Input: 不妨坦然迎接失败！
Output: Почему бы не встретить неудачу спокойно и достойно!

Input: 母校演讲
Output: Выступление в альма-матер
"""

def parse_part_marker(title_text):
    match_cn = re.search(r'[\(\（]([一二三四五六七八九十]+)[\)\）]', title_text)
    if match_cn:
        cn_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        part_num = cn_map.get(match_cn.group(1), None)
        clean_title = re.sub(r'[\(\（][一二三四五六七八九十]+[\)\）]', '', title_text)
        return clean_title.strip(), part_num

    match_num = re.search(r'[\(\（]([1-9])[\)\）\保存]', title_text)
    if match_num:
        clean_title = re.sub(r'[\(\（][1-9][\)\）\保存]', '', title_text)
        return clean_title.strip(), int(match_num.group(1))
        
    match_geng = re.search(r'[\(\（]([1-9])更[\)\）\筋]', title_text)
    if match_geng:
        clean_title = re.sub(r'[\(\開][1-9]更[\)\）\筋]', '', title_text)
        return clean_title.strip(), int(match_geng.group(1))
        
    if '（上）' in title_text or '(上)' in title_text:
        clean_title = title_text.replace('（上）', '').replace('(上)', '')
        return clean_title.strip(), 1
    if '（中）' in title_text or '(中)' in title_text:
        clean_title = title_text.replace('（中）', '').replace('(中)', '')
        return clean_title.strip(), 2
    if '（下）' in title_text or '(下)' in title_text:
        clean_title = title_text.replace('（下）', '').replace('(下)', '')
        return clean_title.strip(), 3
        
    clean_title = re.sub(r'[\(\（]完[\)\）\结构]', '', title_text)
    return clean_title.strip(), None

def translate_title_with_gemini(client, model_name, chinese_title):
    prompt_content = f"{SYSTEM_PROMPT}\n\nInput: {chinese_title}"
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_content
            )
            if response and response.text:
                result = response.text.strip().replace('*', '').replace('"', '')
                result = re.sub(r'[\s\\/:*?"<>|]+', ' ', result).strip()
                # Небольшая пауза между успешными запросами, чтобы уберечься от лимитов
                time.sleep(1.0)
                return result
        except Exception as e:
            if "503" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_retries - 1:
                    time.sleep(3 * (attempt + 1)) # Увеличиваем паузу при каждой ошибке
                    continue
            st.error(f"Ошибка Gemini для заголовка '{chinese_title}': {e}")
            break
    return None

def process_translation(target_dir, api_key, model_name, status_container):
    if not api_key:
        status_container.error("Пожалуйста, введите ваш Gemini API Key!")
        return False

    client = genai.Client(api_key=api_key)

    filename_pattern = re.compile(r'^(\d+)_(.*)$')
    try:
        all_files = os.listdir(target_dir)
    except Exception:
        status_container.error("Error reading directory.")
        return False

    matched_files = []
    for f in all_files:
        match = filename_pattern.match(f)
        if match:
            matched_files.append((int(match.group(1)), match.group(2), f))
            
    if not matched_files:
        status_container.error("No valid files matching the 'XXXX_...' format found.")
        return False

    matched_files.sort(key=lambda x: x[0])
    total_files = len(matched_files)
    status_container.write(f"Found {total_files} files to translate...")

    progress_bar = st.progress(0)
    rename_count = 0

    for idx, (ch_num, raw_title, old_filename) in enumerate(matched_files, 1):
        title_core, ext = os.path.splitext(raw_title)
        if not ext:
            ext = ".txt"
            
        clean_chinese_title, part_num = parse_part_marker(title_core)
        if not clean_chinese_title:
            clean_chinese_title = title_core

        status_container.text(f"[{idx}/{total_files}] Translating: {clean_chinese_title}...")
        
        russian_title = translate_title_with_gemini(client, model_name, clean_chinese_title)
        
        if not russian_title:
            continue
            
        if part_num:
            new_filename = f"Глава {ch_num}. {russian_title} Часть {part_num}{ext}"
        else:
            new_filename = f"Глава {ch_num}. {russian_title}{ext}"
            
        old_filepath = os.path.join(target_dir, old_filename)
        new_filepath = os.path.join(target_dir, new_filename)
        
        if os.path.exists(new_filepath) and old_filepath != new_filepath:
            continue
            
        try:
            os.rename(old_filepath, new_filepath)
            rename_count += 1
        except Exception:
            pass
            
        progress_bar.progress(idx / total_files)

    status_container.success(f"All operations complete! Successfully translated and renamed {rename_count} files.")
    return True

# =====================================================
# STREAMLIT UI
# =====================================================

st.title("🌐 Gemini Chapter Filename Translator")
st.write("Upload your chapter text files to automatically translate Chinese titles into dramatic Russian book chapters via Gemini.")

api_key_input = st.text_input("Gemini API Key", type="password", value="")
model_input = st.text_input("Gemini Model Name", value="gemini-3-flash-preview")

uploaded_files = st.file_uploader("Upload chapter .txt files", accept_multiple_files=True, type=["txt"])

if uploaded_files:
    os.makedirs("input", exist_ok=True)
    for uploaded_file in uploaded_files:
        with open(os.path.join("input", uploaded_file.name), "wb") as f:
            f.write(uploaded_file.getbuffer())
    st.success(f"Successfully loaded {len(uploaded_files)} files ready for translation!")

if st.button("Start Filename Translation"):
    status_box = st.empty()
    success = process_translation("input", api_key_input, model_input, status_box)
    
    if success:
        shutil.make_archive("translated_filenames_output", 'zip', "input")
        with open("translated_filenames_output.zip", "rb") as fp:
            st.download_button(
                label="📦 Download Translated Files ZIP",
                data=fp,
                file_name="translated_chapters.zip",
                mime="application/zip"
            )
