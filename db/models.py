from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .connection import Base


# ------------------------------------------------------------
# USERS
# ------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    processos: Mapped[list["Processo"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )


# ------------------------------------------------------------
# PROCESSOS
# ------------------------------------------------------------
class Processo(Base):
    __tablename__ = "processos"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "numero_processo", name="uq_owner_numero"),
        Index("ix_processos_owner_status", "owner_user_id", "status"),
        Index("ix_processos_owner_papel", "owner_user_id", "papel"),
        Index("ix_processos_owner_categoria", "owner_user_id", "categoria_servico"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    numero_processo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    vara: Mapped[str | None] = mapped_column(String(120))
    comarca: Mapped[str | None] = mapped_column(String(120))
    tipo_acao: Mapped[str | None] = mapped_column(String(180))
    contratante: Mapped[str | None] = mapped_column(String(180))

    # ✅ novo campo (já existe no SQLite)
    categoria_servico: Mapped[str | None] = mapped_column(String(120), index=True)

    papel: Mapped[str] = mapped_column(String(40), default="Assistente Técnico")
    status: Mapped[str] = mapped_column(String(40), default="Ativo")

    pasta_local: Mapped[str | None] = mapped_column(String(300))
    observacoes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="processos")

    andamentos: Mapped[list["Andamento"]] = relationship(
        back_populates="processo",
        cascade="all, delete-orphan",
    )
    prazos: Mapped[list["Prazo"]] = relationship(
        back_populates="processo",
        cascade="all, delete-orphan",
    )
    agendamentos: Mapped[list["Agendamento"]] = relationship(
        back_populates="processo",
        cascade="all, delete-orphan",
    )
    lancamentos: Mapped[list["LancamentoFinanceiro"]] = relationship(
        back_populates="processo",
        cascade="all, delete-orphan",
    )


# ------------------------------------------------------------
# ANDAMENTOS
# ------------------------------------------------------------
class Andamento(Base):
    __tablename__ = "andamentos"
    __table_args__ = (
        Index("ix_andamentos_processo_data", "processo_id", "data_evento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"),
        nullable=False,
        index=True,
    )

    data_evento: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(180), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    processo: Mapped["Processo"] = relationship(back_populates="andamentos")


# ------------------------------------------------------------
# PRAZOS
# ------------------------------------------------------------
class Prazo(Base):
    __tablename__ = "prazos"
    __table_args__ = (
        Index(
            "ix_prazos_processo_concluido_data",
            "processo_id",
            "concluido",
            "data_limite",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"),
        nullable=False,
        index=True,
    )

    evento: Mapped[str] = mapped_column(String(180), nullable=False)
    data_limite: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    prioridade: Mapped[str] = mapped_column(String(20), default="Média")
    concluido: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # rastreabilidade/origem do prazo
    origem: Mapped[str | None] = mapped_column(String(40))
    referencia: Mapped[str | None] = mapped_column(String(120))

    observacoes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    processo: Mapped["Processo"] = relationship(back_populates="prazos")


# ------------------------------------------------------------
# AGENDAMENTOS
# ------------------------------------------------------------
class Agendamento(Base):
    __tablename__ = "agendamentos"
    __table_args__ = (
        Index("ix_agendamentos_status_inicio", "status", "inicio"),
        Index("ix_agendamentos_alertas", "alerta_24h_enviado", "alerta_2h_enviado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id"),
        nullable=True,
        index=True,
    )

    tipo: Mapped[str] = mapped_column(String(40), nullable=False)

    inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fim: Mapped[datetime | None] = mapped_column(DateTime)

    local: Mapped[str | None] = mapped_column(String(220))
    descricao: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Agendado",
    )

    alerta_24h_enviado: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    alerta_2h_enviado: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Mantido por compatibilidade
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)

    processo: Mapped["Processo"] = relationship(back_populates="agendamentos")


# ------------------------------------------------------------
# FINANCEIRO
# ------------------------------------------------------------
class LancamentoFinanceiro(Base):
    __tablename__ = "financeiro"
    __table_args__ = (
        Index("ix_financeiro_processo_data", "processo_id", "data_lancamento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"),
        nullable=False,
        index=True,
    )

    data_lancamento: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)

    categoria: Mapped[str | None] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text)

    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    processo: Mapped["Processo"] = relationship(back_populates="lancamentos")


# ------------------------------------------------------------
# FERIADOS / CALENDÁRIO
# ------------------------------------------------------------
class Feriado(Base):
    __tablename__ = "feriados"
    __table_args__ = (
        # evita duplicidade (mesmo dia + mesmo escopo + mesmo local)
        UniqueConstraint(
            "data", "escopo", "local", name="uq_feriados_data_escopo_local"
        ),
        Index("ix_feriados_escopo_local_data", "escopo", "local", "data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Mantido como DateTime (00:00) por compatibilidade com o banco atual.
    # (o CalendarioService deve consultar com fim exclusivo para não perder registros)
    data: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # NACIONAL | ESTADUAL_SP | MUNICIPAL | TJSP_GERAL | TJSP_COMARCA
    escopo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Para MUNICIPAL: "Ilhabela"
    # Para TJSP_COMARCA: "Ilhabela" (ou "São Sebastião" etc.)
    #
    # SQLite: UNIQUE permite duplicidade quando local é NULL.
    # Por isso, no ORM definimos default="" para reduzir inserções com NULL,
    # especialmente nos escopos FIXOS (NACIONAL/ESTADUAL_SP/TJSP_GERAL).
    local: Mapped[str | None] = mapped_column(String(120), index=True, default="")

    descricao: Mapped[str | None] = mapped_column(String(180))
    fonte: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
