#!/usr/bin/env python3
"""
=============================================================================
 DOCUMENTATION: Step 2 - Duplicate Cleanup Between 'Year' and 'Album'
=============================================================================

1. BASIC PARAMETERS & TECHNICAL DETAILS:
   - Cross-platform: Runs on Windows and macOS (uses native GUI folder dialog
     via Tkinter with console fallback).
   - Folder structure: Automatically creates the 'Discarded' folder in the main
     directory (if not present) and mirrors the original folder structure when
     moving files.
   - Data loss protection: On name collisions in the target directory, a counter
     is automatically appended to avoid overwriting files.

2. LOGIC & WORKFLOW:
   - Reconciliation: Checks whether files from the 'Year' folders already exist in 'Album'.
   - Content Verification: Because camera file numbering resets (e.g., IMG_0001.JPG),
     a SHA-256 hash comparison is performed on filename matches.
   - Action: Files that match an album photo in both filename AND content are recognized
     as duplicates and moved to the 'Discarded' folder.

3. CSV REPORT COLUMNS:
   - Status (sorted = in album, unsorted = not in album)
   - Path (relative = Album name or relative path)
   - Info (notes if sorted into album, otherwise blank/conflict note)
   - Action (move as Discarded / Keep in Year)
=============================================================================
"""

import os
import sys
import hashlib
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Tkinter for cross-platform folder dialog
try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# ==========================================
# BASIC PARAMETERS & EXCLUDED FOLDERS
# ==========================================
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORE_FOLDERS = {"Duplicates", "Discarded", "Duplikate", "Aussortiert"}  # Ignore these folders during scan
CSV_PREFIX = "Photo-Reconciliation-Report"

def choose_parent_folder():
    """Opens a cross-platform folder selection dialog (Windows & Mac)."""
    if HAS_TKINTER:
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder_selected = filedialog.askdirectory(title="Select Main Folder containing 'Album' and 'Year'")
            root.destroy()
            if folder_selected:
                return Path(folder_selected).resolve()
        except Exception:
            pass

    # Fallback for console / headless environment
    print("Folder dialog could not be opened.")
    path_input = input("Please enter the path to the main folder manually: ").strip('"\'')
    p = Path(path_input).resolve()
    if not p.is_dir():
        print(f"Invalid folder path: {p}")
        sys.exit(1)
    return p

def collect_files(root):
    """Recursively collects regular files; ignores system files and excluded folders."""
    found = []
    for current, dirs, files in os.walk(root):
        # Skip hidden folders and all folders defined in IGNORE_FOLDERS
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORE_FOLDERS]

        for name in files:
            if name in SKIP_NAMES or name.startswith("."):
                continue
            path = Path(current) / name
            if path.is_file() and not path.is_symlink():
                found.append(path.resolve())
    return sorted(found, key=lambda p: str(p).casefold())

def key_name(path):
    """Returns filename in lowercase for matching."""
    return path.name.casefold()

