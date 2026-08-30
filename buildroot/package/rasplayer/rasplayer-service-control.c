#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef DNL_UID
#define DNL_UID 1000
#endif
#ifndef SERVICE_SCRIPT
#define SERVICE_SCRIPT "/etc/init.d/S50rasplayer"
#endif
#ifndef RUNTIME_DIR
#define RUNTIME_DIR "/run/rasplayer"
#endif
#ifndef GPIO_DEVICE
#define GPIO_DEVICE "/dev/gpiomem"
#endif
#define DEPLOY_INSTALLER "/usr/sbin/rasplayer-deploy"
#define CONTROL_LOCK RUNTIME_DIR "/service-control.lock"
#define CONTROL_LOCK_PID CONTROL_LOCK "/pid"
#define MANAGER_PID_FILE RUNTIME_DIR "/manager.pid"
#define CHILD_PID_FILE RUNTIME_DIR "/rasplayer.pid"

#define TRIGGER_PIN 14U
#define ECHO_PIN 15U
#define GPIO_MAP_SIZE 4096U
#define GPFSEL1_INDEX (0x04U / sizeof(uint32_t))
#define GPSET0_INDEX (0x1cU / sizeof(uint32_t))
#define GPCLR0_INDEX (0x28U / sizeof(uint32_t))
#define GPLEV0_INDEX (0x34U / sizeof(uint32_t))
#define TRIGGER_FSEL_SHIFT ((TRIGGER_PIN % 10U) * 3U)
#define ECHO_FSEL_SHIFT ((ECHO_PIN % 10U) * 3U)
#define TRIGGER_FSEL_MASK (7U << TRIGGER_FSEL_SHIFT)
#define ECHO_FSEL_MASK (7U << ECHO_FSEL_SHIFT)
#define TEST_FSEL_MASK (TRIGGER_FSEL_MASK | ECHO_FSEL_MASK)
#define GPIO_OUTPUT (1U << TRIGGER_FSEL_SHIFT)
#define ECHO_TIMEOUT_US 30000U
#define MEASUREMENT_PAUSE_US 60000U

static volatile uint32_t *gpio_regs;
static uint32_t original_fsel_bits;
static int gpio_configured;
static int control_lock_held;
static volatile sig_atomic_t interrupted;

static int process_alive(pid_t pid)
{
    char path[64];
    char buffer[256];
    FILE *status;

    if (pid <= 1 || kill(pid, 0) != 0) {
        return 0;
    }
    snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid);
    status = fopen(path, "r");
    if (status == NULL) {
        return 0;
    }
    while (fgets(buffer, sizeof(buffer), status) != NULL) {
        if (strncmp(buffer, "State:", 6) == 0 && strchr(buffer, 'Z') != NULL) {
            fclose(status);
            return 0;
        }
    }
    fclose(status);
    return 1;
}

static int read_pid_file(const char *path, pid_t *pid)
{
    long value;
    char trailing;
    FILE *file = fopen(path, "r");

    if (file == NULL) {
        return 0;
    }
    if (fscanf(file, "%ld%c", &value, &trailing) < 1 || value <= 1) {
        fclose(file);
        return 0;
    }
    fclose(file);
    *pid = (pid_t)value;
    return 1;
}

static int process_cmdline_contains(pid_t pid, const char *marker)
{
    char path[64];
    char buffer[512];
    ssize_t length;
    int fd;
    ssize_t index;

    if (!process_alive(pid)) {
        return 0;
    }
    snprintf(path, sizeof(path), "/proc/%ld/cmdline", (long)pid);
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        return 0;
    }
    length = read(fd, buffer, sizeof(buffer) - 1U);
    close(fd);
    if (length <= 0) {
        return 0;
    }
    for (index = 0; index < length; ++index) {
        if (buffer[index] == '\0') {
            buffer[index] = ' ';
        }
    }
    buffer[length] = '\0';
    return strstr(buffer, marker) != NULL;
}

static int pid_file_matches(const char *path, const char *marker, pid_t *pid)
{
    return read_pid_file(path, pid) && process_cmdline_contains(*pid, marker);
}

static void sleep_microseconds(unsigned int microseconds)
{
    struct timespec delay;

    delay.tv_sec = microseconds / 1000000U;
    delay.tv_nsec = (long)(microseconds % 1000000U) * 1000L;
    while (!interrupted && nanosleep(&delay, &delay) != 0 && errno == EINTR) {
    }
}

static uint64_t monotonic_nanoseconds(void)
{
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return 0;
    }
    return (uint64_t)now.tv_sec * 1000000000ULL + (uint64_t)now.tv_nsec;
}

static int gpio_level(unsigned int pin)
{
    return (gpio_regs[GPLEV0_INDEX] & (1U << pin)) != 0U;
}

static void gpio_write(unsigned int pin, int high)
{
    gpio_regs[high ? GPSET0_INDEX : GPCLR0_INDEX] = 1U << pin;
    __sync_synchronize();
}

