import asyncio
import os
from pathlib import Path


async def test_exact_command():
    """Test that we can generate the exact command format that works"""
    
    # First, check gallery-dl location and version
    print("=" * 80)
    print("CHECKING GALLERY-DL ENVIRONMENT")
    print("=" * 80)
    
    try:
        # Check where gallery-dl is
        process = await asyncio.create_subprocess_exec(
            "where", "gallery-dl",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"gallery-dl location:\n{stdout.decode('utf-8', errors='replace')}")
        
        # Check version
        process = await asyncio.create_subprocess_exec(
            "gallery-dl", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"gallery-dl version:\n{stdout.decode('utf-8', errors='replace')}")
        
        # Check config location
        process = await asyncio.create_subprocess_exec(
            "gallery-dl", "--list-config",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if stdout:
            print(f"gallery-dl config:\n{stdout.decode('utf-8', errors='replace')[:500]}")
    except Exception as e:
        print(f"Error checking environment: {e}")
    
    # Expected command (the one that works when typed manually)
    expected_cmd = 'gallery-dl --write-info-json --destination C:/Temp/gallery-dl/gallery-dl/ --exec-after "C:\\Users\\James\\Git\\gallery-arr\\snitch\\write_path_wrapper.bat {_directory} C:\\Temp\\gallery-dl\\304-path.txt" https://hentai-cosplay-xxx.com/image/recommendation-beauty34p/'
    
    # Build the command parts
    executable = "gallery-dl"
    destination = "C:/Temp/gallery-dl/gallery-dl/"
    write_path_wrapper = r"C:\Users\James\Git\gallery-arr\snitch\write_path_wrapper.bat"
    path_file = r"C:\Temp\gallery-dl\304-path.txt"
    url = "https://hentai-cosplay-xxx.com/image/recommendation-beauty34p/"
    
    # Build exec_cmd - wrap the ENTIRE value in quotes (no internal quotes)
    exec_cmd = f'"{write_path_wrapper} {{_directory}} {path_file}"'
    
    # Build the full command
    generated_cmd = f'{executable} --write-info-json --destination {destination} --exec-after {exec_cmd} {url}'
    
    print("=" * 80)
    print("COMMAND VALIDATION TEST")
    print("=" * 80)
    print(f"\nExpected command:\n{expected_cmd}")
    print(f"\nGenerated command:\n{generated_cmd}")
    print(f"\nMatch: {generated_cmd == expected_cmd}")
    
    if generated_cmd == expected_cmd:
        print("\n✓ COMMAND MATCHES EXACTLY!")
    else:
        print("\n✗ COMMANDS DON'T MATCH")
        print("\nDifferences:")
        for i, (e, g) in enumerate(zip(expected_cmd, generated_cmd)):
            if e != g:
                print(f"  Position {i}: expected '{e}' got '{g}'")
        if len(expected_cmd) != len(generated_cmd):
            print(f"  Length: expected {len(expected_cmd)} got {len(generated_cmd)}")
    
    print("\n" + "=" * 80)
    print("RUNNING TEST WITH create_subprocess_shell")
    print("=" * 80)
    
    try:
        process = await asyncio.create_subprocess_shell(
            generated_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"Return code: {process.returncode}")
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='replace')
            print(f"STDOUT:\n{stdout_text[:500]}")  # First 500 chars
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='replace')
            print(f"STDERR:\n{stderr_text[:500]}")  # First 500 chars
        
        if process.returncode == 0:
            print("\n✓ COMMAND SUCCEEDED!")
        else:
            print(f"\n✗ COMMAND FAILED with return code {process.returncode}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("RUNNING TEST WITH cmd.exe /c explicitly")
    print("=" * 80)
    
    cmd_exe_cmd = f'cmd.exe /c "{generated_cmd}"'
    print(f"Command: {cmd_exe_cmd}\n")
    
    try:
        process = await asyncio.create_subprocess_shell(
            cmd_exe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"Return code: {process.returncode}")
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='replace')
            print(f"STDOUT:\n{stdout_text[:500]}")
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='replace')
            print(f"STDERR:\n{stderr_text[:500]}")
        
        if process.returncode == 0:
            print("\n✓ COMMAND SUCCEEDED!")
        else:
            print(f"\n✗ COMMAND FAILED with return code {process.returncode}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("RUNNING TEST WITH PowerShell -Command explicitly")
    print("=" * 80)
    
    ps_cmd = f'powershell -NoProfile -Command "{generated_cmd}"'
    print(f"Command: {ps_cmd}\n")
    
    try:
        process = await asyncio.create_subprocess_shell(
            ps_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"Return code: {process.returncode}")
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='replace')
            print(f"STDOUT:\n{stdout_text[:500]}")
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='replace')
            print(f"STDERR:\n{stderr_text[:500]}")
        
        if process.returncode == 0:
            print("\n✓ COMMAND SUCCEEDED!")
        else:
            print(f"\n✗ COMMAND FAILED with return code {process.returncode}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("RUNNING TEST WITH create_subprocess_exec calling cmd.exe directly")
    print("=" * 80)
    
    print(f"Calling: cmd.exe with /c and command as separate arg\n")
    
    try:
        process = await asyncio.create_subprocess_exec(
            "cmd.exe", "/c", generated_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"Return code: {process.returncode}")
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='replace')
            print(f"STDOUT:\n{stdout_text[:500]}")
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='replace')
            print(f"STDERR:\n{stderr_text[:500]}")
        
        if process.returncode == 0:
            print("\n✓ COMMAND SUCCEEDED!")
        else:
            print(f"\n✗ COMMAND FAILED with return code {process.returncode}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("RUNNING TEST WITH create_subprocess_exec using ARGUMENT LIST")
    print("=" * 80)
    
    cmd_list = [
        executable,
        "--write-info-json",
        "--destination", destination,
        "--exec-after", f"{write_path_wrapper} {{_directory}} {path_file}",  # No quotes - passed as single arg
        url
    ]
    
    print(f"Command list: {cmd_list}\n")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        print(f"Return code: {process.returncode}")
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='replace')
            print(f"STDOUT:\n{stdout_text[:500]}")
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='replace')
            print(f"STDERR:\n{stderr_text[:500]}")
        
        if process.returncode == 0:
            print("\n✓ COMMAND SUCCEEDED!")
        else:
            print(f"\n✗ COMMAND FAILED with return code {process.returncode}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(test_exact_command())
