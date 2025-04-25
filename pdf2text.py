import argparse
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

import fitz  # pymupdf

# --- ロギング設定 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",  # 関数名もログに追加
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- 定数 ---
# NFKC正規化後に基本的なOCRエラーを修正するための辞書
# （全角英数字や記号を半角に置換）
OCR_REPLACEMENTS = {
    "，": ",",
    "．": ".",
    "；": ";",
    "：": ":",
    "！": "!",
    "？": "?",
    "＂": '"',
    "＇": "'",
    "｀": "`",
    "（": "(",
    "）": ")",
    "［": "[",
    "］": "]",
    "｛": "{",
    "｝": "}",
    "＜": "<",
    "＞": ">",
    "＝": "=",
    "＋": "+",
    "－": "-",
    "＊": "*",
    "／": "/",
    "￥": "\\",
    "｜": "|",
    "＠": "@",
    "＃": "#",
    "＄": "$",
    "％": "%",
    "＆": "&",
    "＾": "^",
    "￣": "~",
    "　": " ",  # 全角スペース
    # 全角英数字 (例)
    "０": "0",
    "１": "1",
    "２": "2",
    "３": "3",
    "４": "4",
    "５": "5",
    "６": "6",
    "７": "7",
    "８": "8",
    "９": "9",
    "Ａ": "A",
    "Ｂ": "B",
    "Ｃ": "C",
    "Ｄ": "D",
    "Ｅ": "E",
    "Ｆ": "F",
    "Ｇ": "G",
    "Ｈ": "H",
    "Ｉ": "I",
    "Ｊ": "J",
    "Ｋ": "K",
    "Ｌ": "L",
    "Ｍ": "M",
    "Ｎ": "N",
    "Ｏ": "O",
    "Ｐ": "P",
    "Ｑ": "Q",
    "Ｒ": "R",
    "Ｓ": "S",
    "Ｔ": "T",
    "Ｕ": "U",
    "Ｖ": "V",
    "Ｗ": "W",
    "Ｘ": "X",
    "Ｙ": "Y",
    "Ｚ": "Z",
    "ａ": "a",
    "ｂ": "b",
    "ｃ": "c",
    "ｄ": "d",
    "ｅ": "e",
    "ｆ": "f",
    "ｇ": "g",
    "ｈ": "h",
    "ｉ": "i",
    "ｊ": "j",
    "ｋ": "k",
    "ｌ": "l",
    "ｍ": "m",
    "ｎ": "n",
    "ｏ": "o",
    "ｐ": "p",
    "ｑ": "q",
    "ｒ": "r",
    "ｓ": "s",
    "ｔ": "t",
    "ｕ": "u",
    "ｖ": "v",
    "ｗ": "w",
    "ｘ": "x",
    "ｙ": "y",
    "ｚ": "z",
}

# 許可する文字の正規表現パターン
# 基本的な英数字、日本語、一般的な句読点・記号、空白
# ClaudeCodeの許可リストから数学記号などを除外し、YourCodeのリストをベースに拡張
ALLOWED_CHARS_PATTERN = re.compile(
    r"[^"
    r"a-zA-Z0-9"
    r"\u3040-\u309F"  # Hiragana
    r"\u30A0-\u30FF"  # Katakana
    r"\u4E00-\u9FFF"  # Kanji
    r"\u3000-\u303F"  # CJK Symbols and Punctuation (includes full-width space)
    r"\s"  # Whitespace
    r".,!?:;'\"()\[\]{}<>`\+\-\*/=\\%&\|#@~"  # Basic ASCII punctuation and symbols
    r"・「」『』【】"  # Common Japanese symbols
    r"]+"
)

# PDFアーティファクトのパターン (大文字小文字無視)
PDF_ARTIFACT_PATTERNS = [
    re.compile(r"\b(confidential|draft|do not copy|sample|watermark)\b", re.IGNORECASE),
    re.compile(r"\bpage\s+\d+(\s+of\s+\d+)?\b", re.IGNORECASE),
    re.compile(
        r"^\s*[-_]*\s*\d+\s*[-_]*\s*$", re.MULTILINE
    ),  # ページ番号のみの行 (例: - 1 -)
    re.compile(r"\d{1,3}\s*/\s*\d{1,3}"),  # ページ番号パターン (例: 1 / 10)
]