static int wait_for_gpio_level(int expected, unsigned int timeout_us,
                               uint64_t *observed_at)
{
    uint64_t deadline = monotonic_nanoseconds() +
                        (uint64_t)timeout_us * 1000ULL;
    uint64_t now;

    while (!interrupted) {
        if (gpio_level(ECHO_PIN) == expected) {
            *observed_at = monotonic_nanoseconds();
            return 1;
        }
        now = monotonic_nanoseconds();
        if (now == 0 || now >= deadline) {
            return 0;
        }
    }
    return 0;
}

static void release_control_lock(void)
{
    if (control_lock_held) {
        unlink(CONTROL_LOCK_PID);
        rmdir(CONTROL_LOCK);
        control_lock_held = 0;
    }
}

static void cleanup(void)
{
    if (gpio_regs != NULL && gpio_regs != MAP_FAILED) {
        if (gpio_configured) {
            uint32_t current;

            gpio_write(TRIGGER_PIN, 0);
            current = gpio_regs[GPFSEL1_INDEX];
            current &= ~TEST_FSEL_MASK;
            current |= original_fsel_bits;
            gpio_regs[GPFSEL1_INDEX] = current;
            __sync_synchronize();
            gpio_configured = 0;
        }
        munmap((void *)gpio_regs, GPIO_MAP_SIZE);
        gpio_regs = NULL;
    }
    release_control_lock();
}

static void handle_signal(int signal_number)
{
    (void)signal_number;
    interrupted = 1;
}

static int acquire_control_lock(void)
{
    unsigned int attempts = 0;

    if (mkdir(RUNTIME_DIR, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "rasplayer-service: cannot create runtime directory: %s\n",
                strerror(errno));
        return 0;
    }
    while (mkdir(CONTROL_LOCK, 0700) != 0) {
        pid_t owner;

        if (errno != EEXIST) {
            fprintf(stderr, "rasplayer-service: cannot create control lock: %s\n",
                    strerror(errno));
            return 0;
        }
        if (!read_pid_file(CONTROL_LOCK_PID, &owner) || !process_alive(owner)) {
            unlink(CONTROL_LOCK_PID);
            if (rmdir(CONTROL_LOCK) == 0 || errno == ENOENT) {
                continue;
            }
        }
        if (++attempts >= 100U) {
            fputs("rasplayer-service: service control is busy\n", stderr);
            return 0;
        }
        sleep_microseconds(100000U);
    }
    control_lock_held = 1;
    {
        int fd = open(CONTROL_LOCK_PID,
                      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                      0600);
        char pid_text[32];
        int length;

        if (fd < 0) {
            fprintf(stderr, "rasplayer-service: cannot record control lock: %s\n",
                    strerror(errno));
            release_control_lock();
            return 0;
        }
        length = snprintf(pid_text, sizeof(pid_text), "%ld\n", (long)getpid());
        if (write(fd, pid_text, (size_t)length) != length) {
            fprintf(stderr, "rasplayer-service: cannot write control lock: %s\n",
                    strerror(errno));
            close(fd);
            release_control_lock();
            return 0;
        }
        close(fd);
    }
    return 1;
}

static int ultrasonic_test(void)
{
    pid_t manager = 0;
    pid_t child = 0;
    int manager_running;
    int child_running;
    int gpio_fd;
    uint32_t current;
    unsigned int measurement;

    if (!acquire_control_lock()) {
        return 75;
    }
    manager_running = pid_file_matches(MANAGER_PID_FILE, "S50rasplayer", &manager);
    child_running = pid_file_matches(CHILD_PID_FILE, "RasPlayer.py", &child);
    if (manager_running || child_running) {
        fprintf(stderr,
                "rasplayer-service: ultrasonic-test refused; RasPlayer is running"
                " (manager_pid=%ld child_pid=%ld)\n",
                manager_running ? (long)manager : 0L,
                child_running ? (long)child : 0L);
        return 1;
    }

    gpio_fd = open(GPIO_DEVICE, O_RDWR | O_SYNC | O_CLOEXEC);
    if (gpio_fd < 0) {
        fprintf(stderr, "ultrasonic-test: cannot open %s: %s\n",
                GPIO_DEVICE, strerror(errno));
        return 1;
    }
    gpio_regs = mmap(NULL, GPIO_MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
                     gpio_fd, 0);
    close(gpio_fd);
    if (gpio_regs == MAP_FAILED) {
        gpio_regs = NULL;
        fprintf(stderr, "ultrasonic-test: cannot map %s: %s\n",
                GPIO_DEVICE, strerror(errno));
        return 1;
    }

    current = gpio_regs[GPFSEL1_INDEX];
    original_fsel_bits = current & TEST_FSEL_MASK;
    current &= ~TEST_FSEL_MASK;
    current |= GPIO_OUTPUT;
    gpio_regs[GPFSEL1_INDEX] = current;
    __sync_synchronize();
    gpio_configured = 1;
    gpio_write(TRIGGER_PIN, 0);
    sleep_microseconds(2000U);

    printf("ultrasonic-test BCM trigger=%u echo=%u measurements=10 timeout_us=%u\n",
           TRIGGER_PIN, ECHO_PIN, ECHO_TIMEOUT_US);
    printf("initial_echo_state=%d\n", gpio_level(ECHO_PIN));
    fflush(stdout);

    for (measurement = 1; measurement <= 10U && !interrupted; ++measurement) {
        uint64_t pulse_start = 0;
        uint64_t pulse_end = 0;
        double duration_us;
        double distance_cm;

        gpio_write(TRIGGER_PIN, 0);
        sleep_microseconds(2U);
        gpio_write(TRIGGER_PIN, 1);
        sleep_microseconds(10U);
        gpio_write(TRIGGER_PIN, 0);

        if (!wait_for_gpio_level(1, ECHO_TIMEOUT_US, &pulse_start)) {
            printf("measurement=%u timeout waiting for ECHO HIGH\n", measurement);
        } else if (!wait_for_gpio_level(0, ECHO_TIMEOUT_US, &pulse_end)) {
            printf("measurement=%u timeout waiting for ECHO LOW\n", measurement);
        } else {
            duration_us = (double)(pulse_end - pulse_start) / 1000.0;
            distance_cm = duration_us * 0.0343 / 2.0;
            printf("measurement=%u pulse_duration_us=%.1f distance_cm=%.2f\n",
                   measurement, duration_us, distance_cm);
        }
        fflush(stdout);
        sleep_microseconds(MEASUREMENT_PAUSE_US);
    }

    if (interrupted) {
        fputs("ultrasonic-test interrupted; GPIO state restored\n", stderr);
        return 130;
    }
    return 0;
}

