"""GitHub Actions Markdown + dark, static HTML status dashboards for legacy-base Windows workflow.

No secret is included. The HTML is an offline snapshot, not live remote access.
"""
from __future__ import annotations
from html import escape
from pathlib import Path
from collections import Counter
import ipaddress, json, os, re, subprocess, sys
from shared.workspace import state_dir, read_config

COLORS = {'ready':'ok','installed':'ok','configured':'mid','failed':'bad','warning':'warn',
          'timed out':'bad','attempted':'mid','pending interactive':'warn','skipped':'muted',
          'unavailable':'muted','unsupported':'muted'}
TITLES={'access':'REMOTE CONNECTION','apps':'APPLICATIONS & EXTENSIONS'}


def rows_in_state(state:Path):
    rows=[]
    d=state/'status'
    if d.is_dir():
        for f in sorted(d.glob('*.json')):
            try:
                val=json.loads(f.read_text(encoding='utf-8'))
                if isinstance(val, list) and len(val)==3 and all(isinstance(v,str) for v in val):
                    rows.append(tuple(val))
            except (OSError, ValueError):
                continue
    ledger=state/'status.jsonl'
    if ledger.is_file():
        for line in ledger.read_text(encoding='utf-8').splitlines():
            try:
                val=json.loads(line)
                if isinstance(val,list) and len(val)==3 and all(isinstance(v,str) for v in val):
                    rows.append(tuple(val))
            except ValueError:
                continue
    # stable unique key order
    latest={}
    for name,status,detail in rows:
        latest[name]=(name,status,detail)
    return list(latest.values())


def private_v4(value:str)->bool:
    try:
        return ipaddress.IPv4Address(value) in ipaddress.IPv4Network('100.64.0.0/10')
    except ValueError:
        return False


def safe_endpoint(detail):
    # Never convert user-controlled text to an unrestricted link.
    first=detail.split(';')[0].strip()
    if first.startswith('http://'):
        host=first.removeprefix('http://').split('/')[0].split(':')[0]
        return first if private_v4(host) and '/vnc.html' in first else ''
    if first.startswith('https://'):
        host=first.removeprefix('https://').split('/')[0].split(':')[0]
        return first if host.endswith('.ts.net') and '/vnc.html' in first else ''
    return ''



def verified_magicdns():
    """Get the real MagicDNS FQDN from Tailscale if it is available."""
    try:
        result = subprocess.run(['tailscale', 'status', '--json'], capture_output=True,
                                text=True, timeout=6, check=False)
        if result.returncode:
            return ''
        dns = json.loads(result.stdout).get('Self', {}).get('DNSName', '')
        if not isinstance(dns, str):
            return ''
        dns = dns.rstrip('.').lower()
        return dns if re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net', dns) else ''
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return ''


def console_access_lines(cfg, rows):
    """One convenient, copyable access card in the job log; credentials omitted."""
    status = {name: state for name, state, _ in rows}
    ip = tailnet_ipv4(rows)
    rdp_ready = bool(ip and status.get('Windows RDP') == 'ready')
    web = next((safe_endpoint(detail) for name, state, detail in rows
                if name == 'Windows noVNC' and state == 'ready'), '')
    fqdn = next((detail for name, state, detail in rows
                 if name == 'Tailnet DNS' and state == 'ready'), '')
    rdp_command = f'mstsc /v:{ip}:3389 /f' if rdp_ready else 'Not ready / not selected'
    web_status = 'READY' if web else ('FAILED — see 06a' if status.get('Windows noVNC') == 'failed' else 'NOT READY / NOT SELECTED')
    return [
        '[WFS/ACCESS] ========= WINDOWS REMOTE ACCESS =========',
        '[WFS/ACCESS] MODE             : ' + str(cfg.get('remote_access','rdp')).upper(),
        '[WFS/ACCESS] TAILSCALE IPv4   : ' + (ip or 'Not ready'),
        '[WFS/ACCESS] HOSTNAME         : ' + str(cfg.get('hostname','rdp-runner')),
        '[WFS/ACCESS] MAGICDNS         : ' + (fqdn or 'Not available'),
        '[WFS/ACCESS] RDP STATUS       : ' + ('READY' if rdp_ready else 'NOT READY / NOT SELECTED'),
        '[WFS/ACCESS] RDP FULLSCREEN   : ' + rdp_command,
        '[WFS/ACCESS] RDP USER         : ' + str(cfg.get('rdp_username','RDP')),
        '[WFS/ACCESS] noVNC STATUS     : ' + web_status,
        '[WFS/ACCESS] noVNC URL        : ' + (web or 'Not ready / not selected'),
        '[WFS/ACCESS] PASSWORD MODES   : RDP=' + str(cfg.get('rdp_password_mode','same_from_secret')) +
            '; noVNC=' + str(cfg.get('vnc_password_mode','same_from_secret')),
        '[WFS/ACCESS] PASSWORD         : See Job Summary when reveal_random_password=true (random mode only)',
        '[WFS/ACCESS] NETWORK          : Connect from an authorized device on the same Tailscale network',
        '[WFS/ACCESS] =========================================',
    ]


