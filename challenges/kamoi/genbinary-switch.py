#!/usr/bin/exec-suid -- /usr/bin/python3 -I
import os
import uuid
import random
import string
import argparse
from typing import List

CHARSET = string.printable

random.seed(0x1337)


def GetRandomChar():
    return random.choice(CHARSET)


def GetRandomRet():
    return random.randint(2**16, 2**17 - 1)


# each case will have a character and a return
# value that ret will be set to
class Case:
    def __init__(self, char, ret) -> None:
        self.id = uuid.uuid4()
        self.char = char
        self.ret = ret

    def to_c(self) -> str:
        return (
            # 'case %d: hash[ctr++] = 0x%06x ^ idx; printf("%%%%d\\n", idx); break;\n'
            "case %d: hash[ctr++] = 0x%06x ^ idx; break;\n"
            % (
                ord(self.char),
                self.ret,
            )
        )

    def __str__(self):
        return "Case('%s', 0x%06x)" % (self.char, self.ret)


# each switch will be a function with many cases
class Switch:
    def __init__(self, cases: List[Case]) -> None:
        self.id = uuid.uuid4()
        self.cases = cases

    def get_func_name(self):
        return "check_" + self.id.hex[:8]

    def to_c(self):
        return (
            "int %s(unsigned int idx)\x7b\nswitch(flag[idx])\x7b\n"
            + "".join([case.to_c() for case in self.cases])
            + "\x7d\nreturn 0;\n\x7d\n\n"
        ) % self.get_func_name()

    def __str__(self):
        return "Switch([%s, ... %d cases])" % (str(self.cases[0]), len(self.cases))


# generate a switch with random cases
# for a flag character
def GenerateSwitch(char, n_cases):

    cases = []
    r_chars = []
    r_len = random.randint(0, n_cases)
    # while len(r_chars) != r_len:
    #     r_chars.append(GetRandomChar())

    r_chars = list(CHARSET)  # list(set(r_chars))
    if char not in r_chars:
        r_chars.append(char)

    random.shuffle(r_chars)

    for r_char in r_chars:
        cases.append(Case(r_char, GetRandomRet()))

    return Switch(cases)


FLAG = (
    "Haha, you have a lot of knowledge about how AFL++'s instrumentation works. here is your flag %s"
    % (open("/flag", "r").read().strip())
)


def WriteSource(n_cases):
    ret = (
        '#include <stdio.h>\n#include <stdlib.h>\n#include <stdint.h>\n#include <unistd.h>\n#include <fcntl.h>\n#include <errno.h>\n\nstatic unsigned int *pool = NULL;\nstatic size_t pool_size = 0;\nstatic size_t next_index = 0;\nstatic unsigned int get_urandom_uint(void) {\nunsigned int val;\nint fd = open("/dev/urandom", O_RDONLY);\nif (fd < 0) {\nperror("open /dev/urandom");\nexit(1);\n}\nssize_t n = read(fd, &val, sizeof(val));\nclose(fd);\nif (n != sizeof(val)) {\nperror("read /dev/urandom");\nexit(1);\n}\nreturn val;\n}\nstatic void init_pool(size_t max) {\npool = malloc(max * sizeof(unsigned int));\nif (!pool) {\nperror("malloc");\nexit(1);\n}\npool_size = max;\nnext_index = 0;\nfor (size_t i = 0; i < max; i++)\npool[i] = i;\nfor (size_t i = max - 1; i > 0; i--) {\nunsigned int r = get_urandom_uint() %% (i + 1);\nunsigned int tmp = pool[i];\npool[i] = pool[r];\npool[r] = tmp;\n}\n}\nunsigned int g_rand(size_t max) {\nif (max == 0) {\nfprintf(stderr, "max must be > 0\\n");\nexit(1);\n}\n\nif (pool == NULL || pool_size != max)\ninit_pool(max);\n\nif (next_index >= pool_size)\ninit_pool(max);\n\nreturn pool[next_index++];\n}\n\n\n\nunsigned char flag[%d] = {0};\nunsigned char hash[%d] = {0};\nint ctr=0;void print_hex(unsigned char *buf, size_t len) {\nFILE* fp = fopen("output.txt", "w");\nif (!fp){\nprintf("Cannot write output.txt, contact admin\\n");\nexit(-1);\n}\nfor (size_t i = 0; i < len; i++) {\nfprintf(fp, "%%02x", buf[i]);\n}\nfclose(fp);\n}\n\n'
        % (
            len(FLAG) + 1,
            len(FLAG),
        )
    )
    switches = []
    for idx, ch in enumerate(FLAG):
        switches.append((idx, GenerateSwitch(ch, n_cases)))
        ret += switches[-1][1].to_c()

    ret += "int main()\x7b\nfgets((char*)flag, sizeof(flag), stdin);\n\n"

    random.shuffle(switches)

    for idx, switch in switches:
        ret += "%s(g_rand(%d));\n" % (switch.get_func_name(), len(FLAG))

    ret += 'print_hex(hash, sizeof(hash));\nputs("");'
    ret += "return 0;\n"
    ret += "}"
    return ret


def main():
    parser = argparse.ArgumentParser(
        prog="generatebinary-switch.py",
        description="Generate Switch Case version of AFL++ Reversing challenge.",
    )

    parser.add_argument("--cases", type=int, default=0xFE)
    parser.add_argument("--source", type=str, default="challenge.c")

    args = parser.parse_args()
    if args.cases:
        with open(args.source, "w") as fp:
            fp.write(WriteSource(0x100))

    with open("/challenge/input.txt", "w") as fp:
        fp.write(FLAG)

    # os.system("/opt/AFLplusplus/afl-clang-lto -O0 %s -o /challenge/chall" % args.source)


if __name__ == "__main__":
    main()
