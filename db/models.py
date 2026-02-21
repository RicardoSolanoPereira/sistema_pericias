from sqlalchemy import (
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .connection import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    processos: Mapped[list["Processo"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Processo(Base):
    __tablename__ = "processos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    numero_processo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    vara: Mapped[str | None] = mapped_column(String(120))
    comarca: Mapped[str | None] = mapped_column(String(120))
    tipo_acao: Mapped[str | None] = mapped_column(String(180))
    contratante: Mapped[str | None] = mapped_column(String(180))

    papel: Mapped[str] = mapped_column(
        String(40), default="Assistente Técnico"
    )  # Perito / Assistente Técnico
    status: Mapped[str] = mapped_column(
        String(40), default="Ativo"
    )  # Ativo / Concluído / Suspenso

    pasta_local: Mapped[str | None] = mapped_column(String(300))
    observacoes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="processos")

    andamentos: Mapped[list["Andamento"]] = relationship(
        back_populates="processo", cascade="all, delete-orphan"
    )
    prazos: Mapped[list["Prazo"]] = relationship(
        back_populates="processo", cascade="all, delete-orphan"
    )
    agendamentos: Mapped[list["Agendamento"]] = relationship(
        back_populates="processo", cascade="all, delete-orphan"
    )
    lancamentos: Mapped[list["LancamentoFinanceiro"]] = relationship(
        back_populates="processo", cascade="all, delete-orphan"
    )


class Andamento(Base):
    __tablename__ = "andamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"), nullable=False, index=True
    )

    data_evento: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    titulo: Mapped[str] = mapped_column(String(180), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    processo: Mapped["Processo"] = relationship(back_populates="andamentos")


class Prazo(Base):
    __tablename__ = "prazos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"), nullable=False, index=True
    )

    evento: Mapped[str] = mapped_column(String(180), nullable=False)
    data_limite: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    prioridade: Mapped[str] = mapped_column(
        String(20), default="Média"
    )  # Baixa/Média/Alta
    concluido: Mapped[bool] = mapped_column(Boolean, default=False)

    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    processo: Mapped["Processo"] = relationship(back_populates="prazos")


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id"), nullable=True, index=True
    )

    tipo: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # Vistoria/Reunião/Audiência/Outro
    inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fim: Mapped[datetime | None] = mapped_column(DateTime)

    local: Mapped[str | None] = mapped_column(String(220))
    descricao: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    processo: Mapped["Processo"] = relationship(back_populates="agendamentos")


class LancamentoFinanceiro(Base):
    __tablename__ = "financeiro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    processo_id: Mapped[int] = mapped_column(
        ForeignKey("processos.id"), nullable=False, index=True
    )

    data_lancamento: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # Receita/Despesa

    categoria: Mapped[str | None] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text)

    # Numeric é melhor que float pra dinheiro
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    processo: Mapped["Processo"] = relationship(back_populates="lancamentos")
