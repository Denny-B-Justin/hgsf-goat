import re
import os
import fitz
from typing import Optional, Union
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from marker.output import text_from_rendered


def convert_to_markdown(
    filepath: str,
    output_dir: Optional[str] = None,
    skip_pages: Optional[Union[str, list]] = None,
    annexure: Optional[str] = None,
    abbreviation: Optional[str] = None
) -> str:
    """
    Convert PDF to markdown with optional page skipping.
    
    Args:
        filepath: Path to PDF file (required)
        output_dir: Output directory (default: same as PDF directory)  
        skip_pages: Pages to skip - "1-3,5" or [1,2,3,5] (default: None)
        annexure: Annexure info (default: None)
        abbreviation: Abbreviation info (default: None)
        
    Returns:
        Path to generated markdown file
    """
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"PDF not found: {filepath}")
    
    # Set default output directory
    if output_dir is None:
        output_dir = os.path.dirname(filepath)
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    
    # Get total pages and parse all skip pages
    with fitz.open(filepath) as doc:
        total_pages = len(doc)
    
    skip_list = []
    
    # Parse skip_pages parameter
    if skip_pages:
        if isinstance(skip_pages, str):
            for part in re.findall(r"\d+(?:-\d+)?", skip_pages):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    skip_list.extend([i - 1 for i in range(start, end + 1) if 1 <= i <= total_pages])
                else:
                    page_num = int(part)
                    if 1 <= page_num <= total_pages:
                        skip_list.append(page_num - 1)
        else:
            skip_list = [p - 1 if p > 0 else p for p in skip_pages if 0 <= p - 1 < total_pages]
    
    # Add annexure pages to skip list
    if annexure:
        if isinstance(annexure, str):
            for part in re.findall(r"\d+(?:-\d+)?", annexure):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    skip_list.extend([i - 1 for i in range(start, end + 1) if 1 <= i <= total_pages])
                else:
                    page_num = int(part)
                    if 1 <= page_num <= total_pages:
                        skip_list.append(page_num - 1)
        elif isinstance(annexure, list):
            skip_list.extend([p - 1 if p > 0 else p for p in annexure if 0 <= p - 1 < total_pages])
    
    # Add abbreviation pages to skip list  
    if abbreviation:
        if isinstance(abbreviation, str):
            for part in re.findall(r"\d+(?:-\d+)?", abbreviation):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    skip_list.extend([i - 1 for i in range(start, end + 1) if 1 <= i <= total_pages])
                else:
                    page_num = int(part)
                    if 1 <= page_num <= total_pages:
                        skip_list.append(page_num - 1)
        elif isinstance(abbreviation, list):
            skip_list.extend([p - 1 if p > 0 else p for p in abbreviation if 0 <= p - 1 < total_pages])
    
    # Remove duplicates
    skip_list = list(set(skip_list))
    
    # Generate page range
    all_pages = set(range(total_pages))
    valid_pages = sorted(all_pages - set(skip_list))
    
    if not valid_pages:
        raise ValueError("All pages skipped")
    
    ranges = []
    start = prev = valid_pages[0]
    for p in valid_pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = p
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    page_range = ",".join(ranges)
    
    # Configure and convert
    config = {
        "output_format": "markdown",
        "disable_image_extraction": True,
        "output_dir": output_dir,
        "page_range": page_range
    }

    
    config_parser = ConfigParser(config)
    converter = PdfConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=create_model_dict(),
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer()
    )
    
    rendered = converter(filepath)
    markdown_text,_,_ = text_from_rendered(rendered)
    
    # Save files
    md_path = os.path.join(output_dir, f"{base_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    
    return md_path

