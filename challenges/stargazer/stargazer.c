#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <dirent.h>
#include <ctype.h>

#define CONSTELLATIONS_DIR "/challenge/constellations"


static FILE *loaded_fp = NULL; 
static char file_data[0x1d0];

static struct eight_by_eight *load_constellation_points(FILE *fp, char *name);
static size_t list_constellations(char entries[][256], size_t max_entries, int should_print);
static void clear_canvas(void);
static void bump_star_pixel(struct eight_by_eight *canvas, size_t x, size_t y);

static const char STAR_LUT[] = ".+*#%@";

#define NAME_MAX 0xd0

struct eight_by_eight {
    char name[NAME_MAX];
    unsigned char pixels[8*8];
};

struct sixteen_by_sixteen {
    char name[NAME_MAX];
    unsigned char pixels[16*16];
};

struct thirty_two_by_thirty_two {
    char name[NAME_MAX];
    unsigned char pixels[32*32];
};

struct sixty_four_by_sixty_four {
    char name[NAME_MAX];
    unsigned char pixels[64*64];
};

struct eight_by_eight *canvas = NULL;
size_t current_size;

static struct eight_by_eight *alloc_canvas() {
    struct eight_by_eight *new_canvas = NULL;
    size_t canvas_size = 0;
    if (current_size <= 8) {
        new_canvas = (struct eight_by_eight *)malloc(sizeof(struct eight_by_eight));
        canvas_size = 8*8;
    } else if (current_size <= 16) {
        new_canvas = malloc(sizeof(struct sixteen_by_sixteen));
        canvas_size = 16*16;
    } else if (current_size <= 32) {
        new_canvas = malloc(sizeof(struct thirty_two_by_thirty_two));
        canvas_size = 32*32;
    } else if (current_size <= 64) {
        new_canvas = malloc(sizeof(struct sixty_four_by_sixty_four));
        canvas_size = 64*64;
    } else {
        puts("invalid canvas size");
        exit(1);
    }
    memset(new_canvas->pixels, STAR_LUT[0], canvas_size);

    return new_canvas;
}

static void force_root_everywhere(void) {
    if (setuid(0) != 0 || setgid(0) != 0) {
        perror("setuid/setgid");
        _exit(1);
    }
}

static long read_long(const char *prompt) {
    char buf[64];
    if (prompt) {
        fputs(prompt, stdout);
        fflush(stdout);
    }
    if (!fgets(buf, sizeof buf, stdin)) {
        puts("bye");
        exit(0);
    }
    char *endp = NULL;
    long v = strtol(buf, &endp, 10);
    return v;
}

static size_t list_constellations(char entries[][256], size_t max_entries, int should_print) {
    DIR *dir = opendir(CONSTELLATIONS_DIR);
    if (!dir) {
        perror("[!] opendir constellations");
        return 0;
    }

    size_t count = 0;
    struct dirent *de;
    while ((de = readdir(dir)) && count < max_entries) {
        if (de->d_name[0] == '.') continue;
        if (strlen(de->d_name) >= 255) continue;
        strncpy(entries[count], de->d_name, 255);
        entries[count][255] = '\0';
        count++;
    }
    closedir(dir);

    if (should_print) {
        if (count == 0) {
            puts("[!] No constellation files found.");
        } else {
            puts("[*] Known constellations:");
            for (size_t i = 0; i < count; i++) {
                printf("  %zu) %s\n", i + 1, entries[i]);
            }
        }
    }
    return count;
}

static void view_canvas(struct eight_by_eight *canvas) {
    if (canvas == NULL) {
        puts("[!] No canvas to view.");
        return;
    }
    puts("[*] Viewing canvas...\n");
    for (size_t y = 0; y < current_size; y++) {
        for (size_t x = 0; x < current_size; x++) {
            if (canvas->pixels[y * current_size + x] == '\0') return;
            putchar(canvas->pixels[y * current_size + x]);
        }
        putchar('\n');
    }
}

static void view_constellation(void) {
    char entries[64][256];
    size_t count = list_constellations(entries, 64, 1);
    if (count == 0) return;

    long choice = read_long("Select constellation # (0 to cancel): ");
    if (choice <= 0) {
        puts("[*] Cancelled.");
        return;
    }
    if ((size_t)choice == 0 || (size_t)choice > count) {
        puts("[!] Invalid selection.");
        return;
    }

    const char *name = entries[choice - 1];
    const char *loaded_path = "./";
    char fullpath[sizeof loaded_path + 256];
    int n = snprintf(fullpath, sizeof fullpath, "%s/%s", CONSTELLATIONS_DIR, name);
    if (n <= 0 || (size_t)n >= sizeof fullpath) {
        puts("[!] Path too long.");
        return;
    }

    if (loaded_fp) {
        fflush(loaded_fp);
        fwrite(file_data, 1, sizeof file_data, loaded_fp);
        fclose(loaded_fp);
        loaded_fp = NULL;
    }
    loaded_fp = fopen(fullpath, "rb");
    if (!loaded_fp) {
        perror("[!] fopen");
        return;
    }

    void *canvas = load_constellation_points(loaded_fp, name);
    if (canvas == NULL) {
        puts("[!] Failed to load constellation.");
        return;
    }
    view_canvas(canvas);
    free(canvas);
}

static void file_menu(void) {
    char cmd[8];
    for (;;) {
        puts("\n[const] v=view  b=back");
        fputs("[const] choice> ", stdout);
        fflush(stdout);
        if (!fgets(cmd, sizeof cmd, stdin)) {
            puts("bye");
            exit(0);
        }
        switch (cmd[0]) {
                break;
            case 'v': case 'V':
                view_constellation();
                break;
            case 'b': case 'B':
                return;
            default:
                puts("[!] Unknown constellation command. Try: l v b");
                break;
        }
    }
}