def clean_md(value:str)->str:
    return escape(value,quote=False).replace('|','&#124;').replace('\n',' ')


def tailnet_ipv4(rows):
    """Extract a Tailscale-only IPv4; never trust a public address in a link."""
    for name, state, detail in rows:
        if name != 'Tailnet' or state != 'ready':
            continue
        for token in re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', detail):
            if private_v4(token):
                return token
    return ''


def content(stage:str, cfg:dict, rows:list, outcomes:dict, run_id:str, attempt:str):
    entries={name:(status,detail) for name,status,detail in rows}
    ready=any(entries.get(x,('',))[0]=='ready' for x in ('Windows RDP','Windows noVNC'))
    has_rdp=entries.get('Windows RDP',('',))[0]=='ready'
    has_web=entries.get('Windows noVNC',('',))[0]=='ready'
    private_ip=tailnet_ipv4(rows)
    fqdn = next((d for n,s,d in rows if n == 'Tailnet DNS' and s == 'ready'), '')
    if not private_ip and (has_rdp or has_web): ready=False
    rdp_command=f'mstsc /v:{private_ip}:3389 /f' if private_ip and has_rdp else ''
    vnc_url=safe_endpoint(entries['Windows noVNC'][1]) if has_web else ''
    requested_mode=str(cfg.get('remote_access','rdp')).lower()
    if stage=='access' and requested_mode=='both' and ready and not (has_rdp and has_web):
        headline='PARTIAL ACCESS — RDP ONLY' if has_rdp else 'PARTIAL ACCESS — noVNC ONLY'
    else:
        headline=('READY' if ready else 'SETUP FAILED') if stage=='access' else 'INSTALLATION SNAPSHOT'
    priority=[name for name in ('Tailnet','Windows RDP','Windows noVNC') if name in entries]
    ordered=[(n,*entries[n]) for n in priority]+[(n,s,d) for n,s,d in rows if n not in priority]
    if stage=='apps':
        ordered=[(n,s,d) for n,s,d in ordered if n not in ('Tailnet','Windows RDP','Windows noVNC')]
    if not ordered:
        ordered=[('Setup','warning','No application results were recorded yet')]
    stats=Counter(s for _,s,_ in ordered)
    blocks=[]
    for name,status,detail in ordered:
        css=COLORS.get(status,'muted')
        blocks.append(f'<div class="item"><div class="itemhead"><h3>{escape(name)}</h3><span class="pill {css}">{escape(status.upper())}</span></div><p>{escape(detail)}</p></div>')
    link=''
    if has_web:
        endpoint=safe_endpoint(entries['Windows noVNC'][1])
        if endpoint:
            link=f'<a href="{escape(endpoint,quote=True)}" rel="noreferrer" class="btn">Private noVNC desktop</a>'
    summary=[f'# 🖥️ WFS Windows Workspace · {headline}',
             '',f'> **{TITLES[stage]}** · Run `{run_id}` · Attempt `{attempt}` · Legacy source + modern diagnostics','',
             '| Setting | Value |','|---|---|',
             f'| Runner | `{clean_md(str(cfg.get("windows_version","unknown")))}` |',
             f'| Remote mode | `{clean_md(str(cfg.get("remote_access","rdp")))}` |',
             f'| RDP user | `{clean_md(str(cfg.get("rdp_username","RDP")))}` |',
             f'| Hostname | `{clean_md(str(cfg.get("hostname","rdp-runner")))}` |',
             f'| MagicDNS FQDN | `{clean_md(fqdn) if fqdn else "Tidak tersedia"}` |',
             f'| Requested duration | `{clean_md(str(cfg.get("duration_hours","6")))}` hours (subject to setup time) |','',
             '## Connection and installation checks','','| Component | Status | Detail |','|---|---|---|']
    for n,s,d in ordered:
        # Prevent markdown injection and leaking credential-looking info from future status format.
        summary.append(f'| {clean_md(n)} | **{clean_md(s)}** | {clean_md(d)} |')
    if stage=='access':
        summary+=['','## 🔗 Detail koneksi lengkap','',
                  '| Metode | Alamat / perintah |','|---|---|',
                  f'| Hostname Tailscale | `{clean_md(str(cfg.get("hostname","rdp-runner")))}` |',
                  f'| MagicDNS (jika tersedia) | `{clean_md(fqdn) if fqdn else "Tidak tersedia"}` |',
                  f'| Jenis akses | `{clean_md(str(cfg.get("remote_access","rdp")).upper())}` |',
                  f'| IP Tailscale (IPv4) | `{clean_md(private_ip) if private_ip else "Belum siap"}` |',
                  f'| Windows RDP | `{clean_md(rdp_command) if rdp_command else "Belum siap"}` |',
                  f'| noVNC web | {f"[Buka noVNC]({vnc_url})" if vnc_url else "Belum siap / tidak dipilih"} |',
                  f'| Username RDP | `{clean_md(str(cfg.get("rdp_username","RDP")))}` |',
                  f'| Mode password RDP | `{clean_md(str(cfg.get("rdp_password_mode","same_from_secret")))}` |',
                  f'| Mode password noVNC | `{clean_md(str(cfg.get("vnc_password_mode","same_from_secret")))}` |',
                  '', '> [!TIP]',
                  '> Untuk password `random_each_run`, pilih `reveal_random_password=true` saat Run workflow agar password sesi aktif tampil di Job Summary. Password tidak ditampilkan di log biasa atau dashboard HTML.',
                  '','## Connection instructions','',
                  'Connect your client to the **same Tailscale network**. Use the private Tailscale IPv4 in the Tailnet status above.',
                  'For RDP, run `mstsc /f` and enter the private Tailscale IP, with the user above and the password from `RDP_PASSWORD` (or its per-run derivation).',
                  'For noVNC, use the private browser link shown in Windows noVNC status. VNC authentication may use the compatibility password documented in README.',
                  '', '**Local port checks do not guarantee an interactive desktop.** Test keyboard, mouse, and login from a separate authorized tailnet device.']
    else:
        summary+=['','Installers may be **attempted** or require profile login. Do not interpret a scheduled install as a verified application.']
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>WFS · {escape(TITLES[stage])}</title><style>
:root{{--bg:#070f1c;--panel:#14253b;--line:#304969;--fg:#eaf2fd;--muted:#a6bed6;--blue:#7dd3fc;--green:#67e8b5;--red:#ffacb5;--yellow:#ffe49a;}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 9% -15%,#204773 0,transparent 44%),var(--bg);color:var(--fg);font:15px/1.55 system-ui,Segoe UI,sans-serif}}
main{{max-width:1100px;padding:36px 22px 56px;margin:auto}}header.hero{{background:linear-gradient(110deg,#24496d,#102039);border:1px solid #466991;border-radius:23px;padding:32px}}
.eyebrow{{font-size:11px;letter-spacing:.2em;font-weight:800;color:#9fdbff}}h1{{font-size:clamp(32px,5vw,58px);line-height:1.05;margin:12px 0}}h2{{font-size:18px}}h3{{margin:0;font-size:15px}}
p{{color:var(--muted);margin:7px 0 0}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0 26px}}.stat,.item{{background:var(--panel);border:1px solid var(--line);border-radius:15px}}
.stat{{padding:16px}}.stat b{{font-size:27px;display:block}}.stat small{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.item{{padding:19px}}
.itemhead{{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}}.pill{{padding:3px 10px;border-radius:30px;border:1px solid currentColor;font-size:10px;letter-spacing:.06em}}
.ok{{color:var(--green)}}.bad{{color:var(--red)}}.warn{{color:var(--yellow)}}.mid{{color:var(--blue)}}.muted{{color:var(--muted)}}.btn{{display:inline-block;margin:20px 0 0;border:1px solid #62c9ff;color:#e7f6ff;text-decoration:none;padding:11px 16px;border-radius:10px;background:#17486f}}
.footer{{margin-top:26px;border-top:1px solid var(--line);padding-top:15px;color:var(--muted);font:12px ui-monospace,monospace}}@media(max-width:680px){{main{{padding:17px}}header.hero{{padding:23px}}.stats{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}</style></head>
<body><main><header class="hero"><div class="eyebrow">WFS / REMOTE WORKSPACE · WINDOWS</div><h1>{escape(TITLES[stage])}</h1>
<p>{escape(headline)} · {escape(str(cfg.get('windows_version','unknown')))} · {escape(str(cfg.get('remote_access','rdp')).upper())} · {escape(str(cfg.get('hostname','rdp-runner')))}</p>
<p>Tailscale IPv4: <strong>{escape(private_ip or 'Not ready')}</strong> · Hostname: <strong>{escape(str(cfg.get('hostname','rdp-runner')))}</strong> · MagicDNS: <strong>{escape(fqdn or 'Not available')}</strong></p>
<p>RDP: <code>{escape(rdp_command or 'Not ready')}</code> · User: <code>{escape(str(cfg.get('rdp_username','RDP')))}</code></p>{link}</header>
<section class="stats"><div class="stat"><b>{stats['ready']+stats['installed']}</b><small>Verified ready</small></div><div class="stat"><b>{stats['configured']+stats['attempted']}</b><small>Configured / attempted</small></div>
<div class="stat"><b>{stats['failed']+stats['timed out']}</b><small>Failed</small></div><div class="stat"><b>{stats['warning']+stats['pending interactive']}</b><small>Needs attention</small></div></section>
<section class="grid" aria-label="Status details">{''.join(blocks)}</section>
<div class="footer">Run {escape(run_id)} / Attempt {escape(attempt)} · Offline snapshot · No passwords or tokens · Interactive login not yet certified</div></main></body></html>'''
    return '\n'.join(summary)+'\n',html


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in (*TITLES, 'console'):
        raise SystemExit('Specify access, apps or console')
    stage=sys.argv[1]; state=state_dir()
    cfg=read_config()
    run=os.environ.get('GITHUB_RUN_ID','local'); attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1')
    if not (re.fullmatch(r'(local|[0-9]+)',run) and re.fullmatch(r'[0-9]+',attempt)):
        raise SystemExit('Invalid run identity')
    rows=rows_in_state(state)
    if stage in ('access', 'console') and any(n == 'Tailnet' and v == 'ready' for n,v,_ in rows):
        dns = verified_magicdns()
        if dns:
            rows.append(('Tailnet DNS', 'ready', dns))
    if stage == 'console':
        for line in console_access_lines(cfg, rows):
            print(line, flush=True)
        status_by_name={n:state for n,state,_ in rows}
        if cfg.get('remote_access')=='both' and status_by_name.get('Windows noVNC')!='ready':
            print('::warning title=WFS PARTIAL REMOTE ACCESS::RDP is available, but requested noVNC was not verified. See noVNC stage 06a.',flush=True)
        return
    if stage == 'apps':
        keys=('ide_choice','editor_choice','metatrader_choice','router_choice','coding_agent_choice','ai_agent_choice')
        choices='; '.join(f'{key}={cfg.get(key, "none")}' for key in keys)
        print('[WFS/APP/SELECT] Requested application choices: '+choices, flush=True)
        print('[WFS/APP/SELECT] install_artcraft='+str(cfg.get('install_artcraft',False)), flush=True)
        print('[WFS/APP/SELECT] Apps not selected were intentionally skipped.',flush=True)
    summary, page=content(stage,cfg,rows,{},run,attempt)
    if stage == 'access':
        for line in console_access_lines(cfg, rows):
            print(line, flush=True)
    target=Path(os.environ['RUNNER_TEMP'])/f'wfs-legacy-{("connection" if stage=="access" else "apps")}-{run}-{attempt}.html'
    target.write_text(page,encoding='utf8')
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf8') as f:f.write(summary)
    print(f'[WFS/DASHBOARD] {stage}: {len(rows)} status items captured; artifact prepared',flush=True)


if __name__=='__main__':main()