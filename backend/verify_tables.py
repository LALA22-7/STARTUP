"""Verify database tables were created successfully."""
import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import engine


async def verify_tables():
    """Check what tables exist in the database."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
        )
        tables = result.fetchall()
        
        if tables:
            print("\n✓ Database tables found:")
            for table in tables:
                print(f"  - {table[0]}")
            print(f"\nTotal: {len(tables)} tables")
        else:
            print("\n✗ No tables found in database")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_tables())
