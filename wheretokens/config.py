"""Where things live, and the optional project rules.

No config is needed. Defaults:
  data      $TOKENS_DATA, else $XDG_DATA_HOME/where-did-the-tokens-go, else ~/.local/share/where-did-the-tokens-go
  config    $TOKENS_CONFIG, else $XDG_CONFIG_HOME/where-did-the-tokens-go/config.json, else ~/.config/...
"""
import fnmatch
import json
import os

APP = 'where-did-the-tokens-go'
DEFAULT_CODE_ROOTS = ['~/code', '~/CODE', '~/Code', '~/src', '~/projects', '~/Projects', '~/dev',
                      '~/repos', '~/Developer', '~/work', '~/git', '~/github']
UNKNOWN = 'unknown'


def home():
    return os.path.realpath(os.path.expanduser('~'))


def variants(path):
    """A path as written and as resolved. On macOS /var is /private/var: both forms must match."""
    raw = os.path.normpath(os.path.expanduser(path))
    return {raw, os.path.realpath(raw)}


def data_dir():
    d = os.environ.get('TOKENS_DATA') or os.path.join(
        os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), APP)
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.environ.get('TOKENS_CONFIG') or os.path.join(
        os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), APP, 'config.json')


def load():
    path = config_path()
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError('%s must hold a JSON object' % path)
    return cfg


def tilde(path):
    """Show a path with the home folder as ~, so a screen never prints the account name."""
    for h in variants('~'):
        for p in variants(path):
            if p == h or p.startswith(h + os.sep):
                return '~' + p[len(h):]
    return path


def clean(name, limit=80):
    return ''.join(ch for ch in str(name) if ch.isprintable())[:limit] or UNKNOWN


class Attributor:
    """Turns a working folder, and the file paths one message touched, into a project name and a reason.

    The order, first match wins:
      1. rule     your config maps a path pattern to a project
      2. folder   the working folder, reduced to its first folder under a code root (or its own name)
      3. files    the working folder said nothing (home folder or a code root itself), and every file the
                  message's file tools touched sits in one project folder
      4. unknown  none of the above
    Paths are used in memory only. Only the project NAME is kept.
    """

    def __init__(self, cfg=None):
        cfg = cfg or {}
        roots = cfg.get('code_roots') or DEFAULT_CODE_ROOTS
        self.roots = sorted({v for r in roots for v in variants(r)}, key=len, reverse=True)
        self.rules = []
        for r in cfg.get('rules') or []:
            if isinstance(r, dict) and r.get('match') and r.get('project'):
                self.rules.append((os.path.expanduser(str(r['match'])), clean(r['project'])))
        self.homes = variants('~')

    def _rule(self, path):
        for pattern, project in self.rules:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.rstrip('/') + '/*'):
                return project
        return None

    def _folder(self, path):
        """Project name for a path, or None when the path says nothing (home, a code root, outside home)."""
        p = os.path.normpath(path)
        if p == '/' or p in self.homes or p in self.roots:
            return None
        for root in self.roots:
            if p.startswith(root + os.sep):
                first = p[len(root) + 1:].split(os.sep)[0]
                if first == '.worktrees':  # a worktree folder: use the next level
                    parts = p[len(root) + 1:].split(os.sep)
                    first = parts[1] if len(parts) > 1 else None
                return clean(first) if first else None
        return clean(os.path.basename(p))

    def _under_root(self, path):
        p = os.path.normpath(path)
        return any(p.startswith(r + os.sep) for r in self.roots)

    def attribute(self, cwd, files=()):
        cwd = str(cwd or '')
        if cwd:
            hit = self._rule(cwd)
            if hit:
                return hit, 'rule'
            hit = self._folder(cwd)
            if hit:
                return hit, 'folder'
        found = set()
        for f in files:
            hit = self._rule(f) or (self._folder(f) if self._under_root(f) else None)
            if hit:
                found.add(hit)
        if len(found) == 1:
            return found.pop(), 'files'
        return UNKNOWN, 'unknown'
