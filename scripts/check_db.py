#!/usr/bin/env python
"""Check database status."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import select, func
from src.database import db_manager, Decision


async def main():
    await db_manager.initialize()
    async with db_manager.get_session() as session:
        count = await session.execute(select(func.count()).select_from(Decision))
        print(f"Entscheidungen in DB: {count.scalar()}")
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
