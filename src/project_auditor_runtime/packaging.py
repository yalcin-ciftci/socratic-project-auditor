"""Automatic bounded source packets. Source files are read, never executed."""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re
from uuid import uuid4


DIMENSIONS = ['PROBLEM', 'METHOD', 'DECISIONS_AND_TRADEOFFS', 'ASSUMPTIONS',
              'BOUNDARIES_AND_RISKS', 'SUCCESS_METRICS']


def digest(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def package_source(path: Path, *, code: bool = False, domain: str | None = None) -> dict:
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Source exceeds 1 MiB; select a smaller text file.')
    raw = path.read_bytes()
    text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    if '\x00' in text or not text.strip():
        raise ValueError('A non-empty UTF-8 text file is required.')
    domains = {'.py': 'PYTHON_DATA_ENG', '.sql': 'SQL_DATA_ENG', '.r': 'R_STATS',
               '.sps': 'SPSS_STATS', '.sh': 'HARMANOS_SYSTEM_ARCH', '.ps1': 'HARMANOS_SYSTEM_ARCH'}
    if code and path.suffix.lower() not in domains:
        raise ValueError('Supported code files: .py, .sql, .r, .sps, .sh, .ps1 (C/42 excluded).')
    domain = domain or (domains[path.suffix.lower()] if code else 'PROJECT_ARCHITECTURE_GENERAL')
    # Split only at real line boundaries; preserve every character, including trailing LF.
    chunks = []
    current = []
    start = 1
    heading = path.name
    fence = None
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        if len(line) > 6000:
            raise ValueError(f'Line {number} exceeds 6000 characters; split the source line first.')
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line) if not code else None
        header = re.match(r'^#{1,6}\s+(.+?)\s*$', line) if not code and not fence else None
        code_header = re.match(r'^(?:async\s+)?(?:def|class)\s+\w+', line) if code else None
        boundary = bool(header or code_header)
        if current and (boundary or len(current) >= 80 or sum(map(len, current)) + len(line) > 6000):
            chunks.append((start, number - 1, heading, ''.join(current)))
            current = []
            start = number
        if header:
            heading = header.group(1)
        elif code_header:
            heading = code_header.group(0)
        if marker:
            char = marker.group(1)[0]
            fence = None if fence == char else (char if fence is None else fence)
        current.append(line)
    if current:
        chunks.append((start, len(text.splitlines()), heading, ''.join(current)))
    if len(chunks) > 64:
        raise ValueError('Source exceeds the 64-section contract limit; select a smaller document.')
    token = uuid4().hex[:12]
    inv, passages, line_map = [], [], []
    dims = ['METHOD', 'DECISIONS_AND_TRADEOFFS', 'BOUNDARIES_AND_RISKS'] if code else DIMENSIONS
    for i, (first, last, title, content) in enumerate(chunks, 1):
        sid, pid = f'SEC-{i:02d}', f'PSG-{i:02d}'
        heading_path = f'{title[:180]} [lines {first}-{last}]'
        inv.append({'section_id': sid, 'ordinal': i, 'heading_path': heading_path,
                    'section_sha256': digest(content.encode('utf-8')), 'in_current_batch': False,
                    'has_unreadable_visuals': bool(re.search(r'!\[[^\]]*\]\(|<img\b', content)),
                    'unreadable_visual_note': 'Linked images are not inspected.' if re.search(r'!\[[^\]]*\]\(|<img\b', content) else None,
                    'relevant_dimensions': list(dims),
                    'prior_dimension_statuses': [{'dimension': d, 'status': 'OPEN'} for d in dims]})
        passages.append({'passage_id': pid, 'section_id': sid, 'heading_path': heading_path,
                         'verbatim_text': content, 'passage_sha256': digest(content.encode('utf-8')),
                         'completeness': 'COMPLETE', 'claim_epistemic_status': 'IMPLEMENTED' if code else 'PLAN',
                         'evidence_basis': 'OBSERVED_EVIDENCE' if code else 'USER_DECLARATION',
                         'observed_evidence_refs': [f'{path.name[:100]}:{first}-{last} (static source only; not executed)'] if code else [],
                         'cross_section_refs': []})
        line_map.append({'section_id': sid, 'passage_id': pid, 'start_line': first, 'end_line': last})
    return {'token': token, 'file_name': path.name, 'source_sha256': digest(raw),
            'normalized_text_sha256': digest(text.encode('utf-8')), 'line_map': line_map,
            'passages': passages, 'request': {
                'schema_version': 'harmanos.project_auditor.doc_defense.input.v1',
                'task_id': f'CLI-{token}', 'as_of': datetime.now().astimezone().isoformat(timespec='seconds'),
                'operation': 'PREPARE_PROJECT_DEFENSE', 'project_id': f'PROJ-{token}',
                'defense_session_id': f'DDS-{token}', 'learning_domain': domain,
                'allowed_assistance_level': 'QUESTION_AND_CONCEPTUAL_HINT',
                'tool_permissions': {'allowed_tools': [], 'code_execution_allowed': False,
                                     'mutation_allowed': False, 'web_or_mcp_allowed': False,
                                     'subagent_invocation_allowed': False},
                'document_descriptor': {'document_id': f'DOC-{token}', 'document_title': path.name[:240],
                                        'document_type': 'HYBRID_SPEC' if code else 'README_OR_DESIGN_DOC',
                                        'document_version': 'v1', 'document_sha256': digest(raw),
                                        'prior_document_version': None, 'prior_document_sha256': None,
                                        'document_summary': 'Static source supplied for Socratic defense; no execution or measured results verified.' if code else
                                                            'Text supplied for defense. Claims are treated as plans until evidence is supplied.',
                                        'batch_index': 1, 'total_batches': (len(chunks) + 3) // 4},
                'full_section_inventory': inv, 'current_batch_passages': [],
                'contribution_context': {'prepared_by_morks_from_records': True, 'team_structure': 'UNKNOWN',
                                         'user_role_summary': None, 'declared_owned_section_ids': [],
                                         'delegated_or_teammate_section_ids': [],
                                         'prior_assistance_and_help_summary': None,
                                         'missing_contribution_fields': ['TEAM_STRUCTURE', 'USER_ROLE', 'SECTION_OWNERSHIP', 'EXTERNAL_OR_AI_ASSISTANCE']},
                'session_state_snapshot': None, 'prior_defense_batch_package': None, 'defense_responses': []}}
