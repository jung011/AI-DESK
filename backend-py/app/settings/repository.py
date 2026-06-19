"""settings DB 접근 — t_aidesk_setting upsert/select."""
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.settings.models import AideskSetting


class SettingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def select_value(self, account_sn: int, key: str) -> str | None:
        row = self.db.execute(
            select(AideskSetting).where(
                AideskSetting.account_sn == account_sn,
                AideskSetting.setting_key == key,
            )
        ).scalar_one_or_none()
        return row.setting_value if row else None

    def upsert_value(self, account_sn: int, key: str, value: str) -> None:
        """ORM 의 merge 사용 — MySQL 의 ON DUPLICATE KEY UPDATE 와 동등 (SQLAlchemy 가
        dialect 별 자동 처리)."""
        existing = self.db.execute(
            select(AideskSetting).where(
                AideskSetting.account_sn == account_sn,
                AideskSetting.setting_key == key,
            )
        ).scalar_one_or_none()
        if existing:
            existing.setting_value = value
        else:
            self.db.add(AideskSetting(account_sn=account_sn, setting_key=key, setting_value=value))
        self.db.flush()
