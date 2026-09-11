import json

from ..config import Config
from ..memory import MemoryError, capture_story, resolve
from ._common import _artifact_root


def cmd_memory(args):
    try:
        root = _artifact_root(args).parent
        cfg = Config.load(root)
        if args.action == 'providers':
            result = {'local': {'available': True, 'network': False},
                      'openviking': {'available': False, 'reason': 'adapter contract not verified'},
                      'configured': cfg['memory.provider'], 'fallback': cfg['memory.fallback']}
        elif args.action == 'status' and not cfg['memory.enabled']:
            result = {'enabled': False, 'experimental': True, 'provider': cfg['memory.provider']}
        elif not cfg['memory.enabled']:
            raise MemoryError('memory disabled; explicitly enable memory.enabled first')
        else:
            provider, status = resolve(root, cfg)
            if args.action == 'status':
                result = {'enabled': True, 'experimental': True, **provider.health(), 'resolution': status}
            elif args.action == 'show':
                result = provider.get(args.value)
            elif args.action == 'forget':
                result = provider.forget(args.value)
            elif args.action == 'audit':
                result = {'events': provider.audit()}
            elif args.action == 'consolidate':
                result = provider.consolidate()
            elif args.action in ('capture', 'recall', 'search'):
                if not args.story:
                    raise MemoryError('--story required for scoped memory access')
                from ..phases.run import load_plan
                story = load_plan(root / '_bmad-output').stories.get(args.story)
                if story is None:
                    raise MemoryError('story not found')
                if args.action == 'capture':
                    result = capture_story(root, story, cfg.overlay({'memory.capture': True}))
                else:
                    result = provider.recall(query=args.value or story.title,
                        epic=story.epic_id, story=story.id, role=args.role,
                        paths=list(story.write_scope), tool=args.tool,
                        budget=cfg['memory.max_chars'])
                    result['resolution'] = status
            else:
                raise MemoryError('unknown memory command')
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=None if args.json else 2))
        return 0
    except (MemoryError, OSError, ValueError, TypeError):
        print(json.dumps({'error': 'memory unavailable, disabled, unsafe or invalid request',
                          'action': args.action}))
        return 2
