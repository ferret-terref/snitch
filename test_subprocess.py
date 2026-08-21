import asyncio
import subprocess

async def test():
    try:
        process = await asyncio.create_subprocess_exec(
            'echo', 'test',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        await process.wait()
        print('Success: CREATE_NO_WINDOW works')
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test())