# 表の罫線文字パターン
TABLE_BORDER_PATTERN = re.compile(
    r"[│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋]"
)


# --- テキスト抽出 ---
def extract_text_from_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """PDFからページごとにテキストを抽出する"""
    pages_text = []
    try:
        with fitz.open(pdf_path) as doc:
            logger.info(f"'{pdf_path.name}' を開いています。ページ数: {len(doc)}")
            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]  # Get the page by index
                    # flags=fitz.TEXT_INHIBIT_SPACES なども試す価値あり
                    text = page.get_text()  # type:ignore
                    pages_text.append((page_num + 1, text))
                except Exception as e:
                    logger.warning(f"ページ {page_num + 1} の抽出中にエラー: {e}")
                    pages_text.append((page_num + 1, ""))  # エラー時は空文字
            logger.info(
                f"'{pdf_path.name}' から {len(pages_text)} ページ分のテキストを抽出しました。"
            )
            return pages_text
    except Exception as e:
        logger.error(f"'{pdf_path.name}' のオープンまたは処理中にエラー: {e}")
        raise  # エラーを再送出して上位で処理


# --- ヘッダー/フッター検出 ---
def detect_headers_footers(
    pages_text: list[tuple[int, str]], threshold: float = 0.7
) -> tuple[str | None, str | None]:
    """ページテキストリストからヘッダーとフッターを検出する"""
    if not pages_text or len(pages_text) < 3:  # 3ページ未満では検出困難
        return None, None

    first_lines = []
    last_lines = []

    for _, text in pages_text:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines:
            first_lines.append(lines[0])
            last_lines.append(lines[-1])

    if not first_lines or not last_lines:
        return None, None

    # 出現頻度をカウント
    first_counter = Counter(first_lines)
    last_counter = Counter(last_lines)

    # 最も頻繁に出現する行を候補とする
    header_candidate = first_counter.most_common(1)[0] if first_counter else None
    footer_candidate = last_counter.most_common(1)[0] if last_counter else None

    # しきい値以上の頻度で出現する場合のみ採用
    total_pages = len(pages_text)
    header = (
        header_candidate[0]
        if header_candidate and header_candidate[1] / total_pages >= threshold
        else None
    )
    footer = (
        footer_candidate[0]
        if footer_candidate and footer_candidate[1] / total_pages >= threshold
        else None
    )

    # 短すぎる行や数字だけの行はヘッダー/フッターから除外する可能性も検討
    if header and (len(header) < 5 or header.isdigit()):
        header = None
    if footer and (len(footer) < 5 or footer.isdigit()):
        footer = None

    if header:
        logger.debug(f"検出されたヘッダー候補: '{header}'")
    if footer:
        logger.debug(f"検出されたフッター候補: '{footer}'")
    return header, footer


# --- テキストクレンジング補助関数 ---
def fix_hyphenation(text: str) -> str:
    """行末のハイフネーションを修正"""
    # 英語: word-\nword -> wordword
    text = re.sub(r"(\w)-[\n\r]+(\w)", r"\1\2", text)
    # 日本語など: 漢字カタカナひらがな\n漢字カタカナひらがな -> 結合
    # より確実に結合するため、改行周りの空白も考慮
    text = re.sub(
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])[\s\n\r]+([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])",
        r"\1\2",
        text,
    )
    return text


def remove_pdf_artifacts(text: str) -> str:
    """PDF特有のアーティファクトを除去"""
    logger.debug("PDFアーティファクトの除去を開始...")
    # 制御文字やソフトハイフンなどを削除
    text = re.sub(r"[\x00-\x1F\x7F\u00AD\u200B-\u200D\uFEFF]", "", text)
    # 事前定義されたパターンを削除
    for pattern in PDF_ARTIFACT_PATTERNS:
        text = pattern.sub("", text)
    # 表の罫線文字をスペースに置換（削除すると単語が繋がる可能性があるため）
    text = TABLE_BORDER_PATTERN.sub(" ", text)
    logger.debug("PDFアーティファクトの除去が完了。")
    return text


