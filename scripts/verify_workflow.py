"""Workflow verification suite for PrivacyTrace documentation, templates, and agent configs.

This script performs structural integrity and link validity checks on workflow guides,
issue/PR templates, and domain vocabulary. It is a non-mandatory local self-check suite
(invoked via `uv run --with pyyaml python scripts/verify_workflow.py`).
"""

import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "Error: PyYAML is required to run scripts/verify_workflow.py.\n"
        "Please install PyYAML (e.g., 'pip install PyYAML') or run via uv (e.g., 'uv run --with pyyaml python scripts/verify_workflow.py').\n"
    )
    sys.exit(1)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_task_yaml():
    path = os.path.join(ROOT_DIR, '.github', 'ISSUE_TEMPLATE', 'task.yml')
    assert os.path.exists(path), f"File not found: {path}"
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    data = yaml.safe_load(content)
    print("task.yml keys:", list(data.keys()))
    assert 'name' in data, "task.yml missing 'name'"
    assert 'description' in data, "task.yml missing 'description'"
    assert 'body' in data, "task.yml missing 'body'"
    body = data['body']
    assert isinstance(body, list), "task.yml 'body' must be a list"

    ids = [elem.get('id') for elem in body if isinstance(elem, dict)]
    print("Found IDs in task.yml:", ids)
    required_ids = [
        'pt-id',
        'goal',
        'scope',
        'out-of-scope',
        'specs-and-adrs',
        'blockers',
        'acceptance',
        'validation',
        'handoff',
    ]
    for rid in required_ids:
        assert rid in ids, f"Missing required id in task.yml: {rid}"

    # Verify structural integrity of each element
    for elem in body:
        assert 'type' in elem, f"Element missing 'type': {elem}"
        etype = elem['type']
        assert etype in [
            'input',
            'textarea',
            'markdown',
            'dropdown',
            'checkboxes',
        ], f"Invalid type: {etype}"
        if etype in ['input', 'textarea']:
            attrs = elem.get('attributes', {})
            assert 'label' in attrs and attrs['label'].strip(), (
                f"Element {elem.get('id')} missing non-empty attributes.label"
            )

    # Verify required validations for critical fields
    required_validations = ['pt-id', 'goal', 'scope', 'acceptance']
    for elem in body:
        eid = elem.get('id')
        if eid in required_validations:
            validations = elem.get('validations', {})
            assert validations.get('required') is True, (
                f"Field '{eid}' must have validations.required: true"
            )

    # Verify blockers description states waiting requirement
    blockers_elem = next(e for e in body if e.get('id') == 'blockers')
    assert '等待' in blockers_elem['attributes']['description'], (
        "blockers description must state waiting requirement"
    )

    # Verify handoff mentions all 4 essential elements: branch, commit, progress, remaining work
    handoff_elem = next(e for e in body if e.get('id') == 'handoff')
    handoff_text = (
        handoff_elem['attributes']['description']
        + " "
        + handoff_elem['attributes'].get('placeholder', '')
    )
    for elem_name in ['分支', '提交', '进展', '剩余工作']:
        assert elem_name in handoff_text, (
            f"task.yml handoff must mention '{elem_name}'"
        )

    print("task.yml: ALL REQUIRED FIELDS AND STRUCTURES VALID")


