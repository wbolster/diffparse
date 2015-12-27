import sys

from . import parse_patch_sets


def main():
    with open(sys.argv[1]) as fp:
        for patch_set in parse_patch_sets(fp):
            print('patch set:', repr(patch_set))
            for patched_file in patch_set.patched_files:
                print('patched file:', repr(patched_file))
                for hunk in patched_file.hunks:
                    print('hunk:', repr(hunk))
                    for line in hunk.lines:
                        print('line:', repr(line))
            # print(patch_set)

if __name__ == '__main__':
    main()
