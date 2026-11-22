"""Opt-in disclosure of derived per-run credentials to GitHub Job Summary only.

No fixed secret, seed, or derived password is printed to regular Actions logs
or the downloadable connection HTML dashboard.
"""
import os
from pathlib import Path

from shared.workspace import derive, read_config, state_dir
from windows.legacy_dashboard import rows_in_state


def ready_random_passwords(cfg, rows, environment):
    states = {name: status for name, status, _ in rows}
    targets = (
        ('Windows RDP', 'rdp', 'rdp_password_mode', 'RDP_PASSWORD'),
        ('Windows noVNC', 'web', 'vnc_password_mode', 'VNC_PASSWORD'),
    )
    selected = []
    for name, role, mode, secret_key in targets:
        if states.get(name) != 'ready' or cfg.get(mode) != 'random_each_run':
            continue
        seed = environment.get(secret_key, '')
        if not seed:
            raise ValueError('Missing ' + secret_key + ' for per-run password display')
        selected.append((name, derive(cfg, role, seed)))
    return selected


def summary_fragment(cfg, rows, environment):
    if environment.get('WFS_REVEAL_RANDOM_PASSWORD', '').lower() != 'true':
        raise ValueError('Explicit password disclosure opt-in is required')
    selected = ready_random_passwords(cfg, rows, environment)
    if not selected:
        return '## Password acak\n\nTidak ada endpoint aktif dengan password acak untuk ditampilkan.\n\n'
    result = [
        '## Password acak untuk run ini (Anda mengaktifkan pengungkapan)', '',
        '> [!CAUTION]',
        '> Password di bawah dapat dilihat oleh siapa saja yang memiliki izin',
        '> melihat GitHub Actions run ini. Jangan bagikan Job Summary.', '',
        '| Akses | Password sesi aktif |', '| --- | --- |',
    ]
    for access, password in selected:
        result.append(f'| {access} | <code>{password}</code> |')
    result.extend(['', 'Password berasal dari secret yang Anda simpan dan berbeda per run.',
                   'Seed secret asli tidak ditampilkan.', ''])
    return '\n'.join(result) + '\n'


def main():
    cfg = read_config()
    rows = rows_in_state(state_dir())
    fragment = summary_fragment(cfg, rows, os.environ)
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as out:
        out.write(fragment)
    print('[WFS/ACCESS] Derived password appended to Job Summary by explicit opt-in; not shown in job logs.', flush=True)


if __name__ == '__main__':
    main()