def check_pr_template():
    path = os.path.join(ROOT_DIR, '.github', 'PULL_REQUEST_TEMPLATE.md')
    assert os.path.exists(path), f"File not found: {path}"
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    sections = [
        "## Related task",
        "## Result",
        "## Changes",
        "## Verification",
        "## Agent self-review",
        "## Evidence and limits",
        "## 未验证项",
    ]
    for s in sections:
        assert s in content, f"Missing section in PR template: {s}"

    # Check Acceptance and Validation subsections under Verification
    assert "### 验收结果" in content, "Missing '### 验收结果' in PR template"
    assert "### Validation" in content, "Missing '### Validation' in PR template"
    assert "Issue: Closes #<number>" in content, "Missing 'Issue: Closes #<number>' in PR template"

    # Check Review checklist items matching TheMasterplan CI check exactly
    review_checks = [
        "满足 Issue 或明确人类授权",
        "没有扩大任务范围",
        "已阅读完整 diff",
        "必要验证已通过",
        "没有遗留调试代码、临时文件或缓存",
    ]
    for rc in review_checks:
        assert rc in content, (
            f"Missing review checklist item in PR template: {rc}"
        )

    # Check Evidence and limits statement
    assert (
        "Confirm the evidence remains traceable, policy sources remain separate,"
        " and static evidence is described as potential behavior."
        in content
    ), "Missing evidence and limits sentence"

    # Check unverified walkthrough note
    assert (
        "在真实成员试用前将测试结果准确标记为文档场景走查" in content
    ), "Missing walkthrough classification note in unverified section"

    print("PULL_REQUEST_TEMPLATE.md: ALL REQUIRED SECTIONS AND CRITERIA PRESENT")


def check_markdown_links():
    files = [
        'docs/agents/skills-workflow.md',
        'CONTRIBUTING.md',
        'AGENTS.md',
        'docs/agents/issue-tracker.md',
        'docs/agents/triage-labels.md',
        'docs/agents/domain.md',
    ]
    broken_links = []
    total_links = 0
    for f in files:
        full_path = os.path.join(ROOT_DIR, f)
        assert os.path.exists(full_path), f"Document file not found: {full_path}"
        base_dir = os.path.dirname(full_path)
        with open(full_path, 'r', encoding='utf-8') as fp:
            content = fp.read()
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
        print(f"\nChecking links in {f} (count: {len(links)}):")
        total_links += len(links)
        for text, target in links:
            if target.startswith(('http://', 'https://')):
                print(f"  [EXTERNAL] [{text}] -> {target}")
                continue
            target_path = target.split('#')[0]
            if not target_path:
                print(f"  [ANCHOR] [{text}] -> {target}")
                continue
            resolved = os.path.normpath(os.path.join(base_dir, target_path))
            exists = os.path.exists(resolved)
            status = "OK" if exists else "BROKEN"
            print(f"  [{status}] [{text}]({target}) -> {resolved}")
            if not exists:
                broken_links.append((f, text, target, resolved))

    assert len(broken_links) == 0, f"Broken markdown links found: {broken_links}"
    print(f"\nMarkdown links validity: ALL {total_links} LINKS VALID")
    return True


def check_forbidden_terms():
    terms = [
        '实际采集证据',
        '违规证据',
        '最新政策',
        '已验证政策',
        '已匹配条款',
        '事实结论',
        '隐私测谎',
        '合规认证',
        '检测失败',
        '没有采集',
        '阶段通过',
        '备注已保存',
        '单测数量',
        '商业 App 全局真值',
        '实时分析',
        '当前最新结果',
        '系统结果',
        '运行后修改的答案',
        '自动政策理解',
        '全自动核验',
    ]
    files = [
        'docs/agents/skills-workflow.md',
        'CONTRIBUTING.md',
        'AGENTS.md',
        '.github/ISSUE_TEMPLATE/task.yml',
        '.github/PULL_REQUEST_TEMPLATE.md',
        'docs/agents/issue-tracker.md',
        'docs/agents/triage-labels.md',
        'docs/agents/domain.md',
    ]
    violations = []
    for f in files:
        full_path = os.path.join(ROOT_DIR, f)
        with open(full_path, 'r', encoding='utf-8') as fp:
            for idx, line in enumerate(fp, 1):
                for t in terms:
                    if t in line:
                        # Only allow if the line is an explicit negative definition / prohibition
                        is_prohibition_def = any(
                            kw in line
                            for kw in [
                                '例如禁止使用',
                                '禁止使用',
                                '严格避免',
                                'Avoid',
                            ]
                        )
                        if is_prohibition_def:
                            continue
                        violations.append((f, idx, t, line.strip()))

    assert len(violations) == 0, f"Forbidden GLOSSARY terms found: {violations}"
    print("Forbidden terms check: PASSED (0 violations line-by-line)")
    return True


