from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Protocol

from ._compat import atomic_replace, flock_ex_nb, flock_un, open_lock_fd

TAXONOMY = frozenset(['decision', 'lesson', 'failure', 'trajectory', 'tool', 'codebase', 'preference', 'review_pattern', 'security_pattern', 'environment'])
LIFECYCLE = frozenset(['active', 'stale', 'superseded', 'revoked', 'unverified'])
TRUST = ('human', 'deterministic', 'gate', 'security', 'reviewer', 'landed', 'agent')
REVIEWER_TRUST = frozenset(('gate', 'security', 'reviewer', 'landed', 'human'))
SOURCE_TYPES = ('artifact', 'journal', 'evidence')
MAX_BYTES = 4_000_000
BAD = re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|(?:disable|bypass)\s+(?:guards?|security|gates?)|(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*\S+|-----BEGIN .*PRIVATE KEY|\b(?:sk-[\w-]{12,}|AKIA[A-Z0-9]{16}|ghp_[\w]{20,})|<\|(?:system|im_start)\|>|bỏ qua (?:luật|hướng dẫn)', re.IGNORECASE)
SECRET_PATTERNS = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+|(?:token|secret|password|passwd|pwd|api[_-]?key|access[_-]?key|client[_-]?secret|github_pat_[a-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_=-]{20,}\.eyJ[A-Za-z0-9_=-]{20,})\s*[:=]\s*\S+|(?:https?://[^\s]*?(?:token|key|password|secret)=[^\s]+)")


class MemoryError(ValueError):
    pass


def screen(value, *, where='value'):
    if isinstance(value, dict):
        for key, item in value.items():
            screen(key, where=where)
            screen(item, where=where)
    elif isinstance(value, (list, tuple)):
        for item in value:
            screen(item, where=where)
    elif isinstance(value, str) and (
        BAD.search(value) or SECRET_PATTERNS.search(value)
        or any(ord(c) < 32 and c not in '\n\r\t' for c in value)
    ):
        raise MemoryError(f'memory rejected: sensitive or instruction-like content in {where}')


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative:
        raise MemoryError('unsafe memory path')
    if len(relative) > 1024 or ':' in relative[1:]:
        raise MemoryError('unsafe memory path')
    screen(relative, where='path')
    if relative in ('.', '/') or any(part.endswith((' ', '.')) for part in relative.split('/')):
        raise MemoryError('unsafe memory path')
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or any(
        x.lower() in {'.env', '.ssh', '.aws', '.git', 'credentials', 'auth.json', 'secrets'}
        or x.lower().startswith('.env.')
        or x.lower().endswith(('.pem', '.key', '.p12', '.pfx'))
        or x.startswith('-')
        for x in p.parts
    ):
        raise MemoryError('unsafe memory path')
    current = Path(root)
    try:
        resolved_root = _resolved(root)
    except (OSError, RuntimeError) as exc:
        raise MemoryError('memory path escapes project') from exc
    for part in p.parts:
        current /= part
        try:
            if current.is_symlink():
                raise MemoryError('symlink memory path')
        except OSError as err:
            raise MemoryError('unsafe memory path') from err
    try:
        resolved = _resolved(current)
    except (OSError, RuntimeError) as err:
        raise MemoryError('unsafe memory path') from err
    if not (resolved == resolved_root or resolved_root in resolved.parents):
        raise MemoryError('memory path escapes project')
    return Path(resolved_root) / PurePosixPath(relative)


def _resolved(p) -> Path:
    r"""`Path.resolve()` without the extended-length prefix. On Windows, CPython's realpath keeps `\\?\` when the
    file exists at its first lookup but not at its second — another process atomically replacing the store between
    the two (SS-91, CI 2026-09-18: 2 of 8 concurrent writers refused with 'memory path escapes project')."""
    s = str(Path(p).resolve())
    if s.startswith('\\\\?\\UNC\\'):
        s = '\\\\' + s[8:]
    elif s.startswith('\\\\?\\'):
        s = s[4:]
    return Path(s)


def digest(root, relative):
    path = safe_path(root, relative)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise MemoryError('missing or oversized memory source')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_id(root):
    return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()


def authority(root):
    result = {}
    for name in ('docs/requirements.md', '_bmad-output/architecture.md', '_bmad-output/prd.md'):
        try:
            digest(root, name)
            available = True
        except (MemoryError, OSError):
            available = False
        result[name] = digest(root, name) if available else None
    return result


def make_record(root, *, source, text, epic, story, origin_story, paths, roles, tools,
                trust='deterministic', kind='lesson', candidate='', source_type='artifact',
                contract_authority=None, captured_at=None):
    if trust not in TRUST:
        raise MemoryError('invalid trust label')
    authority_state = contract_authority or authority(root)
    row = {
        'project': project_id(root),
        'epic': epic,
        'story': story,
        'roles': list(roles),
        'paths': list(paths),
        'tools': list(tools),
        'kind': kind,
        'trust': trust,
        'status': 'unverified',
        'text': text,
        'source': {'ref': source, 'digest': digest(root, source),
                   'type': source_type, 'at': captured_at or time.time(),
                   'story': origin_story, 'candidate': candidate},
        'authority': authority_state,
        'contract_authority': authority_state,
    }
    screen(row)
    return row


class MemoryProvider(Protocol):
    def recall(self, **query) -> dict: ...
    def get(self, identity: str) -> dict: ...
    def put(self, record: dict) -> str: ...
    def update(self, identity: str, status: str) -> dict: ...
    def forget(self, identity: str) -> dict: ...
    def search(self, **query) -> dict: ...
    def consolidate(self) -> dict: ...
    def health(self) -> dict: ...
    def stats(self) -> dict: ...


def _posix(path: str) -> str:
    """Đường dẫn về một dạng duy nhất trước khi so khớp.

    Phạm vi của bản ghi và phạm vi của truy vấn có thể tới từ hai nơi khác nhau:
    một cái do người/agent viết trong `stories.index.json`, một cái do máy suy
    ra. Trên Windows, hai nguồn ấy dùng hai dấu phân cách, và phép so khớp bằng
    chuỗi thô **trượt im lặng** — bản ghi đúng bị loại với lý do "path scope" và
    không ai biết bộ nhớ vừa mất tác dụng. MiMo-Code phát hành đúng lỗi này
    (issue #1571, `memory_fts` rỗng trên Windows vì lệch dấu phân cách).
    """
    return path.replace("\\", "/").strip("/")


def _in_scope(record_paths, query_paths) -> bool:
    """Bản ghi có phủ ít nhất một đường dẫn của truy vấn không."""
    for p in record_paths:
        if p == "*":
            return True
        pp = _posix(p)
        for q in query_paths:
            qq = _posix(q)
            if qq == pp or qq.startswith(pp + "/"):
                return True
    return False


class LocalMemory:
    def __init__(self, root, *, timeout=2):
        self.root = Path(root).resolve()
        self.project = project_id(self.root)
        self.path = safe_path(self.root, '_bmad-output/memory/store.json')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise MemoryError('invalid memory timeout')
        self.timeout = timeout

    def _validate(self, row):
        if not isinstance(row, dict) or row.get('project') != self.project:
            raise MemoryError('memory project mismatch')
        for key in ('epic', 'story', 'text'):
            if not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 4000:
                raise MemoryError('invalid memory record')
        for key in ('roles', 'paths', 'tools'):
            if not isinstance(row.get(key), list) or not row[key] or len(row[key]) > 50 or not all(isinstance(v, str) and v and len(v) <= 300 for v in row[key]):
                raise MemoryError('incomplete memory scope')
        for p in row['paths']:
            if p != '*':
                safe_path(self.root, p)
        if row.get('kind') not in TAXONOMY or row.get('trust') not in TRUST or row.get('status') not in LIFECYCLE:
            raise MemoryError('invalid memory taxonomy or lifecycle')
        if row['trust'] == 'agent' and row['status'] == 'active':
            raise MemoryError('agent observations cannot self-promote')
        if row['trust'] != 'agent' and row['status'] == 'unverified':
            raise MemoryError('unverified records cannot be stored; verification-time authority digest required for active capture')
        src = row.get('source')
        if not isinstance(src, dict) or not all(isinstance(src.get(k), str) and src[k] for k in ('ref', 'digest', 'type', 'story')):
            raise MemoryError('memory provenance required')
        if not re.fullmatch('[a-f0-9]{64}', src['digest']) or not isinstance(src.get('at'), (int, float)) or isinstance(src['at'], bool) or not math.isfinite(src['at']) or src['at'] <= 0:
            raise MemoryError('invalid memory provenance')
        if row['trust'] in ('gate', 'security', 'reviewer', 'landed') and not src.get('candidate'):
            raise MemoryError('candidate provenance required')
        safe_path(self.root, src['ref'])
        if not isinstance(row.get('authority'), dict):
            raise MemoryError('authority references required')
        screen(row)
        if src['type'] not in SOURCE_TYPES:
            raise MemoryError('unsupported source type')
        if src['type'] in ('journal', 'evidence'):
            expected = f"_bmad-output/{src['type']}/{src['story']}.jsonl"
            if src['ref'] != expected or not re.fullmatch(r'[A-Za-z0-9_.-]+', src['story']):
                raise MemoryError('invalid authoritative event reference')
        if src['type'] in ('journal', 'evidence') and row['roles'] != ['developer']:
            raise MemoryError('event-derived memories are developer-only')
        if any(r not in ('developer', 'reviewer', 'security', 'designer') for r in row['roles']):
            raise MemoryError('invalid memory role')
        for r in ('reviewer', 'security'):
            if r in row['roles']:
                if row['trust'] == 'agent':
                    raise MemoryError('independent reviews must not consume agent observations')
                if row['trust'] not in REVIEWER_TRUST:
                    raise MemoryError('independent reviews require authorized trust label')
                if row['status'] == 'active' and src['type'] == 'artifact':
                    contract = row.get('contract_authority') or {}
                    if not any(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in contract.values()):
                        raise MemoryError('independent reviews require verification-time authority digest')
        if row['status'] in ('active',) and (
            src['type'] == 'journal'
            or (src['type'] == 'evidence' and row['trust'] != 'agent')
            or (row['trust'] in REVIEWER_TRUST and src['type'] == 'artifact')
            or row['trust'] in ('gate', 'security', 'reviewer', 'landed')
        ):
            contract = row.get('contract_authority') or row.get('authority', {})
            if not any(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in contract.values()):
                raise MemoryError('verification-time authority digest required for active capture')
        if (row['trust'] != 'agent' and src['type'] == 'artifact' and not self._stale(row)
                and row['text'] not in safe_path(self.root, src['ref']).read_text(encoding='utf-8')):
            raise MemoryError('artifact claim not present in authoritative source')
        self._validate_source_payload(row)

    def _validate_source_payload(self, row):
        src = row['source']
        story = src.get('story')
        path = safe_path(self.root, src['ref'])
        if src['type'] == 'artifact':
            return
        try:
            lines = [line for line in path.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip()]
        except OSError as err:
            raise MemoryError('event source unreadable') from err
        if src['type'] == 'evidence':
            events = []
            for line in lines:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as err:
                    raise MemoryError('event source not structured jsonl') from err
                if not isinstance(entry, dict):
                    raise MemoryError('event entry not structured')
                events.append(entry)
            self._check_evidence_event_chain(row, events, story)
            return
        if src['type'] == 'journal':
            verified = False
            for line in lines:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as err:
                    raise MemoryError('journal source not structured jsonl') from err
                if not isinstance(entry, dict) or 'step' not in entry or 'seq' not in entry or 'attempt' not in entry:
                    raise MemoryError('journal entry missing required keys')
                data = entry.get('data') or {}
                if entry['step'] == 'verification.completed' and data.get('ok') is True and data.get('candidate') == src.get('candidate', '') and data.get('passed') is not None:
                    verified = True
            if not verified:
                raise MemoryError('journal source lacks matching verification.completed event for candidate')

    def _check_evidence_event_chain(self, row, events, story):
        target_candidate = row['source'].get('candidate', '') or None
        if not target_candidate:
            raise MemoryError('evidence record missing candidate link')
        verified = False
        for entry in events:
            if entry.get('kind') != 'tool.run':
                continue
            if entry.get('story') != story:
                raise MemoryError('evidence event refers to foreign story')
            data = entry.get('data') or {}
            if data.get('candidate') and data.get('candidate') != target_candidate:
                continue
            if entry.get('ok') or row['kind'] != 'tool':
                continue
            verified = True
        if not verified:
            raise MemoryError('no failure event supports this evidence claim')

    def _load(self):
        safe_path(self.root, '_bmad-output/memory/store.json')
        if not self.path.exists():
            return {'version': 1, 'project': self.project, 'records': {}, 'tombstones': [], 'audit': []}
        try:
            if self.path.stat().st_size > MAX_BYTES:
                raise MemoryError('memory store size limit')
            data = json.loads(self.path.read_text())
            if data['version'] != 1 or data['project'] != self.project or not isinstance(data['records'], dict) or not isinstance(data['tombstones'], list) or not isinstance(data['audit'], list):
                raise MemoryError('unsupported memory schema')
            if len(data['records']) > 1000 or not all(re.fullmatch('[a-f0-9]{24}', k) for k in data['records']):
                raise MemoryError('invalid memory record index')
            if not all(isinstance(k, str) and re.fullmatch('[a-f0-9]{24}', k) for k in data['tombstones']):
                raise MemoryError('invalid memory tombstones')
            for key, row in data['records'].items():
                if not isinstance(row, dict) or row.get('id') != key or key in data['tombstones']:
                    raise MemoryError('invalid memory identity')
            return data
        except (KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MemoryError('memory store corrupt or unavailable; retained unchanged') from exc

    @contextmanager
    def _locked(self):
        safe_path(self.root, '_bmad-output/memory')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = safe_path(self.root, '_bmad-output/memory/store.lock')
        fd = open_lock_fd(lock)
        start = time.monotonic()
        try:
            while True:
                try:
                    flock_ex_nb(fd)
                    break
                except BlockingIOError as err:
                    if time.monotonic() - start >= self.timeout:
                        raise MemoryError('memory lock timeout') from err
                    time.sleep(0.01)
            yield
        finally:
            try:
                flock_un(fd)
            finally:
                os.close(fd)

    def _save(self, data):
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if len(payload.encode()) > MAX_BYTES:
            raise MemoryError('memory store size limit')
        safe_path(self.root, '_bmad-output/memory/store.json')
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix='.memory-')
        try:
            with os.fdopen(fd, 'w') as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            atomic_replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _event(self, data, action, **detail):
        data['audit'].append({'at': time.time(), 'event': 'memory.' + action, **detail})
        data['audit'] = data['audit'][-500:]

    def put(self, record):
        row = copy.deepcopy(record)
        self._validate(row)
        if self._stale(row):
            raise MemoryError('source changed before capture')
        if row['status'] == 'active' and row['trust'] != 'agent':
            contract = row.get('contract_authority') or row.get('authority', {})
            if not any(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for v in (contract or {}).values()):
                raise MemoryError('verification-time authority digest required for active capture')
        if row['status'] == 'active' and row['trust'] == 'human' and 'human' not in row['roles']:
            raise MemoryError('human-trust capture must preserve role scope')
        key = copy.deepcopy(row)
        key['source'].pop('at')
        key.pop('id', None)
        key.pop('contract_authority', None)
        identity = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
        row['id'] = identity
        with self._locked():
            data = self._load()
            if identity in data['tombstones']:
                raise MemoryError('memory forgotten; recapture refused')
            data['records'].setdefault(identity, row)
            self._event(data, 'capture', id=identity, source_type=row['source']['type'], trust=row['trust'])
            self._save(data)
        return identity

    def _stale(self, row):
        try:
            return digest(self.root, row['source']['ref']) != row['source']['digest'] or (
                row.get('contract_authority') is not None and authority(self.root) != row['contract_authority']
            )
        except (OSError, MemoryError):
            return True

    def get(self, identity):
        row = self._load()['records'].get(identity)
        if row is None:
            raise MemoryError('memory not found or forgotten')
        self._validate(row)
        row = copy.deepcopy(row)
        if self._stale(row):
            row['status'] = 'stale'
        return row

    def update(self, identity, status):
        if status not in LIFECYCLE or status in ('active', 'unverified'):
            raise MemoryError('promotion requires new authoritative capture')
        with self._locked():
            data = self._load()
            row = data['records'].get(identity)
            if not row:
                raise MemoryError('memory not found')
            self._validate(row)
            if row['status'] in ('revoked', 'superseded'):
                raise MemoryError('terminal memory lifecycle')
            row['status'] = status
            self._event(data, 'supersede' if status == 'superseded' else 'reject', id=identity, reason=status)
            self._save(data)
        return {'id': identity, 'status': status}

    def forget(self, identity):
        with self._locked():
            data = self._load()
            if identity not in data['records']:
                raise MemoryError('memory not found')
            del data['records'][identity]
            data['tombstones'].append(identity)
            self._event(data, 'forget', id=identity)
            self._save(data)
        return {'id': identity, 'status': 'forgotten'}

    def recall(self, **query):
        with self._locked():
            return self._recall(**query)

    def _recall(self, *, query, epic, story, role, paths, tool='*', budget=1200, limit=6):
        start = time.monotonic()
        if type(budget) is not int or not 0 <= budget <= 20000 or type(limit) is not int or not 1 <= limit <= 50:
            raise MemoryError('invalid memory budget')
        if not isinstance(query, str) or len(query) > 4000:
            raise MemoryError('invalid memory query')
        if not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,300}', v) for v in (epic, story)):
            raise MemoryError('invalid memory query scope')
        if role not in ('developer', 'reviewer', 'security', 'designer') or not isinstance(tool, str):
            raise MemoryError('invalid memory query role or tool')
        if not isinstance(paths, list) or len(paths) > 50:
            raise MemoryError('invalid memory query paths')
        for path in paths:
            safe_path(self.root, path)
        screen(query, where='query')
        screen(tool, where='tool')
        review_only_trust = REVIEWER_TRUST if role in ('reviewer', 'security') else set()
        words = set(re.findall(r'\w+', query.lower()))
        candidates, rejected = [], []
        data = self._load()
        for identity, row in data['records'].items():
            reason = ''
            try:
                self._validate(row)
                if row['status'] != 'active':
                    reason = row['status']
                elif self._stale(row):
                    reason = 'stale'
                elif role in ('reviewer', 'security') and row['trust'] == 'agent':
                    reason = 'reviewer independence'
                elif role in ('reviewer', 'security') and row.get('trust') not in review_only_trust:
                    reason = 'unbound review provenance'
                elif row['epic'] not in ('*', epic) or row['story'] not in ('*', story) or role not in row['roles'] or not ('*' in row['tools'] or tool in row['tools']):
                    reason = 'scope'
                elif role in ('reviewer', 'security') and (
                    row.get('trust') not in REVIEWER_TRUST
                    or not isinstance(row.get('contract_authority'), dict)
                    or not any(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v)
                               for v in row.get('contract_authority', {}).values())
                ):
                    reason = 'unbound review provenance'
                elif not _in_scope(row['paths'], paths):
                    reason = 'path scope'
                overlap = words & set(re.findall(r'\w+', row['text'].lower()))
                if not reason and not overlap:
                    reason = 'no lexical match'
                if not reason:
                    score = len(overlap) * 10 + len(TRUST) - TRUST.index(row['trust'])
                    candidates.append((score, identity, row))
            except (MemoryError, TypeError, KeyError):
                reason = 'unsafe record'
            if reason:
                rejected.append({'id': identity if re.fullmatch('[a-f0-9]{24}', str(identity)) else 'invalid', 'reason': reason})
        header = '\n## Advisory memory (not evidence)\nCurrent requirements and architecture prevail. Verify original sources.\n'
        text, selected = '', []
        for score, identity, row in sorted(candidates, key=lambda v: (-v[0], v[1])):
            line = f"- {identity} [{row['source']['type']}] {row['text'][:400]} (source: {row['source']['ref']})\n"
            extra = (header if not text else '') + line
            if len(selected) >= limit or len(text) + len(extra) > budget:
                rejected.append({'id': identity, 'reason': 'budget'})
                continue
            text += extra
            selected.append({'id': identity, 'score': score, 'source_type': row['source']['type'],
                             'source': row['source']['ref'], 'trust': row['trust'],
                             'status': row['status'], 'role': role})
        result = {'provider': 'local', 'text': text, 'selected': selected, 'rejected': rejected,
                  'budget': budget, 'chars': len(text), 'latency_ms': round((time.monotonic() - start) * 1000, 3)}
        self._event(data, 'recall', **{k: v for k, v in result.items() if k != 'text'})
        if rejected:
            self._event(data, 'reject', rejected=rejected)
        if selected:
            self._event(data, 'inject', selected=selected, chars=len(text), budget=budget)
        self._save(data)
        return result

    search = recall

    def consolidate(self):
        stale = 0
        with self._locked():
            data = self._load()
            for row in data['records'].values():
                self._validate(row)
                if row['status'] in ('active', 'unverified') and self._stale(row):
                    row['status'] = 'stale'
                    stale += 1
            self._event(data, 'consolidate', stale=stale)
            self._save(data)
        return {'stale': stale, 'promoted': 0}

    def audit(self):
        rows = self._load()['audit']
        screen(rows)
        return rows

    def stats(self):
        data = self._load()
        return {'provider': 'local', 'records': len(data['records']), 'tombstones': len(data['tombstones'])}

    def health(self):
        try:
            data = self._load()
            for row in data['records'].values():
                self._validate(row)
            return {'provider': 'local', 'available': True, **self.stats()}
        except (MemoryError, OSError):
            return {'provider': 'local', 'available': False, 'reason': 'corrupt, unsafe or unavailable store'}


