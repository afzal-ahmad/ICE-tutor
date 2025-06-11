import fitz  # PyMuPDF
import re
import os
import json
import logging
import datetime
from datetime import datetime, date, time, timedelta
import pytesseract
from PIL import Image

pdf_path = "/home/aahmad/Desktop/DEV/working-dir/leph101.pdf"
output_image = "/home/aahmad/Desktop/DEV/output/images/"
output_json = "/home/aahmad/Desktop/DEV/output/"
log_path= "/home/aahmad/Desktop/DEV/output/chunk-pdf-py.log"

os.makedirs(output_image, exist_ok=True)
os.makedirs(output_json, exist_ok=True)

def is_math_span(span):
    # print("begin print")
    # math_symbols = ['ε', 'π', '^', '=', '/', '|']
    math_symbols = ['π', '^', '=', '/', '|', 'ε', '∑', '√', '∫', 'µ']
    # return any(sym in span['text'] for sym in math_symbols)
    text = span.get('text', '')
    matched_symbols = [sym for sym in math_symbols if sym in text]

    if matched_symbols:
        print(f"🔍 Matched symbols: {matched_symbols} in span text: \"{text}\"")

    return bool(matched_symbols)

def merge_bboxes(spans):
    x0 = min(s['bbox'][0] for s in spans)
    y0 = min(s['bbox'][1] for s in spans)
    x1 = max(s['bbox'][2] for s in spans)
    y1 = max(s['bbox'][3] for s in spans)
    return fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)

def reconstruct_line_text(line, spacing_threshold=1.5):
    words = []
    current_word = ""
    prev_x1 = None  # track right bound of previous character/span

    for span in line["spans"]:
        span_text = span["text"]
        span_bbox = span["bbox"]  # [x0, y0, x1, y1]

        # Approximate average character width for the span
        if len(span_text) > 0:
            avg_char_width = (span_bbox[2] - span_bbox[0]) / len(span_text)
        else:
            avg_char_width = 0

        # Process each character individually with approximate position
        for i, char in enumerate(span_text):
            if not char.strip():
                continue  # skip pure spaces inside span text

            # Approximate x position of this character
            char_x0 = span_bbox[0] + i * avg_char_width
            char_x1 = char_x0 + avg_char_width

            if prev_x1 is not None:
                gap = char_x0 - prev_x1
                if gap > spacing_threshold:
                    # big gap → word boundary
                    if current_word:
                        words.append(current_word)
                    current_word = char
                else:
                    current_word += char
            else:
                current_word = char

            prev_x1 = char_x1

    if current_word:
        words.append(current_word)

    # Join words by space to rebuild the full line
    return " ".join(words)

def line_property(line):
    span_properties = []

    for span in line.get("spans", []):
        text = span.get("text", "")
        size = span.get("size", 0)
        font = span.get("font", "")
        color_int = span.get("color", 0)
        flags = span.get("flags", 0)

        # Determine case type
        if text.isupper():
            case_type = "uppercase"
        elif text.islower():
            case_type = "lowercase"
        elif text.istitle():
            case_type = "titlecase"
        else:
            case_type = "mixed"

        # Check bold and italic
        is_bold = ("bold" in font.lower() or "demi" in font.lower() or (flags & 16) != 0)
        is_italic = ("italic" in font.lower() or (flags & 8) != 0)

        # Extract RGB color
        r = (color_int >> 16) & 255
        g = (color_int >> 8) & 255
        b = color_int & 255
        color_rgb = (r, g, b)

        span_properties.append({
            "text": text,
            "font_size": size,
            "font_name": font,
            "font_flags": flags,
            "font_case": case_type,
            "is_bold": is_bold,
            "is_italic": is_italic,
            "font_color": color_rgb,
        })

    return span_properties
          

