"""Bounded checks for the approved 54-name expansion; does not run CK3.

Compares old bytes after removing the marked additions, then checks new data
against existing option/display/cleanup/inheritance templates. Prints JSON.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
from verify_20261011_maintenance import tree, block, blocks

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path('E:/Steam/steamapps/workshop/content/1158310/3684849062')
BASE = 'fd95957'
NAMES = '息巢滕霍邓舒邹申纪杞葛殷夏鄂彭汴密泽潞沛相襄恒岐陕延济泾漳邺忠荣光仪怀永寿盛信义兴恩嘉端照钦珍和福景昭康吉辉'
IDS = ('xi chao teng huo deng shu zou shen ji_state qi_state ge yin xia e '
       'peng bian mi ze lu pei xiang_state xiang heng qi_prefecture shan yan '
       'ji_prefecture jing zhang ye zhong rong guang yi_ritual huai yong shou '
       'sheng xin yi_righteous xing en jia duan zhao_light qin zhen he fu '
       'jing_auspicious zhao_bright kang ji_auspicious hui').split()
FLAGS = ['flag_MyKingsSubMod_wanghao_' + i for i in IDS]
EVENT = 'events/SanGong_CeFeng.txt'
CLEAN = 'common/scripted_effects/SanGong_action_effects.txt'
DISPLAY = 'common/customizable_localization/SanGong_flag_custom_loc.txt'
TRIGGER = 'common/scripted_triggers/SanGong_HuangShi_trigger.txt'
INHERIT = 'common/scripted_effects/SanGong_dead_effect.txt'
LOC = 'localization/simp_chinese/event/MyKingsSubMod_wanghao_l_simp_chinese.yml'
CATEGORIES = 'localization/simp_chinese/replace/MyKingsSubMod_wanghao_categories_l_simp_chinese.yml'
PINNED = {
    DISPLAY: '59260eee344d1c7f5746d19e7866426f3bf96b00df3d9b7c7a2ddce72d63793c',
    TRIGGER: '7717f2045ffb5ec3ab4b8d22c452baa7d72f899e75964670bbd1242dd468e070',
    INHERIT: 'e6e321efad2627a87b2bfce4ce3d89c502cfb7a351104cbb2d8aa0cafa6b7418',
}
TARGETS = {EVENT, CLEAN, DISPLAY, TRIGGER, INHERIT, LOC, CATEGORIES}
MARK = re.compile(rb'    # BEGIN MyKingsSubMod wanghao additions\r?\n(.*?)    # END MyKingsSubMod wanghao additions\r?\n', re.S)
CHECKS = []


def check(label, ok):
    CHECKS.append({'check': label, 'passed': bool(ok)})


def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}',
                                   '-c', 'core.autocrlf=false', *args], cwd=ROOT)


def clone(value, replacements):
    if isinstance(value, list):
        return [clone(x, replacements) for x in value]
    return replacements.get(value, value)


def main():
    check('approved count and unique identifiers', len(NAMES) == len(IDS) == len(set(NAMES)) == len(set(IDS)) == 54)
    plan = (ROOT/'.codex/plans/2026-10-11-single-character-wanghao-expansion.md').read_text('utf-8')
    check('approved lists match plan', all('、'.join(g) in plan for g in [NAMES[:14], NAMES[14:30], NAMES[30:]]))
    original = {}
    additions = {}
    for rel in [EVENT, CLEAN, DISPLAY, TRIGGER, INHERIT]:
        before = (UPSTREAM/rel).read_bytes() if rel in PINNED else git('show', f'{BASE}:{rel}')
        original[rel] = tree(before)
        if rel in PINNED:
            check(f'upstream hash {rel}', hashlib.sha256(before).hexdigest() == PINNED[rel])
        after = (ROOT/rel).read_bytes()
        check(f'old content byte-identical {rel}', MARK.sub(b'', after) == before)
        check(f'BOM and newline style {rel}', after[:3] == before[:3] and (after.count(b'\r\n') == after.count(b'\n')) == (before.count(b'\r\n') == before.count(b'\n')))
        tree(after)
        additions[rel] = [tree(x) for x in MARK.findall(after)]
        check(f'addition block count {rel}', len(additions[rel]) == (2 if rel == EVENT else 1))

    for idx, (event, first, last, oldflag, oldkey) in enumerate([
        ('SanGong_CeFeng.012', 0, 30, 'flag_SanGong_title_1', 'SanGong_CeFeng.012.a'),
        ('SanGong_CeFeng.013', 30, 54, 'flag_SanGong_title_51', 'SanGong_CeFeng.013.a'),
    ]):
        template = next(o for o in blocks(block(original[EVENT], event), 'option') if o[:3] == ['name', '=', oldkey])
        expected = []
        for i in range(first, last):
            expected += ['option', '=', clone(template, {oldflag: FLAGS[i], oldkey: 'MyKingsSubMod_wanghao_'+IDS[i]})]
        check(f'new options use existing eligibility and grant template {event}', additions[EVENT][idx] == expected)

    old_display = next(t for t in blocks(block(original[DISPLAY], 'SanGong_ZongShiWangHao'), 'text') if 'flag_SanGong_title_1' in t)
    expected_display = []
    for f in FLAGS:
        expected_display += ['text', '=', clone(old_display, {'flag_SanGong_title_1': f})]
    check('new display entries clone old format', additions[DISPLAY][0] == expected_display)
    check('new recognition entries only', additions[TRIGGER][0] == [t for f in FLAGS for t in ['has_character_flag', '=', f]])
    check('new cleanup entries only', additions[CLEAN][0] == [t for f in FLAGS for t in ['remove_character_flag', '=', f]])
    inherit_template = block(block(original[INHERIT], 'SanGong_WangJue_juehao_inherit_effect'), 'if')
    expected_inherit = []
    for f in FLAGS:
        expected_inherit += ['else_if', '=', clone(inherit_template, {'flag_SanGong_title_1': f})]
    check('inheritance copies names using existing scope and condition', additions[INHERIT][0] == expected_inherit)

    locs = {}
    for rel in [LOC, CATEGORIES]:
        data = (ROOT/rel).read_bytes()
        check(f'localization BOM {rel}', data.startswith(b'\xef\xbb\xbf'))
        lines = data.decode('utf-8-sig').splitlines()
        check(f'language and quoted values {rel}', lines[0] == 'l_simp_chinese:' and all(re.fullmatch(r' [A-Za-z0-9_.]+:0 "[^"\n]*"', line) for line in lines[1:]))
        entries = re.findall(r'^ ([A-Za-z0-9_.]+):0 "([^"\n]*)"$', data.decode('utf-8-sig'), re.M)
        check(f'unique localization keys {rel}', len(entries) == len(dict(entries)))
        locs[rel] = dict(entries)
    expected_loc = {}
    for n, ident, flag in zip(NAMES, IDS, FLAGS):
        expected_loc[flag] = n
        expected_loc['MyKingsSubMod_wanghao_'+ident] = '册封$Color_ZanBai$『$'+flag+'$』王#!'
    check('54 name and 54 option keys complete', locs[LOC] == expected_loc)
    check('only two category labels overridden', locs[CATEGORIES] == {
        'SanGong_CeFeng.011.a': '封以古国郡邑之号 #weak （秦、晋、滕、霍、邺……）#!',
        'SanGong_CeFeng.011.b': '封以德行雅称之号 #weak （贤、恭、忠、信、嘉……）#!',
    })
    oldloc = (UPSTREAM/'localization/simp_chinese/event/SanGong_CeFeng_l_simp_chinese.yml').read_text('utf-8-sig')
    oldnames = re.findall(r'^\s*flag_SanGong_title_\d+:\d*\s+"([^"\n]+)"', oldloc, re.M)
    check('new names do not duplicate old names', not set(NAMES).intersection(oldnames))

    game_roots = {'common', 'events', 'gui', 'gfx', 'data_binding', 'localization'}
    basepaths = git('ls-tree', '-r', '--name-only', BASE).decode('utf-8').splitlines()
    basegame = {p for p in basepaths if p.split('/')[0] in game_roots or p == 'descriptor.mod'}
    actual = {p.relative_to(ROOT).as_posix() for folder in game_roots for p in (ROOT/folder).rglob('*') if p.is_file()} | {'descriptor.mod'}
    check('game file inventory has exactly five new files', actual == basegame | (TARGETS - {EVENT, CLEAN}))
    untouched = basegame - {EVENT, CLEAN}
    check('all other gameplay files byte-identical to baseline', all((ROOT/p).read_bytes() == git('show', f'{BASE}:{p}') for p in untouched))
    # Effective IDs: local same-path files supersede upstream; new localization keys must be unique.
    effective = {p.relative_to(UPSTREAM).as_posix(): p for folder in ['common', 'events', 'localization'] for p in (UPSTREAM/folder).rglob('*') if p.is_file()}
    effective.update({p.relative_to(ROOT).as_posix(): p for folder in ['common', 'events', 'localization'] for p in (ROOT/folder).rglob('*') if p.is_file()})
    definition_counts = {key: 0 for key in ['SanGong_ZongShiWangHao', 'SanGong_QinWang_trigger', 'SanGong_WangJue_juehao_inherit_effect']}
    name_counts = dict.fromkeys(expected_loc, 0)
    for rel, p in effective.items():
        if p.suffix not in {'.txt', '.yml'}:
            continue
        text = p.read_text('utf-8-sig')
        if p.suffix == '.txt':
            for key in definition_counts:
                definition_counts[key] += len(re.findall(r'^'+key+r'\s*=\s*\{', text, re.M))
        else:
            for key in re.findall(r'^\s*([\w.]+):', text, re.M):
                if key in name_counts:
                    name_counts[key] += 1
    check('effective overwritten definition IDs unique', all(v == 1 for v in definition_counts.values()))
    check('effective new localization keys unique', all(v == 1 for v in name_counts.values()))

    manifest = json.loads((ROOT/'submod-manifest.json').read_text('utf-8'))
    entries = manifest['files']
    check('manifest inventory complete and unique', len(entries) == len({e['path'] for e in entries}) and {e['path'] for e in entries} == actual | {'README.md'})
    check('manifest hashes and byte counts', all(e['sha256'] == hashlib.sha256((ROOT/e['path']).read_bytes()).hexdigest() and e['bytes'] == (ROOT/e['path']).stat().st_size for e in entries))
    check('new upstream provenance pinned', all(next((e for e in entries if e['path'] == p), {}).get('upstream_sha256') == h for p, h in PINNED.items()))
    check('runtime not claimed', manifest['runtime_verified'] is False)
    whitespace = subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', '-c', 'core.autocrlf=false', '-c', 'core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol', 'diff', '--check'], cwd=ROOT, capture_output=True)
    check('diff whitespace', whitespace.returncode == 0)
    passed = sum(c['passed'] for c in CHECKS)
    print(json.dumps({'date': '2026-10-11', 'baseline': BASE, 'passed': passed == len(CHECKS), 'checks_passed': passed, 'checks_total': len(CHECKS), 'runtime_verified': False, 'new_names': {'geographic': NAMES[:30], 'virtue': NAMES[30:]}, 'game_files_changed': sorted(TARGETS), 'checks': CHECKS}, ensure_ascii=False, indent=2))
    return 0 if passed == len(CHECKS) else 1


if __name__ == '__main__':
    raise SystemExit(main())
