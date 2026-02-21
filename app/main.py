import os
import streamlit as st
from dotenv import load_dotenv

from db.init_db import init_db
from db.connection import get_session
from sqlalchemy import select

from db.models import User
from app.ui import dashboard, processos, prazos, andamentos, agendamentos, financeiro

load_dotenv()
init_db()

st.set_page_config(page_title="Sistema Perícias", layout="wide")
st.title("📁 Sistema de Perícias (MVP local)")

# MVP: sem login, pega usuário default
DEFAULT_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "admin@local")

with get_session() as s:
    user = s.execute(select(User).where(User.email == DEFAULT_EMAIL)).scalars().first()
    if not user:
        st.error("Usuário default não encontrado. Rode: python -m db.init_db")
        st.stop()
    owner_user_id = user.id

menu = st.sidebar.radio(
    "Menu",
    ["Dashboard", "Processos", "Prazos", "Andamentos", "Agendamentos", "Financeiro"],
)

if menu == "Dashboard":
    dashboard.render(owner_user_id)
elif menu == "Processos":
    processos.render(owner_user_id)
elif menu == "Prazos":
    prazos.render(owner_user_id)
elif menu == "Andamentos":
    andamentos.render(owner_user_id)
elif menu == "Agendamentos":
    agendamentos.render(owner_user_id)
elif menu == "Financeiro":
    financeiro.render(owner_user_id)
