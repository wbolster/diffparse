import itertools
import re
import sys

import attr


@attr.s
class PatchSet(object):
    preamble = attr.ib(default=attr.Factory(list))
    patched_files = attr.ib(default=attr.Factory(list))

    @property
    def empty(self):
        return not bool(self.preamble or self.patched_files)


@attr.s
class PatchedFile(object):
    RE_SOURCE_HEADER = re.compile(
        r'^--- (?P<filename>[^\t\n]+)(?:\t(?P<timestamp>[^\n]+))?')
    RE_TARGET_HEADER = re.compile(
        r'^\+\+\+ (?P<filename>[^\t\n]+)(?:\t(?P<timestamp>[^\n]+))?')
    is_start_line = RE_SOURCE_HEADER.match

    source_file = attr.ib(default=None)
    target_file = attr.ib(default=None)
    source_timestamp = attr.ib(default=None)
    target_timestamp = attr.ib(default=None)
    hunks = attr.ib(default=attr.Factory(list))
    git_header = attr.ib(default=None)

    @staticmethod
    def is_git_diff_header_line(line):
        return line.startswith('diff --git ')


@attr.s
class Hunk(object):
    source_start = attr.ib(default=None)
    source_length = attr.ib(default=None)
    target_start = attr.ib(default=None)
    target_length = attr.ib(default=None)
    header = attr.ib(default=None)
    lines = attr.ib(default=attr.Factory(list))

    RE_HEADER = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
        r"(?: (.*))?")
    is_header_line = RE_HEADER.match

    @classmethod
    def from_header_line(cls, line):
        m = Hunk.RE_HEADER.match(line)
        if not m:
            raise ValueError("Invalid hunk header line: {!r}".format(line))
        a, b, c, d, header = m.groups()
        return cls(
            source_start=int(a),
            source_length=int(b) if b else 1,
            target_start=int(c),
            target_length=int(d) if d else 1,
            header=header)

    @property
    def source_lines(self):
        return [line for line in self.lines if not line.is_added]

    @property
    def target_lines(self):
        return [line for line in self.lines if not line.is_removed]


@attr.s
class Line(object):
    type = attr.ib()
    value = attr.ib()
    source_line = attr.ib(default=None)
    target_line = attr.ib(default=None)

    @classmethod
    def from_string(cls, s):
        return cls(type=s[0], value=s[1:])

    @property
    def is_added(self):
        return self.type == '+'

    @property
    def is_removed(self):
        return self.type == '-'

    @property
    def is_context(self):
        return self.type == ' '


@attr.s
class GitExtendedHeader(object):
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

    @classmethod
    def from_lines(cls, lines):
        header = cls()
        for line in lines:
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
                hashes = parts[-2].split('..')
                header.index_from_hash, header.index_to_hash = hashes
                header.index_mode = value
            else:
                raise ValueError(
                    "Unknown git extended diff header line: {!r}"
                    .format(line))
        return header


def iter_lines(iterable):
    # For an iterable with 3 items this yields:
    #   (0, None, 'first')
    #   (1, 'first', 'second')
    #   (2, 'second', 'third')
    #   (3, 'third', None)
    g = (line.rstrip("\n") for line in iterable)
    a, b = itertools.tee(g)
    count = itertools.count(0)
    return zip(count, itertools.chain([None], a), itertools.chain(b, [None]))


def parse_patch_set(it):
    patch_set = PatchSet()
    for lno, line, next_line in it:
        if line is not None:
            patch_set.preamble.append(line)
        if next_line is not None:
            if PatchedFile.is_git_diff_header_line(next_line):
                patched_file = parse_git_patched_file(it)
                patch_set.patched_files.append(patched_file)
            elif PatchedFile.is_start_line(next_line):
                patched_file = parse_patched_file(it)
                patch_set.patched_files.append(patched_file)
    if not patch_set.empty:
        yield patch_set


def parse_patched_file(it):
    pf = PatchedFile()

    lno, line, next_line = next(it)
    m = PatchedFile.RE_SOURCE_HEADER.match(line)
    if not m:
        raise ValueError("Invalid --- line: {!r}".format(line))
    pf.source_file, pf.source_timestamp = m.group('filename', 'timestamp')

    lno, line, next_line = next(it)
    if not m:
        raise ValueError("Invalid +++ line: {!r}".format(line))
    pf.target_file, pf.target_timestamp = m.group('filename', 'timestamp')

    if Hunk.is_header_line(next_line):
        pf.hunks.extend(parse_hunks(it))

    return pf


def parse_git_patched_file(it):
    lno, line, next_line = next(it)
    assert PatchedFile.is_git_diff_header_line(line)
    # TODO: extract a/ and b/ values?

    header_lines = []
    while not PatchedFile.is_start_line(next_line):
        lno, line, next_line = next(it)
        header_lines.append(line.rstrip())

    patched_file = parse_patched_file(it)
    patched_file.git_header = GitExtendedHeader.from_lines(header_lines)
    return patched_file


def parse_hunks(it):
    for lno, line, next_line in it:
        hunk = Hunk.from_header_line(line)
        n_source = n_target = 0
        for lno, line, next_line in it:
            line_obj = Line.from_string(line)
            if line_obj.type != '+':
                n_source += 1
                line_obj.source_line = hunk.source_start + n_source
            if line_obj.type != '-':
                n_target += 1
                line_obj.target_line = hunk.target_start + n_target
            hunk.lines.append(line_obj)
            if (hunk.source_length == n_source and
                    hunk.target_length == n_target):
                break
        yield hunk

        if next_line is None or not Hunk.is_header_line(next_line):
            break


def parse(fp):
    it = iter_lines(fp)
    for patch_set in parse_patch_set(it):
        yield patch_set


if __name__ == '__main__':
    with open(sys.argv[1]) as fp:
        for patch_set in parse(fp):
            print(patch_set)
