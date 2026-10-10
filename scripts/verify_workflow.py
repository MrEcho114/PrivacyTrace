import os
import re
import sys

import yaml

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_task_yaml():
    path = os.path.join(ROOT_DIR, '.github', 'ISSUE_TEMPLATE', 'task.yml')
    assert os.path.exists(path), f"File not found: {path}"
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
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
        "## 关联 Issue",
        "## Problem and resulting behavior",
        "## 验收结果",
        "## Validation",
        "## Review 结论",
        "## Evidence and limits",
        "## 未验证项",
    ]
    for s in sections:
        assert s in content, f"Missing section in PR template: {s}"

    # Check Review checklist items
    review_checks = [
        "满足 Issue 或明确人类授权",
        "没有扩大任务范围",
        "已阅读完整 diff",
        "必要验证（单元测试 / 类型检查 / 构建）已通过",
        "证据边界准确",
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

    # Parse Markdown routing table rows structurally
    table_rows = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if not cells or any(c.startswith(':--') or c.startswith('---') for c in cells):
            continue
        if cells[0] in ('场景类型', '**场景类型**'):
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

    routing_map = {}
    for idx, row in enumerate(table_rows):
        assert len(row) >= 3, f"Row {idx} has fewer than 3 columns: {row}"
        routing_map[row[0]] = row[2]

    for idx, (title, skill) in enumerate(required_scenarios):
        row = table_rows[idx]
        assert title in row[0], (
            f"Row {idx} scenario title mismatch: expected '{title}' in '{row[0]}'"
        )
        assert skill in row[2], (
            f"Routing table row {idx} mismatch for scenario '{title}': "
            f"expected skill '{skill}' in '{row[2]}'"
        )

        matching_keys = [k for k in routing_map if title in k]
        assert len(matching_keys) == 1, (
            f"Expected exactly 1 table row matching scenario '{title}', found {len(matching_keys)}"
        )
        actual_skill = routing_map[matching_keys[0]]
        assert skill in actual_skill, (
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


if __name__ == '__main__':
    print("=" * 60)
    print("Running Comprehensive Workflow Verification Suite")
    print("=" * 60)
    check_task_yaml()
    check_pr_template()
    check_markdown_links()
    check_forbidden_terms()
    check_scenario_routing_table()
    check_blockers_and_handoff_rules()
    check_evidence_boundaries()
    print("=" * 60)
    print("Workflow structure and link integrity verified (docs & templates)")
    print("=" * 60)
