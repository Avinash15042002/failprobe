import asyncio
from failprobe import probe

@probe(name="demo-agent")
async def run_agent(query: str) -> str:
    await asyncio.sleep(0.05)
    return f"Answer to: {query}"

async def main():
    for i in range(10):
        await run_agent(f"question {i}")
    await asyncio.sleep(1.0)   # let the async span emitter flush to SQLite

asyncio.run(main())
