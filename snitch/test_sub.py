import subprocess

result = subprocess.run(
    ["gallery-dl", "--version"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)
print("gallery-dl version:", result.stdout.strip() or result.stderr.strip())