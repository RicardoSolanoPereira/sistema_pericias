from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from dotenv import load_dotenv
from sqlalchemy import select, update

from core.alertas_service import AlertasService
from core.email_service import send_email_smtp
from core.utils import now_br
from db.connection import get_session
from db.init_db import init_db
from db.models import Agendamento, User


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
@dataclass(frozen=True)
class AlertsConfig:
    enabled: bool
    due_days: int
    default_user_email: str


def load_alerts_config() -> AlertsConfig:
    enabled = os.getenv("ALERTS_ENABLED", "1").strip() == "1"
    due_days = int(os.getenv("ALERTS_DUE_DAYS", "3").strip())
    default_user_email = os.getenv("DEFAULT_USER_EMAIL", "admin@local").strip()

    return AlertsConfig(
        enabled=enabled,
        due_days=due_days,
        default_user_email=default_user_email,
    )


# ------------------------------------------------------------
# EMAIL BODY
# ------------------------------------------------------------
def montar_email_prazos(atrasados, vencendo, due_days: int) -> Tuple[str, str]:
    """
    Monta assunto+corpo com a parte de prazos.
    Agendamentos são anexados depois.
    """
    data_ref = now_br().strftime("%d/%m/%Y %H:%M")
    subject = f"[Perícias] Alertas de prazos - {data_ref}"

    lines: List[str] = []
    lines.append(f"Relatório automático ({data_ref})")
    lines.append("")

    if not atrasados and not vencendo:
        lines.append("✅ Nenhum prazo atrasado ou vencendo nos próximos dias.")
        lines.append("")
        lines.append("—")
        lines.append("Sistema de Perícias (MVP local)")
        return subject, "\n".join(lines)

    if atrasados:
        lines.append("🔴 PRAZOS ATRASADOS")
        for it in atrasados:
            lines.append(
                f"- ({it.prioridade}) {it.processo_numero} – {it.tipo_acao} | {it.evento} | "
                f"Venceu em {it.data_limite_br} | {it.dias_restantes} dias"
            )
        lines.append("")

    if vencendo:
        lines.append(f"🟠 PRAZOS VENCENDO EM ATÉ {due_days} DIAS")
        for it in vencendo:
            lines.append(
                f"- ({it.prioridade}) {it.processo_numero} – {it.tipo_acao} | {it.evento} | "
                f"Vence em {it.data_limite_br} | faltam {it.dias_restantes} dias"
            )
        lines.append("")

    lines.append("—")
    lines.append("Sistema de Perícias (MVP local)")
    return subject, "\n".join(lines)


def anexar_agendamentos_no_email(
    body: str,
    ag24_payload: List[tuple[int, str, str, object, str]],
    ag2_payload: List[tuple[int, str, str, object, str]],
) -> str:
    """
    payload: (ag_id, numero_processo, tipo, inicio(datetime), local)
    """
    if ag24_payload:
        body += "\n🔔 AGENDAMENTOS (JANELA 1)\n"
        for _, proc_num, tipo, inicio, local in ag24_payload:
            body += f"- {proc_num} – {tipo} | {inicio:%d/%m/%Y %H:%M} | {local}\n"

    if ag2_payload:
        body += "\n⏰ AGENDAMENTOS (JANELA 2)\n"
        for _, proc_num, tipo, inicio, local in ag2_payload:
            body += f"- {proc_num} – {tipo} | {inicio:%d/%m/%Y %H:%M} | {local}\n"

    return body


# ------------------------------------------------------------
# DB HELPERS
# ------------------------------------------------------------
def get_default_user_id(default_email: str) -> int:
    with get_session() as s:
        user = (
            s.execute(select(User).where(User.email == default_email)).scalars().first()
        )
        if not user:
            raise RuntimeError(
                "Usuário default não encontrado. Rode: python -m db.init_db"
            )
        return int(user.id)


def coletar_payloads(user_id: int, due_days: int):
    """
    Coleta tudo numa sessão e materializa o payload para uso fora.
    """
    with get_session() as s:
        atrasados, vencendo = AlertasService.coletar_prazos_alerta(
            s, owner_user_id=user_id, due_days=due_days
        )

        ag_24h, ag_2h = AlertasService.coletar_agendamentos_alerta(
            s, owner_user_id=user_id
        )

        ag24_payload = [
            (
                int(ag.id),
                str(proc.numero_processo),
                str(ag.tipo),
                ag.inicio,
                (ag.local or "-"),
            )
            for ag, proc in ag_24h
        ]
        ag2_payload = [
            (
                int(ag.id),
                str(proc.numero_processo),
                str(ag.tipo),
                ag.inicio,
                (ag.local or "-"),
            )
            for ag, proc in ag_2h
        ]

    return atrasados, vencendo, ag24_payload, ag2_payload


def marcar_flags_enviadas(
    ag24_ids: Iterable[int],
    ag2_ids: Iterable[int],
) -> None:
    ag24_ids = list(ag24_ids)
    ag2_ids = list(ag2_ids)

    if not ag24_ids and not ag2_ids:
        return

    with get_session() as s:
        if ag24_ids:
            s.execute(
                update(Agendamento)
                .where(Agendamento.id.in_(ag24_ids))
                .values(alerta_24h_enviado=True)
            )

        if ag2_ids:
            s.execute(
                update(Agendamento)
                .where(Agendamento.id.in_(ag2_ids))
                .values(alerta_2h_enviado=True)
            )

        s.commit()


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main() -> None:
    load_dotenv()
    init_db()

    cfg = load_alerts_config()

    if not cfg.enabled:
        print("ALERTS_ENABLED != 1; abortando.")
        return

    user_id = get_default_user_id(cfg.default_user_email)

    atrasados, vencendo, ag24_payload, ag2_payload = coletar_payloads(
        user_id=user_id,
        due_days=cfg.due_days,
    )

    if not atrasados and not vencendo and not ag24_payload and not ag2_payload:
        print("Sem alertas hoje.")
        return

    subject, body = montar_email_prazos(atrasados, vencendo, cfg.due_days)
    body = anexar_agendamentos_no_email(body, ag24_payload, ag2_payload)

    # envio
    send_email_smtp(subject, body)
    print("E-mail de alertas enviado com sucesso.")

    # marca flags
    ag24_ids = [ag_id for ag_id, *_ in ag24_payload]
    ag2_ids = [ag_id for ag_id, *_ in ag2_payload]
    marcar_flags_enviadas(ag24_ids, ag2_ids)


if __name__ == "__main__":
    main()
