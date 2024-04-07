# text2pdf

Converts text files to PDF format.

## Installation

To install `text2pdf`, you can use the following command:

```bash
python -m venv .venv
python -m pip install -U pip setuptools wheel poetry
poetry install
```

## Usage

usage: text2pdf.py [-h] -i INPUT [-o OUTPUT] [-s MAX_SIZE]

Extract text from a PDF file.

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to the input PDF file.
  -o OUTPUT, --output OUTPUT
                        Path to the output text file.
  -s MAX_SIZE, --max-size MAX_SIZE
                        Maximum size of each output file in kilobytes (default: 400).
