import os
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import select

from db.init_db import init_db
from db.connection import get_session
from db.models import User
from app.ui import dashboard, processos, prazos, andamentos, agendamentos, financeiro
from app.ui.theme import inject_global_css

load_dotenv()
init_db()

st.set_page_config(
    page_title="Sistema de Perícias",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()

DEFAULT_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "admin@local")


@st.cache_data(show_spinner=False)
def get_owner_user_id(default_email: str) -> int:
    with get_session() as s:
        user = (
            s.execute(select(User).where(User.email == default_email)).scalars().first()
        )
        if not user:
            raise RuntimeError(
                "Usuário default não encontrado. Rode: python -m db.init_db"
            )
        return user.id


try:
    owner_user_id = get_owner_user_id(DEFAULT_EMAIL)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

st.sidebar.markdown("## 🗂️ Sistema de Perícias")
st.sidebar.caption("MVP local • Alertas por e-mail • SQLite")
st.sidebar.divider()

menu = st.sidebar.radio(
    "Menu",
    ["Dashboard", "Processos", "Prazos", "Andamentos", "Agendamentos", "Financeiro"],
)

ROUTES = {
    "Dashboard": dashboard.render,
    "Processos": processos.render,
    "Prazos": prazos.render,
    "Andamentos": andamentos.render,
    "Agendamentos": agendamentos.render,
    "Financeiro": financeiro.render,
}

ROUTES[menu](owner_user_id)
