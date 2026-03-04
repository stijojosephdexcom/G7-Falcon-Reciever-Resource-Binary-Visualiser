# Resource Font Visualizer — User Guide

> **Version:** 1.0  
> **Platform:** Windows  
> **Author:** Dexcom UI Tools Team  

---

## Table of Contents

- [Overview](#overview)
- [What It Does](#what-it-does)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
  - [Running from Python](#running-from-python)
  - [Running the Standalone EXE](#running-the-standalone-exe)
- [Quick Start](#quick-start)
- [GUI Walkthrough](#gui-walkthrough)
  - [Input Files Section](#input-files-section)
  - [Parsed Configuration Section](#parsed-configuration-section)
  - [Options Section](#options-section)
  - [Progress Section](#progress-section)
  - [Action Buttons](#action-buttons)
- [Output Files](#output-files)
- [Color Format Reference](#color-format-reference)
- [Output Folder Management](#output-folder-management)
- [Building the EXE](#building-the-exe)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Overview

**Resource Font Visualizer** is a standalone GUI tool that extracts and visualizes font and icon images embedded inside `resource.bin` firmware binary files. It parses metadata from companion `resource.c` and `resource.h` C source files to locate image descriptors — then renders every glyph/icon into browsable PNG images and a detailed PDF address table.

---

## What It Does

1. **Parses** `resource.c` and `resource.h` to extract:
   - Number of fonts, font images, icon images, and languages
   - Image dimensions (width × height) for every glyph/icon
   - Binary data offsets (`RES_PRIMARY_FA_OFFSET + offset`)
   - Graphics/audio/total memory sizes

2. **Reads** the raw pixel data from `resource.bin` at the parsed offsets.

3. **Decodes** the pixel data from 16-bit color formats (RGB565, BGR565, Grayscale) into standard RGB images.

4. **Generates** three types of output (each independently toggleable):
   | Output | File | Description |
   |--------|------|-------------|
   | Combined Image | `all_fonts_combined.png` | Every glyph/icon laid out in a single grid image |
   | Paginated Images | `font_page_1.png`, `font_page_2.png`, … | Glyphs split into pages of 100 images each |
   | PDF Address Table | `font_address_table.pdf` | Landscape PDF with thumbnail, index, dimensions, hex start/end addresses, and byte size for every image |

5. **Auto-opens** the generated combined image, PDF, and the output folder in Windows Explorer when complete.

---

## Prerequisites

### For the Python script

| Dependency | Purpose |
|-----------|---------|
| Python 3.8+ | Runtime |
| `Pillow` | Image creation and manipulation |
| `reportlab` | PDF generation |
| `tkinter` | GUI framework (included with standard Python on Windows) |

Install dependencies:

```bash
pip install Pillow reportlab
```

### For the standalone EXE

**No prerequisites required.** The EXE bundles Python and all dependencies. The only system requirement is:

- **Windows 10/11** (64-bit)
- **Microsoft Visual C++ Redistributable 2015–2022** — pre-installed on most Windows machines. If missing, download from [Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe).

---

## Installation & Setup

### Running from Python

```bash
# Clone or copy the project folder
cd "python flash visualiser"

# Install dependencies
pip install Pillow reportlab

# Run
python font_visualiser.py
```

### Running the Standalone EXE

1. Copy `FontVisualizer.exe` (from the `dist/` folder) to any location on any Windows machine.
2. Double-click `FontVisualizer.exe`.
3. No Python installation needed — everything is bundled inside the EXE.

> **Note:** The `output/` folder will be created next to wherever the EXE is placed.

---

## Quick Start

1. Launch the tool (Python script or EXE).
2. Click **Browse** next to `resource.c` and select your file.  
   → `resource.h` and `resource.bin` are **auto-detected** if they exist in the same directory.
3. Click **Parse Resource Files** — the parsed configuration will display.
4. Configure options (color format, checkboxes) as needed.
5. Click **🖼️ GENERATE IMAGES**.
6. Output files open automatically. The output folder also opens in Explorer.

---

## GUI Walkthrough

### Input Files Section

| Field | Description |
|-------|-------------|
| **resource.c** | Path to the C source file containing `chars[]` and `icons[]` array definitions with image descriptors (`{width, height, RES_PRIMARY_FA_OFFSET + offset}`). |
| **resource.h** | Path to the C header file containing `#define` values for `NumFonts`, `NumFontImages`, `NumIconImages`, `NumLanguages`, memory sizes, etc. |
| **resource.bin** | Path to the raw binary file containing the actual pixel data at the offsets described in `resource.c`. |
| **Output Dir** | Directory where timestamped output subfolders are created. Defaults to an `output/` folder next to the script/EXE. Change it only via the **Browse** button — selecting input files does **not** change this. |

**Auto-detection:** When you browse for any one of the three input files, the tool automatically checks the same directory for the other two (`resource.c`, `resource.h`, `resource.bin`) and fills them in if found.

### Parsed Configuration Section

After clicking **Parse Resource Files**, this read-only text area displays:

- Number of Fonts
- Number of Font Images (defined vs. found)
- Number of Icon Images (defined vs. found)
- Number of Languages
- Graphics Size (bytes)
- Audio Size (bytes)
- Total Size (bytes)

### Options Section

#### Color Format Dropdown

| Value | Description |
|-------|-------------|
| `gray16` | 8-bit grayscale stored in 16-bit words (uses first byte per pixel) |
| `rgb565` | RGB565 **Little-Endian** — standard LE byte order |
| `rgb565_be` | RGB565 **Big-Endian** — **default**, most common for Dexcom resource files |
| `bgr565` | BGR565 Little-Endian — blue and red channels swapped |

> **Default:** `rgb565_be` (RGB565 Big-Endian)

#### Checkboxes

| Checkbox | Default | Description |
|----------|---------|-------------|
| **Generate Combined Image** | ✅ On | Creates a single `all_fonts_combined.png` grid with every glyph/icon. The grid auto-sizes based on the number of images. |
| **Generate Paginated Images** | ✅ On | Creates `font_page_N.png` files with 100 images per page. Easier to browse for large font sets. |
| **Generate PDF with Address Table** | ✅ On | Creates `font_address_table.pdf` — a landscape A4 PDF with a table containing: Index, Thumbnail, Size (W×H), Start Address (hex), End Address (hex), Byte Size. Font glyphs are scaled to max 40px height; icon images are shown at exact original size. |
| **Include Icon Images** | ❌ Off | When enabled, icon images (from the `icons[]` array) are included alongside font glyphs in the combined/paginated images **and** get their own dedicated section in the PDF. |

### Progress Section

- **Progress Bar** — shows real-time percentage completion during extraction and generation.
- **Status Label** — displays the current operation (e.g., "Extracting images: 500/1200", "Generating pages", "PDF generated").

### Action Buttons

| Button | Action |
|--------|--------|
| **🖼️ GENERATE IMAGES** | Runs the full generation pipeline: creates a timestamped output subfolder, extracts images, generates selected outputs, then auto-opens the combined image, PDF, and output folder. |
| **🗑️ Clear Output** | Deletes previously generated files (`font_page_*.png`, `all_fonts_combined.png`, `font_address_table.pdf`, test images) from the current output directory. |

---

## Output Files

Each generation run creates a **timestamped subfolder** inside the output directory:

```
output/
├── 2026-03-04_16-31-35/
│   ├── all_fonts_combined.png       ← Combined grid image
│   ├── font_page_1.png             ← Page 1 (images 0–99)
│   ├── font_page_2.png             ← Page 2 (images 100–199)
│   ├── ...
│   └── font_address_table.pdf      ← Address table PDF
├── 2026-03-04_19-11-40/
│   └── ...
```

### Combined Image (`all_fonts_combined.png`)

- All glyphs laid out in a square-ish grid.
- Each cell is sized to the largest glyph + 2px padding.
- White background. Smaller glyphs are centered in their cell.

### Paginated Images (`font_page_N.png`)

- 100 images per page.
- Same grid layout as the combined image, but split for manageability.

### PDF Address Table (`font_address_table.pdf`)

- **Landscape A4** format.
- **Font Images table** (blue header): Index, Thumbnail (max 40px height), Size, Start Address, End Address, Bytes.
- **Icon Images table** (green header, if included): Same columns but thumbnails shown at **exact original size** — no scaling.
- Alternating row colors for readability.
- Monospace font for hex addresses.

---

## Color Format Reference

All pixel data in `resource.bin` is stored as **2 bytes per pixel** (16-bit color). The tool supports four decoding modes:

| Format | Byte Order | Channel Layout | Bits |
|--------|-----------|----------------|------|
| `rgb565_be` | Big-Endian | R(5) G(6) B(5) | 16-bit |
| `rgb565` | Little-Endian | R(5) G(6) B(5) | 16-bit |
| `bgr565` | Little-Endian | B(5) G(6) R(5) | 16-bit |
| `gray16` | N/A | Grayscale (8-bit in 16-bit word) | 16-bit |

The conversion expands to 8 bits per channel (RGB888) for PNG output.

---

## Output Folder Management

- **Default location:** `output/` subfolder next to the script or EXE.
- **Browsable:** Use the **Browse** button next to "Output Dir" to change it.
- **Not auto-changed:** Selecting or changing input files does **not** modify the output directory.
- **Timestamped subfolders:** Each generation run creates a subfolder like `2026-03-04_16-31-35/`.
- **Auto-cleanup:** A maximum of **6 subfolders** are kept. When generating a 7th, the oldest subfolder is automatically deleted.
- **Manual cleanup:** Use the **🗑️ Clear Output** button to remove generated files.

---

## Building the EXE

To create a standalone Windows executable from the Python source:

```bash
# Install PyInstaller (one-time)
pip install pyinstaller

# Build single-file windowed EXE
pyinstaller --onefile --windowed --name "FontVisualizer" font_visualiser.py
```

The EXE is created at `dist/FontVisualizer.exe`. Build artifacts in `build/` and `FontVisualizer.spec` can be deleted after building.

### EXE Behavior Notes

- The EXE detects it is running as a frozen PyInstaller bundle and resolves the `output/` folder relative to the **EXE's location** (not a temp directory).
- File size is approximately 30–50 MB (bundles Python runtime + all libraries).
- First launch may take a few seconds as the bundled files are extracted.

---

## Limitations

| Limitation | Details |
|------------|---------|
| **Windows only** | The EXE is Windows-specific. The Python script can theoretically run on macOS/Linux but `os.startfile()` is Windows-only (folder/file auto-open will fail on other OSes). |
| **16-bit color only** | Only 16-bit pixel formats are supported (RGB565, BGR565, Grayscale-16). True color (24-bit/32-bit) images are not handled. |
| **Fixed array naming** | The parser expects C arrays named exactly `chars[]` and `icons[]` of type `resourceImageDescriptor_t` with offset pattern `RES_PRIMARY_FA_OFFSET + <number>`. Different naming conventions will not be detected. |
| **No animation support** | Only static images are extracted. Animated sequences or sprite sheets are not interpreted. |
| **Single bin file** | Only one `resource.bin` can be processed at a time. |
| **No image editing** | This is a read-only visualization tool. It cannot modify or write back to `resource.bin`. |
| **Max 6 output folders** | Only the 6 most recent timestamped output subfolders are retained. Older ones are automatically deleted. |
| **PDF sizing** | Very large icon images may overflow PDF table cells. Font glyph thumbnails are capped at 40px height in the PDF. |
| **No multi-language separation** | While `NumLanguages` is parsed and displayed, the tool does not separate font images by language — all images are rendered together. |
| **Antivirus false positives** | PyInstaller EXEs are occasionally flagged by antivirus software. This is a known PyInstaller issue, not a security concern. |

---

## Troubleshooting

### "Could not find chars array definition in resource.c"

The parser expects the exact pattern:
```c
const resourceImageDescriptor_t chars[NumFontImages] = {
    {width, height, RES_PRIMARY_FA_OFFSET + offset},
    ...
};
```
Verify your `resource.c` uses this exact naming and structure.

### Images appear garbled or wrong colors

Try a different **Color Format** in the dropdown. The most common format is `rgb565_be` (Big-Endian). If colors look inverted, try `bgr565`. If the image looks like static noise, the offset or format may be incorrect.

### EXE won't start — missing DLL error

Install the **Microsoft Visual C++ Redistributable**:  
[Download vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)

### EXE is slow to start

Normal for PyInstaller `--onefile` builds. The first launch extracts bundled files to a temp directory. Subsequent launches may be faster if the temp cache is preserved.

### "Failed to generate images" error

- Ensure `resource.bin` is accessible and not locked by another process.
- Ensure the output directory is writable.
- Check that the parsed configuration matches the actual binary (correct number of images, valid offsets).

---

## FAQ

**Q: Can I use this on a machine without Python?**  
A: Yes. Use the `FontVisualizer.exe` — it bundles everything needed.

**Q: Does selecting a new resource.c change my output folder?**  
A: No. The output directory only changes when you explicitly use the Browse button for "Output Dir".

**Q: What happens if I run generation multiple times?**  
A: Each run creates a new timestamped subfolder. After 6 runs, the oldest subfolder is automatically deleted.

**Q: Can I include both font glyphs and icons?**  
A: Yes. Check the **Include Icon Images** checkbox before generating.

**Q: What is the PDF useful for?**  
A: It provides a printable reference table with each image's memory address range — useful for debugging firmware resource layouts or verifying binary contents.

**Q: Can I change the number of images per page?**  
A: Not from the GUI. The default is 100 images per page. This can be changed in the source code by modifying the `images_per_page` parameter in `generate_paginated_images()`.

---

> _Last updated: March 2026_
# G7-Falcon-Reciever-Flash-Images-Visualiser
