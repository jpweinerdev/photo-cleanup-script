#!/usr/bin/env python3
"""
=============================================================================
 DOCUMENTATION: Step 1 - Script for Duplicate and Edit Detection
 Cross-platform script (Windows & macOS) to detect and filter
 duplicates, originals, and edits with CSV report generation.
=============================================================================

1. BASIC PARAMETERS & TECHNICAL DETAILS:
   - Cross-platform: Runs on Windows and macOS (uses native GUI folder dialog
     via Tkinter with console fallback).
   - Folder structure: Automatically creates the subfolder 'Duplicates' in the
     main directory (if not present) and mirrors the original folder structure
     when moving files.
   - Data loss protection: On name collisions in the target directory, a suffix
     (e.g., _filtered1) is automatically appended so no files are overwritten.
   - CSV report: Generates a 'Duplicate-Report-<timestamp>.csv' in the main folder
     with Status, Filename, Relative Folder Path, and Action.

2. MEDIA HANDLING & SELECTION LOGIC (PHOTOS VS. VIDEOS):
   - Photos (Default):
     - `[name]_original.ext`: Represents the full uncropped sensor capture (e.g. 4:3)
       when a specific aspect ratio (e.g. 16:9) was chosen. The primary file `[name].ext`
       reflects the intentional framing.
       -> Default Action: Discard `_original` (Keep cropped `[name].ext`).
   - Videos (Default vs. `--strict-video-originals`):
     - Default Mode: Assumes the video edit (trimmed/processed file without `_original`)
       is the intended final result (e.g., raw clip = draft, edit = final).
       -> Action: Discard `_original` (Keep edited file).
     - Strict Video Originals Mode (`--strict-video-originals`):
       Reverses the logic for video files only! Assumes `video_original.mov` is the
       valuable uncompressed master file.
       -> Action: Keep `_original` video and discard the un-suffixed edit (`[name].mov`).

3. DEFINED ACTIONS (--move mode vs. test run):
   - True Duplicate -> Action: discard (moved to 'Duplicates' folder)
   - Original       -> Action: discard / keep (depending on media type & CLI flags)
   - Edit           -> Action: discard / keep (depending on media type & CLI flags)
   - Conflict       -> Action: check (no automatic action / flagged in CSV)
=============================================================================
"""

import os
import sys
import re
import csv
import hashlib
from datetime import datetime
from pathlib import Path
import shutil

# Tkinter for cross-platform folder dialog
try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

# ==========================================
# BASIC PARAMETERS & FILE EXTENSIONS
# ==========================================
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORE_FOLDERS = {"Duplicates", "Discarded", "Duplikate", "Aussortiert"}  # Ignore these folders during scan
CSV_PREFIX = "Duplicate-Report"

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png", ".webp", ".tif", ".tiff", ".dng", ".cr2", ".nef"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp"}

def choose_folder():
    """Opens a cross-platform folder selection dialog (Windows & Mac)."""
    if HAS_TKINTER:
        try:
            root = tk.Tk()
            root.withdraw()  # Hide main window
            root.attributes('-topmost', True)
            folder_selected = filedialog.askdirectory(title="Select Main Folder to Scan")
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

