Set-Location "$PSScriptRoot\..\frontend"
$env:FLETES_API_URL = "http://127.0.0.1:8000/api/v1"
streamlit run streamlit_app.py
