from pathlib import Path

source_file = Path("src/pitloom/__main__.py")
source_code = source_file.read_text()

# We will just manually copy over pieces by slicing the source code, but since we don't know exact lines easily from a script,
# I will use multi_replace_file_content or a script to find and extract.