def apply_ocr_fixes(text: str) -> str:
    """辞書に基づいて一般的なOCRエラーを修正"""
    logger.debug("OCR修正を開始...")
    for wrong, correct in OCR_REPLACEMENTS.items():
        text = text.replace(wrong, correct)
    logger.debug("OCR修正が完了。")
    return text


def normalize_whitespace_and_punctuation(text: str) -> str:
    """空白、句読点、括弧周りを正規化"""
    logger.debug("空白と句読点の正規化を開始...")

    # 連続する空白（改行含む）を単一スペースに置換
    text = re.sub(r"\s+", " ", text)

    # 箇条書き記号の調整 (先頭に改行を入れ、スペースを1つにする)
    # text = re.sub(r"([\•\◦\⦿\⦁\⚫\○])\s*", r"\n• ", text) # 解析内容によっては改行が邪魔な場合もある
    text = re.sub(
        r"[\•\◦\⦿\⦁\⚫\○]\s*", "• ", text
    )  # 箇条書き記号を統一し、後ろにスペース1つ
    text = re.sub(r"^\s*•", "•", text, flags=re.MULTILINE)  # 行頭のスペース+• を • に

    # 句読点の前にあるスペースを削除
    text = re.sub(r"\s+([.,!?:;、。』】）\)\]])", r"\1", text)
    # 括弧類の後に続くスペースを削除
    text = re.sub(r"([「『（\(\[【])\s+", r"\1", text)
    # 括弧類の前にスペースがない場合に追加（ただし日本語文字が続く場合を除く）
    # text = re.sub(r"([a-zA-Z0-9])([「『（\(\[【])", r"\1 \2", text) # 必要に応じて有効化
    # 括弧類の後にスペースがない場合に追加（ただし日本語文字が前にある場合を除く）
    # text = re.sub(r"([」』）\)\]】])([a-zA-Z0-9])", r"\1 \2", text) # 必要に応じて有効化

    # 日本語文字間の不要なスペースを削除
    text = re.sub(
        r"([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])\s+([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])",
        r"\1\2",
        text,
    )

    # 連続する同じ句読点を1つにまとめる
    text = re.sub(r"([.,!?:;、。])\1+", r"\1", text)

    # 文頭・文末の空白を削除
    text = text.strip()
    logger.debug("空白と句読点の正規化が完了。")
    return text


