import itertools
import re
import sys

import attr


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


@attr.s
class PatchSet(object):
    preamble = attr.ib(default=attr.Factory(list))
    patched_files = attr.ib(default=attr.Factory(list))

    @property
    def empty(self):
        return not bool(self.preamble or self.patched_files)

    @classmethod
    def _from_peekable(cls, it):
        ps = PatchSet()
        while True:
            next_line = it.peek()
            if it.peek() is None:
                break
            if PatchedFile._is_start_line(next_line):
                ps.patched_files.append(PatchedFile._from_peekable(it))
            elif ps.patched_files:
                break
            else:
                ps.preamble.append(next(it))
        return ps

    def __str__(self):
        parts = self.preamble[:]
        for patched_file in self.patched_files:
            parts.append(str(patched_file))
        return '\n'.join(parts)


@attr.s
class PatchedFile(object):
    _RE_SOURCE_HEADER = re.compile(
        r'^--- (?P<filename>[^\t\n]+)(?:\t(?P<timestamp>[^\n]+))?')
    _RE_TARGET_HEADER = re.compile(
        r'^\+\+\+ (?P<filename>[^\t\n]+)(?:\t(?P<timestamp>[^\n]+))?')

    _source_header = attr.ib(default=None, repr=False)
    _target_header = attr.ib(default=None, repr=False)
    source_file = attr.ib(default=None)
    target_file = attr.ib(default=None)
    source_timestamp = attr.ib(default=None)
    target_timestamp = attr.ib(default=None)
    hunks = attr.ib(default=attr.Factory(list), repr=False)
    git_header = attr.ib(default=None)

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
        if it.peek() is None:
            # This happens for a git patching adding a new empty file.
            return cls(git_header=git_header)
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
        source_file = source_match.group('filename')
        target_file = target_match.group('filename')
        if git_header:
            if source_file.startswith('a/'):
                source_file = source_file[2:]
            if target_file.startswith('b/'):
                target_file = target_file[2:]
        if source_file == '/dev/null':
            source_file = None
        if target_file == '/dev/null':
            target_file = None
        patched_file = cls(
            source_header=source_line,
            target_header=target_line,
            source_file=source_file,
            source_timestamp=source_match.group('timestamp'),
            target_file=target_file,
            target_timestamp=target_match.group('timestamp'),
            git_header=git_header)
        print(repr(patched_file))
        while True:
            next_line = it.peek()
            if next_line is None or not Hunk._is_header_line(next_line):
                break
            patched_file.hunks.append(Hunk._from_peekable(it))
        return patched_file

    def __str__(self):
        parts = []
        if self.git_header:
            parts.append(str(self.git_header))
        if self._source_header is not None:
            parts.append(self._source_header)
        if self._target_header is not None:
            parts.append(self._target_header)
        for hunk in self.hunks:
            parts.append(str(hunk))
        return '\n'.join(parts)

    @property
    def added(self):
        if not self.hunks:
            return self.source_file is None
        elif len(self.hunks) == 1:
            hunk = self.hunks[0]
            return (hunk.source_start, hunk.source_length) == (0, 0)
        elif len(self.hunks) > 1:
            return False

    @property
    def removed(self):
        if not self.hunks:
            return self.target_file is None
        elif len(self.hunks) == 1:
            hunk = self.hunks[0]
            return (hunk.target_start, hunk.target_length) == (0, 0)
        elif len(self.hunks) > 1:
            return False

    @property
    def modified(self):
        return not self.added and not self.removed


@attr.s
class Hunk(object):
    _header_line = attr.ib(repr=False)
    source_start = attr.ib()
    source_length = attr.ib()
    target_start = attr.ib()
    target_length = attr.ib()
    section = attr.ib()
    lines = attr.ib(default=attr.Factory(list), repr=False)

    _RE_HEADER = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
        r"(?: (.*))?")

    @classmethod
    def _is_header_line(cls, line):
        return cls._RE_HEADER.match(line) is not None

    @classmethod
    def _from_peekable(cls, it):
        line = next(it)
        m = Hunk._RE_HEADER.match(line)
        if not m:
            raise ValueError("Invalid hunk header line: {!r}".format(line))
        a, b, c, d, section = m.groups()
        hunk = cls(
            header_line=line,
            source_start=int(a),
            source_length=int(b) if b else 1,
            target_start=int(c),
            target_length=int(d) if d else 1,
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

    @property
    def source_lines(self):
        return [line for line in self.lines if not line.added]

    @property
    def target_lines(self):
        return [line for line in self.lines if not line.removed]


@attr.s
class Line(object):
    _line = attr.ib(repr=False)
    type = attr.ib()
    value = attr.ib()
    source_line = attr.ib(default=None)
    target_line = attr.ib(default=None)

    def __str__(self):
        return self._line

    @classmethod
    def _from_string(cls, s):
        obj = cls(
            line=s,
            type=s[0],
            value=s[1:])
        assert obj.type in (' -+')
        return obj

    @property
    def added(self):
        return self.type == '+'

    @property
    def removed(self):
        return self.type == '-'

    @property
    def context(self):
        return self.type == ' '


@attr.s
class GitExtendedHeader(object):
    _lines = attr.ib(repr=False)
    source_name = attr.ib()
    target_name = attr.ib()
    old_mode = attr.ib(default=None)
    new_mode = attr.ib(default=None)
    deleted_file_mode = attr.ib(default=None)
    new_file_mode = attr.ib(default=None)
    copy_from = attr.ib(default=None)
    copy_to = attr.ib(default=None)
    rename_from = attr.ib(default=None)
    rename_to = attr.ib(default=None)
    similarity_index = attr.ib(default=None)
    dissimilarity_index = attr.ib(default=None)
    index_from_hash = attr.ib(default=None)
    index_to_hash = attr.ib(default=None)
    index_mode = attr.ib(default=None)

    _RE_HEADER = re.compile(
        r'^diff --git '
        r'"?a/(?P<source_name>.*?)"? '
        r'"?b/(?P<target_name>.*?)"?$')

    @classmethod
    def _is_start_line(cls, line):
        return cls._RE_HEADER.match(line) is not None

    @classmethod
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
            parts = line.split()
            value = parts[-1]
            if line.startswith('old mode'):
                header.old_mode = value
            elif line.startswith('new mode'):
                header.new_mode = value
            elif line.startswith('deleted file mode'):
                header.deleted_file_mode = value
            elif line.startswith('new file mode'):
                header.new_file_mode = value
            elif line.startswith('copy from'):
                header.copy_from = value
            elif line.startswith('copy to'):
                header.copy_to = value
            elif line.startswith('rename from'):
                header.rename_from = value
            elif line.startswith('rename to'):
                header.rename_to = value
            elif line.startswith('similarity index'):
                header.similarity_index = int(value[:-1])
            elif line.startswith('dissimilarity index'):
                header.dissimilarity_index = int(value[:-1])
            elif line.startswith('index'):
                hashes = parts[1].split('..')
                header.index_from_hash, header.index_to_hash = hashes
                if len(parts) == 3:
                    header.index_mode = value
            else:
                raise ValueError(
                    "Unknown git extended diff header line: {!r}"
                    .format(line))
        return header

    def __str__(self):
        return '\n'.join(self._lines)


def parse_patch_sets(fp):
    it = PeekableFile(fp)
    while it.peek() is not None:
        patch_set = PatchSet._from_peekable(it)
        yield patch_set
