# Make sure your python is in PATH, otherwise do something like below before running this script
# $env:PATH = "$env:PATH;E:\Python\Python311"

$cwd = Get-Location

if (! ((Get-Item .env) -as [bool])) {
    python -m venv .env
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

    $env:PATH = "$env:PATH;$env:APPDATA\Python\Scripts"
    poetry install --sync
} else {
    $env:PATH = "$env:PATH;$env:APPDATA\Python\Scripts"
}

$env:POETRY_VENV = "$cwd/.venv"
$env:POETRY_DEPS = "$env:POETRY_VENV/.deps"

poetry run python -c "import sys; sys.path.append('$cwd/bin'); from lib.ce_install import main; main()" $args