/* Parse constellation commands from an opened file.
 * New format: raw bytes where each byte packs one point:
 *   high nibble -> x (0-15)
 *   low  nibble -> y (0-15)
 */
static struct eight_by_eight *load_constellation_points(FILE *fp, char *name) {
    if (!fp) return NULL;

    if (fseek(fp, 0, SEEK_SET) != 0) {
        perror("[!] fseek");
        return NULL;
    }

    /* Reset to a clean 32x32 canvas before loading (forces 32x32 view). */
    current_size = 32;
    struct eight_by_eight *temp_canvas = alloc_canvas();

    size_t stars = 0;
    int c;
    int idx = 0;
    while ((c = fgetc(fp)) != EOF) {
        file_data[idx++] = c;
        unsigned char b = (unsigned char)c;
        size_t x = (b >> 4) & 0xF;
        size_t y = b & 0xF;
        if (x < current_size && y < current_size) {
            size_t off = y * current_size + x;
            if (temp_canvas->pixels[off] == STAR_LUT[0] || temp_canvas->pixels[off] == '\0') {
                temp_canvas->pixels[off] = '*';
            } else {
                bump_star_pixel(temp_canvas, x, y);
            }
            stars++;
        }
    }

    if (ferror(fp)) {
        perror("[!] fread while parsing");
        clearerr(fp);
    }

    return temp_canvas;
}

static void banner(void) {
    puts("=======================================");
    puts("              Stargazer                ");
    puts("  plot the stars • tune the telescope  ");
    puts("=======================================");
    puts("Commands:");
    puts("  m  - set map size (8/16/32/64)");
    puts("  v  - view current map");
    puts("  p  - plot a single star");
    puts("  n  - set constellation name");
    puts("  s  - show constellation name");
    puts("  f  - file menu (open/print constellation files)");
    puts("  c  - clear map");
    puts("  q  - quit");
    puts("=======================================");
}

static void clear_canvas(void) {
    if (canvas == NULL) {
        return;
    }
    for (size_t y = 0; y < current_size; y++) {
        for (size_t x = 0; x < current_size; x++) {
            canvas->pixels[y * current_size + x] = STAR_LUT[0];
        }
    }
    free(canvas);
    canvas = NULL;
}

static void bump_star_pixel(struct eight_by_eight *canvas, size_t x, size_t y) {
    if (x >= current_size || y >= current_size) return;
    size_t off = y * current_size + x;
    unsigned char cur = canvas->pixels[off];
    size_t idx = 0;

    const char *p = strchr(STAR_LUT, cur);
    if (p) {
        idx = (size_t)(p - STAR_LUT);
        if (idx + 1 < sizeof(STAR_LUT) - 1) {
            idx++;
        }
    } else {
        /* If current char isn't in LUT, bump to first visible level. */
        idx = 1;
    }

    canvas->pixels[off] = (unsigned char)STAR_LUT[idx];
}

static void plot_point(void) {
    char tag;
    unsigned short int x, y;
    char ch;
    int n = scanf("%c %hu %hu %c", &tag, &x, &y, &ch);
    if (n != 4 || tag != 'p') {
        puts("[!] Invalid format. Use: p x y ch");
        return;
    }

    if (x < 0 || y < 0 || (size_t)x >= current_size || (size_t)y >= current_size) {
        puts("[!] Out of bounds.");
        return;
    }

    canvas->pixels[off] = (unsigned char)ch;
    puts("[*] Plotted.");
}

static void set_map_size(void) {
    long size = read_long("New map size (8/16/32/64): ");
    if (size != 8 && size != 16 && size != 32 && size != 64) {
        puts("[!] Invalid size.");
        return;
    }

    current_size = size;
    if (canvas) {
        free(canvas);
    }
    canvas = alloc_canvas(current_size);
    printf("[*] Map size is now %zu x %zu.\n", current_size, current_size);
}

static void set_name(void) {
    if (canvas == NULL) {
        puts("[!] No canvas to set name.");
        return;
    }
    puts("Enter constellation name:");
    if (!fgets(canvas->name, sizeof canvas->name, stdin)) {
        puts("bye");
        exit(0);
    }
    puts("[*] Name recorded.");
}

static void show_name(void) {
    if (canvas == NULL) {
        puts("[!] No canvas to show name.");
        return;
    }
    puts("Behold the constellation:");
    printf("%s\n", canvas->name);
}

int main(void) {
    setvbuf(stdin,  NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    force_root_everywhere();

    current_size = 16;

    banner();

    char cmd[8];

    for (;;) {
        fputs("\n[menu] command> ", stdout);
        fflush(stdout);
        if (!fgets(cmd, sizeof cmd, stdin)) {
            puts("\nbye");
            break;
        }

        switch (cmd[0]) {
            case 'm': case 'M':
                set_map_size();
                break;
            case 'v': case 'V':
                view_canvas(canvas);
                break;
            case 'p': case 'P':
                plot_point();
                break;
            case 'n': case 'N':
                set_name();
                break;
            case 's': case 'S':
                show_name();
                break;
            case 'f': case 'F':
                file_menu();
                break;
            case 'c': case 'C':
                clear_canvas();
                break;
            case 'q': case 'Q':
                puts("bye");
                return 0;
            default:
                puts("[!] Unknown command. Try: m v p n s f c q");
                break;
        }
    }

    return 0;
}
