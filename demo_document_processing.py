import json
import os
import sys
from app.services.document_processing import process_document
from app.services.document_processing.loaders import SUPPORTED_EXTENSIONS

# Fix Windows console encoding for Arabic/French output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JSON_OUTPUT_DIR = os.path.join("outputs", "json")
os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)


def run_demo():

    print("\nRunning document processing demo...\n")
    print(f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}\n")

    samples_dir = "samples"
    supported_files = [
        os.path.join(samples_dir, f)
        for f in os.listdir(samples_dir)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]

    if not supported_files:
        print("No supported documents found in samples/.")
        return

    for i, file_path in enumerate(supported_files, start=1):

        print(f"\nProcessing: {file_path}")

        try:
            document = process_document(file_path, document_number=i)

            print(f"  language : {document.metadata.language}")
            print(f"  pages    : {document.metadata.total_pages}")
            print(f"  sections : {len(document.sections)}")
            print(f"  tables   : {len(document.tables)}")
            print(f"  images   : {len(document.images)}")

            json_name = os.path.join(JSON_OUTPUT_DIR, f"{document.document_id}.json")
            with open(json_name, "w", encoding="utf-8") as f:
                json.dump(document.model_dump(), f, indent=2, ensure_ascii=False)

            print(f"  saved -> {json_name}")

            print("\n  Sections detected:")
            for section in document.sections:
                level_indent = "  " * (section.level - 1)
                print(f"  {level_indent}[L{section.level}] {section.heading}")

        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    run_demo()