def calculate_hash(file_path, chunk_size=65536):
    """Calculates SHA-256 hash of a file in chunks."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None

def parse_filename_pattern(filename):
    """
    Analyzes filenames for duplicate/edit patterns.
    
    Returns: (pattern_type, target_original_filename)
    - pattern_type: 'numbered', 'original_suffix', or None
    """
    path_obj = Path(filename)
    stem = path_obj.stem
    ext = path_obj.suffix

    # Pattern 1: Explicit Original Suffix -> "name_original.ext"
    match_orig = re.match(r"^(.+)_original$", stem, re.IGNORECASE)
    if match_orig:
        return "original_suffix", f"{match_orig.group(1)}{ext}"

    # Pattern 2: Edit / Copy with number -> "name 1.ext" or "name copy.ext"
    match_num = re.match(r"^(.+)\s+\d+$", stem)
    if match_num:
        return "numbered", f"{match_num.group(1)}{ext}"

    match_copy = re.match(r"^(.+?)\s+(?:copy|kopie)(?:\s+\d+)?$", stem, re.IGNORECASE)
    if match_copy:
        return "numbered", f"{match_copy.group(1)}{ext}"

    return None, None

def main():
    move_mode = "--move" in sys.argv[1:]
    strict_video_originals = "--strict-video-originals" in sys.argv[1:]
    
    root = choose_folder()
    duplicates_root = root / "Duplicates"

    print(f"Scanning main folder: {root} ...")
    if strict_video_originals:
        print("Option active: --strict-video-originals (Master video files '_original' will be KEPT, edits without '_original' will be discarded).")
    else:
        print("Default mode active: Video edits without '_original' will be KEPT, raw '_original' videos will be discarded (use --strict-video-originals to invert).")

    filtered_items = []

    # Recursive walk through all subfolders
    for current, dirs, files in os.walk(root):
        # Skip hidden folders and ignored directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORE_FOLDERS]
        current_path = Path(current)

        # Get relative folder path to main directory
        try:
            rel_folder_path = str(current_path.relative_to(root))
            if rel_folder_path == ".":
                rel_folder_path = ""
        except ValueError:
            rel_folder_path = ""

        for name in files:
            if name in SKIP_NAMES or name.startswith("."):
                continue

            file_path = current_path / name
            if not (file_path.is_file() and not file_path.is_symlink()):
                continue

            pattern_type, related_name = parse_filename_pattern(name)
            if not pattern_type:
                continue

            related_path = current_path / related_name
            ext = file_path.suffix.lower()
            is_video = ext in VIDEO_EXTENSIONS

            # --- Case 1: Pattern [name]_original.[ext] ---
            if pattern_type == "original_suffix":
                if is_video and strict_video_originals:
                    # User requested to preserve raw master video originals
                    status = "Video Original (Master Kept)"
                    action = "keep"
                    
                    # Mark the un-suffixed edited video for discard if it exists
                    if related_path.exists() and related_path.is_file():
                        filtered_items.append({
                            "status": "Video Edit (Replaced by Original)",
                            "filename": related_name,
                            "folder_path": rel_folder_path,
                            "action": "discard",
                            "full_path": related_path.resolve()
                        })
                else:
                    # Default: Discard _original (for photos or default video edit preference)
                    status = "Original"
                    action = "discard"

            # --- Case 2: Pattern [name] 1.[ext] (or copy) ---
            elif pattern_type == "numbered":
                if related_path.exists() and related_path.is_file():
                    # Check file size
                    size_match = file_path.stat().st_size == related_path.stat().st_size

                    if size_match:
                        # Hash comparison for verifying true identity
                        hash_current = calculate_hash(file_path)
                        hash_related = calculate_hash(related_path)

                        if hash_current and hash_related and hash_current == hash_related:
                            status = "True Duplicate"
                            action = "discard"
                        else:
                            status = "Edit"
                            action = "discard"
                    else:
                        status = "Edit"
                        action = "discard"
                else:
                    # Fallback: Neither clear duplicate, edit, nor original -> Conflict
                    status = "Conflict"
                    action = "check"

            # Avoid adding items marked as 'keep' to the discard queue
            if action != "keep":
                filtered_items.append({
                    "status": status,
                    "filename": name,
                    "folder_path": rel_folder_path,
                    "action": action,
                    "full_path": file_path.resolve()
                })

    # Deduplicate filtered items list by file path
    unique_filtered = {}
    for item in filtered_items:
        unique_filtered[str(item["full_path"])] = item
    filtered_items = list(unique_filtered.values())

    print(f"Filtered files found: {len(filtered_items)}")

    if not filtered_items:
        print("No matching files found.")
        return

    # Create CSV report
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_report_path = root / f"{CSV_PREFIX}-{timestamp}.csv"
    try:
        with open(csv_report_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(["Status", "Filename", "Folder Path", "Action"])
            for item in filtered_items:
                writer.writerow([item["status"], item["filename"], item["folder_path"], item["action"]])
        print(f"\n✓ CSV report successfully created: {csv_report_path}")
    except Exception as e:
        print(f"\n⚠️ Error writing CSV report: {e}")

    # Output summary preview
    print("\nSummary of filtered results (max 10 entries):")
    for item in filtered_items[:10]:
        print(f"  - [{item['status']}] {item['filename']} (Path: {item['folder_path'] or 'Main Folder'}) -> Action: {item['action']}")
    if len(filtered_items) > 10:
        print(f"  ... and {len(filtered_items) - 10} more.")

    # Dry run / Move logic check
    if not move_mode:
        print("\n" + "=" * 60)
        print("NOTE: This was a test run (dry run). No files were moved.")
        print(f"Please inspect the report in the CSV file: {csv_report_path.name}")
        print("Run the script with the '--move' parameter to discard files:")
        print("  python phase1_duplicate_cleaner.py --move")
        if not strict_video_originals:
            print("  (Optional: Add '--strict-video-originals' if you want to keep raw video _original files)")
        print("=" * 60)
        return

    # Execute move mode
    print("\nMOVE MODE ACTIVE...")
    answer = input('Type exactly MOVE to proceed: ').strip()
    if answer != "MOVE":
        print("Aborted. No files were moved.")
        return

    moved_count = 0
    skipped_count = 0

    for item in filtered_items:
        if item["action"] != "discard":
            skipped_count += 1
            continue

        source = item["full_path"]
        if not source.exists():
            skipped_count += 1
            continue

        rel_path = source.relative_to(root)
        destination = duplicates_root / rel_path

        # Handle collisions
        if destination.exists():
            base = destination.stem
            ext = destination.suffix
            counter = 1
            while destination.exists():
                destination = destination.with_name(f"{base}_filtered{counter}{ext}")
                counter += 1

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved_count += 1
        except Exception as exc:
            print(f"Error moving {source.name}: {exc}")
            skipped_count += 1

    print(f"\nDone! Discarded/Moved: {moved_count}, Skipped/Conflicts: {skipped_count}")
    print(f"Target folder for discarded files: {duplicates_root}")

if __name__ == "__main__":
    main()
