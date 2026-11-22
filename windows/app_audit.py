"""Report actual Windows application evidence, not just successful setup steps.

Only reports a GUI app as 'installed' when a plausible executable exists; this
is not a claim that an interactive RDP desktop launch has been tested.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import subprocess
import sys
from shared.workspace import read_config


def requested(c):
    ide, editor = c.get('ide_choice','none'), c.get('editor_choice','none')
    trader, router = c.get('metatrader_choice','none'), c.get('router_choice','none')
    coding, agents = c.get('coding_agent_choice','none'), c.get('ai_agent_choice','none')
    return {
      'Chrome': True, 'WinRAR': True, 'Node.js': True,
      'VS Code': ide in ('vscode','both'),
      'Antigravity IDE': ide in ('antigravity','both'),
      'CapCut': editor in ('capcut','both'),
      'Shotcut': editor in ('shotcut','both'),
      'MetaTrader 4': trader in ('mt4','both'),
      'MetaTrader 5': trader in ('mt5','both'),
      '9Router': router in ('9router','both'),
      'OmniRoute': router in ('omniroute','both'),
      'Codex CLI': coding in ('codex','both'),
      'Claude Code': coding in ('claude','both'),
      'Hermes': agents in ('hermes','both','all'),
      'OpenClaw': agents in ('openclaw','both','all'),
      'OpenCode': agents in ('opencode','all'),
      'ArtCraft Launcher': str(c.get('install_artcraft',True)).lower()=='true',
    }


def roots(c, env=os.environ):
    pf = Path(env.get('ProgramFiles','C:/Program Files'))
    pf86 = Path(env.get('ProgramFiles(x86)','C:/Program Files (x86)'))
    local = Path(env.get('LOCALAPPDATA','C:/Users/runneradmin/AppData/Local'))
    programs = Path(env.get('ProgramData','C:/ProgramData'))
    user = Path('C:/Users') / c.get('rdp_username','RDP')
    rlocal = user / 'AppData/Local'
    common = programs / 'RDP-Tools/npm'
    return {'pf':pf,'pf86':pf86,'local':local,'programs':programs,
            'user':user,'rlocal':rlocal,'common':common}


def candidates(c, env=os.environ):
    r=roots(c,env); pf=r['pf']; p86=r['pf86']; loc=r['local']; rloc=r['rlocal']; common=r['common']; programs=r['programs']; home=r['user']
    return {
      'Chrome':[pf/'Google/Chrome/Application/chrome.exe',p86/'Google/Chrome/Application/chrome.exe'],
      'WinRAR':[pf/'WinRAR/WinRAR.exe',p86/'WinRAR/WinRAR.exe'],
      'Node.js':[pf/'nodejs/node.exe',p86/'nodejs/node.exe'],
      'VS Code':[pf/'Microsoft VS Code/Code.exe',p86/'Microsoft VS Code/Code.exe',loc/'Programs/Microsoft VS Code/Code.exe',rloc/'Programs/Microsoft VS Code/Code.exe'],
      'Antigravity IDE':[pf/'Antigravity IDE/Antigravity IDE.exe',loc/'Programs/Antigravity IDE/Antigravity IDE.exe',rloc/'Programs/Antigravity IDE/Antigravity IDE.exe',programs/'RDP-Setup/Antigravity IDE/Antigravity IDE.exe'],
      'CapCut':[pf/'CapCut/CapCut.exe',p86/'CapCut/CapCut.exe',rloc/'Programs/CapCut/CapCut.exe',rloc/'CapCut/CapCut.exe',loc/'Programs/CapCut/CapCut.exe'],
      'Shotcut':[pf/'Shotcut/shotcut.exe',p86/'Shotcut/shotcut.exe',loc/'Programs/Shotcut/shotcut.exe'],
      'MetaTrader 4':[pf/'MetaTrader 4/terminal.exe',p86/'MetaTrader 4/terminal.exe',pf/'Exness MT4/terminal.exe'],
      'MetaTrader 5':[pf/'MetaTrader 5/terminal64.exe',pf/'MetaTrader 5/terminal.exe',p86/'MetaTrader 5/terminal64.exe',pf/'Exness MT5/terminal64.exe'],
      '9Router':[common/'9router.cmd',home/'AppData/Roaming/npm/9router.cmd'],
      'OmniRoute':[common/'omniroute.cmd',home/'AppData/Roaming/npm/omniroute.cmd'],
      'Codex CLI':[common/'codex.cmd',home/'AppData/Roaming/npm/codex.cmd'],
      'Claude Code':[home/'.local/bin/claude.exe',common/'claude.cmd',pf/'ClaudeCode/claude.exe'],
      'Hermes':[home/'.local/bin/hermes.exe',loc/'hermes/bin/hermes.exe'],
      'OpenClaw':[common/'openclaw.cmd',home/'AppData/Roaming/npm/openclaw.cmd'],
      'OpenCode':[common/'opencode.cmd',home/'AppData/Roaming/npm/opencode.cmd'],
      'ArtCraft Launcher':[rloc/'Programs/ArtCraft Launcher/artcraft-launcher.exe',pf/'ArtCraft Launcher/artcraft-launcher.exe',p86/'ArtCraft Launcher/artcraft-launcher.exe'],
    }


def inspect(c, exists=lambda p:p.is_file(), env=os.environ):
    wanted=requested(c); paths=candidates(c,env)
    results=[]
    for name,asked in wanted.items():
        if not asked: continue
        found=next((str(p) for p in paths.get(name,[]) if exists(p)),None)
        if found:
            # Executable exists but GUI app launch inside RDP has not been confirmed.
            state='installed' if name in ('Chrome','WinRAR','Node.js','VS Code','Shotcut','MetaTrader 4','MetaTrader 5','CapCut','ArtCraft Launcher') else 'configured'
            detail='Executable found; interactive login/launch not yet confirmed'
        else:
            state='failed'
            detail='Selected, but no executable found in known machine or RDP-user paths'
        results.append((name,state,detail,found))
    return results


def main():
    cfg=read_config(); rows=inspect(cfg)
    print('::group::WFS / Application verification (executable-based)',flush=True)
    installed=missing=0
    for name,state,detail,target in rows:
        if state=='failed': missing+=1
        else: installed+=1
        print(f'[WFS/APP] {name}: {state.upper()}'+(f' | {target}' if target else ''),flush=True)
        p=subprocess.run([sys.executable,'shared/workspace.py','status',f'App: {name}',state,detail],check=False)
        if p.returncode:
            raise RuntimeError(f'Could not record app status: {name}')
    print(f'::endgroup::\n::notice title=WFS application inventory::{installed} executables found; {missing} requested executables missing. See Summary and artifact.',flush=True)
    if missing:
        print(f'::warning title=WFS missing applications::{missing} selected applications have no detected executable. Check installer groups; do not assume step success means installed.',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())