import fitz  # PyMuPDF
import re
import os
import json

pdf_path = "/home/aahmad/Desktop/DEV/working-dir/leph101.pdf"
output_image = "/home/aahmad/Desktop/DEV/output/images/"
output_json = "/home/aahmad/Desktop/DEV/output/"

os.makedirs(output_image, exist_ok=True)
os.makedirs(output_json, exist_ok=True)
# os.makedirs(os.path.dirname(output_json), exist_ok=True)

def extract_structure_from_pdf(pdf_path, output_image, output_json):
    # Define skip phrases or patterns
    chapter_pattern = re.compile(r'^\s*Chapter\s+(.*)', re.IGNORECASE)
    # skip_exact_lines = {"Chapter","Reprint 2025-26", "Page", "Exercise", "Figure", "Example"}
    skip_exact_lines = {"Chapter","Page", "Exercise", "Figure", "Example"}
    skip_regex_patterns = [
        re.compile(r'^\s*Page\s+\d+'),           # Matches: Page 2, Page 15
        re.compile(r'^\s*Figure\s+\d+'),         # Matches: Figure 1, etc.
        re.compile(r'^\s*Example\s+\d+'),        # Matches: Example 2, etc.
        re.compile(r'^\s*[\d]+\s*$'),            # Matches lines with just numbers (page numbers)
        ]

    doc = fitz.open(pdf_path)

    section_pattern = re.compile(r'^\s*(\d+\.\d+)\s+(.+)$')
    subsection_pattern = re.compile(r'^\s*(\d+\.\d+\.\d+)\s+(.+)$')

    count = 0
    structured_content = []
    buffer = []
    current_section = None
    current_section_title = None
    current_subsection = None
    current_subsection_title = None

    for page_index, page in enumerate(doc):
        count += 1
        if count == 6:
            break

        page_text = page.get_text().split('\n')
        page_dict = page.get_text("dict")
        page_images = page.get_images(full=True)

        # Reset image_refs per page
        image_refs = []

        for img_index, img in enumerate(page_images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            image_filename = f"page{page_index+1}_img{img_index+1}.{image_ext}"
            image_path = os.path.join(output_image, image_filename)
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            image_refs.append(image_filename)

        
        collecting_title = False
        title_lines = []
        paragraphs = []
        current_para = []
        prev_indent = None

        for line in page_text:
            line_stripped = line.strip()

            chap_match = chapter_pattern.match(line_stripped)
            if chap_match:
                current_chapter = chap_match.group(1).strip()
                collecting_title = True
                title_lines = []
                continue
            
            if collecting_title:
                # Stop when we hit a section heading, blank line, or something we don’t want in title
                if section_pattern.match(line_stripped) or subsection_pattern.match(line_stripped) or not line_stripped:
                    current_chapter_title = " ".join(title_lines).strip()
                    collecting_title = False
                else:
                    title_lines.append(line_stripped)
                    continue 

            # Skip known unwanted lines
            # if line_stripped in skip_exact_lines:
            #     continue
            # if any(pat.match(line_stripped) for pat in skip_regex_patterns):
            #     continue
            
            # current_chapter = None
            # current_chapter_title = None
            
            sub_match = subsection_pattern.match(line)
            sec_match = section_pattern.match(line)

            if sub_match:
                if buffer:
                    structured_content.append({
                        "chapter": current_chapter,
                        "chapter_title ": current_chapter_title,
                        "section": current_section,
                        "section_title": current_section_title,
                        "subsection": current_subsection,
                        "subsection_title": current_subsection_title,
                        "content": "\n".join(buffer).strip(),
                        # "images": image_refs.copy()
                    })
                    buffer = []

                current_subsection = sub_match.group(1)
                # buffer.append(f"Subsection Title: {sub_match.group(2)}")
                current_subsection_title = sub_match.group(2)
                continue

            elif sec_match:
                if buffer:
                    structured_content.append({
                        "chapter": current_chapter,
                        "chapter_title ": current_chapter_title,
                        "section": current_section,
                        "section_title": current_section_title,
                        "subsection": current_subsection,
                        "subsection_title": current_subsection_title,
                        "content": "\n".join(buffer).strip(),
                        # "images": image_refs.copy()
                    })
                    buffer = []

                current_section = sec_match.group(1)
                # buffer.append(f"Section Title: {sec_match.group(2)}")
                current_section_title = sec_match.group(2)
                current_subsection = None
                current_subsection_title = None
                continue

            else:
                if line.strip():
                    buffer.append(line.strip())

    # Save the final buffer
    if buffer:
        structured_content.append({
            "chapter": current_chapter,
            "chapter_title ": current_chapter_title,
            "section": current_section,
            "section_title": current_section_title,
            "subsection": current_subsection,
            "subsection_title": current_subsection_title,
            "content": "\n".join(buffer).strip(),
            # "images": image_refs.copy()
        })

    # Write to JSON
    with open(os.path.join(output_json, "chunking_data.json"), "w") as f:
        json.dump(structured_content, f, indent=2)

    print(f"✅ Chunking completed and saved to {output_json}")


# Run the function
extract_structure_from_pdf(pdf_path, output_image, output_json)