def rel(path, root):
    """Returns the relative path to a root folder."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)

def get_album_name(path, albums_root):
    """Retrieves the album name (first level under Album/)."""
    try:
        rel_path = path.relative_to(albums_root)
        parts = rel_path.parts
        return parts[0] if parts else "Unknown"
    except ValueError:
        return ""

def calculate_checksum(path, chunk_size=8192):
    """Calculates SHA-256 hash of a file for content verification."""
    sha256_hash = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None

def main():
    move_mode = "--move" in sys.argv[1:]
    parent = choose_parent_folder()

    albums_root = parent / "Album"
    years_root = parent / "Year"
    discarded_root = parent / "Discarded"  # Target directory for duplicates

    # Support fallback to German folder names if English ones are not found
    if not albums_root.is_dir() and (parent / "Alben").is_dir():
        albums_root = parent / "Alben"
    if not years_root.is_dir() and (parent / "Jahre").is_dir():
        years_root = parent / "Jahre"

    for folder in (albums_root, years_root):
        if not folder.is_dir():
            print(f"ERROR: Required directory not found: {folder}")
            sys.exit(2)

    print(f"Collecting files in '{albums_root.name}' and '{years_root.name}'...")
    album_files = collect_files(albums_root)
    year_files = collect_files(years_root)

    # Index album files by name for fast lookup
    albums_by_name = defaultdict(list)
    for p in album_files:
        albums_by_name[key_name(p)].append(p)

    rows = []
    move_candidates = []  # Files from Year that exist in Album -> move to Discarded
    album_hashes = {}     # Checksum cache to avoid repeated hashing

    print("Comparing files and checking checksums on matching filenames...")

    for yp in year_files:
        name_key = key_name(yp)
        y_rel_path = rel(yp, years_root)
        a_paths = albums_by_name.get(name_key, [])

        if not a_paths:
            # Case 1: File does not exist in Album folder (Unique)
            status = "unsorted"
            pfad_val = y_rel_path
            info_val = ""  # Blank, not sorted in any album
            action = "Keep in Year (Unique)"
        else:
            # Case 2: Matching name found -> compare content (Hash) due to camera index resets
            y_hash = calculate_checksum(yp)
            match_found = False
            matched_album = ""

            for ap in a_paths:
                if ap not in album_hashes:
                    album_hashes[ap] = calculate_checksum(ap)

                a_hash = album_hashes[ap]
                if y_hash and a_hash and y_hash == a_hash:
                    match_found = True
                    matched_album = get_album_name(ap, albums_root)
                    break

            if match_found:
                # True duplicate across Year and Album -> Discard!
                status = "sorted"
                pfad_val = f"{y_rel_path} identical with {matched_album}"
                info_val = f"Already in album '{matched_album}'"
                action = "Move as Discarded"
                move_candidates.append(yp)
            else:
                # Same name, different content (e.g. different camera photo from another year)
                status = "unsorted"
                pfad_val = y_rel_path
                info_val = "Matching filename, but different content (different photo)"
                action = "Keep in Year (Content differs)"

        rows.append({
            "Status": status,
            "Path": pfad_val,
            "Info": info_val,
            "Action": action,
            "Full_Path": yp
        })

    # Create CSV file (utf-8-sig for proper Excel display)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_path = parent / f"{CSV_PREFIX}-{timestamp}.csv"

    fields = ["Status", "Path", "Info", "Action"]

    try:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "Status": r["Status"],
                    "Path": r["Path"],
                    "Info": r["Info"],
                    "Action": r["Action"]
                })
        print(f"\n✓ CSV report successfully created:\n  {csv_path}")
    except Exception as e:
        print(f"\n⚠️ Error writing CSV report: {e}")

    print(f"Found duplicates (candidates for 'Discarded'): {len(move_candidates)}")

    if not move_mode:
        print("\n" + "=" * 60)
        print("NOTE: Dry run mode. No files were moved.")
        print(f"Please inspect the report in the CSV file: {csv_path.name}")
        print("Run the script with the '--move' parameter to move duplicates to 'Discarded':")
        print("  python phase2_album_reconciler.py --move")
        print("=" * 60)
        return

    # Execute move mode
    print("\nMOVE MODE ACTIVE...")
    answer = input('Type exactly MOVE to proceed: ').strip()
    if answer != "MOVE":
        print("Aborted. No files were moved.")
        return

    moved = 0
    failed = 0
    for item in rows:
        if item["Action"] != "move as Discarded":
            continue

        source = item["Full_Path"]
        if not source.exists():
            failed += 1
            continue

        # Preserve relative path from Year directory
        rel_path = source.relative_to(years_root)
        destination = discarded_root / rel_path

        # Handle collisions in target directory
        if destination.exists():
            base = destination.stem
            ext = destination.suffix
            counter = 1
            while destination.exists():
                destination = destination.with_name(f"{base}_dup{counter}{ext}")
                counter += 1

        try:
            # Automatically create subdirectories in Discarded as needed
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(str(source), str(destination))
            moved += 1
        except Exception as exc:
            print(f"ERROR moving {source.name}: {exc}")
            failed += 1

    print(f"\nDone! Successfully moved to 'Discarded': {moved}, Errors/Skipped: {failed}")
    print(f"Target directory: {discarded_root}")

if __name__ == "__main__":
    main()
