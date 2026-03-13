"""
PoliMirror - ユーティリティ関数
v1.0.0
"""
import traceback
import logging

logger = logging.getLogger(__name__)


def setup_logging(name: str = "polimirror", level: int = logging.INFO) -> logging.Logger:
    """ロガーをセットアップする"""
    try:
        log = logging.getLogger(name)
        log.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        log.addHandler(handler)
        return log
    except Exception:
        traceback.print_exc()
        raise
