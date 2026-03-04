"""
Font Visualizer for Resource Binary Files
==========================================
This tool extracts and visualizes font images from resource.bin files
based on metadata defined in resource.c and resource.h files.

Features:
- Dynamically parses limits and data from resource files
- GUI for selecting input files
- Generates combined font image and paginated images

IMPORTANT: Color format is ALWAYS RGB565 Big-Endian (fixed).
Only the following vary between resource files:
- Number of fonts/images (NumFontImages, NumIconImages)
- Image dimensions (width, height)
- Data offsets
"""

import struct
import re
import os
import sys
import io
import tempfile
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
from math import ceil
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from datetime import datetime

# Fixed output directory for the app (works both as script and as PyInstaller exe)
if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_OUTPUT_DIR = os.path.join(_APP_DIR, 'output')
MAX_OUTPUT_SUBFOLDERS = 6

# PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


@dataclass
class ResourceConfig:
    """Configuration parsed from resource files."""
    num_fonts: int = 0
    num_font_images: int = 0
    num_icon_images: int = 0
    num_languages: int = 0
    res_primary_fa_offset: int = 0
    graphics_address: int = 0
    graphics_num_bytes: int = 0
    audio_address: int = 0
    audio_num_bytes: int = 0
    total_num_bytes: int = 0


@dataclass
class FontImage:
    """Represents a single font image descriptor."""
    width: int
    height: int
    offset: int


def parse_define_value(content: str, define_name: str) -> Optional[int]:
    """Parse a #define value from C source code."""
    pattern = rf'#define\s+{define_name}\s+(\d+)'
    match = re.search(pattern, content)
    if match:
        return int(match.group(1))
    return None


def parse_resource_config(resource_c_path: str, resource_h_path: str) -> ResourceConfig:
    """Parse configuration values from resource.c and resource.h files."""
    config = ResourceConfig()
    
    # Read both files
    content = ""
    for path in [resource_c_path, resource_h_path]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content += f.read() + "\n"
    
    # Parse all known defines
    defines = {
        'NumFonts': 'num_fonts',
        'NumFontImages': 'num_font_images',
        'NumIconImages': 'num_icon_images',
        'NumLanguages': 'num_languages',
        'UIResourceFileNumLanguages': 'num_languages',
        'UIResourceFileGraphicsNumBytes': 'graphics_num_bytes',
        'UIResourceFileAudioNumBytes': 'audio_num_bytes',
        'UIResourceFileNumBytes': 'total_num_bytes',
    }
    
    for define_name, attr_name in defines.items():
        value = parse_define_value(content, define_name)
        if value is not None:
            setattr(config, attr_name, value)
    
    # RES_PRIMARY_FA_OFFSET is typically 0 for bin file reading
    config.res_primary_fa_offset = 0
    
    return config


