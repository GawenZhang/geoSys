#!/usr/bin/env python3
"""Add only the /geo location to the existing nginx site."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

SNIPPET_PATH = '/etc/nginx/snippets/geosys.conf'
SNIPPET = Path(SNIPPET_PATH)
MARKER = '# geosys-prefix'
INCLUDE = f'    include {SNIPPET_PATH}; {MARKER}\n'
OLD_SERVER_FILES = (
    Path('/etc/nginx/sites-enabled/geosys.conf'),
    Path('/etc/nginx/sites-available/geosys.conf'),
    Path('/etc/nginx/conf.d/geosys.conf'),
)
PUBLIC_HOST = '110.40.173.15'


def server_blocks(text):
    blocks = []
    index = 0
    while True:
        match = re.search(r'(?m)^[ \t]*server\s*\{', text[index:])
        if not match:
            return blocks
        start = index + match.start()
        brace = index + match.end() - 1
        depth = 0
        for pos in range(brace, len(text)):
            if text[pos] == '{':
                depth += 1
            elif text[pos] == '}':
                depth -= 1
                if depth == 0:
                    blocks.append((start, pos + 1, match.end() - match.start()))
                    index = pos + 1
                    break
        else:
            return blocks


def listens_on_port_80(block):
    for listen in re.findall(r'listen\s+([^;]+);', block):
        if re.search(r'(?:^|[^\d])80(?:[^\d]|$)', listen):
            return listen
    return ''


def score(block):
    listen = listens_on_port_80(block)
    if not listen:
        return 0
    names = ' '.join(re.findall(r'server_name\s+([^;]+);', block))
    if PUBLIC_HOST in names:
        return 300
    if 'default_server' in listen:
        return 200
    if re.search(r'(?:^|\s)_(?:\s|$)', names):
        return 100
    return 50


def enabled_configs():
    found = []
    for directory in (Path('/etc/nginx/sites-enabled'), Path('/etc/nginx/conf.d')):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() and not path.is_symlink():
                continue
            if path.name == 'geosys.conf' or path.name.endswith('.geosys-bak'):
                continue
            if SNIPPET.exists() and path.resolve() == SNIPPET.resolve():
                continue
            found.append(path)
    return found


def choose_server(configs):
    best = None
    for path in configs:
        try:
            text = path.resolve().read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if MARKER in text:
            return path.resolve(), None
        for start, end, header_len in server_blocks(text):
            block = text[start:end]
            value = score(block)
            if value and (best is None or value > best[0]):
                best = (value, path.resolve(), start, header_len, text)
    if best is None:
        return None, None
    return best[1], best


def remove_old_server_files(saved):
    for path in OLD_SERVER_FILES:
        if path.is_symlink() or path.exists():
            saved.append((path, path.resolve().read_text(encoding='utf-8') if path.is_file() else None, path.is_symlink()))
            path.unlink()


def restore(saved, edited, created):
    for path, content, is_link in saved:
        if content is None:
            continue
        path.write_text(content, encoding='utf-8')
    for path, content in edited:
        path.write_text(content, encoding='utf-8')
    for path in created:
        if path.is_symlink():
            path.unlink()


def relink_stock_default(configs, created):
    available = Path('/etc/nginx/sites-available/default')
    enabled = Path('/etc/nginx/sites-enabled/default')
    if enabled.exists() or enabled.is_symlink() or not available.is_file():
        return configs
    if any(score(path.read_text(encoding='utf-8', errors='ignore')) for path in configs if path.exists()):
        return configs
    enabled.symlink_to(available)
    created.append(enabled)
    print('已恢复 /etc/nginx/sites-enabled/default')
    return enabled_configs()


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: install-nginx-prefix.py /path/to/nginx-geosys.conf')
    source = Path(sys.argv[1])
    SNIPPET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, SNIPPET)

    saved = []
    created = []
    remove_old_server_files(saved)
    configs = relink_stock_default(enabled_configs(), created)
    target, chosen = choose_server(configs)
    if target is None:
        restore(saved, [], created)
        raise SystemExit('没有找到监听 80 端口的现有站点，未改 nginx，避免覆盖原网站。')

    edited = []
    if chosen is not None:
        _, _, start, header_len, text = chosen
        if MARKER not in text:
            insert_at = start + header_len
            updated = text[:insert_at] + '\n' + INCLUDE + text[insert_at:]
            edited.append((target, text))
            target.write_text(updated, encoding='utf-8')
            print(f'已在 {target} 增加 /geo，未改原有 location。')
        else:
            print(f'{target} 已包含 /geo。')
    else:
        print(f'{target} 已包含 /geo。')

    test = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
    if test.returncode != 0:
        restore(saved, edited, created)
        sys.stderr.write(test.stderr or test.stdout)
        raise SystemExit('nginx 配置检查失败，已恢复原文件。')
    print('nginx 配置检查通过。')


if __name__ == '__main__':
    main()