def check_scenario_routing_table():
    workflow_path = os.path.join(ROOT_DIR, 'docs', 'agents', 'skills-workflow.md')
    with open(workflow_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Locate section "## 4. 任务路由表" to avoid picking up unrelated tables
    section_marker = "## 4. 任务路由表"
    assert section_marker in content, f"Section '{section_marker}' missing from skills-workflow.md"
    section_start = content.index(section_marker)
    # Find next top-level section starting with "## " or end of file
    next_section = re.search(r'\n##\s+', content[section_start + len(section_marker):])
    if next_section:
        section_content = content[section_start : section_start + len(section_marker) + next_section.start()]
    else:
        section_content = content[section_start:]

    # Parse specifically the Markdown routing table (from header row to table termination)
    lines = section_content.splitlines()
    in_routing_table = False
    header_found = False
    table_rows = []

    def parse_cells(l: str):
        raw_cells = re.split(r'(?<!\\)\|', l)[1:-1]
        return [c.replace(r'\|', '|').strip() for c in raw_cells]

    def is_separator(cells):
        return bool(cells) and all(bool(re.match(r'^:?\s*-+\s*:?$', c)) for c in cells)

    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith('|') and stripped.endswith('|')):
            if in_routing_table:
                # Contiguous markdown table has terminated
                break
            continue

        cells = parse_cells(stripped)
        if not header_found:
            clean_first = re.sub(r'[*`_]', '', cells[0]).strip() if cells else ''
            if clean_first == '场景类型':
                header_found = True
            continue

        if not in_routing_table:
            assert is_separator(cells), f"Expected separator row following table header, got: {stripped}"
            in_routing_table = True
            continue

        if is_separator(cells):
            continue
        table_rows.append(cells)

    # Verify all 9 scenario keys exist in the routing table with strict 1-to-1 mapping
    required_scenarios = [
        ('1. 入口不确定', 'ask-matt'),
        ('2. 新功能需求梳理', 'grill-with-docs'),
        ('3. 跨会话 Spec / Ticket 拆分', 'to-spec'),
        ('4. 已明确工单实施', 'implement'),
        ('5. 范围明确的小改动', 'implement'),
        ('6. 外部反馈分流', 'triage'),
        ('7. 棘手 Bug 排查', 'diagnosing-bugs'),
        ('8. 整份 Spec 编排推进', 'implement-spec'),
        ('9. 换人交接 / 跨会话接手', 'Handoff'),
    ]

    assert len(table_rows) == len(required_scenarios), (
        f"Expected {len(required_scenarios)} table rows in routing table, found {len(table_rows)}"
    )

    def skill_matches(expected_skill: str, cell_text: str) -> bool:
        pattern = r'(?<![\w-])' + re.escape(expected_skill) + r'(?![\w-])'
        return bool(re.search(pattern, cell_text, re.IGNORECASE))

    routing_map = {}
    for idx, row in enumerate(table_rows):
        assert len(row) == 5, f"Row {idx} expected 5 columns, found {len(row)}: {row}"
        clean_key = re.sub(r'[*`_]', '', row[0]).strip()
        assert clean_key not in routing_map, f"Duplicate scenario row in routing table: '{clean_key}'"
        routing_map[clean_key] = row[2]

    for idx, (title, skill) in enumerate(required_scenarios):
        row = table_rows[idx]
        clean_row_title = re.sub(r'[*`_]', '', row[0]).strip()
        assert clean_row_title == title, (
            f"Row {idx} scenario title mismatch: expected exact title '{title}', got '{clean_row_title}'"
        )
        assert skill_matches(skill, row[2]), (
            f"Routing table row {idx} mismatch for scenario '{title}': "
            f"expected skill '{skill}' in '{row[2]}'"
        )

        assert title in routing_map, (
            f"Expected table row key matching scenario '{title}' in routing map"
        )
        actual_skill = routing_map[title]
        assert skill_matches(skill, actual_skill), (
            f"Routing table mapping mismatch for scenario '{title}': "
            f"expected skill '{skill}' in '{actual_skill}'"
        )

    # Verify CONTRIBUTING.md contains matching entry points for all 9 scenarios
    with open(os.path.join(ROOT_DIR, 'CONTRIBUTING.md'), 'r', encoding='utf-8') as f:
        contrib_content = f.read()
    contrib_entries = [
        '入口不确定',
        '新功能需求梳理',
        '跨会话中大型需求',
        '已明确工单',
        '范围明确的小改动',
        '外部反馈',
        '棘手 Bug 排查',
        '整份 Spec 编排推进',
        '换人交接',
    ]
    for ce in contrib_entries:
        assert ce in contrib_content, f"Entry '{ce}' missing in CONTRIBUTING.md"

    # Verify AGENTS.md contains explicit call rule and navigation reminders for routing table
    with open(os.path.join(ROOT_DIR, 'AGENTS.md'), 'r', encoding='utf-8') as f:
        agents_content = f.read()
    agents_reminders = [
        'ask-matt',
        'grill-with-docs',
        'diagnosing-bugs',
        'implement',
        'to-spec',
        'triage',
        'implement-spec',
        '显式调用原则',
        '范围明确的小改动',
    ]
    for ar in agents_reminders:
        assert ar in agents_content, f"Reminder '{ar}' missing in AGENTS.md"

    print("Scenario routing table check: ALL 9 SCENARIOS FULLY COVERED AND ALIGNED")
    return True