def parse_font_images(resource_c_path: str, config: ResourceConfig) -> List[FontImage]:
    """Parse font image descriptors from resource.c."""
    font_images = []
    
    if not os.path.exists(resource_c_path):
        print(f"Error: {resource_c_path} not found")
        return font_images
    
    with open(resource_c_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Find the chars array DEFINITION (with '= {'), not just declaration
    # Pattern: const resourceImageDescriptor_t chars[...] = {
    chars_def_match = re.search(
        r'const\s+resourceImageDescriptor_t\s+chars\s*\[\s*\w*\s*\]\s*=\s*\{',
        content
    )
    
    if not chars_def_match:
        print("Error: Could not find chars array definition in resource.c")
        return font_images
    
    chars_start = chars_def_match.start()
    
    # Find the icons array DEFINITION to know where chars section ends
    icons_def_match = re.search(
        r'const\s+resourceImageDescriptor_t\s+icons\s*\[\s*\w*\s*\]\s*=\s*\{',
        content
    )
    icons_start = icons_def_match.start() if icons_def_match else -1
    
    # Extract only the chars array section
    if icons_start != -1 and icons_start > chars_start:
        chars_section = content[chars_start:icons_start]
    else:
        chars_section = content[chars_start:]
    
    # Pattern to match: {width, height, RES_PRIMARY_FA_OFFSET + offset}
    pattern = r'\{(\d+),\s*(\d+),\s*RES_PRIMARY_FA_OFFSET\s*\+\s*(\d+)\}'
    matches = re.findall(pattern, chars_section)
    
    # Limit to NumFontImages if specified
    max_images = config.num_font_images if config.num_font_images > 0 else len(matches)
    
    for i, match in enumerate(matches):
        if i >= max_images:
            break
        font_images.append(FontImage(
            width=int(match[0]),
            height=int(match[1]),
            offset=int(match[2])
        ))
    
    return font_images


def parse_icon_images(resource_c_path: str, config: ResourceConfig) -> List[FontImage]:
    """Parse icon image descriptors from resource.c."""
    icon_images = []
    
    if not os.path.exists(resource_c_path):
        return icon_images
    
    with open(resource_c_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Find the icons array DEFINITION (with '= {'), not just declaration
    icons_def_match = re.search(
        r'const\s+resourceImageDescriptor_t\s+icons\s*\[\s*\w*\s*\]\s*=\s*\{',
        content
    )
    
    if not icons_def_match:
        return icon_images
    
    icons_section = content[icons_def_match.start():]
    
    # Pattern to match: {width, height, RES_PRIMARY_FA_OFFSET + offset}
    pattern = r'\{(\d+),\s*(\d+),\s*RES_PRIMARY_FA_OFFSET\s*\+\s*(\d+)\}'
    matches = re.findall(pattern, icons_section)
    
    # Limit to NumIconImages if specified
    max_images = config.num_icon_images if config.num_icon_images > 0 else len(matches)
    
    for i, match in enumerate(matches):
        if i >= max_images:
            break
        icon_images.append(FontImage(
            width=int(match[0]),
            height=int(match[1]),
            offset=int(match[2])
        ))
    
    return icon_images


def get_output_subfolder(base_output_dir: str = None) -> str:
    """Create and return a timestamped output subfolder, managing max 6 subfolders."""
    output_dir = base_output_dir if base_output_dir else APP_OUTPUT_DIR
    
    # Ensure the main output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Get existing subfolders sorted by creation time
    subfolders = []
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isdir(item_path):
            subfolders.append((item_path, os.path.getctime(item_path)))
    
    # Sort by creation time (oldest first)
    subfolders.sort(key=lambda x: x[1])
    
    # Delete oldest subfolders if we have MAX_OUTPUT_SUBFOLDERS or more
    while len(subfolders) >= MAX_OUTPUT_SUBFOLDERS:
        oldest_folder = subfolders.pop(0)[0]
        try:
            shutil.rmtree(oldest_folder)
            print(f"Deleted old output folder: {os.path.basename(oldest_folder)}")
        except Exception as e:
            print(f"Error deleting {oldest_folder}: {e}")
    
    # Create new timestamped subfolder
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    new_subfolder = os.path.join(output_dir, timestamp)
    os.makedirs(new_subfolder, exist_ok=True)
    print(f"Output folder created: {new_subfolder}")
    
    return new_subfolder


def open_output_folder(folder_path: str):
    """Open the output folder in the system file explorer."""
    try:
        if os.name == 'nt':  # Windows
            os.startfile(folder_path)
        else:  # macOS/Linux
            import subprocess
            subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', folder_path])
        print(f"Opened output folder: {folder_path}")
    except Exception as e:
        print(f"Could not open folder: {e}")


def read_bin_file(file_path: str, offset: int, size: int) -> Optional[bytes]:
    """Read a specific portion of the binary file."""
    try:
        with open(file_path, 'rb') as file:
            file.seek(offset)
            data = file.read(size)
            return data
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error reading bin file: {e}")
        return None


def rgb565_to_rgb888(pixel_data: bytes, color_format: str = 'rgb565_be') -> List[Tuple[int, int, int]]:
    """
    Converts pixel data to RGB888.
    Supports different color formats:
    - 'rgb565': RGB565 little-endian
    - 'rgb565_be': RGB565 big-endian
    - 'bgr565': BGR565 little-endian
    - 'gray16': 8-bit grayscale stored in 16-bit (uses first byte)
    """
    rgb888_data = []
    for i in range(0, len(pixel_data), 2):
        if i + 1 >= len(pixel_data):
            break

        # Grayscale format - just use first byte
        if color_format == 'gray16':
            gray = pixel_data[i]
            rgb888_data.append((gray, gray, gray))
            continue

        # Read two bytes
        if color_format == 'rgb565_be':
            rgb565 = struct.unpack('>H', pixel_data[i:i+2])[0]  # Big-endian
        else:
            rgb565 = struct.unpack('<H', pixel_data[i:i+2])[0]  # Little-endian

        if color_format == 'bgr565':
            b = (rgb565 >> 11) & 0x1F
            g = (rgb565 >> 5) & 0x3F
            r = rgb565 & 0x1F
        else:
            r = (rgb565 >> 11) & 0x1F
            g = (rgb565 >> 5) & 0x3F
            b = rgb565 & 0x1F

        # Convert to 8-bit per channel
        r = (r << 3) | (r >> 2)
        g = (g << 2) | (g >> 4)
        b = (b << 3) | (b >> 2)

        rgb888_data.append((r, g, b))

    return rgb888_data


def create_image(width: int, height: int, rgb888_data: List[Tuple[int, int, int]]) -> Image.Image:
    """Creates an image from the RGB888 data."""
    expected_size = width * height
    if len(rgb888_data) > expected_size:
        rgb888_data = rgb888_data[:expected_size]
    elif len(rgb888_data) < expected_size:
        rgb888_data.extend([(0, 0, 0)] * (expected_size - len(rgb888_data)))

    image = Image.new('RGB', (width, height))
    image.putdata(rgb888_data)
    return image


def extract_font_image(bin_path: str, font_image: FontImage, color_format: str = 'rgb565_be') -> Optional[Image.Image]:
    """Extract a single font image from the binary file."""
    pixel_data_size = font_image.width * font_image.height * 2
    pixel_data = read_bin_file(bin_path, font_image.offset, pixel_data_size)
    
    if not pixel_data:
        return None
    
    rgb888_data = rgb565_to_rgb888(pixel_data, color_format)
    return create_image(font_image.width, font_image.height, rgb888_data)


def generate_combined_image(
    font_images: List[FontImage],
    bin_path: str,
    output_path: str,
    color_format: str = 'rgb565_be',
    background_color: Tuple[int, int, int] = (255, 255, 255),
    progress_callback=None
) -> Optional[Image.Image]:
    """Generate a single combined image of all font characters."""
    
    if not font_images:
        print("No font images to process")
        return None
    
    # Extract all images and find dimensions
    all_images = []
    max_width = 0
    max_height = 0
    
    total = len(font_images)
    for i, font_image in enumerate(font_images):
        img = extract_font_image(bin_path, font_image, color_format)
        if img:
            all_images.append(img)
            max_width = max(max_width, font_image.width)
            max_height = max(max_height, font_image.height)
        
        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(i + 1, total, "Extracting images")
    
    if not all_images:
        print("No images could be extracted")
        return None
    
    # Calculate grid dimensions
    cell_width = max_width + 2
    cell_height = max_height + 2
    
    total_images = len(all_images)
    grid_cols = ceil(total_images ** 0.5)
    grid_rows = ceil(total_images / grid_cols)
    
    total_width = grid_cols * cell_width
    total_height = grid_rows * cell_height
    
    # Create combined image
    combined_image = Image.new('RGB', (total_width, total_height), background_color)
    
    # Place images
    for idx, image in enumerate(all_images):
        row = idx // grid_cols
        col = idx % grid_cols
        
        x_pos = col * cell_width + (cell_width - image.width) // 2
        y_pos = row * cell_height + (cell_height - image.height) // 2
        
        combined_image.paste(image, (x_pos, y_pos))
        
        if progress_callback and (idx + 1) % 500 == 0:
            progress_callback(idx + 1, len(all_images), "Arranging images")
    
    # Save
    combined_image.save(output_path)
    print(f"Saved combined image: {output_path} ({total_width}x{total_height} pixels)")
    
    return combined_image


def generate_paginated_images(
    font_images: List[FontImage],
    bin_path: str,
    output_dir: str,
    images_per_page: int = 100,
    color_format: str = 'rgb565_be',
    background_color: Tuple[int, int, int] = (255, 255, 255),
    progress_callback=None
) -> int:
    """Generate paginated images of font characters."""
    
    if not font_images:
        return 0
    
    total_images = len(font_images)
    total_pages = ceil(total_images / images_per_page)
    page_number = 1
    
    for page_start in range(0, total_images, images_per_page):
        page_images = font_images[page_start:page_start + images_per_page]
        images = []
        max_width = 0
        max_height = 0
        
        for font_image in page_images:
            img = extract_font_image(bin_path, font_image, color_format)
            if img:
                images.append(img)
                max_width = max(max_width, font_image.width)
                max_height = max(max_height, font_image.height)
        
        if not images:
            page_number += 1
            continue
        
        # Create page grid
        cell_width = max_width + 2
        cell_height = max_height + 2
        
        grid_cols = ceil(len(images) ** 0.5)
        grid_rows = ceil(len(images) / grid_cols)
        
        page_width = grid_cols * cell_width
        page_height = grid_rows * cell_height
        
        page_image = Image.new('RGB', (page_width, page_height), background_color)
        
        for idx, image in enumerate(images):
            row = idx // grid_cols
            col = idx % grid_cols
            x_pos = col * cell_width + (cell_width - image.width) // 2
            y_pos = row * cell_height + (cell_height - image.height) // 2
            page_image.paste(image, (x_pos, y_pos))
        
        output_path = os.path.join(output_dir, f'font_page_{page_number}.png')
        page_image.save(output_path)
        
        if progress_callback:
            progress_callback(page_number, total_pages, "Generating pages")
        
        page_number += 1
    
    return page_number - 1


def generate_pdf_with_addresses(
    font_images: List[FontImage],
    icon_images: List[FontImage],
    bin_path: str,
    output_path: str,
    color_format: str = 'rgb565_be',
    progress_callback=None
) -> str:
    """
    Generate a PDF with tables listing font and icon images with:
    - Index
    - Thumbnail image
    - Width x Height
    - Start Address (hex)
    - End Address (hex)
    - Size (bytes)
    """
    
    # Create PDF document in landscape for more width
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=10*mm,
        leftMargin=10*mm,
        topMargin=10*mm,
        bottomMargin=10*mm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=10
    )
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=15,
        textColor=colors.darkblue
    )
    
    elements = []
    
    # Create temporary directory for thumbnails
    temp_dir = tempfile.mkdtemp()
    thumb_counter = 0
    
    def create_image_table(images: List[FontImage], section_title: str, header_color):
        """Helper function to create a table for font glyph images (scaled to max 40px height)."""
        nonlocal thumb_counter
        
        if not images:
            return None
        
        # Section header
        elements.append(Paragraph(section_title, section_style))
        elements.append(Spacer(1, 3*mm))
        
        # Prepare table data
        table_data = [['Index', 'Image', 'Size (WxH)', 'Start Address', 'End Address', 'Bytes']]
        
        total = len(images)
        for i, font_image in enumerate(images):
            # Calculate addresses
            start_addr = font_image.offset
            pixel_size = font_image.width * font_image.height * 2  # 2 bytes per pixel (RGB565)
            end_addr = start_addr + pixel_size - 1
            
            # Extract and save thumbnail
            img = extract_font_image(bin_path, font_image, color_format)
            if img:
                # Scale image if too large (max 40 pixels height for table)
                max_thumb_height = 40
                if img.height > max_thumb_height:
                    scale = max_thumb_height / img.height
                    new_width = int(img.width * scale)
                    img = img.resize((new_width, max_thumb_height), Image.Resampling.LANCZOS)
                
                # Save to temp file
                thumb_path = os.path.join(temp_dir, f'thumb_{thumb_counter}.png')
                thumb_counter += 1
                img.save(thumb_path)
                
                # Create reportlab image
                rl_img = RLImage(thumb_path, width=img.width, height=img.height)
            else:
                rl_img = "N/A"
            
            table_data.append([
                str(i),
                rl_img,
                f"{font_image.width}x{font_image.height}",
                f"0x{start_addr:08X}",
                f"0x{end_addr:08X}",
                str(pixel_size)
            ])
            
            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total, f"Creating PDF ({section_title})")
        
        # Create table
        col_widths = [40, 80, 60, 90, 90, 50]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style the table
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Data rows style
            ('FONTNAME', (0, 1), (-1, -1), 'Courier'),  # Monospace for addresses
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ]))
        
        elements.append(table)
    
    def create_icon_table(images: List[FontImage], section_title: str, header_color):
        """Create table for icon images (exact size, no scaling)."""
        nonlocal thumb_counter
        
        if not images:
            return None
        
        # Section header
        elements.append(Paragraph(section_title, section_style))
        elements.append(Spacer(1, 3*mm))
        
        # Prepare table data
        table_data = [['Index', 'Icon Image (Exact Size)', 'Size (WxH)', 'Start Address', 'End Address', 'Bytes']]
        
        total = len(images)
        for i, icon_image in enumerate(images):
            # Calculate addresses
            start_addr = icon_image.offset
            pixel_size = icon_image.width * icon_image.height * 2  # 2 bytes per pixel (RGB565)
            end_addr = start_addr + pixel_size - 1
            
            # Extract icon at EXACT original size - no scaling
            img = extract_font_image(bin_path, icon_image, color_format)
            if img:
                # Save to temp file at original size
                thumb_path = os.path.join(temp_dir, f'thumb_{thumb_counter}.png')
                thumb_counter += 1
                img.save(thumb_path)
                
                # Create reportlab image at EXACT original dimensions
                rl_img = RLImage(thumb_path, width=icon_image.width, height=icon_image.height)
            else:
                rl_img = "N/A"
            
            table_data.append([
                str(i),
                rl_img,
                f"{icon_image.width}x{icon_image.height}",
                f"0x{start_addr:08X}",
                f"0x{end_addr:08X}",
                str(pixel_size)
            ])
            
            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total, f"Creating PDF ({section_title})")
        
        # Icon table column widths (wider columns to fit icons properly)
        col_widths = [50, 250, 80, 100, 100, 70]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style the table
        table.setStyle(TableStyle([
            # Header style
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Data rows style
            ('FONTNAME', (0, 1), (-1, -1), 'Courier'),  # Monospace for addresses
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ]))
        
        elements.append(table)
    
    # Main Title
    elements.append(Paragraph("Resource Images Memory Address Table", title_style))
    elements.append(Spacer(1, 5*mm))
    
    # Font Images Section
    create_image_table(font_images, f"Font Images ({len(font_images)} items)", colors.darkblue)
    
    # Icon Images Section (exact sizes, no scaling)
    if icon_images:
        elements.append(Spacer(1, 10*mm))  # Add space between sections
        create_icon_table(icon_images, f"Icon Images ({len(icon_images)} items)", colors.darkgreen)
    
    # Build PDF
    doc.build(elements)
    
    # Cleanup temp files
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    return output_path