static int allowed_action(const char *action)
{
    return strcmp(action, "start") == 0 ||
           strcmp(action, "stop") == 0 ||
           strcmp(action, "restart") == 0 ||
           strcmp(action, "status") == 0 ||
           strcmp(action, "ultrasonic-test") == 0 ||
           strcmp(action, "deploy") == 0 ||
           strcmp(action, "rollback") == 0;
}

int main(int argc, char **argv)
{
    struct stat script_stat;
    struct sigaction action;
    char *service_argv[] = {
        (char *)SERVICE_SCRIPT,
        NULL,
        NULL
    };
    char *deploy_argv[] = {
        (char *)DEPLOY_INSTALLER,
        NULL,
        NULL
    };
    char *const service_env[] = {
        (char *)"PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        (char *)"HOME=/root",
        (char *)"USER=root",
        (char *)"LOGNAME=root",
        NULL
    };

    if (getuid() != DNL_UID) {
        fprintf(stderr, "rasplayer-service: only dnl (uid %d) may use this helper\n",
                DNL_UID);
        return 126;
    }
    if (geteuid() != 0) {
        fputs("rasplayer-service: helper is not installed setuid root\n", stderr);
        return 126;
    }
    if (argc != 2 || !allowed_action(argv[1])) {
        fputs("Usage: rasplayer-service {start|stop|restart|status|ultrasonic-test|deploy|rollback}\n",
              stderr);
        return 2;
    }
    if (lstat(SERVICE_SCRIPT, &script_stat) != 0 ||
        !S_ISREG(script_stat.st_mode) || script_stat.st_uid != 0 ||
        (script_stat.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        fputs("rasplayer-service: unsafe service script ownership or mode\n", stderr);
        return 126;
    }
    if (setgroups(0, NULL) != 0 || setgid(0) != 0 || setuid(0) != 0) {
        fprintf(stderr, "rasplayer-service: cannot assume service identity: %s\n",
                strerror(errno));
        return 126;
    }

    if (strcmp(argv[1], "ultrasonic-test") == 0) {
        memset(&action, 0, sizeof(action));
        action.sa_handler = handle_signal;
        sigemptyset(&action.sa_mask);
        sigaction(SIGINT, &action, NULL);
        sigaction(SIGTERM, &action, NULL);
        if (atexit(cleanup) != 0) {
            fputs("rasplayer-service: cannot register GPIO cleanup\n", stderr);
            return 126;
        }
        return ultrasonic_test();
    }

    if (strcmp(argv[1], "deploy") == 0 || strcmp(argv[1], "rollback") == 0) {
        if (lstat(DEPLOY_INSTALLER, &script_stat) != 0 ||
            !S_ISREG(script_stat.st_mode) || script_stat.st_uid != 0 ||
            (script_stat.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
            fputs("rasplayer-service: unsafe deployment installer ownership or mode\n",
                  stderr);
            return 126;
        }
        deploy_argv[1] = argv[1];
        execve(DEPLOY_INSTALLER, deploy_argv, service_env);
        fprintf(stderr, "rasplayer-service: cannot execute deployment installer: %s\n",
                strerror(errno));
        return 126;
    }

    service_argv[1] = argv[1];
    execve(SERVICE_SCRIPT, service_argv, service_env);
    fprintf(stderr, "rasplayer-service: cannot execute service script: %s\n",
            strerror(errno));
    return 126;
}
