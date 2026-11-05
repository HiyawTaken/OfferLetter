"""Run every automated check: unit tests, then the browser and workflow scripts.

Usage (from this folder):  python run_checks.py [--no-browser]
Browser checks need Chrome installed and local networking. Nothing here touches the real data folder or the network.
"""
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ['jobspy_check', 'e2e_check', 'api_check', 'browser_check', 'account_check', 'cover_e2e', 'cursor_check', 'ui_check']


def run(cmd, label):
    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    ok = result.returncode == 0
    tail = (result.stdout + result.stderr).strip().splitlines()[-1:] or ['']
    print(f"{'PASS' if ok else 'FAIL'}  {label}  {tail[0][:100]}")
    if not ok:
        print((result.stdout + result.stderr)[-1500:])
    return ok


def main():
    results = [run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], 'unit tests')]
    if '--no-browser' not in sys.argv:
        results += [run([sys.executable, f'tests/{name}.py'], name) for name in SCRIPTS]
    print('ALL PASSED' if all(results) else 'FAILURES')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