class FontVisualizerGUI:
    """GUI for the Font Visualizer application."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Resource Font Visualizer")
        self.root.geometry("750x750")
        self.root.resizable(True, True)
        
        # Variables
        self.resource_c_path = tk.StringVar()
        self.resource_h_path = tk.StringVar()
        self.resource_bin_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=APP_OUTPUT_DIR)
        self.color_format = tk.StringVar(value='rgb565_be')  # RGB565 Big-Endian for colored fonts
        self.generate_combined = tk.BooleanVar(value=True)
        self.generate_pages = tk.BooleanVar(value=True)
        self.generate_pdf = tk.BooleanVar(value=True)
        self.include_icons = tk.BooleanVar(value=False)
        
        self.config: Optional[ResourceConfig] = None
        self.font_images: List[FontImage] = []
        self.icon_images: List[FontImage] = []
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create GUI widgets."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # File Selection Section
        file_frame = ttk.LabelFrame(main_frame, text="Input Files", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Resource.c
        ttk.Label(file_frame, text="resource.c:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.resource_c_path, width=50).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse", command=lambda: self._browse_file('c')).grid(row=0, column=2, pady=2)
        
        # Resource.h
        ttk.Label(file_frame, text="resource.h:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.resource_h_path, width=50).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse", command=lambda: self._browse_file('h')).grid(row=1, column=2, pady=2)
        
        # Resource.bin
        ttk.Label(file_frame, text="resource.bin:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.resource_bin_path, width=50).grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse", command=lambda: self._browse_file('bin')).grid(row=2, column=2, pady=2)
        
        # Output Directory
        ttk.Label(file_frame, text="Output Dir:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.output_dir, width=50).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="Browse", command=self._browse_output_dir).grid(row=3, column=2, pady=2)
        
        # Parse Button
        ttk.Button(file_frame, text="Parse Resource Files", command=self._parse_files).grid(row=4, column=1, pady=10)
        
        # Configuration Display Section
        config_frame = ttk.LabelFrame(main_frame, text="Parsed Configuration", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.config_text = tk.Text(config_frame, height=8, width=80, state=tk.DISABLED)
        self.config_text.pack(fill=tk.X)
        
        # Options Section
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Color Format
        ttk.Label(options_frame, text="Color Format:").grid(row=0, column=0, sticky=tk.W)
        color_combo = ttk.Combobox(options_frame, textvariable=self.color_format, 
                                   values=['gray16', 'rgb565', 'rgb565_be', 'bgr565'], state='readonly', width=15)
        color_combo.grid(row=0, column=1, padx=10, sticky=tk.W)
        ttk.Label(options_frame, text="(gray16=Grayscale, rgb565=LE, rgb565_be=BE)").grid(row=0, column=2, sticky=tk.W)
        
        # Checkboxes
        ttk.Checkbutton(options_frame, text="Generate Combined Image", variable=self.generate_combined).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Checkbutton(options_frame, text="Generate Paginated Images", variable=self.generate_pages).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Checkbutton(options_frame, text="Generate PDF with Address Table", variable=self.generate_pdf).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        ttk.Checkbutton(options_frame, text="Include Icon Images", variable=self.include_icons).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Progress Section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.pack(anchor=tk.W)
        
        # Generate Button Frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.generate_btn = ttk.Button(btn_frame, text="🖼️ GENERATE IMAGES", command=self._generate_images)
        self.generate_btn.pack(side=tk.LEFT, padx=5, ipadx=20, ipady=10)
        
        self.clear_btn = ttk.Button(btn_frame, text="🗑️ Clear Output", command=self._clear_output)
        self.clear_btn.pack(side=tk.LEFT, padx=5, ipadx=10, ipady=10)
    
    def _browse_file(self, file_type: str):
        """Browse for a file."""
        if file_type == 'c':
            filetypes = [("C Source Files", "*.c"), ("All Files", "*.*")]
            var = self.resource_c_path
        elif file_type == 'h':
            filetypes = [("C Header Files", "*.h"), ("All Files", "*.*")]
            var = self.resource_h_path
        else:
            filetypes = [("Binary Files", "*.bin"), ("All Files", "*.*")]
            var = self.resource_bin_path
        
        filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)
            # Auto-detect related files
            self._auto_detect_files(filename)
    
    def _auto_detect_files(self, selected_file: str):
        """Auto-detect related resource files in the same directory."""
        directory = os.path.dirname(selected_file)
        basename = os.path.basename(selected_file)
        
        # Try to find matching files
        if not self.resource_c_path.get():
            c_path = os.path.join(directory, 'resource.c')
            if os.path.exists(c_path):
                self.resource_c_path.set(c_path)
        
        if not self.resource_h_path.get():
            h_path = os.path.join(directory, 'resource.h')
            if os.path.exists(h_path):
                self.resource_h_path.set(h_path)
        
        if not self.resource_bin_path.get():
            bin_path = os.path.join(directory, 'resource.bin')
            if os.path.exists(bin_path):
                self.resource_bin_path.set(bin_path)
    
    def _browse_output_dir(self):
        """Browse for output directory."""
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir.set(directory)
    
    def _parse_files(self):
        """Parse the resource files."""
        c_path = self.resource_c_path.get()
        h_path = self.resource_h_path.get()
        
        if not c_path:
            messagebox.showerror("Error", "Please select resource.c file")
            return
        
        try:
            # Parse configuration
            self.config = parse_resource_config(c_path, h_path)
            
            # Parse font images
            self.font_images = parse_font_images(c_path, self.config)
            
            # Parse icon images
            self.icon_images = parse_icon_images(c_path, self.config)
            
            # Update display
            self.config_text.config(state=tk.NORMAL)
            self.config_text.delete(1.0, tk.END)
            
            info = f"""Configuration parsed successfully!