# --- メインのクレンジング関数 ---
def clean_pdf_text(
    text: str, remove_header: str | None = None, remove_footer: str | None = None
) -> str:
    """抽出されたPDFテキストに対して包括的なクレンジング処理を行う"""
    if not isinstance(text, str) or not text.strip():
        return ""  # 入力が不正または空なら空文字を返す

    logger.debug(f"クレンジング開始。初期文字数: {len(text)}")

    # 1. Unicode正規化 (NFKC)
    cleaned_text = unicodedata.normalize("NFKC", text)
    logger.debug(f"NFKC正規化後文字数: {len(cleaned_text)}")

    # 2. 一般的なOCRエラー修正
    cleaned_text = apply_ocr_fixes(cleaned_text)

    # 3. PDF特有のアーティファクト除去
    cleaned_text = remove_pdf_artifacts(cleaned_text)
    logger.debug(f"アーティファクト除去後文字数: {len(cleaned_text)}")

    # 4. ヘッダー/フッター除去 (検出された場合)
    #    複数行のヘッダー/フッターには対応していない点に注意
    if remove_header:
        # 行頭の一致のみ削除 (完全一致)
        cleaned_text = re.sub(
            r"^\s*" + re.escape(remove_header) + r"\s*[\r\n]+",
            "",
            cleaned_text,
            flags=re.MULTILINE,
        )
        logger.debug(f"ヘッダー除去試行後文字数: {len(cleaned_text)}")
    if remove_footer:
        # 行末の一致のみ削除 (完全一致)
        cleaned_text = re.sub(
            r"[\r\n]+\s*" + re.escape(remove_footer) + r"\s*$",
            "",
            cleaned_text,
            flags=re.MULTILINE,
        )
        logger.debug(f"フッター除去試行後文字数: {len(cleaned_text)}")

    # 5. ハイフネーション修正
    cleaned_text = fix_hyphenation(cleaned_text)
    logger.debug(f"ハイフネーション修正後文字数: {len(cleaned_text)}")

    # 6. 改行をスペースに置換 (段落構造はある程度失われる)
    #    ページ区切りや意図的な改行を保持したい場合は、この処理を変更する必要がある
    cleaned_text = cleaned_text.replace("\n", " ").replace("\r", "")
    logger.debug(f"改行置換後文字数: {len(cleaned_text)}")

    # 7. 許可文字以外を削除
    original_len = len(cleaned_text)
    cleaned_text = ALLOWED_CHARS_PATTERN.sub("", cleaned_text)
    if len(cleaned_text) != original_len:
        logger.debug(
            f"許可文字以外を除去。除去文字数: {original_len - len(cleaned_text)}"
        )

    # 8. 空白と句読点の正規化
    cleaned_text = normalize_whitespace_and_punctuation(cleaned_text)
    logger.debug(f"最終クレンジング後文字数: {len(cleaned_text)}")

    # 最終チェック: 全体が空白文字だけなら空にする
    if cleaned_text.isspace():
        return ""

    return cleaned_text


# --- ファイル処理 ---
def process_pdf_file(input_path: Path, output_path: Path, overwrite: bool) -> bool:
    """単一のPDFファイルを処理し、クレンジングされたテキストを保存する"""
    if output_path.exists() and not overwrite:
        logger.info(
            f"出力ファイル '{output_path.name}' は既に存在するためスキップします。"
        )
        return False  # スキップは成功ではない

    try:
        # 1. テキスト抽出 (ページごと)
        pages_text = extract_text_from_pdf_pages(input_path)
        if not pages_text:
            logger.warning(
                f"'{input_path.name}' からテキストを抽出できませんでした。空のファイルを作成します。"
            )
            output_path.touch()  # 空ファイルを作成
            return True  # 処理自体は完了

        # 2. ヘッダー/フッター検出
        header, footer = detect_headers_footers(pages_text)
        if header:
            logger.info(f"検出されたヘッダー: '{header}'")
        if footer:
            logger.info(f"検出されたフッター: '{footer}'")

        # 3. 全ページのテキストを結合 (ページ区切りとして空行を挿入)
        #    注意: clean_pdf_text内で改行はスペースに置換されるため、
        #          このページ区切りは最終出力には残らない。
        #          残したい場合は clean_pdf_text の改行処理を変更する必要がある。
        full_text = "\n\n".join([text for _, text in pages_text])

        # 4. テキストクレンジング
        logger.info(f"'{input_path.name}' のテキストクレンジングを開始します...")
        cleaned_text = clean_pdf_text(full_text, header, footer)
        logger.info(f"'{input_path.name}' のテキストクレンジングが完了しました。")

        # 5. 結果を保存
        output_path.parent.mkdir(parents=True, exist_ok=True)  # 出力ディレクトリ作成
        with output_path.open("w", encoding="utf-8") as f:
            if not cleaned_text:
                logger.warning(
                    f"'{input_path.name}' のクレンジング結果が空になりました。空のファイルを保存します。"
                )
            f.write(cleaned_text)

        status = "上書き保存" if overwrite and output_path.exists() else "保存"
        logger.info(
            f"クレンジングされたテキストを '{output_path.name}' に{status}しました。"
        )
        return True

    except Exception as e:
        logger.error(
            f"'{input_path.name}' の処理中に予期せぬエラーが発生しました: {e}",
            exc_info=True,
        )  # トレースバックも出力
        # エラー発生時に部分的に作成されたファイルを削除する (オプション)
        # if output_path.exists():
        #     try: output_path.unlink()
        #     except OSError: pass
        return False