def check_blockers_and_handoff_rules():
    with open(
        os.path.join(ROOT_DIR, 'docs', 'agents', 'skills-workflow.md'),
        'r',
        encoding='utf-8',
    ) as f:
        workflow_content = f.read()
    with open(os.path.join(ROOT_DIR, 'CONTRIBUTING.md'), 'r', encoding='utf-8') as f:
        contrib_content = f.read()
    with open(os.path.join(ROOT_DIR, 'AGENTS.md'), 'r', encoding='utf-8') as f:
        agents_content = f.read()

    # Waiting on blockers rule
    for name, text in [
        ('skills-workflow.md', workflow_content),
        ('CONTRIBUTING.md', contrib_content),
        ('AGENTS.md', agents_content),
    ]:
        assert '未解除' in text and ('原地等待' in text or '必须等待' in text), (
            f"Blocker waiting rule missing or incomplete in {name}"
        )
        assert '严禁在阻塞未解除前提前启动' in text, (
            f"Strict non-early-start rule missing in {name}"
        )

    # Handoff context rule
    handoff_elements = ['分支', '提交', '进展', '剩余工作']
    for he in handoff_elements:
        assert he in workflow_content, (
            f"Handoff requirement element '{he}' missing in skills-workflow.md"
        )
        assert he in contrib_content, (
            f"Handoff requirement element '{he}' missing in CONTRIBUTING.md"
        )
        assert he in agents_content, (
            f"Handoff requirement element '{he}' missing in AGENTS.md"
        )

    print("Blockers and handoff rules: ALL RULES FULLY ENFORCED ACROSS ALL ENTRY DOCS")
    return True


def check_evidence_boundaries():
    with open(
        os.path.join(ROOT_DIR, 'docs', 'agents', 'skills-workflow.md'),
        'r',
        encoding='utf-8',
    ) as f:
        workflow_content = f.read()
    with open(
        os.path.join(ROOT_DIR, '.github', 'PULL_REQUEST_TEMPLATE.md'),
        'r',
        encoding='utf-8',
    ) as f:
        pr_content = f.read()
    with open(os.path.join(ROOT_DIR, 'CONTRIBUTING.md'), 'r', encoding='utf-8') as f:
        contrib_content = f.read()
    with open(os.path.join(ROOT_DIR, 'AGENTS.md'), 'r', encoding='utf-8') as f:
        agents_content = f.read()

    assert '文档场景走查' in workflow_content, (
        "Missing '文档场景走查' in skills-workflow.md"
    )
    assert '文档场景走查' in pr_content, "Missing '文档场景走查' in PULL_REQUEST_TEMPLATE.md"
    assert '静态证据不能证明运行时已发生数据收集或外传' in workflow_content, (
        "Missing static evidence boundary rule in skills-workflow.md"
    )
    assert '静态证据不能证明运行时收集或外传' in contrib_content, (
        "Missing static evidence rule in CONTRIBUTING.md"
    )
    assert '严格区分静态证据' in agents_content and '潜在线索' in agents_content, (
        "Missing static evidence boundary in AGENTS.md"
    )

    print("Evidence boundaries check: STRICTLY ENFORCED AND ACCURATELY LABELED")
    return True


