import subprocess


def run_gallery_dl(url: str) -> list[str]:
    result = subprocess.run(
        ["gallery-dl", url],
        capture_output=True,
        text=True
    )

    output_lines = (result.stdout + "\n" + result.stderr).splitlines()

    print("=== RAW OUTPUT ===")
    for line in output_lines:
        print(line)

    files: list[str] = []

    print("\n=== PARSING ===")

    for line in output_lines:
        line = line.strip()

        # your idea, but slightly safer
        if "gallery-dl" in line and (".jpg" in line or ".png" in line or ".mp4" in line):
            print("FOUND FILE:", line)
            files.append(line)

    print("\n=== FILES FOUND ===")
    for f in files:
        print(f)

    return files


if __name__ == "__main__":
    run_gallery_dl("https://x.com/sailorscholar_/status/2063023132173017411")