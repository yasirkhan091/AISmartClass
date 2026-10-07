from pathlib import Path

OUTPUT = Path(__file__).parent / "demo_papers"


PAPERS = {
    "linear_equations": (
        "CLASS 9 ALGEBRA - LINEAR EQUATIONS",
        "10 questions - 2 marks each - Show your working",
        [
            "1. Solve: 3x + 5 = 26.",
            "2. Solve: 5(2y - 3) = 35.",
            "3. Solve: 4a - 7 = 2a + 9.",
            "4. Simplify: 3x + 4 - 2x + 7.",
            "5. Expand: 4(2m - 3).",
            "6. Factorise: 6x + 18.",
            "7. If 2x + y = 13 and y = 5, find x.",
            "8. Two consecutive integers have a sum of 35. Find them.",
            "9. A rectangle has length 3 cm more than its width and perimeter 30 cm. Find its dimensions.",
            "10. Three quarters of a number, plus 2, equals 17. Find the number.",
        ],
    ),
    "linear_equations_answers": (
        "SAMPLE STUDENT WORK - LINEAR EQUATIONS",
        "Practice submission - show each step and check the final answer",
        [
            "1. 3x + 5 = 26; 3x = 21; x = 7.",
            "2. 5(2y - 3) = 35; 10y - 15 = 35; 10y = 50; y = 4.",
            "3. 2a = 16; a = 8.",
            "4. (3x - 2x) + (4 + 7) = x + 11.",
            "5. 8m - 12.",
            "6. 6(x + 3).",
            "7. 2x + 5 = 13; x = 4.",
            "8. Let the integers be n and n + 1. 2n + 1 = 35; they are 17 and 18.",
            "9. Let width be w. 2(w + w + 3) = 30; w = 6 cm, length = 9 cm.",
            "10. (3/4)n + 2 = 17; n = 20.",
        ],
    ),
    "linear_equations_key": (
        "TEACHER ANSWER KEY - LINEAR EQUATIONS",
        "Worked solutions for teacher-side grading reference",
        [
            "1. 3x + 5 = 26; 3x = 21; x = 7.",
            "2. 10y - 15 = 35; 10y = 50; y = 5.",
            "3. 4a - 7 = 2a + 9; 2a = 16; a = 8.",
            "4. 3x + 4 - 2x + 7 = x + 11.",
            "5. 4(2m - 3) = 8m - 12.",
            "6. 6x + 18 = 6(x + 3).",
            "7. 2x + 5 = 13; x = 4.",
            "8. n + (n + 1) = 35; n = 17; integers are 17 and 18.",
            "9. 2(w + w + 3) = 30; w = 6 cm; length = 9 cm.",
            "10. 3n/4 + 2 = 17; n = 20.",
        ],
    ),
    "polynomials": (
        "CLASS 9 ALGEBRA - POLYNOMIALS",
        "10 questions - 2 marks each - Show your working",
        [
            "1. Simplify: 4a + 3a - 5 + 2.",
            "2. Expand: (x + 3)(x + 4).",
            "3. Factorise: x^2 + 7x + 12.",
            "4. Factorise: x^2 - 16.",
            "5. Factorise fully: 3x^2 + 6x.",
            "6. Evaluate 2p^2 - 3q when p = 3 and q = 2.",
            "7. Solve: 2(x - 3) + 4 = 14.",
            "8. Simplify the ratio 12:18.",
            "9. Triangle angles are x, 2x and 3x. Find all three angles.",
            "10. Evaluate n^2 + 3n when n = -2.",
        ],
    ),
    "polynomials_answers": (
        "SAMPLE STUDENT WORK - POLYNOMIALS",
        "Practice submission - show each step and check the final answer",
        [
            "1. 7a - 3.",
            "2. x^2 + 7x + 12.",
            "3. (x + 3)(x + 4).",
            "4. (x - 4)(x + 4).",
            "5. 3x(x + 2).",
            "6. 2(3)^2 - 3(2) = 18 - 6 = 15.",
            "7. 2x - 2 = 14; x = 8.",
            "8. Divide both terms by 6: 2:3.",
            "9. 6x = 180; x = 30. Angles: 30, 60 and 90 degrees.",
            "10. (-2)^2 + 3(-2) = 4 - 6 = -2.",
        ],
    ),
    "polynomials_key": (
        "TEACHER ANSWER KEY - POLYNOMIALS",
        "Worked solutions for teacher-side grading reference",
        [
            "1. 7a - 3.",
            "2. x^2 + 7x + 12.",
            "3. (x + 3)(x + 4).",
            "4. (x - 4)(x + 4).",
            "5. 3x(x + 2).",
            "6. 2(3)^2 - 3(2) = 18 - 6 = 12.",
            "7. 2(x - 3) + 4 = 14; 2x - 2 = 14; x = 8.",
            "8. 12:18 = 2:3.",
            "9. x + 2x + 3x = 180; x = 30; angles are 30, 60 and 90 degrees.",
            "10. (-2)^2 + 3(-2) = 4 - 6 = -2.",
        ],
    ),
}


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(title: str, subtitle: str, lines: list[str]) -> bytes:
    pages = [lines[index:index + 28] for index in range(0, len(lines), 28)] or [[]]
    page_ids = [5 + index * 2 for index in range(len(pages))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(pages)} >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    for page_index, page_lines in enumerate(pages):
        page_id = page_ids[page_index]
        stream_id = page_id + 1
        content_lines = [
            "BT",
            "/F2 15 Tf",
            "50 790 Td",
            f"({escape_pdf_text(title)}) Tj",
            "/F1 10 Tf",
            "0 -22 Td",
            f"({escape_pdf_text(subtitle)}) Tj",
            "0 -24 Td",
            "(Name: ______________________________    Date: ______________) Tj",
            "0 -26 Td",
        ]
        for line in page_lines:
            content_lines.extend([f"({escape_pdf_text(line)}) Tj", "0 -23 Td"])
        content_lines.extend(["ET", ""])
        content = "\n".join(content_lines).encode("ascii", "replace")
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>").encode())
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"endstream")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f\n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n\n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(output)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, (title, subtitle, lines) in PAPERS.items():
        output_path = OUTPUT / f"{name}.pdf"
        output_path.write_bytes(make_pdf(title, subtitle, lines))
        print(f"Created {output_path.name}")


if __name__ == "__main__":
    main()
