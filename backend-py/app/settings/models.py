"""settings ORM — t_aidesk_setting (사용자별 key/value)."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AideskSetting(Base):
    """t_aidesk_setting — PK = (account_sn, setting_key).

    호출은 항상 account_sn 동반. user 별 격리.
    """

    __tablename__ = "t_aidesk_setting"

    account_sn: Mapped[int] = mapped_column(primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    setting_value: Mapped[str] = mapped_column(String(2000), default="")
