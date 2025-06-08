import fitz  # PyMuPDF
import re
import os
import json

pdf_path = "/home/aahmad/Desktop/DEV/working-dir/leph101.pdf"
output_image = "/home/aahmad/Desktop/DEV/output/images/"
output_json = "/home/aahmad/Desktop/DEV/output/"

os.makedirs(output_image, exist_ok=True)
os.makedirs(output_json, exist_ok=True)

def extract_structure_from_pdf(pdf_path, output_image, output_json):
    chapter_pattern = re.compile(r'^\s*Chapter\s+(.*)', re.IGNORECASE)
    section_pattern = re.compile(r'^\s*(\d+\.\d+)\s+(.+)$')
    subsection_pattern = re.compile(r'^\s*(\d+\.\d+\.\d+)\s+(.+)$')

    doc = fitz.open(pdf_path)

    structured_content = []
    buffer = []
    current_chapter = None
    current_chapter_title = None
    current_section = None
    current_section_title = None
    current_subsection = None
    current_subsection_title = None

    for page_index, page in enumerate(doc):
        if page_index >= 5:
            break

        page_dict = page.get_text("dict")
        page_images = page.get_images(full=True)

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

        for block in page_dict["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                line_text = " ".join(span["text"] for span in line["spans"]).strip()
                if not line_text:
                    continue

                chap_match = chapter_pattern.match(line_text)
                if chap_match:
                    current_chapter = chap_match.group(1).strip()
                    collecting_title = True
                    title_lines = []
                    continue

                if collecting_title:
                    if section_pattern.match(line_text) or subsection_pattern.match(line_text):
                        current_chapter_title = " ".join(title_lines).strip()
                        collecting_title = False
                    else:
                        title_lines.append(line_text)
                        continue

                sub_match = subsection_pattern.match(line_text)
                sec_match = section_pattern.match(line_text)

                if sub_match:
                    if buffer:
                        structured_content.append({
                            "chapter": current_chapter,
                            "chapter_title": current_chapter_title,
                            "section": current_section,
                            "section_title": current_section_title,
                            "subsection": current_subsection,
                            "subsection_title": current_subsection_title,
                            "content": "\n".join(buffer).strip(),
                        })
                        buffer = []
                    current_subsection = sub_match.group(1)
                    current_subsection_title = sub_match.group(2)
                    continue

                elif sec_match:
                    if buffer:
                        structured_content.append({
                            "chapter": current_chapter,
                            "chapter_title": current_chapter_title,
                            "section": current_section,
                            "section_title": current_section_title,
                            "subsection": current_subsection,
                            "subsection_title": current_subsection_title,
                            "content": "\n".join(buffer).strip(),
                        })
                        buffer = []
                    current_section = sec_match.group(1)
                    current_section_title = sec_match.group(2)
                    current_subsection = None
                    current_subsection_title = None
                    continue

                buffer.append(line_text)

    if buffer:
        structured_content.append({
            "chapter": current_chapter,
            "chapter_title": current_chapter_title,
            "section": current_section,
            "section_title": current_section_title,
            "subsection": current_subsection,
            "subsection_title": current_subsection_title,
            "content": "\n".join(buffer).strip(),
        })

    with open(os.path.join(output_json, "chunking_data.json"), "w") as f:
        json.dump(structured_content, f, indent=2)

    print(f"✅ Chunking completed and saved to {output_json}")

extract_structure_from_pdf(pdf_path, output_image, output_json)