Number of Fonts: {self.config.num_fonts}
Number of Font Images: {self.config.num_font_images} (Found: {len(self.font_images)})
Number of Icon Images: {self.config.num_icon_images} (Found: {len(self.icon_images)})
Number of Languages: {self.config.num_languages}
Graphics Size: {self.config.graphics_num_bytes:,} bytes
Audio Size: {self.config.audio_num_bytes:,} bytes
Total Size: {self.config.total_num_bytes:,} bytes
"""
            self.config_text.insert(tk.END, info)
            self.config_text.config(state=tk.DISABLED)
            
            self.status_label.config(text=f"Parsed {len(self.font_images)} font images and {len(self.icon_images)} icon images")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse files: {str(e)}")
    
    def _update_progress(self, current: int, total: int, message: str):
        """Update progress bar and status."""
        progress = (current / total) * 100 if total > 0 else 0
        self.progress_var.set(progress)
        self.status_label.config(text=f"{message}: {current}/{total}")
        self.root.update_idletasks()
    
    def _clear_generated_files(self, output_dir: str) -> int:
        """Clear all previously generated image and PDF files."""
        cleared_count = 0
        if not os.path.exists(output_dir):
            return 0
        
        for f in os.listdir(output_dir):
            # Clear font page images, combined image, test images, and PDF
            if (f.startswith('font_page_') and f.endswith('.png')) or \
               f == 'all_fonts_combined.png' or \
               f == 'font_address_table.pdf' or \
               (f.startswith('test_') and f.endswith('.png')) or \
               f == 'char_visualisation.png' or \
               f == 'all_chars_visualisation.png':
                try:
                    os.remove(os.path.join(output_dir, f))
                    cleared_count += 1
                    print(f"Deleted: {f}")
                except Exception as e:
                    print(f"Error deleting {f}: {e}")
        
        return cleared_count
    
    def _clear_output(self):
        """Clear output directory button handler."""
        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory first")
            return
        
        if not os.path.exists(output_dir):
            messagebox.showinfo("Info", "Output directory does not exist yet")
            return
        
        cleared = self._clear_generated_files(output_dir)
        self.status_label.config(text=f"Cleared {cleared} generated files")
        messagebox.showinfo("Cleared", f"Removed {cleared} generated image files from:\n{output_dir}")
    
    def _generate_images(self):
        """Generate the output images."""
        bin_path = self.resource_bin_path.get()
        
        if not bin_path or not os.path.exists(bin_path):
            messagebox.showerror("Error", "Please select a valid resource.bin file")
            return
        
        if not self.font_images:
            messagebox.showerror("Error", "Please parse resource files first")
            return
        
        # Create timestamped output subfolder (manages max 6 subfolders automatically)
        output_dir = get_output_subfolder(self.output_dir.get())
        
        # Prepare image list
        images_to_process = self.font_images.copy()
        if self.include_icons.get():
            images_to_process.extend(self.icon_images)
        
        color_format = self.color_format.get()
        
        try:
            self.generate_btn.config(state=tk.DISABLED)
            
            self.status_label.config(text=f"Output folder: {os.path.basename(output_dir)}. Starting generation...")
            self.root.update_idletasks()
            
            combined_image_path = None
            
            # Generate combined image
            if self.generate_combined.get():
                self.status_label.config(text="Generating combined image...")
                self.root.update_idletasks()
                
                combined_image_path = os.path.join(output_dir, 'all_fonts_combined.png')
                generate_combined_image(
                    images_to_process,
                    bin_path,
                    combined_image_path,
                    color_format,
                    progress_callback=self._update_progress
                )
            
            # Generate paginated images
            if self.generate_pages.get():
                self.status_label.config(text="Generating paginated images...")
                self.root.update_idletasks()
                
                num_pages = generate_paginated_images(
                    images_to_process,
                    bin_path,
                    output_dir,
                    color_format=color_format,
                    progress_callback=self._update_progress
                )
                self.status_label.config(text=f"Generated {num_pages} pages")
            
            pdf_path = None
            
            # Generate PDF with address table
            if self.generate_pdf.get():
                self.status_label.config(text="Generating PDF with address table...")
                self.root.update_idletasks()
                
                pdf_path = os.path.join(output_dir, 'font_address_table.pdf')
                generate_pdf_with_addresses(
                    self.font_images,
                    self.icon_images if self.include_icons.get() else [],
                    bin_path,
                    pdf_path,
                    color_format,
                    progress_callback=self._update_progress
                )
                self.status_label.config(text="PDF generated")
            
            self.progress_var.set(100)
            self.status_label.config(text="Generation complete!")
            messagebox.showinfo("Success", f"Images generated successfully in:\n{output_dir}")
            
            # Open the combined image if it exists
            if combined_image_path and os.path.exists(combined_image_path):
                os.startfile(combined_image_path)
            
            # Open the PDF if it exists
            if pdf_path and os.path.exists(pdf_path):
                os.startfile(pdf_path)
            
            # Open the output folder at the end
            open_output_folder(output_dir)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate images: {str(e)}")
        finally:
            self.generate_btn.config(state=tk.NORMAL)
    
    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point."""
    app = FontVisualizerGUI()
    app.run()


if __name__ == '__main__':
    main()
