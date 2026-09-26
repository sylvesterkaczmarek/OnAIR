"""Check the exact submitted importer fix and its original failure cases."""

from pathlib import Path
import subprocess
import sys

source = Path(sys.argv[1]).resolve()
evidence = Path(sys.argv[2]).resolve()
evidence.mkdir(parents=True, exist_ok=True)
BASE = "e8af1187203dbda3af00fbf3b1eec05103996e01"
SHA = "f5c0ee026ce792fabe8fadf201704c9dd526c4a1"
assert (
    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    == SHA
)


def run(name, command, expected=0, contains=None):
    result = subprocess.run(
        command, cwd=source, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    (evidence / (name + ".log")).write_text(result.stdout)
    if result.returncode != expected or (contains and contains not in result.stdout):
        print(result.stdout)
        raise RuntimeError(name + " failed with status " + str(result.returncode))
    print(name + (" EXPECTED FAILURE" if expected else " PASS"), flush=True)
    return result.stdout


python = sys.executable
suite = [
    python,
    "-m",
    "coverage",
    "run",
    "--branch",
    "--source=onair,plugins",
    "-m",
    "pytest",
    "test",
    "--conftest-seed=42",
    "--randomly-seed=42",
    "-q",
]
run("submitted-suite", suite, contains="386 passed")
run(
    "importer-coverage",
    [
        python,
        "-m",
        "coverage",
        "report",
        "--include=onair/src/util/plugin_import.py,onair/src/util/service_import.py",
        "--fail-under=100",
    ],
)
run("format", [python, "-m", "black", "--check", "."])
# The repository's existing pylint configuration makes warnings advisory.
run("pylint", [python, "-m", "pylint", "onair", "plugins", "test"])
files = ["onair/src/util/plugin_import.py", "onair/src/util/service_import.py"]
fixed = {name: (source / name).read_bytes() for name in files}
try:
    for name in files:
        (source / name).write_bytes(
            subprocess.check_output(["git", "show", BASE + ":" + name], cwd=source)
        )
    run(
        "original-regressions",
        [
            python,
            "-m",
            "pytest",
            "--rootdir=.",
            "test/onair/src/util/test_extension_package_loading.py",
            "--conftest-seed=42",
            "--randomly-seed=42",
            "-q",
        ],
        expected=1,
        contains="11 failed, 4 passed",
    )
finally:
    for name, data in fixed.items():
        (source / name).write_bytes(data)
run("restored-suite", suite, contains="386 passed")
run("patch-check", ["git", "diff", "--check", BASE, "HEAD"])
run("restoration-check", ["git", "diff", "--exit-code", "--", *files])
run("environment", [python, "-m", "pip", "freeze"])
print(
    "386 tests passed; importers have 100% line and branch coverage; original 11 failures reproduced; submitted files restored."
)
