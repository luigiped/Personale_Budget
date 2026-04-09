import streamlit as st
import base64
import os

def get_base64_of_bin_file(bin_file):
    if not os.path.exists(bin_file):
        return ""
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def render_glow_icon(image_path, width=100):
    img_base64 = get_base64_of_bin_file(image_path)
    if not img_base64:
        st.error(f"Immagine non trovata in: {image_path}")
        return

    st.markdown(f"""
        <style>
        .icon-container {{
            display: flex; justify-content: center;
            align-items: center; padding: 10px;
        }}
        .glow-img {{
            width: {width}px; border-radius: 20px;
            filter: drop-shadow(0 0 15px rgba(0, 209, 255, 0.6));
        }}
        </style>
        <div class="icon-container">
            <img class="glow-img" src="data:image/png;base64,{img_base64}">
        </div>
    """, unsafe_allow_html=True)