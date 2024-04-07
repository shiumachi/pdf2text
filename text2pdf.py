import argparse
from pathlib import Path
import fitz  # pymupdf
import re
import unicodedata


def extract_text_from_pdf(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        text = ""
        for page in doc:
            text += page.get_text()  # type:ignore
        return text


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


def process_file(input_path: Path, output_path: Path, overwrite: bool) -> bool:
    if output_path.exists() and not overwrite:
        print(f"Skipping '{input_path}' as output file '{output_path}' already exists.")
        return False

    try:
        text = extract_text_from_pdf(input_path)
        cleaned_text = clean_text(text)

        with output_path.open("w", encoding="utf-8") as output_file:
            output_file.write(cleaned_text)

        if overwrite:
            print(
                f"Text extracted from '{input_path}', cleaned, and saved to '{output_path}' (overwritten)."
            )
        else:
            print(
                f"Text extracted from '{input_path}', cleaned, and saved to '{output_path}'."
            )
        return True
    except Exception as e:
        print(f"Error processing '{input_path}': {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from PDF files.")
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Path to the input PDF file or directory.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Path to the output text file or directory."
    )
    parser.add_argument(
        "-w",
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    overwrite: bool = args.overwrite

    if input_path.is_file():
        if args.output:
            output_path: Path = args.output
        else:
            output_path = input_path.with_suffix(".txt")
        process_file(input_path, output_path, overwrite)
    elif input_path.is_dir():
        if args.output:
            output_dir: Path = args.output
            if not output_dir.is_dir():
                print(f"Error: Output path '{output_dir}' is not a directory.")
                return
        else:
            output_dir = input_path

        total_files = 0
        success_files = 0
        error_files = 0

        for pdf_file in input_path.glob("*.pdf"):
            output_path = output_dir / pdf_file.with_suffix(".txt").name
            total_files += 1
            if process_file(pdf_file, output_path, overwrite):
                success_files += 1
            else:
                error_files += 1

        print(
            f"Processed {total_files} files: {success_files} success, {error_files} errors."
        )
    else:
        print(f"Error: Input path '{input_path}' is not a file or directory.")


if __name__ == "__main__":
    main()