def extract_structure_from_pdf(pdf_path, output_image, output_json, log_path):
    chapter_pattern = re.compile(r'^\s*Chapter\s+(.*)', re.IGNORECASE)
    skip_exact_lines = {"Chapter", "Page", "Exercise", "Figure", "Reprint", "Fig"}
    skip_regex_patterns = [
        re.compile(r'^\s*Page\s+\d+'),           # Matches: Page 2, Page 15
        re.compile(r'^\s*FIGURE\s+\d+'),         # Matches: Figure 1, etc.
        re.compile(r'^\s*Fig\s+\d+'),  
        # re.compile(r'^\s*Example\s+\d+'),      # Matches: Example 2, etc.
        re.compile(r'^\s*Reprint\s+\d+'),
        re.compile(r'^\s*[\d]+\s*$'),            # Matches lines with just numbers (page numbers)
    ]

    doc = fitz.open(pdf_path)
    section_pattern = re.compile(r'^\s*(\d+\.\d+)\s+(.+)$')
    subsection_pattern = re.compile(r'^\s*(\d+\.\d+\.\d+)\s+(.+)$')

    structured_content = []
    buffer = []
    current_chapter = None
    current_chapter_title = None
    current_section = None
    current_section_title = None
    current_subsection = None
    current_subsection_title = None
    prev_section = None
    prev_subsection = None
    prev_indent_x = None
    math_image_counter = 0

    logging.basicConfig(
        filename=log_path,                # Name of log file
        filemode='w',                    # Overwrite file on each run; use 'a' to append
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO               # Set to INFO to capture general messages
    )

    for page_num, page in enumerate(doc, start=1):
        # if page_num == 5:
        #     break

        # if page_num != 3:
        #     continue

        # logging.info("page_num:" + str(page_num))
        page_dict = page.get_text("dict")
        # page_images = page.get_images(full=True)
        # formula_spans = []

        # image_refs = []
        # for img_index, img in enumerate(page_images):
        #     xref = img[0]
        #     base_image = doc.extract_image(xref)
        #     image_bytes = base_image["image"]
        #     image_ext = base_image["ext"]
        #
        #     image_filename = f"page{page_num+1}_img{img_index+1}.{image_ext}"
        #     image_path = os.path.join(output_image, image_filename)
        #     with open(image_path, "wb") as f:
        #         f.write(image_bytes)
        #     image_refs.append(image_filename)

        collecting_title = False
        title_lines = []
        line_counter = 0
        all_lines = []

        for block in page_dict["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                all_lines.append(line)

        line_consumed = 0
        for idx, line in enumerate(all_lines):
            # line_text = reconstruct_line_text(line).strip()
            formula_spans = [] 
            line_text_parts = []
            math_exist = False
            # print(" ".join([span["text"] for span in line["spans"]]))
                       
            for span in line.get("spans", []):
                if is_math_span(span):
                    math_exist = True
                    math_image_counter+=1
                    formula_spans.append(span)
                    formula_rect = merge_bboxes(formula_spans)
                    pix = page.get_pixmap(clip=formula_rect, dpi=300)
                    image_filename = f"math_image{math_image_counter}.png"
                    line_text_parts.append(f"<{image_filename}>")
                    image_path = os.path.join(output_image, image_filename)
                    pix.save(image_path)
                else:
                    line_text_parts.append(span["text"])
                
            if math_exist:                
                line_text = " ".join(line_text_parts).strip()
                line_text_parts = []
            else:
                line_text = reconstruct_line_text(line).strip()

            # print("line_text", line_text)
            # logging.info(f"page_num: {page_num}, line_index: {line_counter}, text: {line_text}")

            line_counter += 1
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

            # Skip known unwanted lines
            if line_text in skip_exact_lines:
                continue
            if any(pat.match(line_text) for pat in skip_regex_patterns):
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
                        "paragraph": str(para),
                        # "content": "\n".join(buffer).strip(),
                        "content": " ".join(buffer).strip(),
                        # "images": image_refs.copy()
                    })
                    buffer = []

                current_subsection = sub_match.group(1)
                current_subsection_title = sub_match.group(2)
                prev_subsection = current_subsection
                para=1

                props = line_property(line)  # Call your function here

                if props:
                    span_info = props[0]
                    subsection_text = span_info["text"]
                    subsection_font_size = span_info["font_size"]
                    subsection_font_name = span_info["font_name"]
                    subsection_font_case = span_info["font_case"]
                    subsection_is_bold = span_info["is_bold"]
                    subsection_is_italic = span_info["is_italic"]
                    subsection_font_color = span_info["font_color"]

                current_text = " ".join(span["text"] for span in line["spans"]).strip()
                # print("Current line:", current_text)
                remaining_lines = all_lines[idx + 1: idx + 6]
                k = 0
                for subr_line in remaining_lines:
                    subr_text = " ".join(span["text"] for span in subr_line["spans"])
                    # print("Subsection Remaining lines:", subr_text)
                    sub_props_remain = line_property(subr_line)
                    if sub_props_remain:
                        for i, sub_span_info in enumerate(sub_props_remain):
                            i+=1
                            # sub_span_info = props_remain[0]
                            if subsection_font_name == sub_span_info["font_name"] and subsection_font_color == sub_span_info["font_color"]:
                                line_consumed+=1
                                if k == 1 and sub_span_info["font_size"] == 16:
                                    letter = sub_span_info["text"]
                                elif k == 2:
                                    k=0
                                    if sub_span_info["font_size"] < 16:
                                        line_consumed-=1
                                        letter = letter + sub_span_info["text"]
                                        # print("letter: ", letter)
                                        # print("current_section1: ", current_section_title)
                                        current_section_title = " ".join([current_section_title, letter])
                                        # print("current_section2: ", current_section_title)
                                    else: 
                                        word = " ".join([letter, sub_span_info["text"]])
                                        # print("current_section1: ", current_section_title)
                                        current_section_title = " ".join([current_section_title, letter])
                                        # print("current_section2: ", current_section_title)
                            else:
                                break
                    break

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
                        "paragraph": str(para),
                        # "content": "\n".join(buffer).strip(),
                        "content": " ".join(buffer).strip(),
                        # "images": image_refs.copy()
                    })
                    buffer = []
                
                current_section = sec_match.group(1)
                current_section_title = sec_match.group(2)
                prev_section = current_section
                current_subsection = None
                prev_subsection = None
                current_subsection_title = None
                para=1
                
                props = line_property(line)  # Call your function here

                if props:
                    span_info = props[0]
                    section_text = span_info["text"]
                    section_font_size = span_info["font_size"]
                    section_font_name = span_info["font_name"]
                    section_font_case = span_info["font_case"]
                    section_is_bold = span_info["is_bold"]
                    section_is_italic = span_info["is_italic"]
                    section_font_color = span_info["font_color"]

                current_text = " ".join(span["text"] for span in line["spans"]).strip()
                # print("Current line:", current_text)
                remaining_lines = all_lines[idx + 1: idx + 6]
                k = 0
                for r_line in remaining_lines:
                    r_text = " ".join(span["text"] for span in r_line["spans"])
                    # print("Section Remaining lines:", r_text)
                    props_remain = line_property(r_line)
                    if props_remain:
                        for i, span_info in enumerate(props_remain):
                            i+=1
                            # span_info = props_remain[0]
                            if section_font_name == span_info["font_name"] and section_font_color == span_info["font_color"]:
                                line_consumed+=1
                                k+=1
                                if k == 1 and span_info["font_size"] == 16:
                                    letter = span_info["text"]
                                elif k == 2:
                                    k=0
                                    if span_info["font_size"] < 16:
                                        line_consumed-=1
                                        letter = letter + span_info["text"]
                                        # print("letter: ", letter)
                                        # print("current_section1: ", current_section_title)
                                        current_section_title = " ".join([current_section_title, letter])
                                        # print("current_section2: ", current_section_title)
                                    else: 
                                        word = " ".join([letter, span_info["text"]])
                                        # print("current_section1: ", current_section_title)
                                        current_section_title = " ".join([current_section_title, letter])
                                        # print("current_section2: ", current_section_title)
                            else:
                                break
                    break
                continue

            if line_consumed == 0: 
                current_indent_x = line["spans"][0]["bbox"][0] if line.get("spans") else None
                first_word = line_text.split()[0] if line_text.split() else ""
                word_count = len(" ".join(buffer).strip().split())
                is_first_word_capital = first_word.istitle() 
                is_indent_break = (prev_indent_x is not None and current_indent_x is not None 
                                   and (current_indent_x - prev_indent_x) > 10
                )
                is_capital_paragraph_start = (is_first_word_capital and
                                              (len(buffer) > 0 and word_count > 49 
                                               and buffer[-1][-1] in '.!?')  # previous sentence ended
                )

                if is_indent_break and is_capital_paragraph_start: 
                    if buffer: 
                        structured_content.append({
                            "chapter": current_chapter,
                            "chapter_title": current_chapter_title,
                            "section": current_section,
                            "section_title": current_section_title,
                            "subsection": current_subsection,
                            "subsection_title": current_subsection_title,
                            "paragraph": str(para),
                            "content": " ".join(buffer).strip(),
                            # "images": image_refs.copy()
                        })
                        buffer = []
                        buffer.append(line_text)
                        print("paragraph_buffer: ", buffer)
                        
                        if current_section == prev_section and current_subsection == prev_subsection:
                            para+=1
                        else:
                            para=1

                        prev_section = current_section
                        prev_subsection = prev_subsection
                        # print("Prev Word count:", prev_word_count)
                else:
                    buffer.append(line_text)

                prev_indent_x = current_indent_x
            else:
                line_consumed-=1
    
    if buffer: 
        structured_content.append({
            "chapter": current_chapter,
            "chapter_title": current_chapter_title,
            "section": current_section,
            "section_title": current_section_title,
            "subsection": current_subsection,
            "subsection_title": current_subsection_title,
            "paragraph": str(para),
            "content": " ".join(buffer).strip(),
            # "images": image_refs.copy()
        })

    with open(os.path.join(output_json, "chunking_data.json"), "w") as f:
        json.dump(structured_content, f, indent=2)

    logging.info(f"✅ Chunking completed and saved to {output_json}")

print(f"begin: {datetime.now()}")
extract_structure_from_pdf(pdf_path, output_image, output_json, log_path)
print(f"end:{datetime.now()}")
