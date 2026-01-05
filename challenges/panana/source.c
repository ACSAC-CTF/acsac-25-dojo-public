#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>

int main() {
    printf("\n\n===========================================\n");
    printf("         Welcome to the ACSAC CTF!\n");
    printf("         _    ____ ____    _    ____\n");
    printf("        / \\  / ___/ ___|  / \\  / ___|\n");
    printf("       / _ \\| |   \\___ \\ / _ \\| |\n");
    printf("      / ___ \\ |___ ___) / ___ \\ |___\n");
    printf("     /_/   \\_\\____|____/_/   \\_\\____|\n");
    printf("        Let the hacking begin!\n");
    printf("===========================================\n\n\n");
    int fd = open("/flag", 0);
    char buf[100];
    buf[read(fd, buf, 100)] = 0;
    printf("Here is the flag: %s\n", buf);
    return 0;
}

