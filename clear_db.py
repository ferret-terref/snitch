"""
clear_db.py - Deletes database and logging files specified in config.yaml
"""
import os
from pathlib import Path

import yaml


def load_config(config_path="config.yaml"):
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def delete_file_safely(file_path):
    """Delete a file if it exists and report the result."""
    path = Path(file_path)
    if path.exists():
        try:
            path.unlink()
            print(f"✓ Deleted: {file_path}")
            return True
        except Exception as e:
            print(f"✗ Error deleting {file_path}: {e}")
            return False
    else:
        print(f"- File not found (skipping): {file_path}")
        return False


def main():
    """Main function to delete database and logging files."""
    try:
        # Load config
        config = load_config()
        
        files_to_delete = []
        
        # Get database file path
        if 'database' in config and 'path' in config['database']:
            db_path = config['database']['path']
            files_to_delete.append(db_path)
        
        # Get logging file path
        if 'logging' in config and 'file' in config['logging']:
            log_path = config['logging']['file']
            files_to_delete.append(log_path)
        
        if not files_to_delete:
            print("No database or logging files found in config.yaml")
            return
        
        print("Files to delete:")
        for file in files_to_delete:
            print(f"  - {file}")
        print()
        
        # Confirm deletion
        response = input("Are you sure you want to delete these files? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Deletion cancelled.")
            return
        
        print("\nDeleting files...")
        deleted_count = 0
        for file in files_to_delete:
            if delete_file_safely(file):
                deleted_count += 1
        
        print(f"\nDone! Deleted {deleted_count} file(s).")
        
    except FileNotFoundError:
        print("Error: config.yaml not found in the current directory.")
    except yaml.YAMLError as e:
        print(f"Error parsing config.yaml: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
