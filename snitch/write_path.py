"""Helper script to write folder path with UTF-8 encoding."""
import sys
from pathlib import Path

if __name__ == "__main__":
    print("sys.argv:", sys.argv, file=sys.stderr)  # <--- Add this line
    if len(sys.argv) < 3:
        print("Usage: write_path.py <folder_path> <output_file>", file=sys.stderr)
        sys.exit(1)

    # Join all args except the last one as folder path (handles spaces and weird quoting)
    folder_path = ' '.join(sys.argv[1:-1])
    output_file = sys.argv[-1]

    # Clean up the folder path - remove extended-length prefix, quotes, and trailing slashes/backslashes
    folder_path = folder_path.rstrip('#')
    folder_path = folder_path.strip('"').strip("'")
    if folder_path.startswith('\\\\?\\'):
        folder_path = folder_path[4:]
    folder_path = folder_path.rstrip('\\/')

    # Write with UTF-8 encoding
    Path(output_file).write_text(folder_path, encoding='utf-8')