# --- メイン処理 ---
def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDFファイルからテキストを抽出し、テキスト解析用にクレンジングします。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,  # デフォルト値をヘルプに表示
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="入力PDFファイルまたはディレクトリのパス",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力テキストファイルまたはディレクトリのパス。指定がない場合、入力と同じ場所に .txt 拡張子で保存されます。",
    )
    parser.add_argument(
        "-w",
        "--overwrite",
        action="store_true",
        help="既存の出力ファイルを上書きします。",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="デバッグレベルの詳細なログ出力を有効にします。",
    )
    # ヘッダー/フッター検出の閾値オプションを追加しても良い
    # parser.add_argument("--hf-threshold", type=float, default=0.7, help="Header/footer detection threshold (0.0-1.0)")

    args = parser.parse_args()

    # ログレベル設定
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.info("詳細ログモードが有効になりました。")

    input_path: Path = args.input
    overwrite: bool = args.overwrite

    if not input_path.exists():
        logger.error(f"エラー: 入力パス '{input_path}' が存在しません。")
        return

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            logger.error(
                f"エラー: 入力ファイル '{input_path}' はPDFファイルではありません。"
            )
            return

        if args.output:
            output_path: Path = args.output
            if output_path.is_dir():  # 出力がディレクトリならファイル名を維持して結合
                output_path = output_path / input_path.with_suffix(".txt").name
        else:
            output_path = input_path.with_suffix(".txt")

        process_pdf_file(input_path, output_path, overwrite)

    elif input_path.is_dir():
        output_dir: Path
        if args.output:
            output_dir = args.output
            if output_dir.exists() and not output_dir.is_dir():
                logger.error(
                    f"エラー: 出力パス '{output_dir}' はディレクトリではありません。"
                )
                return
        else:
            output_dir = input_path  # デフォルトは入力ディレクトリと同じ

        output_dir.mkdir(parents=True, exist_ok=True)  # 出力ディレクトリ作成保証

        pdf_files = sorted(
            list(input_path.glob("*.pdf"))
        )  # 順番を安定させるためにソート
        if not pdf_files:
            logger.warning(
                f"ディレクトリ '{input_path}' にPDFファイルが見つかりませんでした。"
            )
            return

        logger.info(
            f"ディレクトリ '{input_path}' 内の {len(pdf_files)} 個のPDFファイルを処理します..."
        )

        total_files = len(pdf_files)
        success_count = 0
        failure_count = 0
        skipped_count = 0  # スキップされたファイル数をカウント

        for i, pdf_file in enumerate(pdf_files):
            logger.info(f"--- ファイル {i+1}/{total_files}: '{pdf_file.name}' ---")
            output_filename = pdf_file.with_suffix(".txt").name
            output_path = output_dir / output_filename

            # process_pdf_file は overwrite=False でファイルが存在する場合 False を返す
            if output_path.exists() and not overwrite:
                logger.info(
                    f"出力ファイル '{output_path.name}' は既に存在するためスキップします。"
                )
                skipped_count += 1
                continue  # 次のファイルへ

            if process_pdf_file(pdf_file, output_path, overwrite):
                success_count += 1
            else:
                failure_count += 1

        logger.info("=" * 30)
        logger.info("全ファイルの処理が完了しました。")
        logger.info("処理結果:")
        logger.info(f"  合計ファイル数: {total_files}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失敗: {failure_count}")
        logger.info(f"  スキップ (上書きなしで既存): {skipped_count}")
        logger.info(f"  出力ディレクトリ: {output_dir.resolve()}")
        logger.info("=" * 30)

    else:
        logger.error(
            f"エラー: 入力パス '{input_path}' は有効なファイルまたはディレクトリではありません。"
        )


if __name__ == "__main__":
    main()
