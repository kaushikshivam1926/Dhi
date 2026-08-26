import os
import tempfile
from audio_overview_engine import AudioOverviewEngine

def test_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = AudioOverviewEngine()
        engine.input_folder = os.path.join(tmpdir, "input")
        os.makedirs(engine.input_folder, exist_ok=True)

        # Test 1: Valid path inside input_folder
        engine.scan_input_files("subdir") # should create and return []

        # Test 2: Path Traversal attempts
        try:
            engine.scan_input_files("../../../../../etc")
            print("FAILED: Path traversal allowed in scan_input_files")
            exit(1)
        except ValueError as e:
            print("SUCCESS: Path traversal blocked in scan_input_files", e)

        try:
            engine.scan_input_files("/etc")
            print("FAILED: Absolute path outside allowed in scan_input_files")
            exit(1)
        except ValueError as e:
            print("SUCCESS: Absolute path outside blocked in scan_input_files", e)

        # Test 3: read_article_contents
        with open(os.path.join(tmpdir, "secret.txt"), "w") as f:
            f.write("SECRET")

        content = engine.read_article_contents([os.path.join(tmpdir, "secret.txt")])
        if "SECRET" in content:
            print("FAILED: Arbitrary file read allowed in read_article_contents")
            exit(1)
        else:
            print("SUCCESS: Arbitrary file read blocked in read_article_contents")

        print("All tests passed.")

test_traversal()
