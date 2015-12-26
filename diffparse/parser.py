class PeekableFile(object):

    def __init__(self, fp):
        self.fp = fp
        self.lno = 0
        a, b = itertools.tee(line.rstrip("\n") for line in fp)
        self.peeked = next(b, None)
        count = itertools.count(1)
        self._it = zip(count, a, itertools.chain(b, [None]))

    def __iter__(self):
        return self

    def __next__(self):
        self.lno, line, self.peeked = next(self._it)
        return line

    def peek(self):
        return self.peeked

    def exception(self, message):
        raise ValueError("{}:{}: {}".format(
            self.fp.name,
            self.lno,
            message))


    @classmethod
    def _from_peekable(cls, it):
        ps = PatchSet()
        while True:
            next_line = it.peek()
            if PatchedFile._is_start_line(next_line):
                ps.patched_files.append(PatchedFile._from_peekable(it))
            elif ps.patched_files:
                break
            else:
                ps.preamble.append(next(it))
            if it.peek() is None:
                break
        return ps

    def __str__(self):
        parts = self.preamble[:]
        for patched_file in self.patched_files:
            parts.append(str(patched_file))
        return '\n'.join(parts)

    _RE_SOURCE_HEADER = re.compile(
    _RE_TARGET_HEADER = re.compile(
    _source_header = attr.ib(repr=False)
    _target_header = attr.ib(repr=False)
    source_file = attr.ib()
    target_file = attr.ib()
    source_timestamp = attr.ib()
    target_timestamp = attr.ib()
    hunks = attr.ib(default=attr.Factory(list), repr=False)
    @classmethod
    def _is_start_line(cls, line):
        if cls._RE_SOURCE_HEADER.match(line) is not None:
            return True
        elif GitExtendedHeader._is_start_line(line):
            return True
        return False

    @classmethod
    def _from_peekable(cls, it):
        git_header = None
        if GitExtendedHeader._is_start_line(it.peek()):
            git_header = GitExtendedHeader._from_peekable(it)
        source_line = next(it)
        source_match = PatchedFile._RE_SOURCE_HEADER.match(source_line)
        if not source_match:
            it.exception("malformed --- line")
        try:
            target_line = next(it)
        except StopIteration:
            it.exception("incomplete patch: missing +++ line")
        target_match = PatchedFile._RE_TARGET_HEADER.match(target_line)
        if not target_match:
            it.exception("malformed +++ line")
        obj = cls(
            source_header=source_line,
            target_header=target_line,
            source_file=source_match.group('filename'),
            source_timestamp=source_match.group('timestamp'),
            target_file=target_match.group('filename'),
            target_timestamp=target_match.group('timestamp'),
            git_header=git_header)
        while True:
            next_line = it.peek()
            if next_line is None or not Hunk._is_header_line(next_line):
                break
            obj.hunks.append(Hunk._from_peekable(it))
        return obj

    def __str__(self):
        parts = []
        if self.git_header:
            parts.append(str(self.git_header))
        parts.append(self._source_header)
        parts.append(self._target_header)
        for hunk in self.hunks:
            parts.append(str(hunk))
        return '\n'.join(parts)
    _header_line = attr.ib(repr=False)
    source_start = attr.ib()
    source_length = attr.ib()
    target_start = attr.ib()
    target_length = attr.ib()
    section = attr.ib()
    lines = attr.ib(default=attr.Factory(list), repr=False)

    _RE_HEADER = re.compile(
    def _is_header_line(cls, line):
        return cls._RE_HEADER.match(line) is not None

    @classmethod
    def _from_peekable(cls, it):
        line = next(it)
        m = Hunk._RE_HEADER.match(line)
        a, b, c, d, section = m.groups()
        hunk = cls(
            header_line=line,
            section=section)
        source_seen = target_seen = 0
        while True:
            line = next(it, None)
            if line is None:
                it.exception("incomplete patch hunk")
            line_obj = Line._from_string(line)
            if line_obj.type != '+':
                line_obj.source_line = hunk.source_start + source_seen
                source_seen += 1
            if line_obj.type != '-':
                line_obj.target_line = hunk.target_start + target_seen
                target_seen += 1
            hunk.lines.append(line_obj)
            if (hunk.source_length == source_seen and
                    hunk.target_length == target_seen):
                break
        return hunk

    def __str__(self):
        return "{}\n{}".format(
            self._header_line,
            "\n".join(str(line) for line in self.lines))
        return [line for line in self.lines if not line.added]
        return [line for line in self.lines if not line.removed]
    _line = attr.ib(repr=False)
    def __str__(self):
        return self._line

    def _from_string(cls, s):
        obj = cls(
            line=s,
            type=s[0],
            value=s[1:])
        assert obj.type in (' -+')
        return obj
    def added(self):
    def removed(self):
    def context(self):
    _lines = attr.ib(repr=False)
    source_name = attr.ib()
    target_name = attr.ib()
    _RE_HEADER = re.compile(
        r'^diff --git '
        r'"?a/(?P<source_name>.*?)"? '
        r'"?b/(?P<target_name>.*?)"?')

    @classmethod
    def _is_start_line(cls, line):
        return line.startswith('diff --git ')

    def _from_peekable(cls, it):
        # First line contains two names, which may contain confusing escaping.
        #   diff --git a/file b/file
        #   diff --git "a/a b c\n\txyz" "b/a b c\n\txyz"
        #   diff --git a/a b b/a b
        #   diff --git a/b/b a/b/a b b/b/b a/b/a b
        line = next(it)
        m = cls._RE_HEADER.match(line)
        if not m:
            it.exception("malformed extended git patch header line")
        source_name, target_name = m.group('source_name', 'target_name')
        if '"' in line:
            # Attempt to unescape things like \t.
            source_name = source_name.encode('ascii').decode('unicode_escape')
            target_name = target_name.encode('ascii').decode('unicode_escape')
        header = cls([line], source_name, target_name)

        while True:
            next_line = it.peek()
            if next_line is None:
                break
            if next_line.startswith('--- '):
                break
            line = next(it)
            header._lines.append(line)
                hashes = parts[1].split('..')
                if len(parts) == 3:
                    header.index_mode = value
    def __str__(self):
        return '\n'.join(self._lines)
def parse_patch_sets(fp):
    it = PeekableFile(fp)
    while it.peek() is not None:
        patch_set = PatchSet._from_peekable(it)
        for patch_set in parse_patch_sets(fp):
            print('patch set:', repr(patch_set))
            for patched_file in patch_set.patched_files:
                print('patched file:', repr(patched_file))
                for hunk in patched_file.hunks:
                    print('hunk:', repr(hunk))
                    for line in hunk.lines:
                        print('line:', repr(line))