"""
UPI Service — QR code generation, UPI link building, UPI ID management.

Uses qrcode library to generate QR code data URLs for UPI payment links.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import List, Optional
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.upi_config import UpiConfig
from backend.schemas.upi_config import UpiConfigCreate, UpiConfigUpdate

logger = logging.getLogger(__name__)


def build_upi_link(
    upi_id: str,
    payee_name: str,
    amount: float,
    note: str = "",
    txn_ref: str = "",
) -> str:
    """
    Build a UPI intent URI.
    Format: upi://pay?pa=<UPI_ID>&pn=<PAYEE_NAME>&am=<AMOUNT>&cu=INR&tn=<NOTE>&tr=<TXN_REF>
    """
    params = [
        f"pa={quote(upi_id)}",
        f"pn={quote(payee_name)}",
        f"am={amount:.2f}",
        "cu=INR",
    ]
    if note:
        params.append(f"tn={quote(note)}")
    if txn_ref:
        params.append(f"tr={quote(txn_ref)}")
    return "upi://pay?" + "&".join(params)


def generate_upi_qr_data_url(upi_link: str, width: int = 300) -> str:
    """
    Generate a QR code as a base64 data URL for the given UPI link.
    Returns a string like 'data:image/png;base64,...'.
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage
    except ImportError:
        # Fallback: try segno (lighter alternative)
        try:
            import segno
            qr = segno.make(upi_link, error="M")
            buf = io.BytesIO()
            qr.save(buf, kind="png", scale=8, border=2)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            return f"data:image/png;base64,{b64}"
        except ImportError:
            logger.error("Neither 'qrcode' nor 'segno' installed. Cannot generate QR.")
            raise RuntimeError("QR code library not installed. Run: pip install qrcode[pil]")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return f"data:image/png;base64,{b64}"


class UpiService:
    """Manages UPI configuration in the database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: UpiConfigCreate) -> UpiConfig:
        cfg = UpiConfig(**data.model_dump())
        self.db.add(cfg)
        await self.db.flush()
        logger.info("Created UPI config: %s", data.upi_id)
        return cfg

    async def get_by_id(self, config_id: int) -> Optional[UpiConfig]:
        result = await self.db.execute(select(UpiConfig).where(UpiConfig.id == config_id))
        return result.scalar_one_or_none()

    async def update(self, config_id: int, data: UpiConfigUpdate) -> Optional[UpiConfig]:
        cfg = await self.get_by_id(config_id)
        if not cfg:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(cfg, field, value)
        await self.db.flush()
        return cfg

    async def delete(self, config_id: int) -> bool:
        cfg = await self.get_by_id(config_id)
        if not cfg:
            return False
        await self.db.delete(cfg)
        await self.db.flush()
        return True

    async def list_all(self) -> List[UpiConfig]:
        result = await self.db.execute(select(UpiConfig).order_by(UpiConfig.id))
        return list(result.scalars().all())

    async def get_active(self) -> Optional[UpiConfig]:
        """Return the currently active UPI config for payments."""
        result = await self.db.execute(
            select(UpiConfig).where(UpiConfig.is_active == True).limit(1)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def set_active(self, config_id: int) -> Optional[UpiConfig]:
        """Deactivate all, then activate the selected one."""
        # Deactivate all
        await self.db.execute(
            update(UpiConfig).values(is_active=False)
        )
        # Activate selected
        cfg = await self.get_by_id(config_id)
        if not cfg:
            return None
        cfg.is_active = True
        await self.db.flush()
        logger.info("Set UPI ID %s as active", cfg.upi_id)
        return cfg
