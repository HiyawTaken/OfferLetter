"""FR3 acceptance harness: agreement between the model fit check and your own hand labels.

Usage:
    python tests/fit_eval.py labeled.json --resume resume.txt [--base-url http://127.0.0.1:11434/v1] [--model qwen2.5:14b]

labeled.json is a list of {"description": "...", "label": "pass" | "borderline" | "fail"} (aim for 20).
Runs against a loopback local model only. Prints the actual agreement rate; it does not assert a threshold.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import model_client


def agreement(pairs):
    """pairs: list of (label, predicted). Returns exact and pass-vs-not-pass agreement."""
    n = len(pairs)
    if not n:
        return {'n': 0, 'exact': None, 'binary': None}
    exact = sum(1 for a, b in pairs if a == b) / n
    binary = sum(1 for a, b in pairs if (a == 'pass') == (b == 'pass')) / n
    return {'n': n, 'exact': round(exact, 3), 'binary': round(binary, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('labeled')
    ap.add_argument('--resume', required=True)
    ap.add_argument('--base-url', default='http://127.0.0.1:11434/v1')
    ap.add_argument('--model', required=True)
    args = ap.parse_args()
    items = json.loads(Path(args.labeled).read_text(encoding='utf-8'))
    resume = Path(args.resume).read_text(encoding='utf-8')
    config = {'provider': 'local', 'base_url': args.base_url, 'model': args.model}
    pairs, errors = [], 0
    for i, item in enumerate(items):
        try:
            full = model_client.assess(config, '', item['description'], resume)
            result = full['result']
            if result != item['label']:
                for q in full['requirements']:
                    if q['kind'] == 'required' and q['assessment'] != 'met':
                        print(f"    [{q['assessment']}] {q['requirement'][:100]} | {q['reason'][:110]}")
        except Exception as e:  # a failed call counts as a miss, not a skipped row
            errors += 1
            result = 'error'
            print(f'#{i}: {type(e).__name__}')
        pairs.append((item['label'], result))
        print(f"#{i}: label={item['label']} model={result}")
    print(json.dumps({**agreement(pairs), 'errors': errors}))


if __name__ == '__main__':
    main()