def resolve(root, config):
    name = config.get('memory.provider', 'local')
    if name == 'local':
        return LocalMemory(root, timeout=config.get('memory.timeout_seconds', 2)), {'requested': name, 'actual': name}
    if name == 'openviking' and config.get('memory.fallback', 'none') == 'local':
        return LocalMemory(root, timeout=config.get('memory.timeout_seconds', 2)), {'requested': name, 'actual': 'local', 'reason': 'OpenViking adapter unavailable; explicit fallback'}
    raise MemoryError('OpenViking adapter unavailable; no implicit fallback')


def attach(context, story, project, config, role):
    if not config or not config.get('memory.enabled', False):
        return
    try:
        provider, status = resolve(project, config)
        packet = provider.recall(query=story.title + ' ' + ' '.join(story.write_scope),
                                 epic=story.epic_id, story=story.id, role=role,
                                 paths=list(story.write_scope),
                                 budget=config.get('memory.max_chars', 1200))
        packet['resolution'] = status
        context['memory'] = packet.pop('text')
        context['_memory'] = packet
    except (MemoryError, OSError):
        context['_memory'] = {'available': False, 'reason': 'memory unavailable or rejected',
                              'selected': [], 'chars': 0}


def capture_story(project, story, config):
    return {'enabled': bool(config.get('memory.enabled', False)),
            'captured': [],
            'reason': 'automatic event capture is disabled until contract authority is bound; capture only via authoritative artifacts'}


def capture_advisory(project, story, config):
    return {'enabled': bool(config.get('memory.enabled', False)),
            'captured': [],
            'reason': 'automatic advisory capture is disabled; memory remains read-only advisory'}
