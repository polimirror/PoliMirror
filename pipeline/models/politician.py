"""
PoliMirror - 政治家データモデル
v1.1.0
"""
import traceback
from dataclasses import dataclass, field
from typing import Optional
from datetime import date


@dataclass
class Politician:
    """政治家データを表すデータクラス"""

    # 基本情報
    id: str                          # 一意ID（例: shugiin_123）
    name_ja: str                     # 氏名（漢字）
    name_kana: str                   # 氏名（ふりがな）
    name_en: Optional[str] = None    # 氏名（英語）

    # 所属
    house: str = ""                  # 衆議院 / 参議院 / 都道府県議会 等
    party: str = ""                  # 政党
    constituency: str = ""           # 選挙区
    status: str = "現職"             # 現職 / 元職 / 落選

    # 任期
    terms: Optional[int] = None       # 当選回数（None=不明）
    first_elected: Optional[int] = None  # 初当選年

    # プロフィール
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    education: list[str] = field(default_factory=list)
    career: list[str] = field(default_factory=list)

    # SNS・外部リンク
    website: Optional[str] = None
    twitter: Optional[str] = None
    facebook: Optional[str] = None
    official_page: Optional[str] = None  # 議会公式プロフィールURL

    # メタ
    last_updated: Optional[str] = None
    source_url: Optional[str] = None
    image_url: Optional[str] = None

    def to_dict(self) -> dict:
        """辞書に変換する"""
        try:
            return {
                "id": self.id,
                "name_ja": self.name_ja,
                "name_kana": self.name_kana,
                "name_en": self.name_en,
                "house": self.house,
                "party": self.party,
                "constituency": self.constituency,
                "status": self.status,
                "terms": self.terms,
                "first_elected": self.first_elected,
                "birth_date": self.birth_date.isoformat() if self.birth_date else None,
                "birth_place": self.birth_place,
                "education": self.education,
                "career": self.career,
                "website": self.website,
                "twitter": self.twitter,
                "facebook": self.facebook,
                "official_page": self.official_page,
                "last_updated": self.last_updated,
                "source_url": self.source_url,
                "image_url": self.image_url,
            }
        except Exception:
            traceback.print_exc()
            raise