def check_skills_version_baseline():
    workflow_path = os.path.join(ROOT_DIR, 'docs', 'agents', 'skills-workflow.md')
    with open(workflow_path, 'r', encoding='utf-8') as f:
        wf_content = f.read()

    contrib_path = os.path.join(ROOT_DIR, 'CONTRIBUTING.md')
    with open(contrib_path, 'r', encoding='utf-8') as f:
        contrib_content = f.read()

    agents_path = os.path.join(ROOT_DIR, 'AGENTS.md')
    with open(agents_path, 'r', encoding='utf-8') as f:
        agents_content = f.read()

    expected_repo = 'https://github.com/vinvcn/mattpocock-skills-zh-CN'
    expected_sha = 'bf98e53f92089fec9b4885f128a565d7eac0337f'
    expected_date = '2026-10-10'

    assert expected_repo in wf_content, (
        f"Skills repo '{expected_repo}' missing in skills-workflow.md"
    )
    assert expected_sha in wf_content, (
        f"Baseline commit SHA '{expected_sha}' missing in skills-workflow.md"
    )
    assert expected_date in wf_content, (
        f"Verification date '{expected_date}' missing in skills-workflow.md"
    )
    assert '流程维护工单' in wf_content, (
        "Upgrade protocol ('流程维护工单') missing in skills-workflow.md"
    )
    assert '流程维护工单' in contrib_content, (
        "Upgrade protocol ('流程维护工单') missing in CONTRIBUTING.md"
    )

    # Ensure no floating branch baseline descriptions across all entry docs
    floating_terms = [
        '主分支最新可用稳定基线',
        '主分支最新稳定版本',
        '最新可用稳定基线',
    ]
    for doc_name, doc_text in [
        ('skills-workflow.md', wf_content),
        ('CONTRIBUTING.md', contrib_content),
        ('AGENTS.md', agents_content),
    ]:
        for term in floating_terms:
            if term in doc_text:
                for line in doc_text.splitlines():
                    if term in line:
                        is_prohibition = any(
                            p in line
                            for p in ['不再使用', '禁止', '严格避免', 'Avoid']
                        )
                        assert is_prohibition, (
                            f"Floating baseline term '{term}' found in {doc_name}: {line.strip()}"
                        )

    # Verify minimal executable installation steps in skills-workflow.md
    assert 'git clone https://github.com/vinvcn/mattpocock-skills-zh-CN.git' in wf_content, (
        "Missing 'git clone' repository URL in skills-workflow.md"
    )
    assert f'git checkout {expected_sha}' in wf_content, (
        f"Missing 'git checkout {expected_sha}' step in skills-workflow.md"
    )
    assert 'git rev-parse HEAD' in wf_content, (
        "Missing 'git rev-parse HEAD' command in skills-workflow.md"
    )
    assert f'*核验输出必须严格为：`{expected_sha}`*' in wf_content, (
        f"Verification output missing expected SHA '{expected_sha}' in skills-workflow.md"
    )
    for agent_kw in ['Claude Code', 'Codex', 'Google Antigravity', 'Cursor']:
        assert agent_kw in wf_content, f"Missing Agent configuration for '{agent_kw}' in skills-workflow.md"

    print("Skills version baseline check: PINNED TO FIXED COMMIT SHA (NO FLOATING TERMS)")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Running Comprehensive Workflow Verification Suite")
    print("=" * 60)
    check_task_yaml()
    check_pr_template()
    check_markdown_links()
    check_forbidden_terms()
    check_scenario_routing_table()
    check_skills_version_baseline()
    check_blockers_and_handoff_rules()
    check_evidence_boundaries()
    print("=" * 60)
    print("Workflow structure and link integrity verified (docs & templates)")
    print("=" * 60)
