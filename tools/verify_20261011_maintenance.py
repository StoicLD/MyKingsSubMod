"""Read-only, bounded static verification against the pre-maintenance Git baseline.

This checks token structure and inactive effect branches, not CK3 runtime behavior.
Run with Python -X utf8 -B; JSON goes to stdout, never to the old workspace records.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path('E:/Steam/steamapps/workshop/content/1158310/3684849062')
BASE = '75f76f2'
GATE = 'SanGong_ZongShi_taisun_enfeoffment_enabled_trigger'
TARGETS = {
    'common/character_interactions/SanGong_ZongShi_interactions.txt': 'CeLi_taisun_interaction',
    'common/on_action/SanGong_dead_on_actions.txt': 'CeliTaisun_action',
    'common/scripted_effects/SanGong_ZongShi_effect.txt': 'TaiSun_effect',
    'common/scripted_effects/SanGong_ZongShi_rank_effects.txt': 'SanGong_ZongShi_set_taisun_effect',
    'events/SanGong_Zongzu.txt': 'SanGong_Zongzu.002',
    'events/SanGong_DianZhang.txt': 'SanGong_DianZhang.014',
}
TRIGGERS = 'common/scripted_triggers/SanGong_ZongShi_rank_triggers.txt'
DECISIONS = 'common/decisions/SanGong_DianZhang_decisions.txt'
LOC = 'localization/simp_chinese/replace/zzzzz_core_l_simp_chinese.yml'
CHANGED = set(TARGETS) | {TRIGGERS, DECISIONS, LOC}
checks = []


def check(name, ok):
    checks.append({'check': name, 'passed': bool(ok)})


def git(*args):
    return subprocess.check_output([
        'git', '-c', f'safe.directory={ROOT.as_posix()}', '-c', 'core.autocrlf=false',
        *args], cwd=ROOT)


def old(path):
    return git('show', f'{BASE}:{path}')


def tree(data):
    """Nested token lists, respecting strings, escaped quotes and comments."""
    text = data.decode('utf-8-sig') if isinstance(data, bytes) else data
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|#[^\n]*|[{}=]|[^\s{}=#"]+|"', text)
    root = []
    stack = [root]
    for token in tokens:
        if token.startswith('#'):
            continue
        if token == '"':
            raise ValueError('Unterminated quoted string')
        if token == '{':
            child = []
            stack[-1].append(child)
            stack.append(child)
        elif token == '}':
            if len(stack) == 1:
                raise ValueError('Unexpected closing brace')
            stack.pop()
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError('Unclosed brace')
    return root


def blocks(node, key):
    return [node[i+2] for i in range(len(node)-2)
            if node[i] == key and node[i+1] == '=' and isinstance(node[i+2], list)]


def block(node, key):
    found = blocks(node, key)
    assert len(found) == 1, (key, len(found))
    return found[0]


def restore_enabled(node):
    """Remove only the new false gate and its wrappers, for baseline comparison."""
    result = []
    i = 0
    while i < len(node):
        if node[i:i+3] == [GATE, '=', 'yes']:
            i += 3
        elif node[i:i+2] == ['if', '='] and isinstance(node[i+2], list) and node[i+2][:3] == ['limit', '=', [GATE, '=', 'yes']]:
            result.extend(restore_enabled(node[i+2][3:]))
            i += 3
        elif node[i:i+3] == ['trigger', '=', [GATE, '=', 'yes']]:
            i += 3
        else:
            result.append(restore_enabled(node[i]) if isinstance(node[i], list) else node[i])
            i += 1
    return result


def closed_effect(node):
    return len(node) == 3 and node[:2] == ['if', '='] and isinstance(node[2], list) and node[2][:3] == ['limit', '=', [GATE, '=', 'yes']]


def only_option_effect(node):
    result = []
    i = 0
    while i < len(node):
        if node[i] in ('name', 'ai_chance') and node[i+1] == '=':
            i += 3
        else:
            result.append(node[i])
            i += 1
    return result


def guarded_writes(node, guarded=False):
    findings = []
    if blocks(node, 'limit') == [[GATE, '=', 'yes']]:
        guarded = True
    for i, item in enumerate(node):
        if isinstance(item, list):
            findings.extend(guarded_writes(item, guarded))
        elif item in ('add_trait', 'add_character_flag') and node[i+1:i+2] == ['=']:
            value = node[i+2]
            if value in ('SanGong_TaiSun', 'taisun_flag', 'SanGong_ZongShi_crown_taisun_source'):
                findings.append((value, guarded))
    return findings


def main():
    manifest = json.loads((ROOT/'submod-manifest.json').read_text('utf-8'))
    for record in manifest['files']:
        path = record['path']
        raw = (ROOT/path).read_bytes()
        previous = old(path)
        raw.decode('utf-8-sig', errors='strict')
        check(f'BOM preserved: {path}', raw.startswith(b'\xef\xbb\xbf') == previous.startswith(b'\xef\xbb\xbf'))
        check(f'manifest hash: {path}', hashlib.sha256(raw).hexdigest() == record['sha256'] and len(raw) == record['bytes'])
        if path not in CHANGED | {'README.md'}:
            check(f'untouched file: {path}', raw == previous)
        if record['mode'] == 'override':
            check(f'current upstream hash: {path}', hashlib.sha256((UPSTREAM/path).read_bytes()).hexdigest() == record['upstream_sha256'])

    parsed = {}
    for path, name in TARGETS.items():
        current = tree((ROOT/path).read_bytes())
        previous = tree(old(path))
        parsed[name] = block(current, name)
        # Whole-file equivalence catches any non-target change, including cleanup.
        check(f'only reversible gate additions: {path}', restore_enabled(current) == previous)
    triggers = tree((ROOT/TRIGGERS).read_bytes())
    check('gate always false', block(triggers, GATE) == ['always', '=', 'no'])
    check('all previous triggers unchanged', triggers == tree(old(TRIGGERS)) + [GATE, '=', ['always', '=', 'no']])

    interaction = parsed['CeLi_taisun_interaction']
    for key in ('is_shown', 'is_valid_showing_failures_only'):
        check(f'closed interaction {key}', block(interaction, key)[:3] == [GATE, '=', 'yes'])
    for key in ('populate_recipient_list', 'on_accept'):
        check(f'closed interaction {key}', closed_effect(block(interaction, key)))
    check('AI interaction remains disabled', interaction[-3:] == ['ai_will_do', '=', '0'])
    death = parsed['CeliTaisun_action']
    check('death action cannot schedule', block(death, 'trigger')[:3] == [GATE, '=', 'yes'] and closed_effect(block(death, 'effect')))
    for name in ('TaiSun_effect', 'SanGong_ZongShi_set_taisun_effect'):
        check(f'closed entire effect {name}', closed_effect(parsed[name]))
    for name in ('SanGong_Zongzu.002', 'SanGong_DianZhang.014'):
        event = parsed[name]
        check(f'event blocked {name}', block(event, 'trigger') == [GATE, '=', 'yes'])
        for phase in ('immediate', 'after'):
            check(f'pending event no side effects {name}/{phase}', closed_effect(block(event, phase)))
        for number, option in enumerate(blocks(event, 'option')):
            effects = only_option_effect(option)
            check(f'pending event no option side effects {name}/{number}', not effects or closed_effect(effects))
    check('old picker hidden', block(block(parsed['SanGong_Zongzu.002'], 'widget'), 'is_shown')[:3] == [GATE, '=', 'yes'])

    decisions = tree((ROOT/DECISIONS).read_bytes())
    upstream_decisions = tree((UPSTREAM/DECISIONS).read_bytes())
    def strip_taisun(node):
        result = []
        count = 0
        i = 0
        while i < len(node):
            if node[i:i+3] == ['has_trait', '=', 'SanGong_TaiSun']:
                count += 1
                i += 3
            elif isinstance(node[i], list):
                child, n = strip_taisun(node[i])
                result.append(child)
                count += n
                i += 1
            else:
                result.append(node[i])
                i += 1
        return result, count
    stripped, count = strip_taisun(decisions)
    check('all upstream decision semantics preserved', stripped == upstream_decisions and count == 3)
    grouped = block(decisions, 'SanGong_CeFengZongQin_decisions')
    for phase in ('is_shown', 'widget', 'effect'):
        check(f'TaiSun excluded once in {phase}', strip_taisun(block(grouped, phase))[1] == 1)
    loc = (ROOT/LOC).read_text('utf-8-sig')
    new_line = next(x.strip() for x in (UPSTREAM/LOC).read_text('utf-8-sig').splitlines() if x.strip().startswith('DECISION_VIEW_CHARACTER_PICKER_NAME:'))
    check('only picker localization appended', loc == old(LOC).decode('utf-8-sig').rstrip() + '\n ' + new_line + '\n')
    check('global name key unique', len(re.findall(r'^\s*CHARACTER_FULL_NAME_DYNASTY_ALWAYS_FIRST:', loc, re.M)) == 1)

    # Effective same-path overlay: search all active scripts, excluding .info files.
    effective = {p.relative_to(UPSTREAM).as_posix(): p for p in UPSTREAM.rglob('*') if p.is_file() and p.parts[len(UPSTREAM.parts)] in ('common', 'events', 'gui', 'localization', 'gfx', 'data_binding')}
    effective.update({p.relative_to(ROOT).as_posix(): p for folder in ('common', 'events', 'gui', 'localization', 'gfx', 'data_binding') for p in (ROOT/folder).rglob('*') if p.is_file()})
    writes = []
    gate_defs = []
    event_ids = set()
    for relative, path in effective.items():
        if path.suffix != '.txt':
            continue
        source = path.read_text('utf-8-sig')
        event_ids.update(re.findall(r'^([A-Za-z0-9_]+\.[0-9]+)\s*=\s*\{', source, re.M))
        if re.search(r'^'+GATE+r'\s*=', source, re.M):
            gate_defs.append(relative)
        # Parse files containing identity writes, not unrelated upstream syntax.
        active = re.sub(r'#[^\n]*', '', source)
        if re.search(r'add_(?:trait|character_flag)\s*=\s*(?:SanGong_TaiSun|taisun_flag|SanGong_ZongShi_crown_taisun_source)\b', active):
            writes.extend((relative, value, guarded) for value, guarded in guarded_writes(tree(source)))
    check('gate has exactly one effective definition', gate_defs == [TRIGGERS])
    check('all three effective identity writes are gated', len(writes) == 3 and all(item[2] for item in writes))
    decision_source = (ROOT/DECISIONS).read_text('utf-8-sig')
    refs = set(re.findall(r'(?:trigger_event\s*=\s*|\bid\s*=\s*)([A-Za-z_]+\.[0-9]+)', re.sub(r'#[^\n]*', '', decision_source)))
    check('updated decision event references resolve', refs <= event_ids)
    changed = set(git('diff', '--name-only').decode().splitlines())
    check('tracked diff scope', changed == CHANGED | {'README.md', 'submod-manifest.json'})
    # The baseline manifest uses CRLF, while gameplay files use LF. Preserve both;
    # accept CR only as the existing line terminator, still reject trailing spaces.
    check('whitespace and conflict check', subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-c', 'core.autocrlf=false', '-c', 'core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol', 'diff', '--check'], cwd=ROOT, capture_output=True).returncode == 0)
    check('upstream manifest refreshed', manifest['upstream']['manifest'] == '5109611154849456445')
    check('runtime still unverified', manifest['runtime_verified'] is False)
    result = {'date': '2026-10-11', 'baseline': BASE, 'passed': all(c['passed'] for c in checks), 'checks_passed': sum(c['passed'] for c in checks), 'checks_total': len(checks), 'runtime_verified': False, 'identity_writes': writes, 'checks': checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
