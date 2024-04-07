import argparse
from pathlib import Path
import fitz  # pymupdf
from typing import List
import re
import unicodedata


def extract_text_from_pdf(pdf_path: Path) -> List[str]:
    with fitz.open(pdf_path) as doc:
        pages = []
        for page in doc:
            pages.append(page.get_text())
        return pages


def clean_text(text: str) -> str:
    # Remove non-alphanumeric characters except for Japanese characters and common punctuation
    cleaned_text = re.sub(
        r"[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3000-\u303F\s\.\,\!\?\:\;\'\"\(\)\[\]\{\}]",
        "",
        text,
    )
    # Remove extra whitespace
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
    # Remove spaces before punctuations
    cleaned_text = re.sub(r"\s+([^\w\s])", r"\1", cleaned_text)
    # Remove spaces between alphanumeric characters
    cleaned_text = re.sub(r"(\w)\s+(\w)", r"\1\2", cleaned_text)
    # Normalize unicode characters
    cleaned_text = unicodedata.normalize("NFKC", cleaned_text)
    return cleaned_text


def split_text_into_chunks(pages: List[str], max_size: int) -> List[str]:
    chunks = []
    current_chunk = ""

    for page in pages:
        sentences = re.split(r"(?<=[。！？])", page)
        for sentence in sentences:
            if sentence:
                cleaned_sentence = clean_text(sentence)
                if (
                    len(
                        current_chunk.encode("utf-8") + cleaned_sentence.encode("utf-8")
                    )
                    <= max_size
                ):
                    current_chunk += cleaned_sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = cleaned_sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def save_chunks_to_files(chunks: List[str], output_path: Path) -> None:
    for i, chunk in enumerate(chunks, start=1):
        chunk_path = output_path.with_stem(f"{output_path.stem}.{i}")
        with chunk_path.open("w", encoding="utf-8") as chunk_file:
            chunk_file.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from a PDF file.")
    parser.add_argument(
        "-i", "--input", type=Path, required=True, help="Path to the input PDF file."
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Path to the output text file."
    )
    parser.add_argument(
        "-s",
        "--max-size",
        type=int,
        default=400,
        help="Maximum size of each output file in kilobytes (default: 400).",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.is_file():
        print(f"Error: Input file '{input_path}' does not exist.")
        return

    if args.output:
        output_path: Path = args.output
    else:
        output_path = input_path.with_suffix(".txt")

    pages: List[str] = extract_text_from_pdf(input_path)
    max_size: int = args.max_size * 1024  # Convert kilobytes to bytes

    chunks: List[str] = split_text_into_chunks(pages, max_size)
    save_chunks_to_files(chunks, output_path)

    print(
        f"Text extracted from '{input_path}', cleaned, and saved to multiple files with the prefix '{output_path.stem}'."
    )


if __name__ == "__main__":
    main()
