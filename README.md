# Smartphone (especially iOS devices) & Camera Photo Library Cleanup Script (Deduplication & Reconciliation)

A two-phase Python script toolset designed to deduplicate and reconcile large photo and video collections exported from smartphones (via 3rd party tools) or digital cameras without losing album structures or creating duplicate entries during re-import into photo organizing software..

---

## 🎯 The Problem & Goal

When exporting large photo and video libraries accumulated over many years:
1. **Duplicate Exports:** Exporting by **Album** (curated subsets) and by **Year/Date** (the complete chronological archive) causes identical files to exist in multiple places.
2. **Edits vs. Originals & Format Modifications:**
   - **Aspect Ratio Cuts / Edits:** Crop adjustments, social media exports, or format changes (e.g., `IMG_1234 1.JPG` or images saved automatically after Instagram posts) duplicate the primary photo.
   - **Apple iOS `_original` Files:** 
     - *Photos:* When taking photos in non-4:3 aspect ratios (such as 16:9), iOS saves the cropped file as `IMG_1234.JPG` and the full sensor capture as `IMG_1234_original.JPG`. The cropped file represents the user's intentional composition.
     - *Videos:* By default, the raw recorded video sequence represents the original, while files without `_original` indicate post-processing (trimming/cuts). Depending on user workflow, you can choose whether to treat the edited version as final or preserve the raw master video.
3. **Camera Index Rollovers:** Camera counter resets mean `IMG_0001.JPG` from 2018 is completely different from `IMG_0001.JPG` from 2024, despite matching filenames.

**Goal:** Clean up duplicates safely using cryptographic hashing (SHA-256), preserve user-intended edits and album structures, and isolate already-sorted album media so that re-importing into Apple Photos or any photo management software is fast, clean, and deduplicated.

---

## 🏗️ Expected Folder Structure

Place your exported media into a main root folder with the following structure (`Album` and `Year`):

```text
Main_Photo_Library/
├── Album/
│   ├── Summer_Vacation_2023/
│   │   ├── IMG_0042.JPG
│   │   └── IMG_0088.MOV
│   └── Family_Reunion/
│       └── IMG_0105.JPG
├── Year/
│   ├── 2022/
│   │   └── IMG_0001.JPG
│   ├── 2023/
│   │   ├── IMG_0042.JPG
│   │   └── IMG_0088.MOV
│   └── 2024/
│       └── IMG_0105.JPG
├── Duplicates/    <-- (Automatically created during Phase 1 cleanup)
└── Discarded/     <-- (Automatically created during Phase 2 cleanup)
```

---

## 🔄 Two-Phase Workflow

### Phase 1: Local Duplicate & Edit Cleaner (`phase1_duplicate_cleaner.py`)

Scans the library recursively for duplicate patterns within folders.

#### Criteria & Selection Logic:
* **Edits / Format Copies (`[name] 1.[ext]`, `[name] copy.[ext]`):** 
  - *Premise:* Exported edits (for social media, resize, app saves, or format changes) are considered secondary duplicates. The script prioritizes keeping the primary version and marks the extra edit for discard.
* **Apple iOS `_original` Files (`[name]_original.[ext]`):**
  - **Photos (Default):** The primary file `[name].[ext]` reflects the user's intended framing (e.g. 16:9 crop). Thus, `[name]_original.[ext]` is discarded.
  - **Videos (Default vs. `--strict-video-originals`):**
    - *Default:* Assumes the edited/trimmed video clip (`[name].mov`) is the intended final outcome, so `[name]_original.mov` is discarded.
    - *Flag `--strict-video-originals`:* Inverts this behavior for video formats (`.mov`, `.mp4`, `.m4v`, etc.). The raw master file `[name]_original.mov` is preserved, and the edited file `[name].mov` is marked for discard.
* **True Duplicates:** 
  - Verified by matching filename patterns, identical file sizes, and confirmed via **SHA-256 cryptographic hashes**.
* **Conflicts:**
  - If a numbered copy exists without its base file, it is marked as `Conflict` for manual check (action: `check`).

#### Execution:
```bash
# 1. Dry Run (Default: discarding _original files for both photos & videos):
python phase1_duplicate_cleaner.py

# 2. Dry Run with Video Master Preservation:
python phase1_duplicate_cleaner.py --strict-video-originals

# 3. Move Mode (Moves discarded files to 'Duplicates/' folder):
python phase1_duplicate_cleaner.py --move

# 4. Move Mode with Video Master Preservation:
python phase1_duplicate_cleaner.py --move --strict-video-originals
```

---

### Phase 2: Album vs. Year Reconciler (`phase2_album_reconciler.py`)

Compares media files in the `Year/` directory against the curated `Album/` directory.

#### Criteria & Selection Logic:
* **Subset Reconciliation:** Media files in `Album/` represent a curated subset of all media stored in `Year/`.
* **Hash-Based Verification:** Matches files between `Year/` and `Album/` by filename and verifies actual content identity via SHA-256 hash (preventing false matches caused by camera counter resets in different years).
* **Action Logic:**
  - **Identical match in Album:** The file in `Year/` is redundant because it is already organized inside an album. It is moved to `Discarded/` (preserving subfolder structure).
  - **Unique file:** The file exists only in `Year/` (not in any album). It remains safely inside `Year/`.

#### Execution:
```bash
# 1. Dry Run (Creates CSV report, no files moved):
python phase2_album_reconciler.py

# 2. Move Mode (Moves redundant year media to 'Discarded/'):
python phase2_album_reconciler.py --move
```

---

## 📊 CSV Reports & Data Safety

Both scripts generate timestamped CSV reports using UTF-8 BOM encoding for seamless viewing in Excel, Apple Numbers, or any CSV reader:

### Phase 1 Report Columns:
- `Status`: `True Duplicate`, `Edit`, `Original`, `Video Edit (Replaced by Original)`, or `Conflict`
- `Filename`: Name of the candidate file
- `Folder Path`: Relative folder path
- `Action`: `discard` or `check`

### Phase 2 Report Columns:
- `Status`: `sorted` (in album) or `unsorted` (not in album)
- `Path`: Album name or relative year path
- `Info`: Details on album match or content divergence
- `Action`: `Move as Discarded` or `Keep in Year (Unique)`

### Safety Guarantees:
- **No Overwriting:** On target filename collisions in `Duplicates/` or `Discarded/`, numerical suffixes (e.g., `_filtered1`, `_dup1`) are automatically attached.
- **Dry Run by Default:** Files are only moved when explicitly confirming in `--move` mode.
- **Cross-Platform:** Native support for both macOS and Windows.

