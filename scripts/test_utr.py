import httpx
import asyncio

async def test():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            "http://localhost:8000/payments/submit-utr",
            json={"telegram_id": 6189058729, "order_ref": "CRD-2D8489133154E498", "utr": "123456789012"},
        )
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text}")

asyncio.run(test())
