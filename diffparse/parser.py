    def _from_peekable(cls, it, allow_preamble):
            elif allow_preamble:
            else:
                it.exception(
                    "invalid start of patch set (try allowing a preamble?)")
        if not ps.patched_files:
            it.exception("no patch set found")
    svn_header = attr.ib(default=None)
        elif GitHeader._is_start_line(line):
            return True
        elif SubversionHeader._is_start_line(line):
        git_header = svn_header = None
        if GitHeader._is_start_line(it.peek()):
            git_header = GitHeader._from_peekable(it)
            # This happens for a git patch adding a new empty file.
            return cls(
                source_file=git_header.source_file,
                target_file=git_header.target_file,
                git_header=git_header)
        if not git_header and SubversionHeader._is_start_line(it.peek()):
            svn_header = SubversionHeader._from_peekable(it)
            git_header=git_header,
            svn_header=svn_header)
            line = Line._from_peekable(it)
            if line.type != '+':
                line.source_line = hunk.source_start + source_seen
            if line.type != '-':
                line.target_line = hunk.target_start + target_seen
            hunk.lines.append(line)
    def _from_peekable(cls, it):
        s = next(it, None)
        if s is None:
            it.exception("incomplete patch hunk")
        elif not s:
            it.exception("empty diff line")
        type = s[0]
        if type not in (' -+'):
            it.exception("diff line must start with +, -, or space")
        value = s[1:]
        return cls(line=s, type=type, value=value)
class GitHeader(object):
    source_file = attr.ib()
    target_file = attr.ib()
        r'"?a/(?P<source_file>.*?)"? '
        r'"?b/(?P<target_file>.*?)"?$')
        line = next(it, None)
        assert line is not None
        source_file, target_file = m.group('source_file', 'target_file')
            source_file = source_file.encode('ascii').decode('unicode_escape')
            target_file = target_file.encode('ascii').decode('unicode_escape')
        header = cls([line], source_file, target_file)
@attr.s
class SubversionHeader(object):
    _lines = attr.ib(repr=False)
    source_file = attr.ib()

    _RE_HEADER = re.compile(r'^Index: (?P<source_file>.+)')
    _RE_SEPARATOR = re.compile('^={5,}$')

    @classmethod
    def _is_start_line(cls, line):
        return cls._RE_HEADER.match(line) is not None

    @classmethod
    def _from_peekable(cls, it):
        line = next(it, None)
        assert line is not None
        m = cls._RE_HEADER.match(line)
        if not m:
            it.exception("malformed subversion index line")
        lines = [line]
        line = next(it, None)
        if line is None:
            it.exception("subversion header separator line is missing")
        elif not cls._RE_SEPARATOR.match(line):
            it.exception("malformed subversion header separator")
        lines.append(line)
        return cls(lines=lines, source_file=m.group('source_file'))


def parse_patch_sets(fp, allow_preamble=False):
        patch_set = PatchSet._from_peekable(it, allow_preamble=allow_preamble)